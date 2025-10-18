#!/usr/bin/env python3
"""
Backfill device_last_status table from recent heartbeats.
This should be run once before enabling READ_FROM_LAST_STATUS feature flag.

Usage:
    python backfill_last_status.py [--days N]
    
Options:
    --days N    Backfill from last N days of heartbeats (default: 7)
"""

import sys
import os
import argparse
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from models import SessionLocal

def backfill_device_last_status(days: int = 7):
    """
    Backfill device_last_status from the most recent heartbeat for each device
    in the last N days.
    
    Strategy:
    1. Find the most recent heartbeat per device in the last N days
    2. Insert/update into device_last_status with ON CONFLICT DO UPDATE
    3. Report progress and statistics
    """
    db = SessionLocal()
    try:
        cutoff_ts = datetime.now(timezone.utc) - timedelta(days=days)
        
        print(f"🔄 Backfilling device_last_status from heartbeats since {cutoff_ts.isoformat()}")
        print(f"   (last {days} days)")
        
        # Query to find the most recent heartbeat per device and upsert into device_last_status
        # Using window function to get latest heartbeat efficiently
        query = text("""
            WITH latest_heartbeats AS (
                SELECT DISTINCT ON (device_id)
                    device_id,
                    ts as last_ts,
                    battery_pct,
                    network_type,
                    unity_running,
                    signal_dbm,
                    agent_version,
                    ip,
                    status
                FROM device_heartbeats
                WHERE ts >= :cutoff_ts
                ORDER BY device_id, ts DESC
            )
            INSERT INTO device_last_status (
                device_id, last_ts, battery_pct, network_type, unity_running,
                signal_dbm, agent_version, ip, status
            )
            SELECT 
                device_id, last_ts, battery_pct, network_type, unity_running,
                signal_dbm, agent_version, ip, status
            FROM latest_heartbeats
            ON CONFLICT (device_id) DO UPDATE SET
                last_ts = EXCLUDED.last_ts,
                battery_pct = EXCLUDED.battery_pct,
                network_type = EXCLUDED.network_type,
                unity_running = EXCLUDED.unity_running,
                signal_dbm = EXCLUDED.signal_dbm,
                agent_version = EXCLUDED.agent_version,
                ip = EXCLUDED.ip,
                status = EXCLUDED.status
            WHERE EXCLUDED.last_ts > device_last_status.last_ts
        """)
        
        result = db.execute(query, {"cutoff_ts": cutoff_ts})
        db.commit()
        
        # Get statistics
        stats = db.execute(text("""
            SELECT 
                COUNT(*) as total_devices,
                COUNT(*) FILTER (WHERE last_ts >= :recent) as recent_devices,
                MIN(last_ts) as oldest_status,
                MAX(last_ts) as newest_status
            FROM device_last_status
        """), {"recent": datetime.now(timezone.utc) - timedelta(hours=1)}).fetchone()
        
        print(f"\n✅ Backfill complete!")
        print(f"   Total devices in device_last_status: {stats.total_devices}")
        print(f"   Devices active in last hour: {stats.recent_devices}")
        print(f"   Oldest status timestamp: {stats.oldest_status}")
        print(f"   Newest status timestamp: {stats.newest_status}")
        print(f"\n💡 To enable fast reads, set environment variable:")
        print(f"   READ_FROM_LAST_STATUS=true")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Backfill failed: {e}")
        sys.exit(1)
    finally:
        db.close()

def main():
    parser = argparse.ArgumentParser(description='Backfill device_last_status from recent heartbeats')
    parser.add_argument('--days', type=int, default=7, help='Number of days to backfill (default: 7)')
    
    args = parser.parse_args()
    
    if args.days < 1 or args.days > 90:
        print("❌ Error: --days must be between 1 and 90")
        sys.exit(1)
    
    backfill_device_last_status(days=args.days)

if __name__ == "__main__":
    main()
