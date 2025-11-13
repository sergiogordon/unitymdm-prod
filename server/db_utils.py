"""
Database utility functions for idempotency, retention, and maintenance.
"""
from datetime import datetime, timedelta, timezone, date
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
    Dual-writes to both device_heartbeats (partitioned) and device_last_status (fast read).
    Multiple heartbeats within the same bucket window are deduplicated.
    
    PERFORMANCE OPTIMIZED: Uses INSERT...ON CONFLICT for dedup check + insert in one query.
    
    Args:
        db: Database session
        device_id: Device identifier
        heartbeat_data: Heartbeat payload
        bucket_seconds: Time bucket size in seconds (default: 10)
        
    Returns:
        dict with 'created' (bool) and 'last_status_updated' (bool) keys
    """
    from models import DeviceHeartbeat, DeviceLastStatus
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy import text
    
    start = datetime.now(timezone.utc)
    ts = datetime.now(timezone.utc)
    
    # Calculate bucket timestamp (round down to nearest bucket)
    bucket_ts = ts.replace(second=(ts.second // bucket_seconds) * bucket_seconds, 
                           microsecond=0)
    
    # OPTIMIZATION: Use raw SQL with INSERT...ON CONFLICT for atomic dedup + insert
    # This is much faster than checking first then inserting
    heartbeat_insert_sql = text("""
        INSERT INTO device_heartbeats 
        (device_id, ts, ip, status, battery_pct, plugged, temp_c, network_type, 
         signal_dbm, uptime_s, ram_used_mb, unity_pkg_version, unity_running, agent_version)
        SELECT :device_id, :ts, :ip, :status, :battery_pct, :plugged, :temp_c, :network_type,
               :signal_dbm, :uptime_s, :ram_used_mb, :unity_pkg_version, :unity_running, :agent_version
        WHERE NOT EXISTS (
            SELECT 1 FROM device_heartbeats 
            WHERE device_id = :device_id 
            AND ts >= :bucket_start 
            AND ts < :bucket_end
        )
        RETURNING hb_id
    """)
    
    result = db.execute(heartbeat_insert_sql, {
        'device_id': device_id,
        'ts': ts,
        'ip': heartbeat_data.get('ip'),
        'status': heartbeat_data.get('status', 'ok'),
        'battery_pct': heartbeat_data.get('battery_pct'),
        'plugged': heartbeat_data.get('plugged'),
        'temp_c': heartbeat_data.get('temp_c'),
        'network_type': heartbeat_data.get('network_type'),
        'signal_dbm': heartbeat_data.get('signal_dbm'),
        'uptime_s': heartbeat_data.get('uptime_s'),
        'ram_used_mb': heartbeat_data.get('ram_used_mb'),
        'unity_pkg_version': heartbeat_data.get('unity_pkg_version'),
        'unity_running': heartbeat_data.get('unity_running'),
        'agent_version': heartbeat_data.get('agent_version'),
        'bucket_start': bucket_ts,
        'bucket_end': bucket_ts + timedelta(seconds=bucket_seconds)
    })
    
    # Check if a row was inserted (RETURNING clause returns hb_id if inserted)
    created = result.fetchone() is not None
    
    # DUAL WRITE: Always upsert to device_last_status for O(1) reads (even if heartbeat was deduped)
    last_status_data = {
        'device_id': device_id,
        'last_ts': ts,
        'battery_pct': heartbeat_data.get('battery_pct'),
        'network_type': heartbeat_data.get('network_type'),
        'unity_running': heartbeat_data.get('unity_running'),
        'signal_dbm': heartbeat_data.get('signal_dbm'),
        'agent_version': heartbeat_data.get('agent_version'),
        'ip': heartbeat_data.get('ip'),
        'status': heartbeat_data.get('status', 'ok')
    }
    
    # Use PostgreSQL INSERT ... ON CONFLICT UPDATE (upsert)
    stmt = pg_insert(DeviceLastStatus).values(**last_status_data)
    stmt = stmt.on_conflict_do_update(
        index_elements=['device_id'],
        set_={
            'last_ts': stmt.excluded.last_ts,
            'battery_pct': stmt.excluded.battery_pct,
            'network_type': stmt.excluded.network_type,
            'unity_running': stmt.excluded.unity_running,
            'signal_dbm': stmt.excluded.signal_dbm,
            'agent_version': stmt.excluded.agent_version,
            'ip': stmt.excluded.ip,
            'status': stmt.excluded.status
        }
    )
    db.execute(stmt)
    
    latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
    
    if created:
        log_db_operation('create', 'device_heartbeats', 
                         {'device_id': device_id}, latency_ms)
    else:
        log_db_operation('dedup_hit', 'device_heartbeats', 
                         {'device_id': device_id, 'bucket': str(bucket_ts)}, 
                         latency_ms)
    
    return {'created': created, 'last_status_updated': True}


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


def create_heartbeat_partition(target_date: date) -> None:
    """
    Create a daily partition for device_heartbeats table.
    Idempotent: safe to call multiple times for the same date.
    
    Args:
        target_date: Date for which to create the partition (datetime.date object)
    
    Raises:
        Exception: If partition creation fails
    """
    from models import SessionLocal
    
    partition_name = f"device_heartbeats_{target_date.strftime('%Y%m%d')}"
    start_ts = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
    end_ts = datetime.combine(target_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    
    db = SessionLocal()
    try:
        # Check if partition already exists
        check_query = text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_inherits i ON c.oid = i.inhrelid
                JOIN pg_class p ON p.oid = i.inhparent
                WHERE p.relname = 'device_heartbeats'
                AND c.relname = :partition_name
            )
        """)
        
        exists = db.execute(check_query, {"partition_name": partition_name}).scalar()
        
        if exists:
            logger.info(f"Partition {partition_name} already exists (idempotent)")
            return
        
        # Create partition
        create_query = text(f"""
            CREATE TABLE {partition_name} PARTITION OF device_heartbeats
            FOR VALUES FROM (:start_ts) TO (:end_ts)
        """)
        
        db.execute(create_query, {"start_ts": start_ts, "end_ts": end_ts})
        db.commit()
        
        logger.info(f"Created partition {partition_name} for range [{start_ts}, {end_ts})")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create partition {partition_name}: {e}")
        raise
    finally:
        db.close()


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
