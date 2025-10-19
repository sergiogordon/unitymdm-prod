"""
Background tasks for NexMDM - runs purge jobs and cleanup operations.
"""
import asyncio
from datetime import datetime, timezone
from purge_jobs import purge_manager
from bulk_delete import cleanup_expired_selections
from models import SessionLocal
from observability import structured_logger

class BackgroundTaskManager:
    """Manages background tasks for the MDM system."""
    
    def __init__(self):
        self._running = False
        self._purge_task = None
        self._cleanup_task = None
    
    async def start(self):
        """Start all background tasks."""
        if self._running:
            return
        
        self._running = True
        structured_logger.log_event("background_tasks.started")
        
        # Start purge jobs processor
        self._purge_task = asyncio.create_task(self._run_purge_worker())
        
        # Start selection cleanup task
        self._cleanup_task = asyncio.create_task(self._run_cleanup_worker())
    
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


# Global instance
background_tasks = BackgroundTaskManager()
