"""
Fast read helpers using device_last_status table.
These functions provide O(1) lookups when READ_FROM_LAST_STATUS flag is enabled.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
import os
import time
from observability import metrics

def get_offline_devices_fast(db: Session, heartbeat_interval_seconds: int) -> List[Dict[str, Any]]:
    """
    Get offline devices using device_last_status table.
    O(1) index scan vs. full table scan + window function.

    Returns list of: {device_id, alias, last_seen, offline_seconds}
    """
    start_time = time.time()

    cutoff_ts = datetime.now(timezone.utc) - timedelta(seconds=heartbeat_interval_seconds * 3)

    query = text("""
        SELECT 
            d.id as device_id,
            d.alias,
            dls.last_ts as last_seen,
            EXTRACT(EPOCH FROM (NOW() - dls.last_ts)) as offline_seconds
        FROM device_last_status dls
        JOIN devices d ON d.id = dls.device_id
        WHERE dls.last_ts < :cutoff_ts
        ORDER BY dls.last_ts ASC
    """)

    result = db.execute(query, {"cutoff_ts": cutoff_ts})
    devices = [
        {
            "device_id": row.device_id,
            "alias": row.alias,
            "last_seen": row.last_seen,
            "offline_seconds": int(row.offline_seconds)
        }
        for row in result
    ]

    latency_ms = (time.time() - start_time) * 1000
    metrics.observe_histogram("last_status_read_latency_ms", latency_ms, {"query": "offline_devices"})

    return devices

def get_unity_down_devices_fast(db: Session) -> List[Dict[str, Any]]:
    """
    Get devices where Unity is not running using device_last_status table.
    O(1) index scan on unity_running + last_ts.

    Returns list of: {device_id, alias, last_seen, unity_running}
    """
    # Only return devices seen in last 24h to avoid stale data
    cutoff_ts = datetime.now(timezone.utc) - timedelta(hours=24)

    query = text("""
        SELECT 
            d.id as device_id,
            d.alias,
            dls.last_ts as last_seen,
            dls.unity_running
        FROM device_last_status dls
        JOIN devices d ON d.id = dls.device_id
        WHERE (dls.unity_running = false OR dls.unity_running IS NULL)
        AND dls.last_ts >= :cutoff_ts
        ORDER BY dls.last_ts DESC
    """)

    result = db.execute(query, {"cutoff_ts": cutoff_ts})
    return [
        {
            "device_id": row.device_id,
            "alias": row.alias,
            "last_seen": row.last_seen,
            "unity_running": row.unity_running
        }
        for row in result
    ]

def get_device_status_fast(db: Session, device_id: str) -> Optional[Dict[str, Any]]:
    """
    Get current status for a single device using device_last_status table.
    O(1) primary key lookup.

    Returns: {last_ts, battery_pct, network_type, unity_running, signal_dbm, agent_version, ip, status, ssid}
    """
    start_time = time.time()

    query = text("""
        SELECT 
            last_ts,
            battery_pct,
            network_type,
            unity_running,
            signal_dbm,
            agent_version,
            ip,
            status,
            ssid
        FROM device_last_status
        WHERE device_id = :device_id
    """)

    result = db.execute(query, {"device_id": device_id}).fetchone()

    latency_ms = (time.time() - start_time) * 1000
    metrics.observe_histogram("last_status_read_latency_ms", latency_ms, {"query": "device_status"})

    if not result:
        return None

    return {
        "last_ts": result.last_ts,
        "battery_pct": result.battery_pct,
        "network": result.ssid if result.ssid else result.network_type,
        "unity_running": result.unity_running,
        "signal_dbm": result.signal_dbm,
        "agent_version": result.agent_version,
        "ip": result.ip,
        "status": result.status
    }

def get_all_device_statuses_fast(db: Session, device_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Batch get status for multiple devices using device_last_status table.
    Single query with IN clause for efficient bulk lookup.

    Returns: {device_id -> status_dict}
    """
    if not device_ids:
        return {}

    start_time = time.time()

    query = text("""
        SELECT 
            device_id,
            last_ts,
            battery_pct,
            network_type,
            unity_running,
            signal_dbm,
            agent_version,
            ip,
            status,
            ssid
        FROM device_last_status
        WHERE device_id = ANY(:device_ids)
    """)

    result = db.execute(query, {"device_ids": device_ids})
    statuses = {
        row.device_id: {
            "last_ts": row.last_ts,
            "battery_pct": row.battery_pct,
            "network": row.ssid if row.ssid else row.network_type,
            "unity_running": row.unity_running,
            "signal_dbm": row.signal_dbm,
            "agent_version": row.agent_version,
            "ip": row.ip,
            "status": row.status
        }
        for row in result
    }

    latency_ms = (time.time() - start_time) * 1000
    metrics.observe_histogram("last_status_read_latency_ms", latency_ms, {"query": "batch_statuses"})

    return statuses

def is_device_online_fast(db: Session, device_id: str, heartbeat_interval_seconds: int) -> bool:
    """
    Check if device is online using device_last_status table.
    O(1) primary key lookup + timestamp comparison.
    """
    status = get_device_status_fast(db, device_id)
    if not status or not status["last_ts"]:
        return False

    offline_seconds = (datetime.now(timezone.utc) - status["last_ts"].replace(tzinfo=timezone.utc)).total_seconds()
    return offline_seconds <= heartbeat_interval_seconds * 3