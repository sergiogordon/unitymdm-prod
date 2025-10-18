"""
Authentication utilities for MDM System
"""

import bcrypt
import secrets
import hashlib
from typing import Optional

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash
    """
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )

def generate_secure_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure random token
    """
    return secrets.token_urlsafe(length)

def hash_token(token: str) -> str:
    """
    Create SHA256 hash of a token for secure storage
    """
    return hashlib.sha256(token.encode()).hexdigest()

def generate_device_token(device_id: str, secret: Optional[str] = None) -> str:
    """
    Generate a device authentication token
    """
    if not secret:
        secret = secrets.token_hex(16)
    
    combined = f"{device_id}:{secret}"
    return hashlib.sha256(combined.encode()).hexdigest()

def verify_admin_key(provided_key: str, admin_key: str) -> bool:
    """
    Verify admin API key
    """
    return secrets.compare_digest(provided_key, admin_key)

def generate_api_key() -> str:
    """
    Generate an API key for service authentication
    """
    return f"mdm_{secrets.token_hex(32)}"