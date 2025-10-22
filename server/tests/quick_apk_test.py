#!/usr/bin/env python3
"""
Quick APK Management Test - Streamlined version for fast execution
Tests the critical path: register → upload → download
"""

import requests
import hashlib
import io
import os
import sys

BASE_URL = "http://localhost:8000"
ADMIN_KEY = os.getenv("ADMIN_KEY", "")

def main():
    print("🚀 Quick APK Management Test\n")
    
    # Test 1: Register Build
    print("1️⃣ Testing APK registration...")
    payload = {
        "build_id": "test_build_001",
        "version_code": 999,
        "version_name": "9.9.9-test",
        "build_type": "debug",
        "sha256": "a" * 64,
        "file_size_bytes": 100,
        "signer_fingerprint": "TEST:FP",
        "ci_run_id": "test_run",
        "git_sha": "test_sha",
        "package_name": "com.nexmdm.agent"
    }
    
    resp = requests.post(
        f"{BASE_URL}/admin/apk/register",
        headers={"X-Admin": ADMIN_KEY},
        json=payload
    )
    
    if resp.status_code == 200:
        print(f"   ✅ Register OK: {resp.json()}")
    else:
        print(f"   ❌ Register FAIL: {resp.status_code} - {resp.text[:200]}")
        sys.exit(1)
    
    # Test 2: Upload File
    print("\n2️⃣ Testing APK file upload...")
    apk_content = b"MOCK APK CONTENT FOR TESTING"
    
    files = {
        'file': ('test-app.apk', io.BytesIO(apk_content), 'application/vnd.android.package-archive')
    }
    data = {
        'build_id': 'test_build_001',
        'version_code': '999',
        'version_name': '9.9.9-test',
        'build_type': 'debug',
        'package_name': 'com.nexmdm.agent'
    }
    
    resp = requests.post(
        f"{BASE_URL}/admin/apk/upload",
        headers={"X-Admin": ADMIN_KEY},
        files=files,
        data=data
    )
    
    if resp.status_code == 200:
        result = resp.json()
        print(f"   ✅ Upload OK: file_path={result.get('file_path', 'N/A')}")
        print(f"      File size: {result.get('file_size', 0)} bytes")
    else:
        print(f"   ❌ Upload FAIL: {resp.status_code} - {resp.text[:200]}")
        sys.exit(1)
    
    # Test 3: List Builds
    print("\n3️⃣ Testing build listing...")
    resp = requests.get(
        f"{BASE_URL}/admin/apk/builds",
        headers={"X-Admin": ADMIN_KEY},
        params={"build_type": "debug"}
    )
    
    if resp.status_code == 200:
        builds = resp.json().get("builds", [])
        print(f"   ✅ List OK: Found {len(builds)} builds")
        if builds:
            print(f"      Latest: v{builds[0]['version_code']} - {builds[0]['version_name']}")
    else:
        print(f"   ❌ List FAIL: {resp.status_code}")
        sys.exit(1)
    
    # Test 4: Download (Admin)
    print("\n4️⃣ Testing admin download...")
    resp = requests.get(
        f"{BASE_URL}/admin/apk/download/test_build_001",
        headers={"X-Admin": ADMIN_KEY}
    )
    
    if resp.status_code == 200:
        downloaded = resp.content
        print(f"   ✅ Download OK: {len(downloaded)} bytes")
        if downloaded == apk_content:
            print(f"      ✅ Content matches!")
        else:
            print(f"      ⚠️  Content mismatch (expected {len(apk_content)}, got {len(downloaded)})")
    else:
        print(f"   ❌ Download FAIL: {resp.status_code}")
    
    # Test 5: Auth Check
    print("\n5️⃣ Testing authorization...")
    resp = requests.get(f"{BASE_URL}/admin/apk/builds")
    if resp.status_code == 401 or resp.status_code == 403:
        print(f"   ✅ Auth required (got {resp.status_code})")
    else:
        print(f"   ⚠️  Unexpected status: {resp.status_code}")
    
    print("\n✅ Quick test complete!\n")

if __name__ == "__main__":
    main()
