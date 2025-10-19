"""
Rate limiter for protecting admin endpoints.
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Tuple
from collections import defaultdict
import threading

class RateLimiter:
    """
    Simple in-memory rate limiter with sliding window.
    For production, use Redis or similar distributed cache.
    """
    
    def __init__(self):
        self._requests: Dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()
    
    def check_rate_limit(
        self,
        key: str,
        max_requests: int = 10,
        window_minutes: int = 1
    ) -> Tuple[bool, int]:
        """
        Check if request is within rate limit.
        
        Args:
            key: Unique identifier (e.g., admin_user, IP address)
            max_requests: Maximum requests allowed in window
            window_minutes: Time window in minutes
        
        Returns:
            Tuple of (is_allowed, remaining_requests)
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=window_minutes)
        
        with self._lock:
            # Clean up old requests
            self._requests[key] = [
                ts for ts in self._requests[key]
                if ts > window_start
            ]
            
            # Check if under limit
            current_count = len(self._requests[key])
            
            if current_count >= max_requests:
                return False, 0
            
            # Record this request
            self._requests[key].append(now)
            
            remaining = max_requests - current_count - 1
            return True, remaining
    
    def reset(self, key: str):
        """Reset rate limit for a specific key."""
        with self._lock:
            if key in self._requests:
                del self._requests[key]
    
    def cleanup_old_entries(self, max_age_minutes: int = 60):
        """
        Clean up old entries to prevent memory leak.
        Should be called periodically.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        
        with self._lock:
            keys_to_delete = []
            
            for key, timestamps in self._requests.items():
                # Filter out old timestamps
                self._requests[key] = [ts for ts in timestamps if ts > cutoff]
                
                # If no timestamps left, mark for deletion
                if not self._requests[key]:
                    keys_to_delete.append(key)
            
            # Delete empty entries
            for key in keys_to_delete:
                del self._requests[key]


# Global rate limiter instance
rate_limiter = RateLimiter()
