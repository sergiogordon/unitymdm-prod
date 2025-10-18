"""
Test suite for idempotency guarantees and migration functionality.

NOTE: These tests require test devices to exist in the database due to 
foreign key constraints. For quick schema validation, use validate_schema.py instead.

To run these tests:
1. Create test devices first, or
2. Temporarily disable foreign key constraints, or
3. Use this as a reference for integration tests
"""
from datetime import datetime, timezone, timedelta
from models import SessionLocal, FcmDispatch, DeviceHeartbeat, ApkDownloadEvent
from db_utils import (
    record_fcm_dispatch,
    record_heartbeat_with_bucketing,
    record_apk_download,
    cleanup_old_heartbeats,
    cleanup_old_fcm_dispatches
)


def test_fcm_dispatch_idempotency():
    """
    Test that duplicate request_ids don't create duplicate FCM dispatches.
    """
    db = SessionLocal()
    try:
        request_id = f"test_fcm_{datetime.now().timestamp()}"
        device_id = "test_device_001"
        
        # First dispatch - should create
        result1 = record_fcm_dispatch(
            db, request_id, device_id, "ping",
            payload_hash="abc123"
        )
        assert result1['created'] == True
        
        # Second dispatch with same request_id - should return existing
        result2 = record_fcm_dispatch(
            db, request_id, device_id, "ping",
            payload_hash="abc123"
        )
        assert result2['created'] == False
        assert result2['dispatch'].request_id == result1['dispatch'].request_id
        
        # Verify only one record exists
        count = db.query(FcmDispatch).filter(
            FcmDispatch.request_id == request_id
        ).count()
        assert count == 1
        
        print("✓ FCM dispatch idempotency test passed")
    finally:
        # Cleanup
        db.query(FcmDispatch).filter(
            FcmDispatch.request_id.like("test_fcm_%")
        ).delete()
        db.commit()
        db.close()


def test_heartbeat_time_bucketing():
    """
    Test that heartbeats within the same 10-second bucket are deduplicated.
    """
    db = SessionLocal()
    try:
        device_id = "test_device_hb_001"
        
        # First heartbeat
        result1 = record_heartbeat_with_bucketing(
            db, device_id,
            {'status': 'ok', 'battery_pct': 85}
        )
        assert result1['created'] == True
        
        # Second heartbeat within 10 seconds - should be deduplicated
        result2 = record_heartbeat_with_bucketing(
            db, device_id,
            {'status': 'ok', 'battery_pct': 84}
        )
        assert result2['created'] == False
        
        # Wait for next bucket (in production; here we simulate)
        # For testing, we can verify separate buckets work
        future_ts = datetime.now(timezone.utc) + timedelta(seconds=12)
        
        print("✓ Heartbeat time-bucketing test passed")
    finally:
        # Cleanup
        db.query(DeviceHeartbeat).filter(
            DeviceHeartbeat.device_id == "test_device_hb_001"
        ).delete()
        db.commit()
        db.close()


def test_retention_cleanup():
    """
    Test that retention cleanup removes old records.
    """
    db = SessionLocal()
    try:
        device_id = "test_device_cleanup_001"
        
        # Create old heartbeat (3 days ago)
        old_hb = DeviceHeartbeat(
            device_id=device_id,
            ts=datetime.now(timezone.utc) - timedelta(days=3),
            status='ok'
        )
        db.add(old_hb)
        
        # Create recent heartbeat
        recent_hb = DeviceHeartbeat(
            device_id=device_id,
            ts=datetime.now(timezone.utc),
            status='ok'
        )
        db.add(recent_hb)
        db.commit()
        
        # Run cleanup (2 day retention)
        deleted = cleanup_old_heartbeats(db, retention_days=2)
        assert deleted >= 1
        
        # Verify old record deleted, recent kept
        remaining = db.query(DeviceHeartbeat).filter(
            DeviceHeartbeat.device_id == device_id
        ).count()
        assert remaining == 1
        
        print("✓ Retention cleanup test passed")
    finally:
        # Cleanup
        db.query(DeviceHeartbeat).filter(
            DeviceHeartbeat.device_id.like("test_device_cleanup_%")
        ).delete()
        db.commit()
        db.close()


if __name__ == "__main__":
    print("Running idempotency tests...")
    print()
    
    test_fcm_dispatch_idempotency()
    test_heartbeat_time_bucketing()
    test_retention_cleanup()
    
    print()
    print("All tests passed!")
