#!/usr/bin/env python3
"""
APK Migration Script: Export APK records and files from dev to production.

This script:
1. Reads APK records from the local development database
2. Downloads APK files from local object storage
3. Uploads APK files and records to the production environment via API

Usage:
    python server/scripts/migrate_apks_to_prod.py --prod-url https://unitymdm.replit.app --prod-admin-key YOUR_KEY

Environment Variables:
    DATABASE_URL - Development database connection string
    PROD_URL - Production backend URL (or use --prod-url)
    PROD_ADMIN_KEY - Production admin key (or use --prod-admin-key)
"""

import os
import sys
import argparse
import requests
from datetime import datetime
from typing import Optional, List, Dict, Any

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(server_dir)
sys.path.insert(0, server_dir)
sys.path.insert(0, project_root)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def get_db_session():
    """Create database session for dev database."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    return Session()


def get_apk_records(session, limit: Optional[int] = None, active_only: bool = True) -> List[Dict[str, Any]]:
    """Fetch APK records from development database."""
    from models import ApkVersion
    
    query = session.query(ApkVersion)
    if active_only:
        query = query.filter(ApkVersion.is_active == True)
    
    query = query.order_by(ApkVersion.uploaded_at.desc())
    
    if limit:
        query = query.limit(limit)
    
    apks = query.all()
    
    records = []
    for apk in apks:
        records.append({
            "id": apk.id,
            "version_name": apk.version_name,
            "version_code": apk.version_code,
            "package_name": apk.package_name,
            "file_path": apk.file_path,
            "storage_url": apk.storage_url,
            "file_size": apk.file_size,
            "sha256": apk.sha256,
            "build_type": apk.build_type,
            "is_active": apk.is_active,
            "uploaded_at": apk.uploaded_at.isoformat() if apk.uploaded_at else None,
        })
    
    return records


def download_apk_from_storage(file_path: str) -> Optional[bytes]:
    """Download APK file from local object storage."""
    try:
        from object_storage import get_storage_service
        storage = get_storage_service()
        file_data, _, _ = storage.download_file(file_path, use_cache=False)
        return file_data
    except Exception as e:
        print(f"  Error downloading from storage: {e}")
        return None


def upload_to_production(
    prod_url: str,
    prod_admin_key: str,
    file_data: bytes,
    apk_record: Dict[str, Any]
) -> bool:
    """Upload APK to production via API."""
    upload_url = f"{prod_url.rstrip('/')}/api/apk/upload"
    
    files = {
        "file": (f"{apk_record['package_name']}-{apk_record['version_name']}.apk", file_data, "application/vnd.android.package-archive")
    }
    
    data = {
        "build_id": f"migration_{apk_record['id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "version_code": str(apk_record["version_code"]),
        "version_name": apk_record["version_name"],
        "build_type": apk_record.get("build_type", "release"),
        "package_name": apk_record.get("package_name", "com.nexmdm"),
    }
    
    headers = {
        "X-Admin": prod_admin_key,
    }
    
    try:
        response = requests.post(
            upload_url,
            files=files,
            data=data,
            headers=headers,
            timeout=300
        )
        
        if response.status_code in [200, 201]:
            return True
        else:
            print(f"  Upload failed: HTTP {response.status_code}")
            print(f"  Response: {response.text[:500]}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"  Request error: {e}")
        return False


def check_production_connectivity(prod_url: str, prod_admin_key: str) -> bool:
    """Check if production environment is accessible."""
    try:
        health_url = f"{prod_url.rstrip('/')}/api/proxy/healthz"
        response = requests.get(health_url, timeout=10)
        print(f"Production health check: HTTP {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        print(f"Production connectivity check failed: {e}")
        return False


def migrate_apks(
    prod_url: str,
    prod_admin_key: str,
    limit: Optional[int] = None,
    active_only: bool = True,
    dry_run: bool = False
) -> Dict[str, int]:
    """
    Migrate APK records and files from dev to production.
    
    Returns:
        Dictionary with migration statistics
    """
    stats = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
    }
    
    print("=" * 60)
    print("APK Migration: Development -> Production")
    print("=" * 60)
    print(f"Production URL: {prod_url}")
    print(f"Active only: {active_only}")
    print(f"Limit: {limit or 'All'}")
    print(f"Dry run: {dry_run}")
    print("=" * 60)
    
    if not dry_run:
        print("\nChecking production connectivity...")
        if not check_production_connectivity(prod_url, prod_admin_key):
            print("WARNING: Production health check failed, but will attempt migration anyway")
    
    print("\nFetching APK records from development database...")
    session = get_db_session()
    
    try:
        apk_records = get_apk_records(session, limit=limit, active_only=active_only)
        stats["total"] = len(apk_records)
        
        print(f"Found {len(apk_records)} APK records to migrate")
        
        if not apk_records:
            print("No APK records found. Nothing to migrate.")
            return stats
        
        print("\n" + "-" * 60)
        
        for i, apk in enumerate(apk_records, 1):
            print(f"\n[{i}/{len(apk_records)}] Processing APK ID {apk['id']}")
            print(f"  Version: {apk['version_name']} (code: {apk['version_code']})")
            print(f"  Package: {apk['package_name']}")
            print(f"  Size: {apk['file_size']:,} bytes")
            print(f"  File: {apk['file_path']}")
            
            if dry_run:
                print("  [DRY RUN] Would download and upload this APK")
                stats["success"] += 1
                continue
            
            print("  Downloading from object storage...")
            file_data = download_apk_from_storage(apk['file_path'])
            
            if not file_data:
                print("  FAILED: Could not download APK file")
                stats["failed"] += 1
                continue
            
            print(f"  Downloaded {len(file_data):,} bytes")
            
            print("  Uploading to production...")
            success = upload_to_production(prod_url, prod_admin_key, file_data, apk)
            
            if success:
                print("  SUCCESS: APK uploaded to production")
                stats["success"] += 1
            else:
                print("  FAILED: Could not upload to production")
                stats["failed"] += 1
        
        print("\n" + "=" * 60)
        print("Migration Complete")
        print("=" * 60)
        print(f"Total APKs: {stats['total']}")
        print(f"Successful: {stats['success']}")
        print(f"Failed: {stats['failed']}")
        print(f"Skipped: {stats['skipped']}")
        
        return stats
        
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Migrate APK records and files from development to production"
    )
    parser.add_argument(
        "--prod-url",
        default=os.environ.get("PROD_URL", "https://unitymdm.replit.app"),
        help="Production backend URL"
    )
    parser.add_argument(
        "--prod-admin-key",
        default=os.environ.get("PROD_ADMIN_KEY"),
        help="Production admin API key"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of APKs to migrate (default: all)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include inactive APKs (default: active only)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without actually doing it"
    )
    
    args = parser.parse_args()
    
    if not args.prod_admin_key:
        print("ERROR: Production admin key required")
        print("Set PROD_ADMIN_KEY environment variable or use --prod-admin-key")
        sys.exit(1)
    
    stats = migrate_apks(
        prod_url=args.prod_url,
        prod_admin_key=args.prod_admin_key,
        limit=args.limit,
        active_only=not args.all,
        dry_run=args.dry_run
    )
    
    if stats["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
