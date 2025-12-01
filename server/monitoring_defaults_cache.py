"""
Cache for monitoring defaults settings.
Reduces database load for frequent reads during device registration and heartbeat evaluation.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from models import MonitoringDefaults
from observability import structured_logger

class MonitoringDefaultsCache:
    def __init__(self):
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds = 300
    
    def get_defaults(self, db: Session) -> Dict[str, Any]:
        """
        Get monitoring defaults with caching.
        Returns built-in defaults if no custom settings exist.
        """
        now = datetime.now(timezone.utc)
        
        if self._cache is not None and self._cache_timestamp is not None:
            age_seconds = (now - self._cache_timestamp).total_seconds()
            if age_seconds < self._cache_ttl_seconds:
                structured_logger.log_event(
                    "monitoring_defaults.cache_hit",
                    age_seconds=age_seconds
                )
                return self._cache.copy()
        
        defaults_record = db.query(MonitoringDefaults).first()
        
        if defaults_record:
            defaults = {
                "enabled": defaults_record.enabled,
                "package": defaults_record.package,
                "alias": defaults_record.alias,
                "threshold_min": defaults_record.threshold_min,
                "updated_at": defaults_record.updated_at.isoformat() + "Z"
            }
        else:
            defaults = {
                "enabled": True,
                "package": "io.unitynodes.unityapp",
                "alias": "Unity App",
                "threshold_min": 10,
                "updated_at": None
            }
        
        self._cache = defaults
        self._cache_timestamp = now
        
        structured_logger.log_event(
            "monitoring_defaults.cache_refresh",
            has_custom_settings=defaults_record is not None
        )
        
        return defaults.copy()
    
    def invalidate(self):
        """Invalidate the cache (call after updates)."""
        self._cache = None
        self._cache_timestamp = None
        structured_logger.log_event("monitoring_defaults.cache_invalidated")

monitoring_defaults_cache = MonitoringDefaultsCache()
