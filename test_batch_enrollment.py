#!/usr/bin/env python3
"""
Bug bash script to test batch enrollment by creating 15 test devices
"""
import os
import requests
import uuid
import hashlib
import json

BACKEND_URL = "http://localhost:8000"
ADMIN_KEY = os.environ.get("ADMIN_KEY")

def generate_device_token(device_id: str) -> str:
    """Generate a bcrypt-compatible token hash for testing"""
    # For testing, we'll use a simple hash since we don't need actual bcrypt
    return hashlib.sha256(f"test_token_{device_id}".encode()).hexdigest()

def register_device(alias: str):
    """Register a single test device"""
    device_id = str(uuid.uuid4())
    fcm_token = f"test_fcm_{alias}_{uuid.uuid4().hex[:16]}"
    
    payload = {
        "device_id": device_id,
        "alias": alias,
        "fcm_token": fcm_token,
        "android_version": "13",
        "model": f"Test_Device_{alias}"
    }
    
    headers = {
        "X-Admin-Key": ADMIN_KEY,
        "Content-Type": "application/json"
    }
    
    print(f"Registering {alias}...", end=" ")
    response = requests.post(
        f"{BACKEND_URL}/v1/register",
        json=payload,
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Success - Token: {data.get('device_token', 'N/A')[:20]}...")
        return {
            "alias": alias,
            "device_id": data.get('device_id', device_id),
            "token": data.get('device_token', ''),
            "success": True
        }
    else:
        print(f"✗ Failed - {response.status_code}: {response.text}")
        return {
            "alias": alias,
            "device_id": device_id,
            "success": False,
            "error": response.text
        }

def main():
    print("=" * 80)
    print("Bug Bash: Batch Enrollment Test")
    print("Creating 15 test devices (D02-D16)")
    print("=" * 80)
    print()
    
    if not ADMIN_KEY:
        print("ERROR: ADMIN_KEY environment variable not set")
        return
    
    results = []
    
    # Create devices D02 through D16
    for i in range(2, 17):
        alias = f"D{i:02d}"  # Format as D02, D03, ... D16
        result = register_device(alias)
        results.append(result)
    
    print()
    print("=" * 80)
    print("Registration Summary")
    print("=" * 80)
    
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    
    print(f"Total: {len(results)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    
    if failed:
        print("\nFailed devices:")
        for r in failed:
            print(f"  - {r['alias']}: {r.get('error', 'Unknown error')}")
    
    # Save device IDs for cleanup
    with open('test_devices.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\nDevice IDs saved to test_devices.json for cleanup")

if __name__ == "__main__":
    main()
