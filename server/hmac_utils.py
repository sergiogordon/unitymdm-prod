import hmac
import hashlib
import os

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
