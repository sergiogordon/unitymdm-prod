"""
Replit App Storage Service for Python
Uses Replit's native Object Storage SDK for persistent file storage.

This replaces the previous GCS-based implementation to eliminate 401 auth errors.
All authentication is handled automatically by the Replit sidecar.
"""

import os
import uuid
import time
import json
from typing import Optional, Tuple
from replit.object_storage import Client
from replit.object_storage.errors import (
    ObjectNotFoundError as ReplitObjectNotFoundError,
    TooManyRequestsError,
    UnauthorizedError,
    ForbiddenError,
    DefaultBucketError,
    BucketNotFoundError
)


class ObjectNotFoundError(Exception):
    """Raised when an object is not found in storage"""
    pass


class StorageUnavailableError(Exception):
    """Raised when storage service is unavailable"""
    pass


class AppStorageService:
    """
    Service for interacting with Replit Object Storage.
    
    Files are stored with keys like: apk/debug/{uuid}_{filename}.apk
    Database paths use format: storage://apk/debug/{uuid}_{filename}.apk
    """
    
    MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB (supports chunked uploads)
    MAX_RETRIES = 3
    RETRY_DELAY = 0.5  # seconds
    
    def __init__(self):
        """Initialize storage client (uses default bucket)"""
        try:
            self.client = Client()
            self._logger = self._get_logger()
        except Exception as e:
            raise StorageUnavailableError(f"Failed to initialize storage client: {e}")
    
    def _get_logger(self):
        """Get structured logger"""
        try:
            from structured_logger import structured_logger  # type: ignore
            return structured_logger
        except ImportError:
            return None
    
    def _log_event(self, event: str, **kwargs):
        """Log storage event with structured logging"""
        if self._logger:
            self._logger.log_event(event, **kwargs)
        else:
            print(json.dumps({"event": event, **kwargs}))
    
    def _retry_on_error(self, operation, *args, **kwargs):
        """Retry operation on transient errors"""
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                return operation(*args, **kwargs)
            except TooManyRequestsError as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY * (2 ** attempt))
                    continue
                raise
            except (UnauthorizedError, ForbiddenError, DefaultBucketError, BucketNotFoundError) as e:
                self._log_event("storage.error.critical", error=str(e), error_type=type(e).__name__)
                raise StorageUnavailableError(f"Storage service error: {e}")
        
        if last_error:
            raise last_error
    
    def _validate_apk_file(self, filename: str, file_size: int):
        """Validate APK file before upload"""
        if not filename.lower().endswith('.apk'):
            raise ValueError(f"Invalid file type: {filename}. Must be .apk")
        
        if file_size > self.MAX_FILE_SIZE:
            size_mb = file_size / (1024 * 1024)
            max_mb = self.MAX_FILE_SIZE / (1024 * 1024)
            raise ValueError(f"File too large: {size_mb:.1f}MB. Maximum allowed: {max_mb}MB")
        
        if file_size == 0:
            raise ValueError("File is empty")
    
    def upload_file(self, file_data: bytes, filename: str, content_type: str = "application/vnd.android.package-archive") -> str:
        """
        Upload a file to Replit Object Storage.
        
        Args:
            file_data: Binary file data
            filename: Name of the file (e.g., "app.apk")
            content_type: MIME type
            
        Returns:
            Storage path in format: storage://apk/debug/{uuid}_{filename}
            
        Raises:
            ValueError: If file validation fails
            StorageUnavailableError: If storage service is unavailable
        """
        file_size = len(file_data)
        self._validate_apk_file(filename, file_size)
        
        # Generate unique key
        object_id = str(uuid.uuid4())
        storage_key = f"apk/debug/{object_id}_{filename}"
        
        self._log_event(
            "storage.upload.start",
            key=storage_key,
            file_size=file_size,
            filename=filename
        )
        
        try:
            # Upload with retry logic
            self._retry_on_error(
                self.client.upload_from_bytes,
                storage_key,
                file_data
            )
            
            # Verify upload succeeded
            if not self.client.exists(storage_key):
                raise StorageUnavailableError(f"Upload verification failed: {storage_key}")
            
            storage_path = f"storage://{storage_key}"
            
            self._log_event(
                "storage.upload.success",
                key=storage_key,
                storage_path=storage_path,
                file_size=file_size
            )
            
            return storage_path
            
        except Exception as e:
            self._log_event(
                "storage.upload.error",
                key=storage_key,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    def download_file(self, storage_path: str, use_cache: bool = True) -> Tuple[bytes, str, int]:
        """
        Download a file from Replit Object Storage.
        
        Args:
            storage_path: Path in format storage://apk/debug/{uuid}_{filename}
                         or just apk/debug/{uuid}_{filename}
            use_cache: If True, check in-memory cache first (default: True)
            
        Returns:
            Tuple of (file_data, content_type, file_size)
            
        Raises:
            ObjectNotFoundError: If file doesn't exist
            StorageUnavailableError: If storage service is unavailable
        """
        # Parse storage path
        storage_key = storage_path.replace("storage://", "")
        
        # Try cache first if enabled
        if use_cache:
            try:
                from apk_cache import get_apk_cache
                cache = get_apk_cache()
                cached = cache.get(f"storage:{storage_key}")
                if cached:
                    self._log_event(
                        "storage.download.cache_hit",
                        key=storage_key
                    )
                    return cached
            except Exception:
                pass  # Cache miss or cache not available
        
        self._log_event(
            "storage.download.start",
            key=storage_key
        )
        
        try:
            # Check if file exists
            if not self.client.exists(storage_key):
                raise ObjectNotFoundError(f"Object not found: {storage_path}")
            
            # Download with retry logic
            file_data = self._retry_on_error(
                self.client.download_as_bytes,
                storage_key
            )
            
            if file_data is None:
                raise ObjectNotFoundError(f"Downloaded data is empty: {storage_path}")
            
            file_size = len(file_data)
            content_type = "application/vnd.android.package-archive"
            
            # Cache the result for future requests
            if use_cache:
                try:
                    from apk_cache import get_apk_cache
                    cache = get_apk_cache()
                    cache.put(f"storage:{storage_key}", file_data, content_type, file_size)
                except Exception:
                    pass  # Continue even if caching fails
            
            self._log_event(
                "storage.download.success",
                key=storage_key,
                file_size=file_size
            )
            
            return file_data, content_type, file_size
            
        except ReplitObjectNotFoundError:
            self._log_event(
                "storage.download.error",
                key=storage_key,
                error="Object not found",
                error_type="ObjectNotFoundError"
            )
            raise ObjectNotFoundError(f"Object not found: {storage_path}")
        except ObjectNotFoundError:
            raise
        except Exception as e:
            self._log_event(
                "storage.download.error",
                key=storage_key,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    def delete_file(self, storage_path: str) -> bool:
        """
        Delete a file from Replit Object Storage.
        
        Args:
            storage_path: Path in format storage://apk/debug/{uuid}_{filename}
            
        Returns:
            True if deleted, False if not found
        """
        storage_key = storage_path.replace("storage://", "")
        
        try:
            if not self.client.exists(storage_key):
                self._log_event(
                    "storage.delete.not_found",
                    key=storage_key
                )
                return False
            
            self._retry_on_error(
                self.client.delete,
                storage_key,
                ignore_not_found=True
            )
            
            self._log_event(
                "storage.delete.success",
                key=storage_key
            )
            
            return True
            
        except Exception as e:
            self._log_event(
                "storage.delete.error",
                key=storage_key,
                error=str(e),
                error_type=type(e).__name__
            )
            return False
    
    def file_exists(self, storage_path: str) -> bool:
        """Check if a file exists in storage"""
        storage_key = storage_path.replace("storage://", "")
        try:
            return self.client.exists(storage_key)
        except Exception:
            return False
    
    def list_files(self, prefix: str = "apk/") -> list:
        """
        List files in storage with given prefix.
        
        Args:
            prefix: Key prefix to filter by (default: "apk/")
            
        Returns:
            List of storage keys
        """
        try:
            objects = list(self.client.list(prefix=prefix))
            return [obj.name for obj in objects]
        except Exception as e:
            self._log_event(
                "storage.list.error",
                prefix=prefix,
                error=str(e)
            )
            return []


# Singleton instance
_storage_service: Optional[AppStorageService] = None


def get_storage_service() -> AppStorageService:
    """Get or create the singleton App Storage service instance"""
    global _storage_service
    if _storage_service is None:
        _storage_service = AppStorageService()
    return _storage_service
