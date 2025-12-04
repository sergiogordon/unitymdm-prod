import hmac
import hashlib
import os
import json

def compute_hmac_signature(request_id: str, device_id: str, action: str, timestamp: str) -> str:
    """
    Compute HMAC-SHA256 signature for FCM command validation.
    
    Args:
        request_id: Unique request identifier
        device_id: Target device ID
        action: Command action (ping, launch_app, etc.)
        timestamp: ISO8601 timestamp
    
    Returns:
        Hex-encoded HMAC signature
    """
    hmac_secret = os.getenv("HMAC_SECRET", "")
    if not hmac_secret:
        raise ValueError("HMAC_SECRET environment variable not set")
    
    message = f"{request_id}|{device_id}|{action}|{timestamp}"
    
    signature = hmac.new(
        hmac_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return signature

def compute_hmac_signature_with_payload(
    request_id: str, 
    device_id: str, 
    action: str, 
    timestamp: str,
    payload_fields: dict = None
) -> str:
    """
    Compute HMAC-SHA256 signature for FCM command validation including critical payload fields.
    This prevents tampering with command parameters (e.g., changing type from launch_app to clear_app_data).
    
    Args:
        request_id: Unique request identifier
        device_id: Target device ID
        action: Command action (remote_exec_fcm, remote_exec_shell, etc.)
        timestamp: ISO8601 timestamp
        payload_fields: Dictionary of critical payload fields to include in HMAC (e.g., {"type": "launch_app", "package_name": "com.example.app"})
    
    Returns:
        Hex-encoded HMAC signature
    """
    hmac_secret = os.getenv("HMAC_SECRET", "")
    if not hmac_secret:
        raise ValueError("HMAC_SECRET environment variable not set")
    
    # Build base message
    message = f"{request_id}|{device_id}|{action}|{timestamp}"
    
    # Append payload fields in sorted order for deterministic hashing
    if payload_fields:
        # Sort keys for deterministic ordering
        sorted_fields = sorted(payload_fields.items())
        # Create canonical JSON-like representation (without JSON overhead)
        payload_str = "|".join(f"{k}:{v}" for k, v in sorted_fields if v)  # Only include non-empty values
        if payload_str:
            message += f"|{payload_str}"
    
    signature = hmac.new(
        hmac_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return signature

def verify_hmac_signature(
    request_id: str,
    device_id: str,
    action: str,
    timestamp: str,
    provided_signature: str
) -> bool:
    """
    Verify HMAC signature matches expected value.
    
    Returns:
        True if signature is valid, False otherwise
    """
    try:
        expected_signature = compute_hmac_signature(request_id, device_id, action, timestamp)
        return hmac.compare_digest(expected_signature, provided_signature)
    except Exception:
        return False
