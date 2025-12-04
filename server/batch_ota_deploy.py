#!/usr/bin/env python3
"""
Batch OTA Deployment Script
Deploys APK v1.0.234 to devices in batches of 7
"""

import os
import sys
import time
import json
import uuid
import hmac
import hashlib
import httpx
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Device, ApkVersion, ApkInstallation
from fcm_v1 import get_access_token, get_firebase_project_id, build_fcm_v1_url
from config import config

# Configuration
APK_ID = 133  # v1.0.234
BATCH_SIZE = 7
BATCH_DELAY_SECONDS = 5  # Wait between batches
EXCLUDE_ALIASES = ['S7']  # S7 already has v1.0.234

def get_db_session():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not set")
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    return Session()

def compute_hmac_signature(request_id: str, device_id: str, action: str, timestamp: str) -> str:
    """Compute HMAC signature for FCM command"""
    hmac_secret = os.environ.get('HMAC_SECRET', '')
    message = f"{request_id}:{device_id}:{action}:{timestamp}"
    signature = hmac.new(
        hmac_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

def get_devices_needing_update(db):
    """Get all devices that need the update (excluding S7)"""
    devices = db.query(Device).filter(
        Device.alias.notin_(EXCLUDE_ALIASES),
        Device.alias.isnot(None),
        Device.fcm_token.isnot(None)  # Only devices with FCM tokens
    ).order_by(Device.alias).all()
    return devices

def create_batches(devices, batch_size):
    """Split devices into batches"""
    return [devices[i:i + batch_size] for i in range(0, len(devices), batch_size)]

def send_fcm_message(client, fcm_url, access_token, device, apk, installation):
    """Send FCM message to a single device"""
    request_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    hmac_signature = compute_hmac_signature(request_id, device.id, "install_apk", timestamp)
    
    # Generate the download URL for the APK
    download_url = f"{config.server_url}/v1/apk/download/{apk.id}"
    
    fcm_message = {
        "message": {
            "token": device.fcm_token,
            "data": {
                "action": "install_apk",
                "request_id": request_id,
                "device_id": device.id,
                "ts": timestamp,
                "hmac": hmac_signature,
                "installation_id": str(installation.id),
                "apk_id": str(apk.id),
                "version_name": apk.version_name,
                "version_code": str(apk.version_code),
                "file_size": str(apk.file_size) if apk.file_size else "0",
                "package_name": apk.package_name if apk.package_name else "com.nexmdm",
                "download_url": download_url
            },
            "android": {
                "priority": "high"
            }
        }
    }
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    response = client.post(fcm_url, json=fcm_message, headers=headers, timeout=10.0)
    return response

def deploy_batch(db, apk, devices, batch_num, client, access_token, fcm_url):
    """Deploy OTA update to a batch of devices"""
    print(f"\n{'='*60}")
    print(f"BATCH {batch_num}: Deploying to {len(devices)} devices")
    print(f"{'='*60}")
    
    results = {
        'success': [],
        'failed': []
    }
    
    now = datetime.now(timezone.utc)
    
    for device in devices:
        try:
            # Create installation record
            installation = ApkInstallation(
                device_id=device.id,
                apk_version_id=apk.id,
                status="pending",
                initiated_at=now,
                initiated_by="batch_deploy"
            )
            db.add(installation)
            db.commit()
            db.refresh(installation)
            
            # Send FCM message
            response = send_fcm_message(client, fcm_url, access_token, device, apk, installation)
            
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get("name"):
                    results['success'].append(device.alias)
                    print(f"  ✓ {device.alias}: FCM sent successfully")
                else:
                    results['failed'].append({
                        'alias': device.alias,
                        'reason': str(response_data)
                    })
                    print(f"  ✗ {device.alias}: FCM failed - {response_data}")
            else:
                error_text = response.text[:200] if response.text else "Unknown error"
                results['failed'].append({
                    'alias': device.alias,
                    'reason': f"HTTP {response.status_code}: {error_text}"
                })
                print(f"  ✗ {device.alias}: HTTP {response.status_code} - {error_text}")
                
        except Exception as e:
            results['failed'].append({
                'alias': device.alias,
                'reason': str(e)
            })
            print(f"  ✗ {device.alias}: Error - {str(e)}")
    
    print(f"\nBatch {batch_num} Results: {len(results['success'])} success, {len(results['failed'])} failed")
    return results

def main():
    print("\n" + "="*60)
    print("BATCH OTA DEPLOYMENT - v1.0.234")
    print("="*60)
    
    # Get database session
    db = get_db_session()
    
    try:
        # Verify APK exists
        apk = db.query(ApkVersion).filter(ApkVersion.id == APK_ID).first()
        if not apk:
            print(f"ERROR: APK ID {APK_ID} not found!")
            return
        
        print(f"\nAPK Details:")
        print(f"  Version: {apk.version_name}")
        print(f"  Version Code: {apk.version_code}")
        print(f"  File Size: {apk.file_size:,} bytes")
        print(f"  Server URL: {config.server_url}")
        
        # Get devices needing update
        devices = get_devices_needing_update(db)
        print(f"\nDevices needing update: {len(devices)}")
        print(f"Batch size: {BATCH_SIZE}")
        
        # Create batches
        batches = create_batches(devices, BATCH_SIZE)
        print(f"Total batches: {len(batches)}")
        
        # Get FCM credentials once
        print("\nInitializing FCM...")
        access_token = get_access_token()
        project_id = get_firebase_project_id()
        fcm_url = build_fcm_v1_url(project_id)
        print("FCM initialized successfully")
        
        # Deploy each batch
        all_results = {
            'success': [],
            'failed': []
        }
        
        with httpx.Client() as client:
            for i, batch in enumerate(batches, 1):
                results = deploy_batch(db, apk, batch, i, client, access_token, fcm_url)
                all_results['success'].extend(results['success'])
                all_results['failed'].extend(results['failed'])
                
                # Wait between batches (except for the last one)
                if i < len(batches):
                    print(f"\nWaiting {BATCH_DELAY_SECONDS}s before next batch...")
                    time.sleep(BATCH_DELAY_SECONDS)
        
        # Final summary
        print("\n" + "="*60)
        print("DEPLOYMENT COMPLETE")
        print("="*60)
        print(f"Total Success: {len(all_results['success'])}")
        print(f"Total Failed: {len(all_results['failed'])}")
        
        if all_results['failed']:
            print("\nFailed devices:")
            for f in all_results['failed']:
                print(f"  - {f['alias']}: {f['reason']}")
        
        print("\nSuccessful devices:")
        for alias in sorted(all_results['success']):
            print(f"  ✓ {alias}")
            
    finally:
        db.close()

if __name__ == "__main__":
    main()
