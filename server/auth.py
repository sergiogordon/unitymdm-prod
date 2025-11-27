import bcrypt
import secrets
import jwt
import os
import hashlib
import time
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Security, Depends, Cookie, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Request as FastAPIRequest
from fastapi import Request
from sqlalchemy.orm import Session
from models import Device, User, Session as SessionModel, get_db
from typing import Optional
from observability import structured_logger, metrics
from collections import defaultdict
import time

security = HTTPBearer(auto_error=False)

# Rate limiter for invalid token attempts (prevent log flooding)
class InvalidTokenRateLimiter:
    def __init__(self, max_attempts=5, window_seconds=60):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.attempts = defaultdict(list)
    
    def is_blocked(self, token_id_prefix: str) -> bool:
        """Check if this token prefix should be blocked due to too many failures"""
        now = time.time()
        window_start = now - self.window_seconds
        
        # Clean old attempts
        self.attempts[token_id_prefix] = [
            attempt_time for attempt_time in self.attempts[token_id_prefix] 
            if attempt_time > window_start
        ]
        
        # Check if over limit
        if len(self.attempts[token_id_prefix]) >= self.max_attempts:
            return True
        
        # Record this attempt
        self.attempts[token_id_prefix].append(now)
        return False

invalid_token_limiter = InvalidTokenRateLimiter(max_attempts=5, window_seconds=60)

# IP-based rate limiter to block flooding clients entirely
class IPRateLimiter:
    def __init__(self, max_failures=20, window_seconds=300, block_duration=3600):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.block_duration = block_duration  # How long to block after hitting limit
        self.failures = defaultdict(list)
        self.blocked_until = {}  # IP -> timestamp when block expires
    
    def record_failure(self, ip: str):
        now = time.time()
        window_start = now - self.window_seconds
        
        # Clean old failures
        self.failures[ip] = [t for t in self.failures[ip] if t > window_start]
        self.failures[ip].append(now)
        
        # Check if over limit
        if len(self.failures[ip]) >= self.max_failures:
            self.blocked_until[ip] = now + self.block_duration
            return True
        return False
    
    def is_blocked(self, ip: str) -> bool:
        if ip in self.blocked_until:
            if time.time() < self.blocked_until[ip]:
                return True
            else:
                del self.blocked_until[ip]
        return False

ip_rate_limiter = IPRateLimiter(max_failures=20, window_seconds=300, block_duration=3600)

SESSION_DURATION_DAYS = 7
JWT_SECRET = os.getenv("SESSION_SECRET", "default-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 168  # 7 days

def hash_token(token: str) -> str:
    return bcrypt.hashpw(token.encode(), bcrypt.gensalt()).decode()

def verify_token(token: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(token.encode(), hashed.encode())
    except (ValueError, AttributeError):
        # Invalid salt or malformed hash - token doesn't match
        return False

def compute_token_id(token: str) -> str:
    """Compute SHA256 hash of token for fast database lookups"""
    return hashlib.sha256(token.encode()).hexdigest()

def generate_device_token() -> str:
    return secrets.token_urlsafe(32)

async def verify_device_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(security),
    db: Session = Depends(get_db)
) -> Device:
    auth_start_time = time.time()
    
    # Extract client IP address
    client_ip = None
    if request.client:
        client_ip = request.client.host
    elif request.headers.get("x-forwarded-for"):
        # Handle proxy/load balancer forwarded IP
        client_ip = request.headers.get("x-forwarded-for").split(",")[0].strip()
    elif request.headers.get("x-real-ip"):
        client_ip = request.headers.get("x-real-ip")
    else:
        client_ip = "unknown"
    
    # Check if IP is blocked due to excessive failures
    if ip_rate_limiter.is_blocked(client_ip):
        metrics.inc_counter("device_auth_failures_total", {"reason": "ip_blocked"})
        raise HTTPException(
            status_code=429, 
            detail="Too many authentication failures. Try again later.",
            headers={"Retry-After": "3600"}
        )
    
    if not credentials:
        ip_rate_limiter.record_failure(client_ip)
        metrics.inc_counter("device_auth_failures_total", {"reason": "missing_header"})
        structured_logger.log_event(
            "auth.device_token.failed",
            level="WARN",
            reason="missing_header",
            client_ip=client_ip
        )
        raise HTTPException(status_code=403, detail="Missing authorization header")
    
    token = credentials.credentials
    token_length = len(token) if token else 0
    
    # Compute token_id for fast lookup
    token_id = compute_token_id(token)
    token_id_prefix = token_id[:8] if len(token_id) >= 8 else token_id
    
    # First try fast lookup by token_id (for new devices)
    device = db.query(Device).filter(Device.token_id == token_id).first()
    device_found_by_token_id = device is not None
    
    if device:
        # Device found by token_id, verify the token hash
        token_verified = verify_token(token, device.token_hash)
        if token_verified:
            auth_latency_ms = (time.time() - auth_start_time) * 1000
            metrics.observe_histogram("device_auth_latency_ms", auth_latency_ms, {})
            structured_logger.log_event(
                "auth.device_token.success",
                level="INFO",
                device_id=device.id,
                token_id_prefix=token_id_prefix,
                lookup_method="token_id",
                latency_ms=auth_latency_ms
            )
            return device
        else:
            # Token ID matched but hash verification failed - data integrity issue
            # Don't try legacy lookup since token_id is unique and already matched
            metrics.inc_counter("device_auth_failures_total", {"reason": "token_mismatch"})
            structured_logger.log_event(
                "auth.device_token.failed",
                level="WARN",
                reason="token_mismatch",
                token_id_prefix=token_id_prefix,
                device_id=device.id,
                device_alias=device.alias,
                client_ip=client_ip,
                device_found_by_token_id=True
            )
            raise HTTPException(status_code=401, detail="Invalid device token")
    
    # Device not found by token_id, try legacy lookup
    legacy_devices = db.query(Device).filter(Device.token_id.is_(None)).all()
    legacy_count = len(legacy_devices)
    
    for legacy_device in legacy_devices:
        if verify_token(token, legacy_device.token_hash):
            # Migrate legacy device by setting token_id
            legacy_device.token_id = token_id
            db.commit()
            auth_latency_ms = (time.time() - auth_start_time) * 1000
            metrics.observe_histogram("device_auth_latency_ms", auth_latency_ms, {})
            structured_logger.log_event(
                "auth.device_token.success",
                level="INFO",
                device_id=legacy_device.id,
                token_id_prefix=token_id_prefix,
                lookup_method="legacy_migrated",
                latency_ms=auth_latency_ms
            )
            return legacy_device
    
    # No device found matching the token
    # Try to match by IP address from recent heartbeats
    matched_device_id = None
    matched_device_alias = None
    last_heartbeat_ts = None
    
    if client_ip and client_ip != "unknown":
        from models import DeviceHeartbeat
        recent_hb = db.query(DeviceHeartbeat).filter(
            DeviceHeartbeat.ip == client_ip
        ).order_by(DeviceHeartbeat.ts.desc()).first()
        
        if recent_hb:
            device_by_ip = db.query(Device).filter(Device.id == recent_hb.device_id).first()
            if device_by_ip:
                matched_device_id = device_by_ip.id
                matched_device_alias = device_by_ip.alias
                last_heartbeat_ts = recent_hb.ts.isoformat() if recent_hb.ts else None
    
    # Record IP failure for rate limiting
    ip_rate_limiter.record_failure(client_ip)
    
    metrics.inc_counter("device_auth_failures_total", {"reason": "token_not_found"})
    
    # Rate limit logging for repeated invalid token attempts
    if not invalid_token_limiter.is_blocked(token_id_prefix):
        log_data = {
            "level": "WARN",
            "reason": "token_not_found",
            "token_id_prefix": token_id_prefix,
            "client_ip": client_ip,
            "device_found_by_token_id": False,
            "legacy_devices_checked": legacy_count,
            "token_length": token_length,
            "user_agent": request.headers.get("user-agent", "unknown")  # Add user-agent to identify source
        }
        
        if matched_device_id:
            log_data["matched_device_id"] = matched_device_id
            log_data["matched_device_alias"] = matched_device_alias
            log_data["last_heartbeat_ts"] = last_heartbeat_ts
        
        structured_logger.log_event("auth.device_token.failed", **log_data)
    else:
        # Log once when rate limit kicks in
        structured_logger.log_event(
            "auth.device_token.rate_limited",
            level="INFO",
            token_id_prefix=token_id_prefix,
            client_ip=client_ip,
            message="Suppressing repeated invalid token logs"
        )
    
    raise HTTPException(status_code=401, detail="Invalid device token")

def verify_admin_key(admin_key: str) -> bool:
    import os
    expected_key = os.getenv("ADMIN_KEY", "admin")
    return admin_key == expected_key

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_jwt_token(user_id: int, username: str) -> str:
    """Create a JWT token for the user"""
    expires_at = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": expires_at,
        "iat": datetime.now(timezone.utc)
    }
    
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token

def verify_jwt_token(token: str) -> dict:
    """Verify and decode a JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def create_session(user_id: int, db: Session) -> str:
    """Legacy function - kept for compatibility"""
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DURATION_DAYS)
    
    session = SessionModel(
        id=session_id,
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
        expires_at=expires_at
    )
    
    db.add(session)
    db.commit()
    
    return session_id

async def get_current_user(
    authorization: Optional[str] = Header(None),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    db: Session = Depends(get_db)
) -> User:
    """Get current user from JWT token in Authorization header"""
    token = None
    
    # Try Bearer token from security scheme first
    if credentials:
        token = credentials.credentials
    # Fallback to manual Authorization header parsing
    elif authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Verify and decode JWT token
    try:
        payload = verify_jwt_token(token)
    except Exception as e:
        raise
        
    user_id = payload.get("user_id")
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user

async def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get current user from JWT token (optional - returns None if not authenticated)"""
    token = None
    
    # Try Bearer token from security scheme first
    if credentials:
        token = credentials.credentials
    # Fallback to manual Authorization header parsing
    elif authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    
    if not token:
        return None
    
    try:
        # Verify and decode JWT token
        payload = verify_jwt_token(token)
        user_id = payload.get("user_id")
        
        if not user_id:
            return None
        
        user = db.query(User).filter(User.id == user_id).first()
        return user
    except:
        return None

async def verify_admin_key_header(
    x_admin_key: str | None = Header(None),
    db: Session = Depends(get_db)
):
    """
    Verify admin key from X-Admin-Key header for device registration
    """
    import os
    
    if not x_admin_key:
        raise HTTPException(status_code=401, detail="Missing X-Admin-Key header")
    
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key or x_admin_key != admin_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")
    
    return {"admin_key_verified": True}
