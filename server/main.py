"""
FastAPI Backend for MDM System
High-performance async API optimized for 100+ concurrent devices
"""

import os
import asyncio
import hashlib
import secrets
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect,
    status, Request, Query, BackgroundTasks, Form
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_, func, desc
from sqlalchemy.orm import selectinload

from database import get_async_db, init_db, cleanup_old_events, get_pool_status
from models_async import (
    User, Device, DeviceEvent, PasswordResetToken,
    ApkVersion, ApkInstallation, BatteryWhitelist, Command, EnrollmentToken
)
from auth import verify_password, hash_password
from email_service import send_password_reset_email, send_password_reset_confirmation
from websocket_manager import WebSocketManager
import bcrypt
import hmac
import httpx
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# WebSocket manager for real-time updates
ws_manager = WebSocketManager()

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET", secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Admin Configuration for FCM commands
ADMIN_KEY = os.getenv("ADMIN_KEY", "default-admin-key-change-in-production")
# Use consistent default for development, random in production
HMAC_SECRET = os.getenv("HMAC_SECRET", "cde0c5b91a69aea8900c7bcd989098913285fcfc1f451b0b7854acafb52b3e3d")

# Security
security = HTTPBearer()

# Rate limiting tracking
rate_limit_cache: Dict[str, List[datetime]] = {}

# Metrics counters
metrics_counters: Dict[str, int] = {
    "register": 0,
    "heartbeat": 0,
    "command_send": 0,
    "action_result": 0
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    logger.info("🚀 Starting MDM Backend...")
    await init_db()
    
    # Start background tasks
    asyncio.create_task(cleanup_task())
    asyncio.create_task(monitor_devices())
    
    logger.info("✅ MDM Backend started successfully")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down MDM Backend...")
    await ws_manager.disconnect_all()
    logger.info("✅ MDM Backend shutdown complete")

app = FastAPI(
    title="MDM System API",
    description="High-performance Mobile Device Management System",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS Configuration for Frontend
# Get Replit domain from environment or allow common origins
replit_domain = os.getenv("REPLIT_DEV_DOMAIN", "")
allowed_origins = [
    "http://localhost:5000",
    "http://127.0.0.1:5000",
]

# Add Replit domain with both http and https
if replit_domain:
    allowed_origins.extend([
        f"https://{replit_domain}",
        f"http://{replit_domain}",
    ])

# For development without credentials, we could use "*" but since we use credentials,
# we need specific origins. Add any additional dev origins here.
logger.info(f"🔒 CORS allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ============== Pydantic Models ==============

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6)
    email: Optional[str] = Field(None, max_length=255)

class UserLogin(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class HeartbeatRequest(BaseModel):
    device_id: str
    alias: str
    app_version: Optional[str] = None
    timestamp_utc: datetime
    battery: Dict[str, Any]
    system: Dict[str, Any]
    memory: Dict[str, Any]
    network: Dict[str, Any]
    fcm_token: Optional[str] = None
    is_ping_response: Optional[bool] = False
    ping_request_id: Optional[str] = None

class DeviceCommand(BaseModel):
    command: str
    parameters: Optional[Dict[str, Any]] = None

class PasswordResetRequest(BaseModel):
    username_or_email: str

class PasswordResetComplete(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6)

class DeviceRegisterRequest(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=100)
    alias: str = Field(..., min_length=1, max_length=255)

class DeviceRegisterResponse(BaseModel):
    device_id: str
    device_token: str

class V1HeartbeatRequest(BaseModel):
    battery: Dict[str, Any]
    system: Dict[str, Any]
    memory: Dict[str, Any]
    network: Dict[str, Any]
    fcm_token: Optional[str] = None
    alias: Optional[str] = None
    app_version: Optional[str] = None

class AdminCommandRequest(BaseModel):
    device_ids: List[str]
    command_type: str
    parameters: Optional[Dict[str, Any]] = None
    signature: str

class ActionResultRequest(BaseModel):
    request_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

# ============== Helper Functions ==============

def create_access_token(data: dict) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "jti": secrets.token_hex(16)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_async_db)
) -> User:
    """Validate JWT token and return current user"""
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        result = await db.execute(
            select(User).where(User.username == username, User.is_active == True)
        )
        user = result.scalar_one_or_none()
        
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        
        return user
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def check_rate_limit(ip: str, endpoint: str, max_requests: int = 10, window_minutes: int = 1) -> bool:
    """Check if IP has exceeded rate limit"""
    key = f"{ip}:{endpoint}"
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=window_minutes)
    
    if key not in rate_limit_cache:
        rate_limit_cache[key] = []
    
    # Clean old entries
    rate_limit_cache[key] = [
        t for t in rate_limit_cache[key] if t > window_start
    ]
    
    if len(rate_limit_cache[key]) >= max_requests:
        return False
    
    rate_limit_cache[key].append(now)
    return True

async def verify_admin_key(request: Request) -> str:
    """Verify admin key from X-Admin header"""
    admin_key = request.headers.get("X-Admin")
    if not admin_key or admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin key")
    return admin_key

def verify_hmac_signature(payload: str, signature: str) -> bool:
    """Verify HMAC signature"""
    expected = hmac.new(
        HMAC_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

async def get_device_by_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_async_db)
) -> Device:
    """Validate device Bearer token and return device"""
    token = credentials.credentials
    token_id = hashlib.sha256(token.encode()).hexdigest()[:16]
    
    result = await db.execute(
        select(Device).where(Device.token_id == token_id)
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise HTTPException(status_code=401, detail="Invalid device token")
    
    try:
        if bcrypt.checkpw(token.encode(), device.token_hash.encode()):
            return device
    except Exception:
        pass
    
    raise HTTPException(status_code=401, detail="Invalid device token")

# ============== Background Tasks ==============

async def cleanup_task():
    """Background task to clean up old device events"""
    while True:
        try:
            await asyncio.sleep(3600)  # Run hourly
            count = await cleanup_old_events(days=2)
            logger.info(f"Cleaned up {count} old device events")
        except Exception as e:
            logger.error(f"Cleanup task error: {e}")

async def monitor_devices():
    """Monitor device status and send alerts"""
    while True:
        try:
            await asyncio.sleep(60)  # Check every minute
            
            from database import get_db_session
            async with get_db_session() as db:
                # Find devices that haven't reported in 5 minutes
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
                result = await db.execute(
                    select(Device).where(Device.last_seen < cutoff)
                )
                offline_devices = result.scalars().all()
                
                for device in offline_devices:
                    # Create alert event
                    event = DeviceEvent(
                        device_id=device.id,
                        event_type="device_offline",
                        severity="warning",
                        details={"last_seen": device.last_seen.isoformat()}
                    )
                    db.add(event)
                    
                    # Notify WebSocket clients
                    await ws_manager.broadcast({
                        "type": "device_alert",
                        "device_id": device.id,
                        "alert": "Device offline"
                    })
                
                await db.commit()
                
        except Exception as e:
            logger.error(f"Device monitor error: {e}")

# ============== V1 Device Endpoints (Production Control Loop) ==============

@app.post("/v1/enrollment-token")
async def create_enrollment_token(
    alias: str = Query(..., description="Device alias"),
    unity_package: Optional[str] = Query(None, description="Unity package to monitor"),
    admin_key: str = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_async_db),
    req: Request = None
):
    """Generate a single-use enrollment token for zero-touch provisioning"""
    enrollment_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(enrollment_token.encode()).hexdigest()
    
    enroll_token = EnrollmentToken(
        token=enrollment_token,
        token_hash=token_hash,
        alias=alias,
        unity_package=unity_package,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        created_by="admin",
        ip_address=req.client.host if req and req.client else None
    )
    
    db.add(enroll_token)
    await db.commit()
    
    logger.info(f"Enrollment token created for alias: {alias}")
    
    return {
        "enrollment_token": enrollment_token,
        "alias": alias,
        "unity_package": unity_package,
        "expires_at": enroll_token.expires_at.isoformat()
    }

@app.get("/v1/apk/download/latest")
async def download_latest_apk(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """Download latest NexMDM APK using enrollment token"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    
    enrollment_token = auth_header.replace("Bearer ", "")
    token_hash = hashlib.sha256(enrollment_token.encode()).hexdigest()
    
    result = await db.execute(
        select(EnrollmentToken).where(
            EnrollmentToken.token == enrollment_token,
            EnrollmentToken.used == False,
            EnrollmentToken.expires_at > datetime.now(timezone.utc)
        )
    )
    enroll_token = result.scalar_one_or_none()
    
    if not enroll_token:
        raise HTTPException(status_code=401, detail="Invalid or expired enrollment token")
    
    apk_result = await db.execute(
        select(ApkVersion).where(ApkVersion.is_active == True).order_by(desc(ApkVersion.version_code)).limit(1)
    )
    latest_apk = apk_result.scalar_one_or_none()
    
    if not latest_apk:
        raise HTTPException(status_code=404, detail="No APK available")
    
    if not os.path.exists(latest_apk.file_path):
        raise HTTPException(status_code=404, detail="APK file not found on server")
    
    logger.info(f"APK download requested with enrollment token for: {enroll_token.alias}")
    
    return FileResponse(
        path=latest_apk.file_path,
        media_type="application/vnd.android.package-archive",
        filename=f"nexmdm-{latest_apk.version_name}.apk",
        headers={
            "X-APK-Version": latest_apk.version_name,
            "X-APK-Version-Code": str(latest_apk.version_code)
        }
    )

@app.post("/v1/register", response_model=DeviceRegisterResponse)
async def register_device(
    request: DeviceRegisterRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """Register a new device with secure bcrypt token"""
    metrics_counters["register"] += 1
    
    result = await db.execute(
        select(Device).where(Device.id == request.device_id)
    )
    existing_device = result.scalar_one_or_none()
    
    if existing_device:
        raise HTTPException(status_code=400, detail="Device already registered")
    
    device_token = secrets.token_urlsafe(32)
    token_hash = bcrypt.hashpw(device_token.encode(), bcrypt.gensalt()).decode()
    token_id = hashlib.sha256(device_token.encode()).hexdigest()[:16]
    
    device = Device(
        id=request.device_id,
        alias=request.alias,
        token_hash=token_hash,
        token_id=token_id,
        last_seen=datetime.now(timezone.utc)
    )
    
    db.add(device)
    await db.commit()
    
    logger.info(f"Device registered: {request.device_id}, alias: {request.alias}")
    
    return DeviceRegisterResponse(
        device_id=request.device_id,
        device_token=device_token
    )

@app.post("/v1/enroll")
async def enroll_device_with_token(
    device_id: str = Query(...),
    request: Request = None,
    db: AsyncSession = Depends(get_async_db)
):
    """Enroll device using enrollment token (idempotent)"""
    auth_header = request.headers.get("Authorization") if request else None
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer enrollment token required")
    
    enrollment_token = auth_header.replace("Bearer ", "")
    
    result = await db.execute(
        select(EnrollmentToken).where(
            EnrollmentToken.token == enrollment_token,
            EnrollmentToken.expires_at > datetime.now(timezone.utc)
        )
    )
    enroll_token = result.scalar_one_or_none()
    
    if not enroll_token:
        raise HTTPException(status_code=401, detail="Invalid or expired enrollment token")
    
    if enroll_token.used and enroll_token.device_id != device_id:
        raise HTTPException(status_code=400, detail="Enrollment token already used for different device")
    
    device_result = await db.execute(
        select(Device).where(Device.id == device_id)
    )
    existing_device = device_result.scalar_one_or_none()
    
    if existing_device:
        logger.info(f"Device {device_id} already enrolled, returning existing token (idempotent)")
        return {
            "device_id": existing_device.id,
            "device_token": "*** Token already issued, check device configuration ***",
            "alias": existing_device.alias,
            "message": "Device already enrolled"
        }
    
    device_token = secrets.token_urlsafe(32)
    token_hash = bcrypt.hashpw(device_token.encode(), bcrypt.gensalt()).decode()
    token_id = hashlib.sha256(device_token.encode()).hexdigest()[:16]
    
    device = Device(
        id=device_id,
        alias=enroll_token.alias,
        token_hash=token_hash,
        token_id=token_id,
        last_seen=datetime.now(timezone.utc),
        monitored_package=enroll_token.unity_package or "org.zwanoo.android.speedtest"
    )
    
    db.add(device)
    
    enroll_token.used = True
    enroll_token.used_at = datetime.now(timezone.utc)
    enroll_token.device_id = device_id
    
    await db.commit()
    
    logger.info(f"Device enrolled via token: {device_id}, alias: {enroll_token.alias}")
    
    return {
        "device_id": device.id,
        "device_token": device_token,
        "alias": device.alias,
        "unity_package": enroll_token.unity_package
    }

@app.post("/v1/heartbeat")
async def v1_heartbeat(
    request: V1HeartbeatRequest,
    device: Device = Depends(get_device_by_token),
    db: AsyncSession = Depends(get_async_db)
):
    """Process device heartbeat with Bearer token auth - optimized for <150ms p95"""
    start_time = datetime.now(timezone.utc)
    metrics_counters["heartbeat"] += 1
    
    device.last_seen = datetime.now(timezone.utc)
    device.fcm_token = request.fcm_token or device.fcm_token
    
    if request.alias:
        device.alias = request.alias
    if request.app_version:
        device.app_version = request.app_version
    
    device.battery_level = request.battery.get("pct")
    device.battery_charging = request.battery.get("charging")
    device.android_version = request.system.get("android_version")
    device.sdk_int = request.system.get("sdk_int")
    device.model = request.system.get("model")
    device.manufacturer = request.system.get("manufacturer")
    device.memory_available_mb = request.memory.get("avail_ram_mb")
    device.memory_total_mb = request.memory.get("total_ram_mb")
    device.network_type = request.network.get("transport")
    
    device.last_status = {
        "battery": request.battery,
        "system": request.system,
        "memory": request.memory,
        "network": request.network
    }
    
    await db.commit()
    
    elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
    logger.debug(f"Heartbeat processed for {device.id} in {elapsed_ms:.2f}ms")
    
    return {
        "ok": True,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "latency_ms": elapsed_ms
    }

@app.post("/v1/action-result")
async def action_result(
    request: ActionResultRequest,
    device: Device = Depends(get_device_by_token),
    db: AsyncSession = Depends(get_async_db)
):
    """Receive action result from device"""
    metrics_counters["action_result"] += 1
    
    result_obj = await db.execute(
        select(Command).where(Command.request_id == request.request_id)
    )
    command = result_obj.scalar_one_or_none()
    
    if not command:
        raise HTTPException(status_code=404, detail="Command not found")
    
    command.status = request.status
    command.result = request.result
    command.error_message = request.error_message
    command.completed_at = datetime.now(timezone.utc)
    
    await db.commit()
    
    logger.info(f"Action result received: request_id={request.request_id}, status={request.status}")
    
    return {"ok": True}

# ============== Admin Endpoints ==============

@app.post("/admin/command")
async def admin_send_command(
    request: AdminCommandRequest,
    req: Request,
    admin_key: str = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_async_db)
):
    """Send FCM command to devices with HMAC validation"""
    metrics_counters["command_send"] += 1
    
    client_ip = req.client.host if req.client else "unknown"
    if not check_rate_limit(client_ip, "admin_command", max_requests=100, window_minutes=1):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    # HMAC payload uses JSON serialization for consistent validation
    import json
    params_str = json.dumps(request.parameters, sort_keys=True) if request.parameters else ""
    payload = f"{','.join(request.device_ids)}:{request.command_type}:{params_str}"
    if not verify_hmac_signature(payload, request.signature):
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")
    
    from fcm_v1 import get_access_token, get_firebase_project_id, build_fcm_v1_url
    
    request_id = secrets.token_hex(16)
    results = []
    
    try:
        fcm_token = get_access_token()
        project_id = get_firebase_project_id()
        fcm_url = build_fcm_v1_url(project_id)
    except Exception as e:
        logger.error(f"FCM setup error: {e}")
        raise HTTPException(status_code=500, detail=f"FCM configuration error: {str(e)}")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for device_id in request.device_ids:
            result_obj = await db.execute(
                select(Device).where(Device.id == device_id)
            )
            device = result_obj.scalar_one_or_none()
            
            if not device or not device.fcm_token:
                results.append({"device_id": device_id, "status": "error", "message": "No FCM token"})
                continue
            
            command = Command(
                request_id=f"{request_id}_{device_id}",
                device_id=device_id,
                command_type=request.command_type,
                parameters=request.parameters,
                initiated_by="admin"
            )
            db.add(command)
            
            fcm_message = {
                "message": {
                    "token": device.fcm_token,
                    "data": {
                        "command": request.command_type,
                        "request_id": command.request_id,
                        "parameters": str(request.parameters or {})
                    },
                    "android": {
                        "priority": "high"
                    }
                }
            }
            
            try:
                fcm_response = await client.post(
                    fcm_url,
                    headers={
                        "Authorization": f"Bearer {fcm_token}",
                        "Content-Type": "application/json"
                    },
                    json=fcm_message
                )
                
                command.fcm_sent_at = datetime.now(timezone.utc)
                command.fcm_response_code = fcm_response.status_code
                command.fcm_response_body = fcm_response.json() if fcm_response.text else {}
                
                if fcm_response.status_code == 200:
                    command.status = "sent"
                    results.append({
                        "device_id": device_id,
                        "status": "sent",
                        "request_id": command.request_id
                    })
                    logger.info(f"FCM sent to {device_id}, request_id={command.request_id}")
                else:
                    command.status = "failed"
                    error_detail = command.fcm_response_body.get("error", {}) if command.fcm_response_body else {}
                    results.append({
                        "device_id": device_id,
                        "status": "error",
                        "message": f"FCM error: {fcm_response.status_code}",
                        "request_id": command.request_id
                    })
                    logger.error(f"FCM failed for {device_id}: {fcm_response.status_code}, detail={error_detail}")
                    
            except Exception as e:
                command.status = "failed"
                command.error_message = str(e)
                results.append({
                    "device_id": device_id,
                    "status": "error",
                    "message": str(e)
                })
                logger.error(f"FCM send error for {device_id}: {e}")
    
    await db.commit()
    
    return {
        "ok": True,
        "request_id": request_id,
        "results": results
    }

# ============== Authentication Endpoints ==============

@app.post("/api/auth/register", response_model=TokenResponse)
async def register(
    request: UserRegister,
    db: AsyncSession = Depends(get_async_db)
):
    """Register a new user"""
    # Check if username exists
    result = await db.execute(
        select(User).where(User.username == request.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")
    
    # Check if email exists
    if request.email:
        result = await db.execute(
            select(User).where(User.email == request.email)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already exists")
    
    # Create user
    user = User(
        username=request.username,
        email=request.email,
        password_hash=hash_password(request.password)
    )
    
    db.add(user)
    await db.commit()
    
    # Create token
    token = create_access_token(data={"sub": user.username})
    return TokenResponse(access_token=token)

@app.post("/api/auth/login", response_model=TokenResponse)
async def login(
    request: UserLogin,
    db: AsyncSession = Depends(get_async_db)
):
    """Login user and return JWT token"""
    result = await db.execute(
        select(User).where(User.username == request.username, User.is_active == True)
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token(data={"sub": user.username})
    return TokenResponse(access_token=token)

@app.post("/api/auth/forgot-password")
async def forgot_password(
    request: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """Request password reset"""
    # Rate limiting
    client_ip = req.client.host if req.client else "unknown"
    if not check_rate_limit(client_ip, "forgot_password", max_requests=3, window_minutes=60):
        raise HTTPException(status_code=429, detail="Too many requests")
    
    # Find user by username or email
    query = select(User).where(
        or_(
            User.username == request.username_or_email,
            User.email == request.username_or_email
        )
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if user and user.email:
        # Generate reset token
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        reset_token = PasswordResetToken(
            user_id=user.id,
            token=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ip_address=client_ip
        )
        
        db.add(reset_token)
        await db.commit()
        
        # Send email in background
        background_tasks.add_task(
            send_password_reset_email, 
            user.email, 
            user.username, 
            token
        )
    
    # Always return success to prevent user enumeration
    return {"ok": True, "message": "If the account exists, a reset email has been sent"}

@app.post("/api/auth/reset-password")
async def reset_password(
    request: PasswordResetComplete,
    db: AsyncSession = Depends(get_async_db)
):
    """Complete password reset"""
    token_hash = hashlib.sha256(request.token.encode()).hexdigest()
    
    # Find valid token
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token == token_hash,
            PasswordResetToken.expires_at > datetime.now(timezone.utc),
            PasswordResetToken.used == False
        ).options(selectinload(PasswordResetToken.user))
    )
    reset_token = result.scalar_one_or_none()
    
    if not reset_token:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    
    # Update password
    user = reset_token.user
    user.password_hash = hash_password(request.new_password)
    
    # Mark token as used
    reset_token.used = True
    reset_token.used_at = datetime.now(timezone.utc)
    
    await db.commit()
    
    # Send confirmation email
    if user.email:
        await send_password_reset_confirmation(user.email, user.username)
    
    # Return new login token
    token = create_access_token(data={"sub": user.username})
    return TokenResponse(access_token=token)

# ============== Device Management Endpoints ==============

@app.post("/api/devices/heartbeat")
async def device_heartbeat(
    request: HeartbeatRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """Process device heartbeat - optimized for high concurrency"""
    device_id = request.device_id
    
    # Get or create device
    result = await db.execute(
        select(Device).where(Device.id == device_id)
    )
    device = result.scalar_one_or_none()
    
    if not device:
        # Auto-register new device
        device = Device(
            id=device_id,
            alias=request.alias,
            token_hash=hashlib.sha256(device_id.encode()).hexdigest(),
            app_version=request.app_version
        )
        db.add(device)
    
    # Update device status
    device.last_seen = datetime.now(timezone.utc)
    device.alias = request.alias
    device.app_version = request.app_version
    device.fcm_token = request.fcm_token
    
    # Update battery info
    device.battery_level = request.battery.get("pct")
    device.battery_charging = request.battery.get("charging")
    
    # Update system info
    device.android_version = request.system.get("android_version")
    device.sdk_int = request.system.get("sdk_int")
    device.model = request.system.get("model")
    device.manufacturer = request.system.get("manufacturer")
    device.build_id = request.system.get("build_id")
    
    # Update memory info
    device.memory_available_mb = request.memory.get("avail_ram_mb")
    device.memory_total_mb = request.memory.get("total_ram_mb")
    
    # Update network info
    device.network_type = request.network.get("transport")
    
    # Store full status
    device.last_status = request.model_dump()
    
    # Handle ping response
    if request.is_ping_response and request.ping_request_id:
        device.last_ping_response = datetime.now(timezone.utc)
        device.ping_request_id = request.ping_request_id
    
    # Create heartbeat event
    event = DeviceEvent(
        device_id=device_id,
        event_type="heartbeat",
        severity="info",
        details={
            "battery": request.battery,
            "memory": request.memory,
            "network": request.network
        }
    )
    db.add(event)
    
    await db.commit()
    
    # Broadcast update via WebSocket
    await ws_manager.broadcast({
        "type": "device_update",
        "device_id": device_id,
        "data": {
            "last_seen": device.last_seen.isoformat(),
            "battery_level": device.battery_level,
            "status": "online"
        }
    })
    
    # Check for pending commands
    commands = []
    if device.auto_relaunch_enabled:
        commands.append({
            "type": "check_app_status",
            "package": device.monitored_package
        })
    
    return {
        "ok": True,
        "commands": commands,
        "server_time": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/devices")
async def list_devices(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """List all devices with pagination and search"""
    query = select(Device)
    
    if search:
        query = query.where(
            or_(
                Device.alias.ilike(f"%{search}%"),
                Device.id.ilike(f"%{search}%"),
                Device.model.ilike(f"%{search}%")
            )
        )
    
    # Count total
    count_query = select(func.count()).select_from(Device)
    if search:
        count_query = count_query.where(
            or_(
                Device.alias.ilike(f"%{search}%"),
                Device.id.ilike(f"%{search}%"),
                Device.model.ilike(f"%{search}%")
            )
        )
    
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Get paginated results
    query = query.order_by(desc(Device.last_seen))
    query = query.offset((page - 1) * limit).limit(limit)
    
    result = await db.execute(query)
    devices = result.scalars().all()
    
    # Format response
    devices_data = []
    for device in devices:
        # Calculate status
        time_diff = datetime.now(timezone.utc) - device.last_seen
        if time_diff.total_seconds() < 300:  # 5 minutes
            status = "online"
        elif time_diff.total_seconds() < 900:  # 15 minutes
            status = "warning"
        else:
            status = "offline"
        
        devices_data.append({
            "id": device.id,
            "alias": device.alias,
            "app_version": device.app_version,
            "last_seen": device.last_seen.isoformat(),
            "created_at": device.created_at.isoformat(),
            "status": status,
            "battery_level": device.battery_level,
            "battery_charging": device.battery_charging,
            "model": device.model,
            "manufacturer": device.manufacturer,
            "android_version": device.android_version,
            "network_type": device.network_type,
            "memory_available_mb": device.memory_available_mb,
            "auto_relaunch_enabled": device.auto_relaunch_enabled
        })
    
    return {
        "devices": devices_data,
        "total": total,
        "page": page,
        "pages": ((total or 0) + limit - 1) // limit
    }

@app.get("/api/devices/{device_id}")
async def get_device(
    device_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get detailed device information"""
    result = await db.execute(
        select(Device).where(Device.id == device_id)
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # Get recent events
    events_result = await db.execute(
        select(DeviceEvent)
        .where(DeviceEvent.device_id == device_id)
        .order_by(desc(DeviceEvent.timestamp))
        .limit(100)
    )
    events = events_result.scalars().all()
    
    return {
        "device": {
            "id": device.id,
            "alias": device.alias,
            "app_version": device.app_version,
            "last_seen": device.last_seen.isoformat(),
            "created_at": device.created_at.isoformat(),
            "last_status": device.last_status,
            "battery_level": device.battery_level,
            "battery_charging": device.battery_charging,
            "model": device.model,
            "manufacturer": device.manufacturer,
            "android_version": device.android_version,
            "sdk_int": device.sdk_int,
            "build_id": device.build_id,
            "network_type": device.network_type,
            "memory_available_mb": device.memory_available_mb,
            "memory_total_mb": device.memory_total_mb,
            "auto_relaunch_enabled": device.auto_relaunch_enabled,
            "monitored_package": device.monitored_package,
            "monitored_app_name": device.monitored_app_name
        },
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "timestamp": e.timestamp.isoformat(),
                "severity": e.severity,
                "details": e.details
            }
            for e in events
        ]
    }

@app.post("/api/devices/{device_id}/command")
async def send_device_command(
    device_id: str,
    command: DeviceCommand,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Send command to device"""
    result = await db.execute(
        select(Device).where(Device.id == device_id)
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # Create command event
    event = DeviceEvent(
        device_id=device_id,
        event_type="command",
        severity="info",
        details={
            "command": command.command,
            "parameters": command.parameters,
            "initiated_by": current_user.username
        }
    )
    db.add(event)
    await db.commit()
    
    # Send via WebSocket if device is connected
    await ws_manager.send_to_device(device_id, {
        "type": "command",
        "command": command.command,
        "parameters": command.parameters
    })
    
    return {"ok": True, "message": "Command sent"}

@app.delete("/api/devices/{device_id}")
async def delete_device(
    device_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a device and all its data"""
    result = await db.execute(
        select(Device).where(Device.id == device_id)
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    await db.delete(device)
    await db.commit()
    
    return {"ok": True, "message": "Device deleted"}

# ============== WebSocket Endpoint ==============

@app.websocket("/ws/{device_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    device_id: str,
    token: str = Query(None)
):
    """WebSocket connection for real-time device communication"""
    # Validate token
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    await ws_manager.connect(device_id, websocket)
    
    try:
        while True:
            # Receive messages from device
            data = await websocket.receive_json()
            
            # Process message based on type
            if data.get("type") == "heartbeat":
                await websocket.send_json({"type": "ack"})
            elif data.get("type") == "event":
                # Store event in database
                from database import get_db_session
                async with get_db_session() as db:
                    event = DeviceEvent(
                        device_id=device_id,
                        event_type=data.get("event_type", "unknown"),
                        severity=data.get("severity", "info"),
                        details=data.get("details")
                    )
                    db.add(event)
                    await db.commit()
                
                # Broadcast to other clients
                await ws_manager.broadcast({
                    "type": "device_event",
                    "device_id": device_id,
                    "event": data
                })
    except WebSocketDisconnect:
        ws_manager.disconnect(device_id)
        logger.info(f"Device {device_id} disconnected from WebSocket")

# ============== System Status Endpoints ==============

@app.get("/api/metrics")
async def get_metrics():
    """Get basic metrics counters"""
    return {
        "ok": True,
        "metrics": metrics_counters,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/system/status")
async def system_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get system status and statistics"""
    # Device statistics
    total_devices = await db.execute(select(func.count()).select_from(Device))
    online_cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    online_devices = await db.execute(
        select(func.count()).select_from(Device).where(Device.last_seen > online_cutoff)
    )
    
    # Event statistics
    total_events = await db.execute(select(func.count()).select_from(DeviceEvent))
    today_events = await db.execute(
        select(func.count()).select_from(DeviceEvent).where(
            DeviceEvent.timestamp > datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        )
    )
    
    # User statistics
    total_users = await db.execute(select(func.count()).select_from(User))
    
    return {
        "status": "healthy",
        "statistics": {
            "devices": {
                "total": total_devices.scalar(),
                "online": online_devices.scalar()
            },
            "events": {
                "total": total_events.scalar(),
                "today": today_events.scalar()
            },
            "users": {
                "total": total_users.scalar()
            }
        },
        "database": {
            "pool": get_pool_status()
        },
        "websocket": {
            "connections": len(ws_manager.active_connections)
        }
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

# ============== Root Redirect ==============

@app.get("/")
async def root():
    """Redirect to API documentation"""
    return {"message": "MDM Backend API", "docs": "/api/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )