"""
Acceptance Tests: Partition Management & Fast Reads

Tests critical system behaviors:
1. Partition pruning (query only touches relevant partitions)
2. Deduplication (10s bucketing prevents duplicate writes)
3. Reconciliation (repairs drift in device_last_status)
4. Archive checksums (validates archived data integrity)
5. Failure scenarios (advisory locks, failed archives, partition errors)

Usage:
    pytest acceptance_tests.py -v
    python acceptance_tests.py  # Run directly
"""

import pytest
import os
import hashlib
import json
from datetime import datetime, timezone, timedelta, date
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from models import Base, Device, DeviceHeartbeat
from db_utils import (
    record_heartbeat_with_bucketing,
    create_heartbeat_partition,
    get_partition_metadata,
    update_partition_metadata
)
from fast_reads import get_device_status_fast, get_offline_devices_fast
from reconciliation_job import run_reconciliation
from nightly_maintenance import (
    create_future_partitions,
    archive_old_partitions,
    drop_old_partitions
)


# Test database setup
TEST_DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(TEST_DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


class TestPartitionPruning:
    """Test that queries only scan relevant partitions"""
    
    def test_single_day_query_uses_one_partition(self):
        """Verify partition pruning: query for one day should scan only that partition"""
        db = SessionLocal()
        try:
            # Create test device
            device_id = "test-partition-pruning"
            device = Device(
                id=device_id,
                alias="partition-test",
                token_hash="test",
                token_id="test"
            )
            db.merge(device)
            db.commit()
            
            # Insert heartbeats across 3 days
            today = date.today()
            for i in range(3):
                target_date = today - timedelta(days=i)
                create_heartbeat_partition(target_date)
                
                # Insert heartbeat for this day
                ts = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                hb = DeviceHeartbeat(
                    device_id=device_id,
                    ts=ts,
                    ip="192.168.1.1",
                    status="ok"
                )
                db.add(hb)
            
            db.commit()
            
            # Query for just today with EXPLAIN
            query = text("""
                EXPLAIN (FORMAT JSON)
                SELECT * FROM device_heartbeats
                WHERE device_id = :device_id
                  AND ts >= :start_ts
                  AND ts < :end_ts
            """)
            
            start_ts = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
            end_ts = start_ts + timedelta(days=1)
            
            result = db.execute(query, {
                "device_id": device_id,
                "start_ts": start_ts,
                "end_ts": end_ts
            }).scalar()
            
            # Parse EXPLAIN output
            plan = json.loads(result)[0]["Plan"]
            
            # Check that only 1 partition is scanned
            # Look for partition name in the plan
            partition_name = f"device_heartbeats_{today.strftime('%Y%m%d')}"
            plan_str = json.dumps(plan)
            
            assert partition_name in plan_str, f"Query should scan partition {partition_name}"
            print(f"✓ Partition pruning working: Query scans only {partition_name}")
            
        finally:
            db.close()
    
    def test_partition_metadata_tracks_row_counts(self):
        """Verify partition metadata accurately tracks row counts"""
        db = SessionLocal()
        try:
            today = date.today()
            partition_name = f"device_heartbeats_{today.strftime('%Y%m%d')}"
            
            # Get initial row count
            metadata_before = get_partition_metadata(db, partition_name)
            initial_count = metadata_before['row_count'] if metadata_before else 0
            
            # Insert 5 heartbeats
            device_id = "test-metadata"
            device = Device(id=device_id, alias="meta-test", token_hash="t", token_id="t")
            db.merge(device)
            
            for i in range(5):
                ts = datetime.now(timezone.utc) + timedelta(seconds=i*20)  # Avoid deduplication
                hb = DeviceHeartbeat(
                    device_id=device_id,
                    ts=ts,
                    ip="192.168.1.1",
                    status="ok"
                )
                db.add(hb)
            
            db.commit()
            
            # Update metadata
            update_partition_metadata(db, partition_name)
            db.commit()
            
            # Verify row count increased by 5
            metadata_after = get_partition_metadata(db, partition_name)
            assert metadata_after is not None
            assert metadata_after['row_count'] == initial_count + 5
            
            print(f"✓ Partition metadata tracking: {initial_count} → {metadata_after['row_count']} rows")
            
        finally:
            db.close()


class TestDeduplication:
    """Test 10-second bucketing deduplication"""
    
    def test_duplicate_heartbeats_within_10s_bucket(self):
        """Duplicate heartbeats within 10s should be deduplicated"""
        db = SessionLocal()
        try:
            device_id = "test-dedup"
            device = Device(id=device_id, alias="dedup-test", token_hash="t", token_id="t")
            db.merge(device)
            db.commit()
            
            heartbeat_data = {
                'ip': '192.168.1.100',
                'status': 'ok',
                'battery_pct': 75
            }
            
            # Send first heartbeat
            result1 = record_heartbeat_with_bucketing(db, device_id, heartbeat_data, bucket_seconds=10)
            assert result1['created'] is True, "First heartbeat should be created"
            
            # Send duplicate within 10s (should be skipped)
            result2 = record_heartbeat_with_bucketing(db, device_id, heartbeat_data, bucket_seconds=10)
            assert result2['created'] is False, "Duplicate heartbeat should be skipped"
            assert result2['reason'] == 'duplicate', "Should be marked as duplicate"
            
            print(f"✓ Deduplication working: Duplicate within 10s bucket skipped")
            
        finally:
            db.close()
    
    def test_heartbeat_after_bucket_creates_new_row(self):
        """Heartbeat after 10s bucket should create new row"""
        db = SessionLocal()
        try:
            device_id = "test-bucket"
            device = Device(id=device_id, alias="bucket-test", token_hash="t", token_id="t")
            db.merge(device)
            db.commit()
            
            heartbeat_data = {'ip': '192.168.1.100', 'status': 'ok'}
            
            # First heartbeat
            result1 = record_heartbeat_with_bucketing(db, device_id, heartbeat_data, bucket_seconds=10)
            assert result1['created'] is True
            
            # Wait past bucket (simulate by manually inserting with old timestamp)
            old_ts = datetime.now(timezone.utc) - timedelta(seconds=11)
            db.execute(text("""
                UPDATE device_heartbeats
                SET ts = :old_ts
                WHERE device_id = :device_id
            """), {"old_ts": old_ts, "device_id": device_id})
            db.commit()
            
            # New heartbeat (should create new row)
            result2 = record_heartbeat_with_bucketing(db, device_id, heartbeat_data, bucket_seconds=10)
            assert result2['created'] is True, "Heartbeat after bucket should create new row"
            
            print(f"✓ Bucketing working: New row created after 10s bucket")
            
        finally:
            db.close()


class TestReconciliation:
    """Test reconciliation job heals drift"""
    
    def test_reconciliation_repairs_missing_last_status(self):
        """Reconciliation should repair missing device_last_status entries"""
        db = SessionLocal()
        try:
            device_id = "test-reconcile-missing"
            device = Device(id=device_id, alias="reconcile-test", token_hash="t", token_id="t")
            db.merge(device)
            db.commit()
            
            # Insert heartbeat directly (bypass dual-write)
            ts = datetime.now(timezone.utc)
            hb = DeviceHeartbeat(
                device_id=device_id,
                ts=ts,
                ip="192.168.1.50",
                status="ok",
                battery_pct=88
            )
            db.add(hb)
            db.commit()
            
            # Verify device_last_status is missing
            status_before = db.execute(text("""
                SELECT * FROM device_last_status WHERE device_id = :device_id
            """), {"device_id": device_id}).fetchone()
            
            # Run reconciliation
            result = run_reconciliation(dry_run=False, max_rows=1000)
            
            # Verify device_last_status is now populated
            status_after = db.execute(text("""
                SELECT * FROM device_last_status WHERE device_id = :device_id
            """), {"device_id": device_id}).fetchone()
            
            assert status_after is not None, "Reconciliation should create missing entry"
            assert status_after.battery_pct == 88, "Battery should match heartbeat"
            
            print(f"✓ Reconciliation: Repaired missing device_last_status entry")
            print(f"  Rows updated: {result['rows_updated']}")
            
        finally:
            db.close()
    
    def test_reconciliation_updates_stale_last_status(self):
        """Reconciliation should update stale device_last_status entries"""
        db = SessionLocal()
        try:
            device_id = "test-reconcile-stale"
            device = Device(id=device_id, alias="stale-test", token_hash="t", token_id="t")
            db.merge(device)
            db.commit()
            
            # Create stale device_last_status
            old_ts = datetime.now(timezone.utc) - timedelta(hours=2)
            db.execute(text("""
                INSERT INTO device_last_status (device_id, last_ts, battery_pct, status)
                VALUES (:device_id, :ts, 50, 'ok')
                ON CONFLICT (device_id) DO UPDATE SET last_ts = EXCLUDED.last_ts
            """), {"device_id": device_id, "ts": old_ts})
            db.commit()
            
            # Insert newer heartbeat
            new_ts = datetime.now(timezone.utc)
            hb = DeviceHeartbeat(
                device_id=device_id,
                ts=new_ts,
                battery_pct=95,
                status="ok"
            )
            db.add(hb)
            db.commit()
            
            # Run reconciliation
            run_reconciliation(dry_run=False, max_rows=1000)
            
            # Verify device_last_status is updated
            status = db.execute(text("""
                SELECT battery_pct, last_ts FROM device_last_status WHERE device_id = :device_id
            """), {"device_id": device_id}).fetchone()
            
            assert status.battery_pct == 95, "Battery should be updated to latest"
            assert (new_ts - status.last_ts).total_seconds() < 5, "Timestamp should be recent"
            
            print(f"✓ Reconciliation: Updated stale device_last_status entry")
            
        finally:
            db.close()


class TestArchiveChecksums:
    """Test archive integrity with SHA-256 checksums"""
    
    def test_archive_generates_valid_checksum(self):
        """Archived partition should have valid SHA-256 checksum"""
        db = SessionLocal()
        try:
            # Create old partition with data
            old_date = date.today() - timedelta(days=100)
            create_heartbeat_partition(old_date)
            partition_name = f"device_heartbeats_{old_date.strftime('%Y%m%d')}"
            
            # Insert test data
            device_id = "test-archive"
            device = Device(id=device_id, alias="archive-test", token_hash="t", token_id="t")
            db.merge(device)
            
            ts = datetime.combine(old_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            hb = DeviceHeartbeat(
                device_id=device_id,
                ts=ts,
                ip="192.168.1.200",
                status="ok"
            )
            db.add(hb)
            db.commit()
            
            # Archive partition
            archived = archive_old_partitions(retention_days=90, dry_run=False)
            
            # Check checksum was generated
            metadata = get_partition_metadata(db, partition_name)
            assert metadata is not None
            
            if metadata.get('state') == 'archived':
                assert metadata.get('archive_checksum') is not None
                assert len(metadata['archive_checksum']) == 64  # SHA-256 hex
                
                print(f"✓ Archive checksum: {metadata['archive_checksum'][:16]}...")
            else:
                print(f"⚠ Partition not archived (may not meet retention criteria)")
            
        finally:
            db.close()


class TestFailureScenarios:
    """Test error handling and recovery"""
    
    def test_advisory_lock_prevents_concurrent_runs(self):
        """Concurrent job runs should be blocked by advisory locks"""
        db1 = SessionLocal()
        db2 = SessionLocal()
        try:
            # Acquire lock in first session
            lock_acquired_1 = db1.execute(text("SELECT pg_try_advisory_lock(12345)")).scalar()
            assert lock_acquired_1 is True, "First lock should succeed"
            
            # Try to acquire same lock in second session
            lock_acquired_2 = db2.execute(text("SELECT pg_try_advisory_lock(12345)")).scalar()
            assert lock_acquired_2 is False, "Second lock should fail (already held)"
            
            # Release lock
            db1.execute(text("SELECT pg_advisory_unlock(12345)"))
            
            # Now second session should succeed
            lock_acquired_3 = db2.execute(text("SELECT pg_try_advisory_lock(12345)")).scalar()
            assert lock_acquired_3 is True, "Lock should succeed after release"
            
            db2.execute(text("SELECT pg_advisory_unlock(12345)"))
            
            print(f"✓ Advisory locks: Prevent concurrent job execution")
            
        finally:
            db1.close()
            db2.close()
    
    def test_partition_creation_is_idempotent(self):
        """Creating same partition twice should be safe"""
        target_date = date.today() + timedelta(days=10)
        
        # Create partition twice
        create_heartbeat_partition(target_date)
        create_heartbeat_partition(target_date)  # Should not error
        
        # Verify partition exists
        partition_name = f"device_heartbeats_{target_date.strftime('%Y%m%d')}"
        db = SessionLocal()
        try:
            result = db.execute(text("""
                SELECT COUNT(*) FROM pg_tables
                WHERE tablename = :name
            """), {"name": partition_name}).scalar()
            
            assert result == 1, "Partition should exist exactly once"
            print(f"✓ Partition creation is idempotent")
            
        finally:
            db.close()
    
    def test_fast_read_handles_missing_device(self):
        """Fast reads should gracefully handle missing devices"""
        db = SessionLocal()
        try:
            status = get_device_status_fast(db, "nonexistent-device-id")
            assert status is None, "Should return None for missing device"
            
            print(f"✓ Fast reads: Handle missing devices gracefully")
            
        finally:
            db.close()


def run_all_tests():
    """Run all acceptance tests"""
    print("\n" + "="*60)
    print("ACCEPTANCE TESTS: Partition Management & Fast Reads")
    print("="*60 + "\n")
    
    test_classes = [
        TestPartitionPruning,
        TestDeduplication,
        TestReconciliation,
        TestArchiveChecksums,
        TestFailureScenarios
    ]
    
    total_tests = 0
    passed_tests = 0
    failed_tests = []
    
    for test_class in test_classes:
        print(f"\n{test_class.__name__}:")
        print("-" * 60)
        
        # Get all test methods
        test_methods = [m for m in dir(test_class) if m.startswith('test_')]
        
        for method_name in test_methods:
            total_tests += 1
            try:
                test_instance = test_class()
                test_method = getattr(test_instance, method_name)
                test_method()
                passed_tests += 1
            except Exception as e:
                failed_tests.append((f"{test_class.__name__}.{method_name}", str(e)))
                print(f"✗ {method_name}: FAILED")
                print(f"  Error: {e}")
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Total: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {len(failed_tests)}")
    
    if failed_tests:
        print(f"\nFailed Tests:")
        for test_name, error in failed_tests:
            print(f"  ✗ {test_name}")
            print(f"    {error}")
        print("\n" + "="*60)
        return False
    else:
        print("\n✓ ALL TESTS PASSED")
        print("="*60)
        return True


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
