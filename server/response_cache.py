"""
Simple in-memory response cache with TTL for frequently accessed endpoints.
"""
from typing import Any, Optional, Dict
from datetime import datetime, timezone, timedelta
import threading
import hashlib
import json

class ResponseCache:
    """
    Thread-safe in-memory cache with TTL support.
    """
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
    
    def get(self, key: str, ttl_seconds: int) -> Optional[Any]:
        """
        Get cached value if it exists and hasn't expired.
        
        Args:
            key: Cache key
            ttl_seconds: Time-to-live in seconds
            
        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            if key not in self._cache:
                return None
            
            entry = self._cache[key]
            expires_at = entry['expires_at']
            
            if datetime.now(timezone.utc) > expires_at:
                # Expired, remove it
                del self._cache[key]
                return None
            
            return entry['value']
    
    def set(self, key: str, value: Any, ttl_seconds: int, path: Optional[str] = None):
        """
        Store value in cache with TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time-to-live in seconds
            path: Request path for pattern-based invalidation (e.g., "/v1/devices")
        """
        with self._lock:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            self._cache[key] = {
                'value': value,
                'expires_at': expires_at,
                'path': path  # Store path for pattern-based invalidation
            }
    
    def invalidate(self, pattern: Optional[str] = None):
        """
        Invalidate cache entries.
        
        Args:
            pattern: If provided, invalidate entries matching the path pattern.
                     Matches entries where stored path starts with pattern.
                     Also invalidates entries without path metadata (legacy entries).
                     If None, invalidate all entries.
        """
        with self._lock:
            if pattern is None:
                self._cache.clear()
            else:
                # Match by stored path metadata instead of key prefix
                # This works with MD5-hashed keys
                # Also invalidate entries without path metadata (legacy entries created before path was added)
                # to avoid serving stale data from entries that can't be matched by pattern
                keys_to_remove = [
                    k for k, entry in self._cache.items()
                    if not entry.get('path') or entry['path'].startswith(pattern)
                ]
                for key in keys_to_remove:
                    del self._cache[key]
    
    def cleanup_expired(self):
        """Remove all expired entries from cache."""
        now = datetime.now(timezone.utc)
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if now > entry['expires_at']
            ]
            for key in expired_keys:
                del self._cache[key]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            self.cleanup_expired()
            return {
                'size': len(self._cache),
                'keys': list(self._cache.keys())
            }

# Global cache instance
response_cache = ResponseCache()

def make_cache_key(path: str, query_params: Optional[Dict[str, Any]] = None) -> str:
    """
    Generate a cache key from path and query parameters.
    
    Args:
        path: Request path
        query_params: Query parameters dict
        
    Returns:
        Cache key string
    """
    if query_params:
        # Sort params for consistent keys
        sorted_params = sorted(query_params.items())
        params_str = json.dumps(sorted_params, sort_keys=True)
        key_str = f"{path}?{params_str}"
    else:
        key_str = path
    
    # Hash for shorter keys
    return hashlib.md5(key_str.encode()).hexdigest()

