import bcrypt
import secrets
import jwt
import os
import hashlib
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Security, Depends, Cookie, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from models import Device, User, Session as SessionModel, get_db
from typing import Optional

security = HTTPBearer(auto_error=False)
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
    credentials: HTTPAuthorizationCredentials | None = Security(security),
    db: Session = Depends(get_db)
) -> Device:
    if not credentials:
        raise HTTPException(status_code=403, detail="Missing authorization header")
    token = credentials.credentials
    
    # Compute token_id for fast lookup
    token_id = compute_token_id(token)
    
    # First try fast lookup by token_id (for new devices)
    device = db.query(Device).filter(Device.token_id == token_id).first()
    if device and verify_token(token, device.token_hash):
        return device
    
    # Fallback: check devices without token_id (legacy devices)
    # This will only run for old devices until they're migrated
    legacy_devices = db.query(Device).filter(Device.token_id.is_(None)).all()
    for device in legacy_devices:
        if verify_token(token, device.token_hash):
            # Migrate legacy device by setting token_id
            device.token_id = token_id
            db.commit()
            return device
    
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
    
    # DEBUG: Log what we received
    print(f"[AUTH DEBUG] Authorization header: {authorization[:50] if authorization else 'None'}...")
    print(f"[AUTH DEBUG] Credentials: {credentials}")
    
    # Try Bearer token from security scheme first
    if credentials:
        token = credentials.credentials
        print(f"[AUTH DEBUG] Token from credentials: {token[:20] if token else 'None'}...")
    # Fallback to manual Authorization header parsing
    elif authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        print(f"[AUTH DEBUG] Token from header: {token[:20] if token else 'None'}...")
    
    if not token:
        print("[AUTH DEBUG] No token found - raising 401")
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Verify and decode JWT token
    try:
        payload = verify_jwt_token(token)
        print(f"[AUTH DEBUG] Token verified successfully, payload: {payload}")
    except Exception as e:
        print(f"[AUTH DEBUG] Token verification failed: {e}")
        raise
        
    user_id = payload.get("user_id")
    
    if not user_id:
        print("[AUTH DEBUG] No user_id in payload - raising 401")
        raise HTTPException(status_code=401, detail="Invalid token payload")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        print(f"[AUTH DEBUG] User {user_id} not found - raising 401")
        raise HTTPException(status_code=401, detail="User not found")
    
    print(f"[AUTH DEBUG] Authentication successful for user: {user.username}")
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

async def verify_enrollment_token(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
    required_scope: str = "register",
    db: Session = Depends(get_db)
):
    """
    Verify enrollment token with complete security validation:
    - Token exists and matches hash
    - Not expired
    - Not exhausted (uses_consumed < uses_allowed)
    - Correct scope
    - Status is active
    """
    from models import EnrollmentToken
    
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    raw_token = credentials.credentials
    token_id = compute_token_id(raw_token)
    
    # Look up token by token_id (fast indexed lookup)
    enrollment_token = db.query(EnrollmentToken).filter(
        EnrollmentToken.token_id == token_id
    ).first()
    
    if not enrollment_token:
        raise HTTPException(status_code=401, detail="Invalid enrollment token")
    
    # Verify token hash matches
    if not verify_token(raw_token, enrollment_token.token_hash):
        raise HTTPException(status_code=401, detail="Invalid enrollment token")
    
    # Check token status
    if enrollment_token.status == 'revoked':
        raise HTTPException(status_code=401, detail="Token has been revoked")
    
    if enrollment_token.status == 'exhausted':
        raise HTTPException(status_code=401, detail="Token has been exhausted")
    
    # Check expiry (BUG FIX #1)
    now = datetime.now(timezone.utc)
    if enrollment_token.expires_at:
        # Handle timezone-naive datetimes from database
        expires_at = enrollment_token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            raise HTTPException(status_code=401, detail="Token has expired")
    
    # Check usage limits (BUG FIX #2)
    if enrollment_token.uses_consumed >= enrollment_token.uses_allowed:
        # Mark as exhausted
        enrollment_token.status = 'exhausted'
        db.commit()
        raise HTTPException(status_code=401, detail="Token has been exhausted")
    
    # Check scope (BUG FIX #3)
    if enrollment_token.scope != required_scope:
        raise HTTPException(
            status_code=401, 
            detail=f"Invalid token scope. Required: {required_scope}, got: {enrollment_token.scope}"
        )
    
    return enrollment_token
