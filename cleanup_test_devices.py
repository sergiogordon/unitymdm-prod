#!/usr/bin/env python3
"""
Cleanup script to remove all test devices from the MDM system.
Uses the existing bulk delete API to ensure proper cleanup.
"""

import os
import sys
import requests
from typing import List, Dict

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


def get_auth_token() -> str:
    """Authenticate and get JWT token."""
    print("🔐 Authenticating...")
    response = requests.post(
        f"{BACKEND_URL}/api/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
    )
    
    if response.status_code != 200:
        print(f"❌ Authentication failed: {response.status_code}")
        print(response.text)
        sys.exit(1)
    
    token = response.json().get("access_token")
    if not token:
        print("❌ No access token received")
        sys.exit(1)
    
    print("✅ Authentication successful")
    return token


def fetch_all_devices(token: str) -> List[Dict]:
    """Fetch all devices from the API with pagination."""
    print("\n📱 Fetching all devices...")
    
    headers = {"Authorization": f"Bearer {token}"}
    all_devices = []
    page = 1
    
    while True:
        response = requests.get(
            f"{BACKEND_URL}/v1/devices",
            params={"page": page, "limit": 100},
            headers=headers
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch devices: {response.status_code}")
            print(response.text)
            sys.exit(1)
        
        data = response.json()
        devices = data.get("devices", [])
        pagination = data.get("pagination", {})
        
        all_devices.extend(devices)
        
        print(f"  Page {page}: Fetched {len(devices)} devices")
        
        # Check if there are more pages
        if not pagination.get("has_next", False):
            break
        
        page += 1
    
    print(f"\n✅ Total devices found: {len(all_devices)}")
    return all_devices


def confirm_deletion(devices: List[Dict]) -> bool:
    """Show devices and ask for confirmation."""
    print("\n" + "="*60)
    print("⚠️  DELETION CONFIRMATION")
    print("="*60)
    print(f"\nTotal devices to delete: {len(devices)}")
    
    if len(devices) == 0:
        print("No devices to delete!")
        return False
    
    # Show sample devices
    print("\nSample devices (first 10):")
    for i, device in enumerate(devices[:10], 1):
        alias = device.get("alias", "N/A")
        device_id = device.get("id", "N/A")
        status = device.get("status", "N/A")
        print(f"  {i}. {alias} (ID: {device_id[:8]}..., Status: {status})")
    
    if len(devices) > 10:
        print(f"  ... and {len(devices) - 10} more devices")
    
    print("\n" + "="*60)
    print("⚠️  This action will:")
    print("  - Revoke all device tokens")
    print("  - Delete all device records")
    print("  - Queue async data purging")
    print("  - Cannot be undone!")
    print("="*60)
    
    response = input("\nType 'DELETE ALL' to confirm deletion: ")
    return response.strip() == "DELETE ALL"


def bulk_delete_devices(token: str, device_ids: List[str]) -> Dict:
    """Call the bulk delete API endpoint."""
    print("\n🗑️  Deleting devices...")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(
        f"{BACKEND_URL}/v1/devices/bulk-delete",
        json={"device_ids": device_ids},
        headers=headers
    )
    
    if response.status_code != 200:
        print(f"❌ Bulk delete failed: {response.status_code}")
        print(response.text)
        sys.exit(1)
    
    return response.json()


def main():
    """Main cleanup workflow."""
    print("🧹 MDM Device Cleanup Script")
    print("="*60)
    
    # Step 1: Authenticate
    token = get_auth_token()
    
    # Step 2: Fetch all devices
    devices = fetch_all_devices(token)
    
    if not devices:
        print("\n✨ No devices found - database is already clean!")
        return
    
    # Step 3: Confirm deletion
    if not confirm_deletion(devices):
        print("\n❌ Deletion cancelled by user")
        return
    
    # Step 4: Perform bulk delete
    device_ids = [device["id"] for device in devices]
    result = bulk_delete_devices(token, device_ids)
    
    # Step 5: Report results
    print("\n" + "="*60)
    print("✅ CLEANUP COMPLETE")
    print("="*60)
    print(f"Deleted: {result.get('deleted_count', 0)} devices")
    print(f"Message: {result.get('message', 'Success')}")
    print("\n✨ Database is now clean!")
    print("="*60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Cleanup cancelled by user (Ctrl+C)")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
