"""
Background tasks for NexMDM - runs purge jobs and cleanup operations.
"""
import asyncio
import time
from datetime import datetime, timezone
from purge_jobs import purge_manager
from bulk_delete import cleanup_expired_selections
from models import SessionLocal
from observability import structured_logger
import queue
from typing import Dict, Any
import threading

class AsyncEventQueue:
    """Thread-safe queue for async event logging to avoid blocking the main request thread."""
    
    def __init__(self, max_size: int = 10000):
        self._queue = queue.Queue(maxsize=max_size)
        self._stats = {"enqueued": 0, "processed": 0, "errors": 0}
        self._lock = threading.Lock()
    
    def enqueue(self, device_id: str, event_type: str, details: Dict[str, Any]):
        """Add an event to the queue for async processing."""
        try:
            self._queue.put_nowait({
                "device_id": device_id,
                "event_type": event_type,
                "details": details,
                "timestamp": datetime.now(timezone.utc)
            })
            with self._lock:
                self._stats["enqueued"] += 1
        except queue.Full:
            with self._lock:
                self._stats["errors"] += 1
            structured_logger.log_event(
                "event_queue.full",
                level="WARN",
                device_id=device_id,
                event_type=event_type
            )
    
    def get_batch(self, max_batch_size: int = 50, timeout: float = 0.1):
        """Get a batch of events from the queue."""
        events = []
        deadline = time.time() + timeout
        
        while len(events) < max_batch_size and time.time() < deadline:
            try:
                event = self._queue.get_nowait()
                events.append(event)
            except queue.Empty:
                break
        
        return events
    
    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        with self._lock:
            return self._stats.copy()

class BackgroundTaskManager:
    """Manages background tasks for the MDM system."""
    
    def __init__(self):
        self._running = False
        self._purge_task = None
        self._cleanup_task = None
        self._event_logger_task = None
        self.event_queue = AsyncEventQueue()
    
    async def start(self):
        """Start all background tasks."""
        if self._running:
            return
        
        self._running = True
        structured_logger.log_event("background_tasks.started")
        
        # TEMPORARILY DISABLED ALL WORKERS FOR DEBUGGING
        # Start purge jobs processor
        # self._purge_task = asyncio.create_task(self._run_purge_worker())
        
        # Start selection cleanup task
        # self._cleanup_task = asyncio.create_task(self._run_cleanup_worker())
        
        # Start event logging worker
        # self._event_logger_task = asyncio.create_task(self._run_event_logger_worker())
    
    async def stop(self):
        """Stop all background tasks."""
        if not self._running:
            return
        
        self._running = False
        
        # Cancel tasks
        if self._purge_task:
            self._purge_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._event_logger_task:
            self._event_logger_task.cancel()
        
        structured_logger.log_event("background_tasks.stopped")
    
    async def _run_purge_worker(self):
        """
        Background worker that processes purge jobs every 30 seconds.
        Purges historical data for deleted devices.
        """
        while self._running:
            try:
                # Process pending purge jobs
                purge_manager.process_purge_jobs(
                    max_jobs=10,
                    max_duration_seconds=60
                )
                
                # Wait 30 seconds before next run
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                structured_logger.log_event(
                    "purge_worker.error",
                    level="ERROR",
                    error=str(e)
                )
                # Wait a bit before retrying on error
                await asyncio.sleep(60)
    
    async def _run_cleanup_worker(self):
        """
        Background worker that cleans up expired selections every 10 minutes.
        """
        while self._running:
            try:
                db = SessionLocal()
                try:
                    # Clean up expired device selections
                    deleted = cleanup_expired_selections(db)
                    
                    if deleted > 0:
                        structured_logger.log_event(
                            "selection_cleanup.completed",
                            deleted=deleted
                        )
                finally:
                    db.close()
                
                # Wait 10 minutes before next run
                await asyncio.sleep(600)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                structured_logger.log_event(
                    "cleanup_worker.error",
                    level="ERROR",
                    error=str(e)
                )
                # Wait a bit before retrying on error
                await asyncio.sleep(600)
    
    async def _run_event_logger_worker(self):
        """
        Background worker that processes event logging queue.
        Batches events for efficient database writes.
        """
        while self._running:
            try:
                # Get a batch of events
                events = self.event_queue.get_batch(max_batch_size=50, timeout=0.5)
                
                if not events:
                    # No events, wait a bit
                    await asyncio.sleep(0.1)
                    continue
                
                # Process batch in database
                db = SessionLocal()
                try:
                    from models import DeviceEvent
                    import json
                    
                    # Bulk insert for efficiency
                    device_events = [
                        DeviceEvent(
                            device_id=event["device_id"],
                            event_type=event["event_type"],
                            timestamp=event["timestamp"],
                            details=json.dumps(event["details"]) if event["details"] else None
                        )
                        for event in events
                    ]
                    
                    db.bulk_save_objects(device_events)
                    db.commit()
                    
                    with self.event_queue._lock:
                        self.event_queue._stats["processed"] += len(events)
                    
                    if len(events) > 10:
                        structured_logger.log_event(
                            "event_logger.batch_processed",
                            count=len(events)
                        )
                
                finally:
                    db.close()
                
                # Small delay to prevent CPU spinning
                await asyncio.sleep(0.05)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                structured_logger.log_event(
                    "event_logger.error",
                    level="ERROR",
                    error=str(e)
                )
                with self.event_queue._lock:
                    self.event_queue._stats["errors"] += 1
                # Wait a bit before retrying on error
                await asyncio.sleep(1)


# Global instance
background_tasks = BackgroundTaskManager()
