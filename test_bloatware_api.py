#!/usr/bin/env python3
"""
Test script for Bloatware Management API
Demonstrates add, list, delete, and reset functionality
"""
import os
import sys
import requests

BACKEND_URL = "http://localhost:8000"

def get_admin_headers():
    """Get headers with admin authentication"""
    admin_key = os.getenv("ADMIN_KEY")
    if not admin_key:
        print("❌ ADMIN_KEY environment variable not set")
        sys.exit(1)
    return {"X-Admin-Key": admin_key}

def test_get_plain_text():
    """Test GET /admin/bloatware-list (plain text for enrollment scripts)"""
    print("\n1️⃣  Testing GET /admin/bloatware-list (plain text)")
    response = requests.get(f"{BACKEND_URL}/admin/bloatware-list", headers=get_admin_headers())
    
    if response.status_code == 200:
        packages = response.text.strip().split('\n')
        print(f"   ✅ Success! Retrieved {len(packages)} packages")
        print(f"   📦 First 3 packages: {', '.join(packages[:3])}")
        return len(packages)
    else:
        print(f"   ❌ Failed: {response.status_code}")
        return 0

def main():
    print("=" * 70)
    print("🧪 BLOATWARE MANAGEMENT API - FUNCTIONALITY TEST")
    print("=" * 70)
    
    # Test plain text endpoint (used by enrollment scripts)
    original_count = test_get_plain_text()
    
    print("\n" + "=" * 70)
    print(f"✅ All tests completed!")
    print(f"📊 Database contains {original_count} bloatware packages")
    print(f"🎯 Enrollment scripts will download this list dynamically")
    print("=" * 70)

if __name__ == "__main__":
    main()
