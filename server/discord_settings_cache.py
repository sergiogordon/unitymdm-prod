"""
Cache for Discord settings.
Reduces database load for frequent reads during alert evaluation.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from models import DiscordSettings
from observability import structured_logger

class DiscordSettingsCache:
    def __init__(self):
        self._cache: Optional[bool] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds = 300
    
    def is_enabled(self, db: Session) -> bool:
        """
        Check if Discord alerts are enabled with caching.
        Returns True if no settings exist (default enabled).
        """
        now = datetime.now(timezone.utc)
        
        if self._cache is not None and self._cache_timestamp is not None:
            age_seconds = (now - self._cache_timestamp).total_seconds()
            if age_seconds < self._cache_ttl_seconds:
                return self._cache
        
        settings_record = db.query(DiscordSettings).first()
        
        if settings_record:
            enabled = settings_record.enabled
        else:
            enabled = True  # Default to enabled
        
        self._cache = enabled
        self._cache_timestamp = now
        
        structured_logger.log_event(
            "discord_settings.cache_refresh",
            enabled=enabled,
            has_custom_settings=settings_record is not None
        )
        
        return enabled
    
    def invalidate(self):
        """Invalidate the cache (call after updates)."""
        self._cache = None
        self._cache_timestamp = None
        structured_logger.log_event("discord_settings.cache_invalidated")

discord_settings_cache = DiscordSettingsCache()

