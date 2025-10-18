import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from alert_manager import alert_manager
from observability import structured_logger

logger = logging.getLogger(__name__)

class AlertScheduler:
    def __init__(self, interval_seconds: int = 60):
        self.interval_seconds = interval_seconds
        self.task: Optional[asyncio.Task] = None
        self.running = False
    
    async def _run_evaluation_loop(self):
        while self.running:
            try:
                start_time = datetime.now(timezone.utc)
                
                await alert_manager.process_alerts()
                
                latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                
                structured_logger.log_event(
                    "alert.scheduler.tick",
                    level="INFO",
                    latency_ms=latency_ms
                )
                
                await asyncio.sleep(self.interval_seconds)
            
            except Exception as e:
                structured_logger.log_event(
                    "alert.scheduler.error",
                    level="ERROR",
                    error=str(e)
                )
                await asyncio.sleep(self.interval_seconds)
    
    async def start(self):
        if self.running:
            logger.warning("Alert scheduler already running")
            return
        
        self.running = True
        self.task = asyncio.create_task(self._run_evaluation_loop())
        
        structured_logger.log_event(
            "alert.scheduler.started",
            level="INFO",
            interval_seconds=self.interval_seconds
        )
    
    async def stop(self):
        if not self.running:
            return
        
        self.running = False
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        structured_logger.log_event(
            "alert.scheduler.stopped",
            level="INFO"
        )

alert_scheduler = AlertScheduler(interval_seconds=60)
