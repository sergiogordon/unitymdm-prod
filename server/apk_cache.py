"""
In-memory APK cache for frequently accessed builds.
Reduces object storage roundtrips and speeds up concurrent downloads.
"""

import time
from typing import Optional, Tuple
from dataclasses import dataclass
from threading import Lock


@dataclass
class CacheEntry:
    """Cached APK file data"""
    file_data: bytes
    content_type: str
    file_size: int
    cached_at: float
    access_count: int = 0
    last_accessed: float = 0.0


class ApkCache:
    """
    Thread-safe in-memory cache for APK files.
    
    Features:
    - LRU eviction when size limit reached
    - TTL expiration (default 1 hour)
    - Access tracking for metrics
    """
    
    def __init__(self, max_size_mb: int = 200, ttl_seconds: int = 3600):
        """
        Initialize cache.
        
        Args:
            max_size_mb: Maximum cache size in MB (default 200MB)
            ttl_seconds: Time-to-live for cache entries (default 1 hour)
        """
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.ttl_seconds = ttl_seconds
        self.cache: dict[str, CacheEntry] = {}
        self.current_size = 0
        self.lock = Lock()
        
        # Metrics
        self.hits = 0
        self.misses = 0
        self.evictions = 0
    
    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if cache entry has expired"""
        return (time.time() - entry.cached_at) > self.ttl_seconds
    
    def _evict_lru(self, required_space: int):
        """Evict least recently used entries until we have required space"""
        if not self.cache:
            return
        
        # Sort by last accessed time (oldest first)
        sorted_keys = sorted(
            self.cache.keys(),
            key=lambda k: self.cache[k].last_accessed
        )
        
        for key in sorted_keys:
            if self.current_size + required_space <= self.max_size_bytes:
                break
            
            entry = self.cache[key]
            self.current_size -= entry.file_size
            del self.cache[key]
            self.evictions += 1
    
    def get(self, cache_key: str) -> Optional[Tuple[bytes, str, int]]:
        """
        Get APK from cache.
        
        Args:
            cache_key: Unique identifier (e.g., f"apk:{apk_id}")
            
        Returns:
            Tuple of (file_data, content_type, file_size) or None if not cached
        """
        with self.lock:
            entry = self.cache.get(cache_key)
            
            if entry is None:
                self.misses += 1
                return None
            
            # Check if expired
            if self._is_expired(entry):
                self.current_size -= entry.file_size
                del self.cache[cache_key]
                self.misses += 1
                return None
            
            # Update access tracking
            entry.access_count += 1
            entry.last_accessed = time.time()
            self.hits += 1
            
            return (entry.file_data, entry.content_type, entry.file_size)
    
    def put(self, cache_key: str, file_data: bytes, content_type: str, file_size: int):
        """
        Store APK in cache.
        
        Args:
            cache_key: Unique identifier (e.g., f"apk:{apk_id}")
            file_data: Binary APK data
            content_type: MIME type
            file_size: Size in bytes
        """
        # Don't cache if file is too large for cache
        if file_size > self.max_size_bytes:
            return
        
        with self.lock:
            # Evict old entries if needed
            if cache_key not in self.cache:
                self._evict_lru(file_size)
            else:
                # Update existing entry - adjust current size
                old_entry = self.cache[cache_key]
                self.current_size -= old_entry.file_size
            
            # Add new entry
            now = time.time()
            entry = CacheEntry(
                file_data=file_data,
                content_type=content_type,
                file_size=file_size,
                cached_at=now,
                access_count=0,
                last_accessed=now
            )
            
            self.cache[cache_key] = entry
            self.current_size += file_size
    
    def invalidate(self, cache_key: str):
        """Remove entry from cache"""
        with self.lock:
            entry = self.cache.get(cache_key)
            if entry:
                self.current_size -= entry.file_size
                del self.cache[cache_key]
    
    def clear(self):
        """Clear all cache entries"""
        with self.lock:
            self.cache.clear()
            self.current_size = 0
            self.evictions = 0
    
    def get_stats(self) -> dict:
        """Get cache statistics"""
        with self.lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                "size_bytes": self.current_size,
                "size_mb": round(self.current_size / (1024 * 1024), 2),
                "max_size_mb": self.max_size_bytes / (1024 * 1024),
                "entries": len(self.cache),
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate_percent": round(hit_rate, 2),
                "evictions": self.evictions,
                "ttl_seconds": self.ttl_seconds
            }


# Global cache instance
_apk_cache: Optional[ApkCache] = None


def get_apk_cache() -> ApkCache:
    """Get or create the singleton APK cache instance"""
    global _apk_cache
    if _apk_cache is None:
        # Default: 200MB cache, 1 hour TTL
        _apk_cache = ApkCache(max_size_mb=200, ttl_seconds=3600)
    return _apk_cache
