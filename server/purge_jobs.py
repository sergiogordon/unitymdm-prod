"""
Background job system for purging historical device data.
Handles partition-aware deletion with advisory locks.
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict, Any
import json
import time
import uuid
from observability import structured_logger, metrics
from models import SessionLocal

class PurgeJobManager:
    """
    Manages background purge jobs for deleted devices.
    Uses PostgreSQL advisory locks to prevent concurrent execution.
    """
    
    # Advisory lock ID for purge jobs (arbitrary constant)
    PURGE_LOCK_ID = 987654321
    
    def __init__(self):
        self.jobs_queue: List[Dict[str, Any]] = []
    
    def enqueue_purge(self, device_ids: List[str], request_id: str, purge_history: bool = True):
        """
        Enqueue device purge job for background processing.
        
        Args:
            device_ids: List of device IDs to purge
            request_id: Request ID for tracking
            purge_history: Whether to purge historical data
        """
        job = {
            "job_id": str(uuid.uuid4()),
            "request_id": request_id,
            "device_ids": device_ids,
            "purge_history": purge_history,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending"
        }
        
        self.jobs_queue.append(job)
        
        structured_logger.log_event(
            "device.purge.enqueued",
            job_id=job["job_id"],
            request_id=request_id,
            device_count=len(device_ids),
            purge_history=purge_history
        )
        
        metrics.inc_counter("purge_jobs_enqueued_total")
        
        return job["job_id"]
    
    def acquire_lock(self, db: Session) -> bool:
        """
        Try to acquire advisory lock for purge operations.
        Returns True if lock acquired, False otherwise.
        """
        try:
            result = db.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": self.PURGE_LOCK_ID}
            )
            acquired = result.scalar()
            return bool(acquired)
        except Exception as e:
            structured_logger.log_event(
                "purge.lock.error",
                level="ERROR",
                error=str(e)
            )
            return False
    
    def release_lock(self, db: Session):
        """Release advisory lock."""
        try:
            db.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": self.PURGE_LOCK_ID}
            )
        except Exception as e:
            structured_logger.log_event(
                "purge.lock.release_error",
                level="ERROR",
                error=str(e)
            )
    
    def purge_device_history(self, db: Session, device_id: str) -> Dict[str, int]:
        """
        Purge historical data for a single device from partitioned tables.
        
        Returns dict with row counts deleted per table.
        """
        start_time = time.time()
        deleted_counts = {}
        
        try:
            # Delete from device_heartbeats (partitioned)
            hb_result = db.execute(
                text("DELETE FROM device_heartbeats WHERE device_id = :device_id"),
                {"device_id": device_id}
            )
            # SQLAlchemy Result.rowcount is an int attribute
            deleted_counts["device_heartbeats"] = getattr(hb_result, 'rowcount', 0)
            
            # Delete from fcm_dispatches
            fcm_result = db.execute(
                text("DELETE FROM fcm_dispatches WHERE device_id = :device_id"),
                {"device_id": device_id}
            )
            deleted_counts["fcm_dispatches"] = getattr(fcm_result, 'rowcount', 0)
            
            # Delete from apk_download_events (if token_id matches device)
            # Note: apk_download_events uses token_id, not device_id directly
            # We'll skip this for now unless there's a mapping
            
            db.commit()
            
            duration_ms = (time.time() - start_time) * 1000
            
            structured_logger.log_event(
                "device.purge.completed",
                device_id=device_id,
                deleted_counts=deleted_counts,
                duration_ms=int(duration_ms)
            )
            
            # Update metrics
            for table, count in deleted_counts.items():
                metrics.inc_counter("purge_rows_deleted_total", {"table": table}, count)
            
            return deleted_counts
            
        except Exception as e:
            db.rollback()
            structured_logger.log_event(
                "device.purge.failed",
                level="ERROR",
                device_id=device_id,
                error=str(e)
            )
            raise
    
    def process_purge_jobs(self, max_jobs: int = 10, max_duration_seconds: int = 60):
        """
        Process pending purge jobs with time budget.
        
        Args:
            max_jobs: Maximum number of jobs to process in this run
            max_duration_seconds: Maximum time to spend processing
        """
        if not self.jobs_queue:
            return
        
        db = SessionLocal()
        start_time = time.time()
        
        try:
            # Try to acquire lock
            if not self.acquire_lock(db):
                structured_logger.log_event(
                    "purge.skipped",
                    reason="lock_held_by_another_process"
                )
                return
            
            processed = 0
            
            while self.jobs_queue and processed < max_jobs:
                # Check time budget
                elapsed = time.time() - start_time
                if elapsed > max_duration_seconds:
                    structured_logger.log_event(
                        "purge.time_budget_exceeded",
                        processed=processed,
                        elapsed_seconds=int(elapsed)
                    )
                    break
                
                job = self.jobs_queue.pop(0)
                
                try:
                    if job["purge_history"]:
                        total_deleted = {}
                        
                        for device_id in job["device_ids"]:
                            deleted = self.purge_device_history(db, device_id)
                            
                            # Aggregate counts
                            for table, count in deleted.items():
                                total_deleted[table] = total_deleted.get(table, 0) + count
                        
                        structured_logger.log_event(
                            "device.purge.batch_completed",
                            job_id=job["job_id"],
                            request_id=job["request_id"],
                            device_count=len(job["device_ids"]),
                            total_deleted=total_deleted
                        )
                    
                    processed += 1
                    metrics.inc_counter("purge_jobs_completed_total")
                    
                except Exception as e:
                    structured_logger.log_event(
                        "purge.job_failed",
                        level="ERROR",
                        job_id=job["job_id"],
                        error=str(e)
                    )
                    # Re-queue for retry (optional)
                    # self.jobs_queue.append(job)
            
            structured_logger.log_event(
                "purge.batch_processed",
                processed=processed,
                remaining=len(self.jobs_queue),
                duration_seconds=int(time.time() - start_time)
            )
            
        finally:
            self.release_lock(db)
            db.close()
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status."""
        return {
            "pending_jobs": len(self.jobs_queue),
            "jobs": self.jobs_queue[:10]  # First 10 for preview
        }


# Global instance
purge_manager = PurgeJobManager()
