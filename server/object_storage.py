"""
Replit App Storage Service for Python
Adapted from blueprint:javascript_object_storage

This module provides App Storage integration for storing and retrieving files
in Google Cloud Storage via Replit's built-in object storage.
"""

import os
import requests
from google.cloud import storage
from google.auth.credentials import Credentials
from datetime import datetime, timedelta
from typing import Optional
import uuid


class ReplitStorageCredentials(Credentials):
    """
    Custom credentials for Replit App Storage
    Uses Replit sidecar endpoint for authentication
    """
    REPLIT_SIDECAR_ENDPOINT = "http://127.0.0.1:1106"
    
    def __init__(self):
        super().__init__()
        self.token = None
        self.expiry = None
    
    def refresh(self, request):
        """Fetch a fresh token from the Replit sidecar"""
        try:
            response = requests.get(f"{self.REPLIT_SIDECAR_ENDPOINT}/credential")
            response.raise_for_status()
            data = response.json()
            self.token = data.get("access_token")
            # Set expiry to 1 hour from now
            self.expiry = datetime.utcnow() + timedelta(hours=1)
        except Exception as e:
            raise Exception(f"Failed to get Replit storage credentials: {e}")
    
    @property
    def valid(self):
        """Check if token is valid"""
        return self.token is not None and (
            self.expiry is None or datetime.utcnow() < self.expiry
        )


class ObjectNotFoundError(Exception):
    """Raised when an object is not found in storage"""
    pass


class AppStorageService:
    """
    Service for interacting with Replit App Storage (Google Cloud Storage backed)
    """
    
    REPLIT_SIDECAR_ENDPOINT = "http://127.0.0.1:1106"
    
    def __init__(self):
        """Initialize storage client with Replit credentials"""
        credentials = ReplitStorageCredentials()
        credentials.refresh(None)
        self.client = storage.Client(
            credentials=credentials,
            project=""  # Empty project ID as per blueprint
        )
    
    def get_private_object_dir(self) -> str:
        """
        Get the private object directory from environment variables.
        Format: /bucket_name/path/to/dir
        """
        dir_path = os.getenv("PRIVATE_OBJECT_DIR", "")
        if not dir_path:
            raise ValueError(
                "PRIVATE_OBJECT_DIR not set. Create a bucket in 'App Storage' "
                "tool and set PRIVATE_OBJECT_DIR env var (format: /bucket_name/apks)"
            )
        return dir_path
    
    def _parse_object_path(self, path: str) -> tuple[str, str]:
        """
        Parse object path into bucket name and object name.
        
        Args:
            path: Path in format /bucket_name/object/path
            
        Returns:
            Tuple of (bucket_name, object_name)
        """
        if not path.startswith("/"):
            path = f"/{path}"
        
        parts = path.split("/")
        if len(parts) < 3:
            raise ValueError("Invalid path: must contain at least a bucket name")
        
        bucket_name = parts[1]
        object_name = "/".join(parts[2:])
        
        return bucket_name, object_name
    
    def upload_file(self, file_data: bytes, filename: str, content_type: str = "application/octet-stream") -> str:
        """
        Upload a file to App Storage.
        
        Args:
            file_data: Binary file data
            filename: Name of the file
            content_type: MIME type
            
        Returns:
            Full object path in format /bucket_name/path/to/file
        """
        private_dir = self.get_private_object_dir()
        object_id = str(uuid.uuid4())
        full_path = f"{private_dir}/{object_id}_{filename}"
        
        bucket_name, object_name = self._parse_object_path(full_path)
        bucket = self.client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        
        blob.upload_from_string(
            file_data,
            content_type=content_type
        )
        
        return full_path
    
    def download_file(self, object_path: str) -> tuple[bytes, str, int]:
        """
        Download a file from App Storage.
        
        Args:
            object_path: Full path to object in format /bucket_name/path/to/file
            
        Returns:
            Tuple of (file_data, content_type, file_size)
        """
        bucket_name, object_name = self._parse_object_path(object_path)
        bucket = self.client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        
        if not blob.exists():
            raise ObjectNotFoundError(f"Object not found: {object_path}")
        
        # Get metadata
        blob.reload()
        content_type = blob.content_type or "application/octet-stream"
        file_size = blob.size or 0
        
        # Download data
        file_data = blob.download_as_bytes()
        
        return file_data, content_type, file_size
    
    def delete_file(self, object_path: str) -> bool:
        """
        Delete a file from App Storage.
        
        Args:
            object_path: Full path to object
            
        Returns:
            True if deleted, False if not found
        """
        bucket_name, object_name = self._parse_object_path(object_path)
        bucket = self.client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        
        if not blob.exists():
            return False
        
        blob.delete()
        return True
    
    def file_exists(self, object_path: str) -> bool:
        """Check if a file exists in storage"""
        try:
            bucket_name, object_name = self._parse_object_path(object_path)
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(object_name)
            return blob.exists()
        except Exception:
            return False
    
    def get_signed_upload_url(self, filename: str, ttl_seconds: int = 900) -> tuple[str, str]:
        """
        Generate a presigned URL for direct upload from client.
        
        Args:
            filename: Name of the file to upload
            ttl_seconds: URL validity period in seconds (default 15 min)
            
        Returns:
            Tuple of (signed_url, object_path)
        """
        private_dir = self.get_private_object_dir()
        object_id = str(uuid.uuid4())
        full_path = f"{private_dir}/{object_id}_{filename}"
        
        bucket_name, object_name = self._parse_object_path(full_path)
        
        # Use Replit sidecar to sign URL
        try:
            request_data = {
                "bucket_name": bucket_name,
                "object_name": object_name,
                "method": "PUT",
                "expires_at": (datetime.utcnow() + timedelta(seconds=ttl_seconds)).isoformat() + "Z"
            }
            
            response = requests.post(
                f"{self.REPLIT_SIDECAR_ENDPOINT}/object-storage/signed-object-url",
                json=request_data
            )
            response.raise_for_status()
            
            signed_url = response.json().get("signed_url")
            return signed_url, full_path
            
        except Exception as e:
            raise Exception(f"Failed to sign upload URL: {e}")


# Singleton instance
_storage_service: Optional[AppStorageService] = None


def get_storage_service() -> AppStorageService:
    """Get or create the singleton App Storage service instance"""
    global _storage_service
    if _storage_service is None:
        _storage_service = AppStorageService()
    return _storage_service
