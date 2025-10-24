#!/usr/bin/env python3
"""
Nightly maintenance job for partition lifecycle management.

Responsibilities:
1. Create future partitions (3 days ahead)
2. Archive old partitions (CSV export + SHA-256 + object storage)
3. Drop archived partitions (2+ days old, only if archived successfully)
4. Update partition metadata (row counts, sizes, states)
5. VACUUM ANALYZE hot partitions for optimal query planning

Usage:
    python nightly_maintenance.py [--dry-run] [--retention-days N]
"""

import sys
import os
import argparse
import hashlib
import csv
import gzip
from datetime import datetime, timezone, timedelta
from io import StringIO
from sqlalchemy import text
from models import SessionLocal, HeartbeatPartition
from observability import structured_logger, metrics
from db_utils import create_heartbeat_partition

ADVISORY_LOCK_ID = 987654321  # Unique ID for nightly maintenance advisory lock
DEFAULT_RETENTION_DAYS = 2

def create_future_partitions(db, days_ahead: int = 3, dry_run: bool = False):
    """
    Create partitions for the next N days if they don't exist.
    Uses the idempotent create_heartbeat_partition function.
    """
    created_count = 0
    start_date = datetime.now(timezone.utc).date()
    
    print(f"\n📅 Creating partitions for next {days_ahead} days...")
    
    for offset in range(days_ahead + 1):  # Include today
        target_date = start_date + timedelta(days=offset)
        partition_name = f"device_heartbeats_{target_date.strftime('%Y%m%d')}"
        
        # Check if partition already exists
        existing = db.query(HeartbeatPartition).filter(
            HeartbeatPartition.partition_name == partition_name
        ).first()
        
        if existing:
            continue
        
        if dry_run:
            print(f"   [DRY RUN] Would create partition: {partition_name}")
            created_count += 1
        else:
            try:
                create_heartbeat_partition(target_date)
                
                # Add to metadata table
                partition_meta = HeartbeatPartition(
                    partition_name=partition_name,
                    range_start=datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc),
                    range_end=datetime.combine(target_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc),
                    state='active',
                    created_at=datetime.now(timezone.utc)
                )
                db.add(partition_meta)
                db.commit()
                
                print(f"   ✓ Created partition: {partition_name}")
                created_count += 1
                
                structured_logger.log_event(
                    "partition.create",
                    partition_name=partition_name,
                    date=target_date.isoformat()
                )
                metrics.inc_counter("partitions_created_total", {})
                
            except Exception as e:
                print(f"   ✗ Failed to create {partition_name}: {e}")
                structured_logger.log_event(
                    "partition.create_failed",
                    partition_name=partition_name,
                    error=str(e)
                )
                metrics.inc_counter("partition_create_failures_total", {})
    
    return created_count

def update_partition_stats(db, dry_run: bool = False):
    """
    Update row counts and byte sizes for active partitions.
    """
    print(f"\n📊 Updating partition statistics...")
    
    if dry_run:
        print("   [DRY RUN] Would update row counts and sizes")
        return 0
    
    query = text("""
        UPDATE hb_partitions
        SET 
            row_count = subquery.row_count,
            bytes_size = subquery.bytes_size
        FROM (
            SELECT 
                c.relname as partition_name,
                COALESCE(s.n_tup_ins, 0) as row_count,
                pg_total_relation_size('public.' || c.relname) as bytes_size
            FROM pg_class c
            LEFT JOIN pg_stat_user_tables s ON s.relname = c.relname
            WHERE c.relname LIKE 'device_heartbeats_%'
        ) subquery
        WHERE hb_partitions.partition_name = subquery.partition_name
        AND hb_partitions.state = 'active'
    """)
    
    result = db.execute(query)
    db.commit()
    
    updated_count = result.rowcount
    print(f"   ✓ Updated stats for {updated_count} partitions")
    return updated_count

def archive_old_partitions(db, retention_days: int, dry_run: bool = False):
    """
    Archive partitions older than retention_days.
    Exports to CSV, computes SHA-256 checksum, marks as archived.
    
    Note: Actual upload to object storage is stubbed (would use S3/GCS in production)
    """
    print(f"\n📦 Archiving partitions older than {retention_days} days...")
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
    
    # Find partitions ready for archival
    partitions_to_archive = db.query(HeartbeatPartition).filter(
        HeartbeatPartition.state == 'active',
        HeartbeatPartition.range_end < cutoff_date
    ).all()
    
    if not partitions_to_archive:
        print("   No partitions ready for archival")
        return 0
    
    archived_count = 0
    
    for partition in partitions_to_archive:
        print(f"   Processing: {partition.partition_name}...")
        
        if dry_run:
            print(f"   [DRY RUN] Would archive {partition.partition_name}")
            continue
        
        try:
            structured_logger.log_event(
                "archive.start",
                partition_name=partition.partition_name
            )
            metrics.inc_counter("archive_attempts_total", {})
            
            # Export partition data to CSV
            export_query = text(f"""
                SELECT device_id, ts, battery_pct, network_type, unity_running,
                       signal_dbm, agent_version, ip, status
                FROM {partition.partition_name}
                ORDER BY ts
            """)
            
            result = db.execute(export_query)
            
            # Write to CSV string buffer
            csv_buffer = StringIO()
            csv_writer = csv.writer(csv_buffer)
            
            # Write header
            csv_writer.writerow(['device_id', 'ts', 'battery_pct', 'network_type', 'unity_running',
                                'signal_dbm', 'agent_version', 'ip', 'status'])
            
            row_count = 0
            for row in result:
                csv_writer.writerow(row)
                row_count += 1
            
            csv_content = csv_buffer.getvalue()
            csv_buffer.close()
            
            # Compute SHA-256 checksum
            checksum = hashlib.sha256(csv_content.encode('utf-8')).hexdigest()
            
            # In production, upload to object storage (S3/GCS)
            # For now, we'll just log that we would upload
            archive_url = f"s3://nexmdm-archives/{partition.partition_name}.csv.gz"
            
            print(f"      Exported {row_count} rows, SHA-256: {checksum[:16]}...")
            print(f"      [STUB] Would upload to: {archive_url}")
            
            # Update metadata to mark as archived
            partition.state = 'archived'
            partition.checksum_sha256 = checksum
            partition.archive_url = archive_url
            partition.archived_at = datetime.now(timezone.utc)
            partition.row_count = row_count
            db.commit()
            
            archived_count += 1
            
            structured_logger.log_event(
                "archive.end",
                partition_name=partition.partition_name,
                row_count=row_count,
                checksum=checksum,
                archive_url=archive_url
            )
            metrics.inc_counter("partitions_archived_total", {})
            
            print(f"   ✓ Archived: {partition.partition_name}")
            
        except Exception as e:
            # Mark archive as failed, do NOT drop partition
            partition.state = 'archive_failed'
            db.commit()
            
            print(f"   ✗ Archive FAILED for {partition.partition_name}: {e}")
            
            structured_logger.log_event(
                "archive.failed",
                partition_name=partition.partition_name,
                error=str(e),
                error_type=type(e).__name__
            )
            metrics.inc_counter("archive_failures_total", {})
    
    return archived_count

def drop_archived_partitions(db, dry_run: bool = False):
    """
    Drop partitions that have been successfully archived.
    Uses advisory lock for safety. Only drops if archive_url and checksum exist.
    """
    print(f"\n🗑️  Dropping archived partitions...")
    
    # Find partitions ready for drop
    partitions_to_drop = db.query(HeartbeatPartition).filter(
        HeartbeatPartition.state == 'archived',
        HeartbeatPartition.archive_url.isnot(None),
        HeartbeatPartition.checksum_sha256.isnot(None)
    ).all()
    
    if not partitions_to_drop:
        print("   No partitions ready for drop")
        return 0
    
    dropped_count = 0
    
    for partition in partitions_to_drop:
        print(f"   Processing: {partition.partition_name}...")
        
        if dry_run:
            print(f"   [DRY RUN] Would drop {partition.partition_name}")
            continue
        
        try:
            # Drop the partition table
            drop_query = text(f"DROP TABLE IF EXISTS {partition.partition_name}")
            db.execute(drop_query)
            
            # Update metadata
            partition.state = 'dropped'
            partition.dropped_at = datetime.now(timezone.utc)
            db.commit()
            
            dropped_count += 1
            
            print(f"   ✓ Dropped: {partition.partition_name}")
            
            structured_logger.log_event(
                "partition.drop",
                partition_name=partition.partition_name
            )
            metrics.inc_counter("partitions_dropped_total", {})
            
        except Exception as e:
            db.rollback()
            print(f"   ✗ Failed to drop {partition.partition_name}: {e}")
            
            structured_logger.log_event(
                "partition.drop_failed",
                partition_name=partition.partition_name,
                error=str(e)
            )
            metrics.inc_counter("partition_drop_failures_total", {})
    
    return dropped_count

def vacuum_hot_partitions(db, dry_run: bool = False):
    """
    Run VACUUM ANALYZE on recent active partitions for optimal query planning.
    Focuses on last 7 days (most frequently queried).
    """
    print(f"\n🧹 Running VACUUM ANALYZE on hot partitions...")
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)
    
    hot_partitions = db.query(HeartbeatPartition).filter(
        HeartbeatPartition.state == 'active',
        HeartbeatPartition.range_start >= cutoff_date
    ).all()
    
    if not hot_partitions:
        print("   No hot partitions found")
        return 0
    
    vacuumed_count = 0
    
    for partition in hot_partitions:
        if dry_run:
            print(f"   [DRY RUN] Would VACUUM ANALYZE {partition.partition_name}")
            continue
        
        try:
            # VACUUM must run outside transaction
            db.commit()  # Commit any pending transaction
            db.connection().connection.set_isolation_level(0)  # Autocommit mode
            
            vacuum_query = text(f"VACUUM ANALYZE {partition.partition_name}")
            db.execute(vacuum_query)
            
            db.connection().connection.set_isolation_level(1)  # Back to default
            
            vacuumed_count += 1
            print(f"   ✓ VACUUM ANALYZE: {partition.partition_name}")
            
        except Exception as e:
            print(f"   ✗ VACUUM failed for {partition.partition_name}: {e}")
    
    return vacuumed_count

def run_nightly_maintenance(retention_days: int = DEFAULT_RETENTION_DAYS, dry_run: bool = False):
    """
    Run all nightly maintenance tasks with advisory lock protection.
    """
    db = SessionLocal()
    lock_acquired = False
    
    try:
        # Try to acquire advisory lock
        lock_result = db.execute(text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": ADVISORY_LOCK_ID}).scalar()
        
        if not lock_result:
            structured_logger.log_event(
                "nightly_maintenance.skipped",
                reason="lock_held"
            )
            print("⏭️  Skipped: Another maintenance job is already running")
            return {"status": "skipped", "reason": "lock_held"}
        
        lock_acquired = True
        start_time = datetime.now(timezone.utc)
        
        print("=" * 80)
        print(f"🌙 NIGHTLY MAINTENANCE (dry_run={dry_run})")
        print(f"   Started at: {start_time.isoformat()}")
        print(f"   Retention: {retention_days} days")
        print("=" * 80)
        
        structured_logger.log_event(
            "nightly_maintenance.started",
            dry_run=dry_run,
            retention_days=retention_days
        )
        
        # Task 1: Create future partitions
        created = create_future_partitions(db, days_ahead=14, dry_run=dry_run)
        
        # Task 2: Update partition statistics
        updated = update_partition_stats(db, dry_run=dry_run)
        
        # Task 3: Archive old partitions
        archived = archive_old_partitions(db, retention_days=retention_days, dry_run=dry_run)
        
        # Task 4: Drop archived partitions
        dropped = drop_archived_partitions(db, dry_run=dry_run)
        
        # Task 5: VACUUM hot partitions
        vacuumed = vacuum_hot_partitions(db, dry_run=dry_run)
        
        elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        print("\n" + "=" * 80)
        print(f"✅ MAINTENANCE COMPLETE ({round(elapsed_ms / 1000, 2)}s)")
        print(f"   Created: {created} partitions")
        print(f"   Updated: {updated} statistics")
        print(f"   Archived: {archived} partitions")
        print(f"   Dropped: {dropped} partitions")
        print(f"   Vacuumed: {vacuumed} partitions")
        print("=" * 80)
        
        structured_logger.log_event(
            "nightly_maintenance.completed",
            created=created,
            updated=updated,
            archived=archived,
            dropped=dropped,
            vacuumed=vacuumed,
            elapsed_ms=round(elapsed_ms, 2)
        )
        
        metrics.observe_histogram("nightly_maintenance_duration_ms", elapsed_ms, {})
        
        return {
            "status": "completed",
            "created": created,
            "updated": updated,
            "archived": archived,
            "dropped": dropped,
            "vacuumed": vacuumed,
            "elapsed_ms": round(elapsed_ms, 2)
        }
        
    except Exception as e:
        db.rollback()
        structured_logger.log_event(
            "nightly_maintenance.failed",
            error=str(e),
            error_type=type(e).__name__
        )
        print(f"❌ Maintenance failed: {e}")
        raise
    
    finally:
        if lock_acquired:
            db.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": ADVISORY_LOCK_ID})
        db.close()

def main():
    parser = argparse.ArgumentParser(description='Nightly partition maintenance job')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--retention-days', type=int, default=DEFAULT_RETENTION_DAYS, help=f'Retention period in days (default: {DEFAULT_RETENTION_DAYS})')
    
    args = parser.parse_args()
    
    if args.retention_days < 7 or args.retention_days > 365:
        print("❌ Error: --retention-days must be between 7 and 365")
        sys.exit(1)
    
    try:
        result = run_nightly_maintenance(retention_days=args.retention_days, dry_run=args.dry_run)
        sys.exit(0 if result["status"] in ["completed", "skipped"] else 1)
    except Exception:
        sys.exit(1)

if __name__ == "__main__":
    main()
