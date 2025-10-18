"""
Database utility functions for idempotency, retention, and maintenance.
"""
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def log_db_operation(event: str, entity: str, keys: dict, latency_ms: float):
    """
    Structured logging for database operations.
    
    Args:
        event: Operation type (create, update, delete, cleanup)
        entity: Table/entity name
        keys: Dictionary of identifying keys
        latency_ms: Operation latency in milliseconds
    """
    logger.info(
        f"db_operation event={event} entity={entity} keys={keys} latency_ms={latency_ms}"
    )


def record_fcm_dispatch(
    db: Session,
    request_id: str,
    device_id: str,
    action: str,
    **kwargs
) -> dict:
    """
    Record FCM dispatch with idempotency guarantee.
    If request_id already exists, return existing record without creating duplicate.
    
    Args:
        db: Database session
        request_id: Unique request identifier (idempotency key)
        device_id: Target device ID
        action: FCM action type
        **kwargs: Additional FCM dispatch fields
        
    Returns:
        dict with 'created' (bool) and 'dispatch' (record) keys
    """
    from models import FcmDispatch
    
    start = datetime.now(timezone.utc)
    
    # Check if dispatch already exists
    existing = db.query(FcmDispatch).filter(
        FcmDispatch.request_id == request_id
    ).first()
    
    if existing:
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        log_db_operation('idempotency_hit', 'fcm_dispatches', 
                         {'request_id': request_id}, latency_ms)
        return {'created': False, 'dispatch': existing}
    
    # Create new dispatch
    dispatch = FcmDispatch(
        request_id=request_id,
        device_id=device_id,
        action=action,
        sent_at=datetime.now(timezone.utc),
        fcm_status=kwargs.get('fcm_status', 'pending'),
        retries=kwargs.get('retries', 0),
        **{k: v for k, v in kwargs.items() 
           if k not in ['fcm_status', 'retries']}
    )
    
    db.add(dispatch)
    db.commit()
    db.refresh(dispatch)
    
    latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
    log_db_operation('create', 'fcm_dispatches', 
                     {'request_id': request_id}, latency_ms)
    
    return {'created': True, 'dispatch': dispatch}


def record_heartbeat_with_bucketing(
    db: Session,
    device_id: str,
    heartbeat_data: dict,
    bucket_seconds: int = 10
) -> dict:
    """
    Record device heartbeat with time-bucketing for deduplication.
    Multiple heartbeats within the same bucket window are deduplicated.
    
    Args:
        db: Database session
        device_id: Device identifier
        heartbeat_data: Heartbeat payload
        bucket_seconds: Time bucket size in seconds (default: 10)
        
    Returns:
        dict with 'created' (bool) and 'heartbeat' (record) keys
    """
    from models import DeviceHeartbeat
    
    start = datetime.now(timezone.utc)
    ts = datetime.now(timezone.utc)
    
    # Calculate bucket timestamp (round down to nearest bucket)
    bucket_ts = ts.replace(second=(ts.second // bucket_seconds) * bucket_seconds, 
                           microsecond=0)
    
    # Check for existing heartbeat in this bucket
    existing = db.query(DeviceHeartbeat).filter(
        DeviceHeartbeat.device_id == device_id,
        DeviceHeartbeat.ts >= bucket_ts,
        DeviceHeartbeat.ts < bucket_ts + timedelta(seconds=bucket_seconds)
    ).first()
    
    if existing:
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        log_db_operation('dedup_hit', 'device_heartbeats', 
                         {'device_id': device_id, 'bucket': str(bucket_ts)}, 
                         latency_ms)
        return {'created': False, 'heartbeat': existing}
    
    # Create new heartbeat
    heartbeat = DeviceHeartbeat(
        device_id=device_id,
        ts=ts,
        status=heartbeat_data.get('status', 'ok'),
        **{k: v for k, v in heartbeat_data.items() if k != 'status'}
    )
    
    db.add(heartbeat)
    db.commit()
    db.refresh(heartbeat)
    
    latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
    log_db_operation('create', 'device_heartbeats', 
                     {'device_id': device_id}, latency_ms)
    
    return {'created': True, 'heartbeat': heartbeat}


def record_apk_download(
    db: Session,
    build_id: int,
    source: str,
    token_id: Optional[str] = None,
    admin_user: Optional[str] = None,
    ip: Optional[str] = None
):
    """
    Record APK download event for audit trail.
    
    Args:
        db: Database session
        build_id: APK version/build ID
        source: Download source (enrollment|manual|ci)
        token_id: Enrollment token ID if applicable
        admin_user: Admin username if manual download
        ip: Client IP address
    """
    from models import ApkDownloadEvent
    
    start = datetime.now(timezone.utc)
    
    event = ApkDownloadEvent(
        build_id=build_id,
        source=source,
        token_id=token_id,
        admin_user=admin_user,
        ip=ip,
        ts=datetime.now(timezone.utc)
    )
    
    db.add(event)
    db.commit()
    
    latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
    log_db_operation('create', 'apk_download_events', 
                     {'build_id': build_id, 'source': source}, latency_ms)


def cleanup_old_heartbeats(db: Session, retention_days: int = 2) -> int:
    """
    Delete heartbeats older than retention period.
    
    Args:
        db: Database session
        retention_days: Number of days to retain (default: 2)
        
    Returns:
        Number of rows deleted
    """
    from models import DeviceHeartbeat
    
    start = datetime.now(timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    
    result = db.query(DeviceHeartbeat).filter(
        DeviceHeartbeat.ts < cutoff
    ).delete(synchronize_session=False)
    
    db.commit()
    
    latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
    log_db_operation('cleanup', 'device_heartbeats', 
                     {'cutoff': str(cutoff), 'deleted': result}, latency_ms)
    
    return result


def cleanup_old_fcm_dispatches(db: Session, retention_days: int = 2) -> int:
    """
    Delete FCM dispatch records older than retention period.
    
    Args:
        db: Database session
        retention_days: Number of days to retain (default: 2)
        
    Returns:
        Number of rows deleted
    """
    from models import FcmDispatch
    
    start = datetime.now(timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    
    result = db.query(FcmDispatch).filter(
        FcmDispatch.sent_at < cutoff
    ).delete(synchronize_session=False)
    
    db.commit()
    
    latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
    log_db_operation('cleanup', 'fcm_dispatches', 
                     {'cutoff': str(cutoff), 'deleted': result}, latency_ms)
    
    return result


def cleanup_old_apk_downloads(db: Session, retention_days: int = 7) -> int:
    """
    Delete APK download events older than retention period.
    
    Args:
        db: Database session
        retention_days: Number of days to retain (default: 7)
        
    Returns:
        Number of rows deleted
    """
    from models import ApkDownloadEvent
    
    start = datetime.now(timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    
    result = db.query(ApkDownloadEvent).filter(
        ApkDownloadEvent.ts < cutoff
    ).delete(synchronize_session=False)
    
    db.commit()
    
    latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
    log_db_operation('cleanup', 'apk_download_events', 
                     {'cutoff': str(cutoff), 'deleted': result}, latency_ms)
    
    return result


def run_all_retention_cleanups(db: Session) -> dict:
    """
    Run all retention cleanup jobs.
    
    Args:
        db: Database session
        
    Returns:
        dict with counts of deleted rows per table
    """
    results = {
        'heartbeats': cleanup_old_heartbeats(db, retention_days=2),
        'fcm_dispatches': cleanup_old_fcm_dispatches(db, retention_days=2),
        'apk_downloads': cleanup_old_apk_downloads(db, retention_days=7)
    }
    
    logger.info(f"Retention cleanup completed: {results}")
    return results
