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
