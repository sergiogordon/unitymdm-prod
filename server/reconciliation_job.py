#!/usr/bin/env python3
"""
Hourly reconciliation job to repair device_last_status from recent heartbeats.
Ensures dual-write consistency by replaying the most recent partition rows.

Design:
- Idempotent: Safe to run multiple times
- Capped: Maximum 5,000 rows per run to prevent resource exhaustion
- Reentrant: Uses advisory locks to prevent concurrent execution
- Fast: Only processes last 24 hours of data

Usage:
    python reconciliation_job.py [--dry-run] [--max-rows N]
"""

import sys
import os
import argparse
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from models import SessionLocal
from observability import structured_logger, metrics

ADVISORY_LOCK_ID = 123456789  # Unique ID for reconciliation job advisory lock

def run_reconciliation(dry_run: bool = False, max_rows: int = 5000):
    """
    Reconcile device_last_status from recent heartbeat partition rows.
    
    Strategy:
    1. Acquire advisory lock to prevent concurrent runs
    2. Find the most recent heartbeat per device in last 24h
    3. Upsert into device_last_status if newer
    4. Log statistics and release lock
    
    Returns:
        dict: Statistics about the reconciliation run
    """
    db = SessionLocal()
    lock_acquired = False
    
    try:
        # Try to acquire advisory lock (non-blocking)
        lock_result = db.execute(text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": ADVISORY_LOCK_ID}).scalar()
        
        if not lock_result:
            structured_logger.log_event(
                "reconciliation.skipped",
                reason="lock_held",
                message="Another reconciliation job is already running"
            )
            print("⏭️  Skipped: Another reconciliation job is already running")
            return {"status": "skipped", "reason": "lock_held"}
        
        lock_acquired = True
        structured_logger.log_event("reconciliation.started", dry_run=dry_run, max_rows=max_rows)
        
        start_time = datetime.now(timezone.utc)
        cutoff_ts = start_time - timedelta(hours=24)
        
        print(f"🔄 Starting reconciliation job (dry_run={dry_run})")
        print(f"   Processing heartbeats since: {cutoff_ts.isoformat()}")
        print(f"   Max rows: {max_rows}")
        
        # Find discrepancies: heartbeats newer than device_last_status
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
                LIMIT :max_rows
            ),
            needs_update AS (
                SELECT lh.*
                FROM latest_heartbeats lh
                LEFT JOIN device_last_status dls ON lh.device_id = dls.device_id
                WHERE dls.device_id IS NULL 
                   OR lh.last_ts > dls.last_ts
            )
            SELECT COUNT(*) as update_count
            FROM needs_update
        """)
        
        update_count_result = db.execute(query, {"cutoff_ts": cutoff_ts, "max_rows": max_rows}).scalar()
        
        if update_count_result == 0:
            db.commit()
            structured_logger.log_event(
                "reconciliation.completed",
                updated=0,
                elapsed_ms=0,
                dry_run=dry_run
            )
            print("✅ Reconciliation complete: No updates needed (data is consistent)")
            return {
                "status": "completed",
                "updated": 0,
                "elapsed_ms": 0
            }
        
        print(f"   Found {update_count_result} devices needing reconciliation")
        
        if dry_run:
            db.rollback()
            print(f"✅ Dry run complete: {update_count_result} rows would be updated")
            return {
                "status": "dry_run",
                "would_update": update_count_result
            }
        
        # Perform the upsert
        upsert_query = text("""
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
                LIMIT :max_rows
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
        
        db.execute(upsert_query, {"cutoff_ts": cutoff_ts, "max_rows": max_rows})
        db.commit()
        
        elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        # Log and metrics
        structured_logger.log_event(
            "reconciliation.completed",
            updated=update_count_result,
            elapsed_ms=round(elapsed_ms, 2)
        )
        
        metrics.inc_counter("reconciliation_runs_total", {"status": "success"})
        metrics.inc_counter("reconciliation_rows_updated_total", {}, update_count_result)
        metrics.observe_histogram("reconciliation_duration_ms", elapsed_ms, {})
        
        print(f"✅ Reconciliation complete:")
        print(f"   Rows updated: {update_count_result}")
        print(f"   Duration: {round(elapsed_ms, 2)}ms")
        
        return {
            "status": "completed",
            "updated": update_count_result,
            "elapsed_ms": round(elapsed_ms, 2)
        }
        
    except Exception as e:
        db.rollback()
        structured_logger.log_event(
            "reconciliation.failed",
            error=str(e),
            error_type=type(e).__name__
        )
        metrics.inc_counter("reconciliation_runs_total", {"status": "error"})
        print(f"❌ Reconciliation failed: {e}")
        raise
    
    finally:
        # Always release advisory lock
        if lock_acquired:
            db.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": ADVISORY_LOCK_ID})
        db.close()

def main():
    parser = argparse.ArgumentParser(description='Reconcile device_last_status from recent heartbeats')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without making changes')
    parser.add_argument('--max-rows', type=int, default=5000, help='Maximum rows to process (default: 5000)')
    
    args = parser.parse_args()
    
    if args.max_rows < 100 or args.max_rows > 50000:
        print("❌ Error: --max-rows must be between 100 and 50000")
        sys.exit(1)
    
    try:
        result = run_reconciliation(dry_run=args.dry_run, max_rows=args.max_rows)
        sys.exit(0 if result["status"] in ["completed", "dry_run", "skipped"] else 1)
    except Exception:
        sys.exit(1)

if __name__ == "__main__":
    main()
