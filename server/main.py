from fastapi import FastAPI, Depends, HTTPException, Header, Request, Response, Cookie, WebSocket, WebSocketDisconnect, Query, File, UploadFile, Form, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from datetime import datetime, timezone, timedelta
from typing import Optional, Set, List
from collections import defaultdict
import json
import asyncio
import os
import time
import hashlib

from models import Device, User, Session as SessionModel, DeviceEvent, ApkVersion, ApkInstallation, BatteryWhitelist, PasswordResetToken, DeviceLastStatus, DeviceSelection, ApkDownloadEvent, MonitoringDefaults, AutoRelaunchDefaults, DiscordSettings, BloatwarePackage, WiFiSettings, DeviceCommand, DeviceMetric, BulkCommand, CommandResult, RemoteExec, RemoteExecResult, get_db, init_db, SessionLocal
from schemas import (
    HeartbeatPayload, HeartbeatResponse, DeviceSummary, RegisterResponse,
    UserRegisterRequest, UserLoginRequest, UpdateDeviceAliasRequest, DeployApkRequest,
    UpdateDeviceSettingsRequest, ActionResultRequest, UpdateAutoRelaunchDefaultsRequest,
    UpdateDiscordSettingsRequest
)
from auth import (
    verify_device_token, hash_token, verify_token, generate_device_token, verify_admin_key,
    hash_password, verify_password, create_session, get_current_user, get_current_user_optional,
    compute_token_id, verify_admin_key_header, security
)
from alerts import alert_scheduler, alert_manager
from background_tasks import background_tasks
from fcm_v1 import get_access_token, get_firebase_project_id, build_fcm_v1_url
from apk_manager import save_apk_file, get_apk_download_url
from object_storage import get_storage_service, ObjectNotFoundError
from email_service import email_service
from observability import structured_logger, metrics, request_id_var
from hmac_utils import compute_hmac_signature
import uuid
import fast_reads
import bulk_delete
from purge_jobs import purge_manager
from rate_limiter import rate_limiter
from monitoring_defaults_cache import monitoring_defaults_cache
from discord_settings_cache import discord_settings_cache
from apk_download_service import download_apk_optimized, get_cache_statistics
from config import config
from response_cache import response_cache, make_cache_key
from alert_config import alert_config

# Feature flags for gradual rollout
READ_FROM_LAST_STATUS = os.getenv("READ_FROM_LAST_STATUS", "false").lower() == "true"

# Helper function to ensure datetime is timezone-aware (assume UTC for naive datetimes)
def ensure_utc(dt: Optional[datetime]) -> datetime:
    """Convert naive datetime to timezone-aware UTC datetime. Returns current time if None."""
    if dt is None:
        return datetime.now(timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def get_device_by_token(token: str, db: Session) -> Optional[Device]:
    """
    Look up a device by its token using efficient token_id lookup.
    Mirrors the logic from auth.verify_device_token but returns None instead of raising.

    Args:
        token: The device token to look up
        db: Database session

    Returns:
        Device if found and token matches, None otherwise
    """
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

    return None

app = FastAPI(title="NexMDM API")

# Registration queue to prevent connection pool saturation
# Limits concurrent device registrations to prevent overwhelming the database
REGISTRATION_CONCURRENCY_LIMIT = 15  # Max concurrent registrations
registration_semaphore = asyncio.Semaphore(REGISTRATION_CONCURRENCY_LIMIT)

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """
    Middleware to generate/extract request_id for correlation across logs.
    Also tracks HTTP request metrics.
    """
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request_id_var.set(req_id)

    start_time = time.time()

    response = await call_next(request)

    latency_ms = (time.time() - start_time) * 1000

    route = request.url.path
    if route.startswith("/v1/apk/download/") and route != "/v1/apk/download-latest":
        route = "/v1/apk/download/{apk_id}"
    elif "/devices/" in route and route.endswith("/ping"):
        route = "/v1/devices/{id}/ping"

    metrics.inc_counter("http_requests_total", {
        "route": route,
        "method": request.method,
        "status_code": str(response.status_code)
    })

    metrics.observe_histogram("http_request_latency_ms", latency_ms, {
        "route": route
    })

    response.headers["X-Request-ID"] = req_id

    return response

@app.middleware("http")
async def exception_guard_middleware(request: Request, call_next):
    """
    Global exception handler middleware to prevent process crashes.

    Catches all unhandled exceptions in routes and returns proper 500 responses
    instead of crashing the backend process. Logs full stacktraces for debugging.
    """
    try:
        return await call_next(request)
    except Exception as e:
        # Log the exception with full stacktrace
        structured_logger.log_event(
            "http.unhandled_exception",
            level="ERROR",
            path=request.url.path,
            method=request.method,
            error=str(e),
            error_type=type(e).__name__
        )

        # Return 500 without exposing internal details to client
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": "An unexpected error occurred. Please try again later."
            }
        )

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """
    Add security headers to all responses for defense-in-depth protection.

    Headers added:
    - X-Content-Type-Options: Prevents MIME-type sniffing
    - X-Frame-Options: Protects against clickjacking
    - X-XSS-Protection: Enables browser XSS filter
    - Strict-Transport-Security: Enforces HTTPS (production only)
    """
    response = await call_next(request)

    # Prevent MIME-type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # Enable XSS filter in older browsers
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Enforce HTTPS in production (only when deployed)
    if config.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request size limit middleware (BUG FIX #5): Prevent DoS attacks with large payloads
@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    """
    Limit request body size to 1MB to prevent DoS attacks.
    Exempts APK upload endpoints which need to handle 18MB+ files.
    Uses streaming size guard to enforce limit regardless of Content-Length header,
    chunked encoding, or other transfer methods.
    """
    # Exempt APK upload endpoints from size limit (needs to handle large APK files)
    if request.url.path in ["/admin/apk/upload", "/v1/apk/upload-chunk", "/v1/apk/complete"]:
        return await call_next(request)

    max_size = 1 * 1024 * 1024  # 1MB

    # Wrap the receive function to track total bytes
    total_bytes = 0
    receive = request.receive
    size_exceeded = False

    async def guarded_receive():
        nonlocal total_bytes, size_exceeded
        message = await receive()

        if message["type"] == "http.request":
            body = message.get("body", b"")
            total_bytes += len(body)

            if total_bytes > max_size:
                size_exceeded = True
                # Return empty body to prevent further processing
                return {"type": "http.request", "body": b""}

        return message

    # Replace request's receive with our guarded version
    request._receive = guarded_receive

    try:
        response = await call_next(request)

        # If size was exceeded, return 413 instead
        if size_exceeded:
            return Response(
                status_code=413,
                content=json.dumps({"detail": "Request body too large (max 1MB)"}),
                media_type="application/json"
            )

        return response
    except Exception as e:
        # If size was exceeded, return 413
        if size_exceeded:
            return Response(
                status_code=413,
                content=json.dumps({"detail": "Request body too large (max 1MB)"}),
                media_type="application/json"
            )
        raise

# Rate limiting for APK update endpoint
class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: int = 30):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds

        # Clean old requests
        self.requests[key] = [req_time for req_time in self.requests[key] if req_time > window_start]

        # Check if under limit
        if len(self.requests[key]) >= self.max_requests:
            return False

        self.requests[key].append(now)
        return True

# Rate limiter: 200 requests per 30 seconds per installation (very lenient for progress updates)
apk_rate_limiter = RateLimiter(max_requests=200, window_seconds=30)

# Registration rate limiter (BUG FIX #4): 3 registrations per minute per IP
registration_rate_limiter = RateLimiter(max_requests=3, window_seconds=60)

# Global error handler to prevent crashes
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"[ERROR] Unhandled exception: {exc}")
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error - backend is still running"}
    )

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        print(f"[WS] Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        print(f"[WS] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return

        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                disconnected.add(connection)

        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

async def send_fcm_launch_app(fcm_token: str, package_name: str, device_id: str = "unknown") -> bool:
    """
    Helper function to send FCM command to launch an app on a device
    Returns True if successful, False otherwise
    """
    import httpx

    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
    except Exception as e:
        print(f"[FCM-LAUNCH] Failed to get access token: {e}")
        return False

    fcm_url = build_fcm_v1_url(project_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    request_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    hmac_signature = compute_hmac_signature(request_id, device_id, "launch_app", timestamp)

    message = {
        "message": {
            "token": fcm_token,
            "data": {
                "action": "launch_app",
                "request_id": request_id,
                "device_id": device_id,
                "ts": timestamp,
                "hmac": hmac_signature,
                "package_name": package_name
            },
            "android": {
                "priority": "high"
            }
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(fcm_url, json=message, headers=headers, timeout=10.0)
            return response.status_code == 200
    except Exception as e:
        print(f"[FCM-LAUNCH] HTTP error: {e}")
        return False

class StreamingConnectionManager:
    """Manages screen streaming connections between devices and dashboard clients"""
    def __init__(self):
        # device_id -> WebSocket (device streaming source)
        self.device_streams: dict[str, WebSocket] = {}
        # device_id -> Set[WebSocket] (dashboard clients watching this device)
        self.stream_viewers: dict[str, Set[WebSocket]] = {}

    async def connect_device_stream(self, device_id: str, websocket: WebSocket):
        """Device connects to start streaming its screen"""
        await websocket.accept()
        self.device_streams[device_id] = websocket
        print(f"[STREAM] Device {device_id} started streaming")

    def disconnect_device_stream(self, device_id: str):
        """Device disconnects from streaming"""
        if device_id in self.device_streams:
            del self.device_streams[device_id]
            print(f"[STREAM] Device {device_id} stopped streaming")

        # Notify all viewers that stream ended
        if device_id in self.stream_viewers:
            viewers = self.stream_viewers[device_id].copy()
            for viewer in viewers:
                asyncio.create_task(self._send_stream_ended(viewer, device_id))
            del self.stream_viewers[device_id]

    async def connect_viewer(self, device_id: str, websocket: WebSocket):
        """Dashboard client connects to view a device stream"""
        await websocket.accept()
        if device_id not in self.stream_viewers:
            self.stream_viewers[device_id] = set()
        self.stream_viewers[device_id].add(websocket)
        print(f"[STREAM] Viewer connected to device {device_id}. Total viewers: {len(self.stream_viewers[device_id])}")

    def disconnect_viewer(self, device_id: str, websocket: WebSocket):
        """Dashboard client disconnects from viewing"""
        if device_id in self.stream_viewers:
            self.stream_viewers[device_id].discard(websocket)
            if not self.stream_viewers[device_id]:
                del self.stream_viewers[device_id]
            print(f"[STREAM] Viewer disconnected from device {device_id}")

    async def relay_frame(self, device_id: str, frame_data: bytes):
        """Relay a screen frame from device to all viewing clients"""
        if device_id not in self.stream_viewers:
            return

        disconnected = set()
        for viewer in self.stream_viewers[device_id]:
            try:
                await viewer.send_bytes(frame_data)
            except:
                disconnected.add(viewer)

        for viewer in disconnected:
            self.disconnect_viewer(device_id, viewer)

    async def _send_stream_ended(self, websocket: WebSocket, device_id: str):
        """Notify viewer that stream has ended"""
        try:
            await websocket.send_json({"type": "stream_ended", "device_id": device_id})
        except:
            pass

streaming_manager = StreamingConnectionManager()

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle validation errors safely without crashing on multipart requests.

    For multipart/form-data requests, the body stream is already consumed by
    the file upload parser, so attempting to read it again causes RuntimeError.
    """
    structured_logger.log_event(
        "validation.error",
        level="WARN",
        path=request.url.path,
        method=request.method,
        errors=exc.errors()
    )

    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

def validate_configuration():
    """
    Validate required environment variables and configuration on startup.
    Provides helpful error messages with links to documentation.
    """
    # Use config.validate() for comprehensive validation
    is_valid, errors, warnings = config.validate()

    # Check Firebase service account path (legacy support)
    firebase_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "")
    if firebase_path and not os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"):
        if not os.path.exists(firebase_path):
            errors.append(
                f"❌ Firebase service account file not found: {firebase_path}\n"
                f"   Please upload the JSON file or switch to FIREBASE_SERVICE_ACCOUNT_JSON secret.\n"
                f"   Expected location: {os.path.abspath(firebase_path)}"
            )
        else:
            warnings.append(
                "⚠️  Using FIREBASE_SERVICE_ACCOUNT_PATH file method\n"
                "   This exposes credentials on public forks. Consider using\n"
                "   FIREBASE_SERVICE_ACCOUNT_JSON secret instead for better security."
            )

    # Get server URL for summary
    server_url = None
    try:
        server_url = config.server_url
    except Exception:
        pass

    # Print validation results
    print("\n" + "="*80)
    print("🔍 NexMDM Configuration Validation")
    print("="*80)

    if errors:
        print("\n🚨 CONFIGURATION ERRORS - Server cannot start properly:\n")
        for error in errors:
            print(f"   {error}")
        print("\n📖 For setup instructions, see: DEPLOYMENT.md")
        print("   Or visit: https://github.com/yourusername/nexmdm#quick-start")
        print("\n" + "="*80 + "\n")
        raise RuntimeError("Configuration validation failed. Please fix the errors above.")

    if warnings:
        print("\n⚠️  Configuration Warnings:\n")
        for warning in warnings:
            print(f"   {warning}")
        print()

    # Print success status
    print("✅ Required configuration validated successfully")

    # Print configuration summary
    print("\n📊 Configuration Summary:")
    admin_key = config.get_admin_key()
    print(f"   • Admin Key: {'✓ Set' if admin_key else '✗ Missing'}")

    firebase_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if firebase_json:
        print(f"   • Firebase: ✓ JSON Secret (secure)")
    elif firebase_path and os.path.exists(firebase_path):
        print(f"   • Firebase: ✓ File Path (⚠️  less secure) - {firebase_path}")
    else:
        print(f"   • Firebase: ✗ Missing")

    print(f"   • Server URL: {server_url if server_url else '⚠️  Not set'}")
    discord_webhook = os.getenv("DISCORD_WEBHOOK_URL")
    print(f"   • Discord Alerts: {'✓ Enabled' if discord_webhook else 'ℹ️  Disabled (console only)'}")
    db_url = config.get_database_url()
    print(f"   • Database: {db_url[:50]}...")
    print("="*80 + "\n")

    # Print detailed config summary
    config.print_config_summary()

# Track backend startup time at module level (before startup_event uses it)
backend_start_time = datetime.now(timezone.utc)

@app.on_event("startup")
async def startup_event():
    """
    Initialize application dependencies and background tasks.
    Wraps background task startup in defensive error handling to prevent
    silent crashes from unhandled exceptions in async loops.
    """
    print("=" * 60)
    print("🚀 Starting NexMDM Backend Server...")
    print(f"⏰ Startup time: {backend_start_time.isoformat()}")
    print("=" * 60)

    try:
        validate_configuration()
        print("✅ Configuration validated")
    except Exception as e:
        print(f"⚠️  Configuration validation had warnings: {e}")
        # Don't raise - allow server to start with warnings
        print("⚠️  Server starting despite configuration warnings...")

    try:
        init_db()
        print("✅ Database initialized")
    except Exception as e:
        print(f"⚠️  Database initialization warning: {e}")
        # Try to continue - database might already be initialized
        print("⚠️  Attempting to continue with existing database...")

    # Note: migrate_database() temporarily skipped due to table lock issues
    # TODO: Fix migration transaction handling to avoid deadlocks
    try:
        seed_bloatware_packages()
        print("✅ Bloatware packages seeded")
    except Exception as e:
        print(f"⚠️  Bloatware seeding failed (non-critical): {e}")

    try:
        ensure_heartbeat_partitions()
        print("✅ Heartbeat partitions ensured")
    except Exception as e:
        print(f"⚠️  Heartbeat partition check failed (non-critical): {e}")

    # Start background tasks with defensive error handling
    try:
        await alert_scheduler.start()
        structured_logger.log_event(
            "startup.alert_scheduler.started",
            level="INFO"
        )
    except Exception as e:
        structured_logger.log_event(
            "startup.alert_scheduler.failed",
            level="ERROR",
            error=str(e),
            error_type=type(e).__name__
        )
        # Log but don't crash - some deployments may not need alerts
        print(f"⚠️  Alert scheduler failed to start: {e}")

    try:
        await background_tasks.start()
        structured_logger.log_event(
            "startup.background_tasks.started",
            level="INFO"
        )
    except Exception as e:
        structured_logger.log_event(
            "startup.background_tasks.failed",
            level="ERROR",
            error=str(e),
            error_type=type(e).__name__
        )
        # Log but don't crash - background tasks may be optional
        print(f"⚠️  Background tasks failed to start: {e}")

    print("=" * 60)
    print("✅ NexMDM Backend Server started successfully!")
    print("📡 Server is ready to accept connections on port 8000")
    print(f"🏥 Health check available at: /healthz")
    print("=" * 60)

@app.on_event("shutdown")
async def shutdown_event():
    await alert_scheduler.stop()
    await background_tasks.stop()

def migrate_database():
    """Add missing columns to existing database tables"""
    from sqlalchemy import text
    from models import engine

    # Whitelist of allowed column names and types to prevent SQL injection
    ALLOWED_COLUMNS = {
        "app_version": "VARCHAR",
        "model": "VARCHAR",
        "manufacturer": "VARCHAR",
        "android_version": "VARCHAR",
        "sdk_int": "INTEGER",
        "build_id": "VARCHAR",
        "is_device_owner": "BOOLEAN",
    }

    # Allowed SQL types for validation
    ALLOWED_TYPES = {"VARCHAR", "INTEGER", "BOOLEAN", "TEXT", "TIMESTAMP"}

    # Each ALTER TABLE needs its own transaction to avoid deadlocks
    for column_name, column_type in ALLOWED_COLUMNS.items():
        # Validate against whitelist to prevent SQL injection
        if column_name not in ALLOWED_COLUMNS:
            structured_logger.log_event(
                "migration.invalid_column",
                level="ERROR",
                column_name=column_name
            )
            continue

        if column_type not in ALLOWED_TYPES:
            structured_logger.log_event(
                "migration.invalid_type",
                level="ERROR",
                column_type=column_type,
                column_name=column_name
            )
            continue

        try:
            # Each ALTER TABLE gets its own transaction
            with engine.begin() as conn:
                # Use identifier quoting for column names to prevent injection
                # SQLAlchemy's text() with proper escaping is safer than f-strings
                conn.execute(text(f'ALTER TABLE devices ADD COLUMN "{column_name}" {column_type}'))
            structured_logger.log_event(
                "migration.column_added",
                level="INFO",
                column_name=column_name
            )
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                # Column already exists, that's fine
                pass
            else:
                structured_logger.log_event(
                    "migration.error",
                    level="ERROR",
                    error=str(e),
                    error_type=type(e).__name__,
                    column_name=column_name
                )

def ensure_heartbeat_partitions():
    """
    Ensure heartbeat partitions exist for today and next 7 days.
    Runs on server startup to prevent partition errors.
    """
    from db_utils import create_heartbeat_partition
    from datetime import date, timedelta

    today = date.today()
    for i in range(8):
        target_date = today + timedelta(days=i)
        try:
            create_heartbeat_partition(target_date)
        except Exception as e:
            print(f"[PARTITION] {target_date}: {e}")

def seed_bloatware_packages():
    """Seed database with default bloatware packages if empty"""
    db = SessionLocal()
    try:
        # Check if already seeded
        count = db.query(BloatwarePackage).count()
        if count > 0:
            return

        # Default bloatware packages from baseline (disabled_list_1761250623211.txt)
        default_packages = [
            "com.vzw.hss.myverizon",
            "com.verizon.obdm_permissions",
            "com.vzw.apnlib",
            "com.verizon.mips.services",
            "com.vcast.mediamanager",
            "com.reliancecommunications.vvmclient",
            "com.google.android.apps.youtube.music",
            "com.google.android.youtube",
            "com.google.android.apps.videos",
            "com.google.android.apps.docs",
            "com.google.android.apps.maps",
            "com.google.android.apps.photos",
            "com.google.android.apps.wallpaper",
            "com.google.android.apps.walletnfcrel",
            "com.google.android.apps.nbu.files",
            "com.google.android.apps.keep",
            "com.google.android.apps.googleassistant",
            "com.google.android.apps.tachyon",
            "com.google.android.apps.safetyhub",
            "com.google.android.apps.nbu.paisa.user",
            "com.google.android.apps.chromecast.app",
            "com.google.android.apps.wellbeing",
            "com.google.android.apps.customization.pixel",
            "com.google.android.deskclock",
            "com.google.android.calendar",
            "com.google.android.gm",
            "com.google.android.calculator",
            "com.google.android.projection.gearhead",
            "com.google.android.printservice.recommendation",
            "com.google.android.feedback",
            "com.google.android.marvin.talkback",
            "com.google.android.tts",
            "com.google.android.gms.supervision",
            "com.LogiaGroup.LogiaDeck",
            "com.dti.folderlauncher",
            "com.huub.viper",
            "us.sliide.viper",
            "com.example.sarswitch",
            "com.handmark.expressweather",
            "com.tripledot.solitaire",
            "com.facebook.katana",
            "com.facebook.appmanager",
            "com.discounts.viper",
            "com.android.egg",
            "com.android.dreams.basic",
            "com.android.dreams.phototable",
            "com.android.musicfx",
            "com.android.soundrecorder",
            "com.android.protips",
            "com.android.wallpapercropper",
            "com.android.wallpaper.livepicker",
            "com.android.providers.partnerbookmarks",
            "com.android.bips",
            "com.android.printspooler",
            "com.android.wallpaperbackup",
            "com.android.soundpicker",
        ]

        # Insert all packages
        for package_name in default_packages:
            pkg = BloatwarePackage(
                package_name=package_name,
                enabled=True
            )
            db.add(pkg)

        db.commit()
        print(f"[SEED] Added {len(default_packages)} default bloatware packages")
    except Exception as e:
        print(f"[SEED] Error seeding bloatware packages: {e}")
        db.rollback()
    finally:
        db.close()

def log_device_event(db: Session, device_id: str, event_type: str, details: Optional[dict] = None):
    """Log a device event to the database"""
    event = DeviceEvent(
        device_id=device_id,
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
        details=json.dumps(details) if details is not None else None
    )
    db.add(event)
    db.commit()
@app.get("/healthz")
async def health_check():
    """
    Liveness check - returns 200 if process is alive.
    Does not check dependencies (use /readyz for that).
    """
    uptime_seconds = (datetime.now(timezone.utc) - backend_start_time).total_seconds()
    return {
        "status": "healthy",
        "uptime_seconds": int(uptime_seconds),
        "uptime_formatted": f"{int(uptime_seconds // 3600)}h {int((uptime_seconds % 3600) // 60)}m",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
    }

@app.get("/readyz")
async def readiness_check():
    """
    Readiness check - verifies all dependencies are operational.
    Checks database connectivity and object storage availability.
    Returns 200 if ready, 503 if not ready.
    """
    checks = {
        "database": False,
        "storage": False,
        "overall": False
    }
    errors = []

    # Check database connectivity
    try:
        db = SessionLocal()
        try:
            # Simple query to verify DB is reachable
            result = db.execute(text("SELECT 1")).scalar()
            checks["database"] = (result == 1)
        finally:
            db.close()
    except Exception as e:
        errors.append(f"database: {str(e)[:100]}")
        checks["database"] = False

    # Check object storage connectivity
    try:
        storage = get_storage_service()
        # Storage service uses sidecar, just verify it's initialized
        checks["storage"] = (storage is not None)
    except Exception as e:
        errors.append(f"storage: {str(e)[:100]}")
        checks["storage"] = False

    # Overall readiness
    checks["overall"] = checks["database"] and checks["storage"]

    status_code = 200 if checks["overall"] else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "ready": checks["overall"],
            "checks": checks,
            "errors": errors if errors else None,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
        }
    )

@app.get("/metrics")
async def prometheus_metrics(x_admin: str = Header(None)):
    """Prometheus-compatible metrics endpoint (requires admin authentication)"""
    if not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=401, detail="Admin key required")

    structured_logger.log_event("metrics.scrape")

    # Update connection pool metrics
    from models import engine
    pool_stats = metrics.get_pool_stats(engine)
    metrics.set_gauge("db_pool_size", pool_stats["size"])
    metrics.set_gauge("db_pool_checked_in", pool_stats["checked_in"])
    metrics.set_gauge("db_pool_checked_out", pool_stats["checked_out"])
    metrics.set_gauge("db_pool_overflow", pool_stats["overflow"])
    metrics.set_gauge("db_pool_in_use", pool_stats["checked_out"])  # Alias for alerts

    metrics_text = metrics.get_prometheus_text()

    return Response(
        content=metrics_text,
        media_type="text/plain; version=0.0.4"
    )

@app.post("/ops/nightly")
async def trigger_nightly_maintenance(
    x_admin: str = Header(None),
    dry_run: bool = False,
    retention_days: int = 90
):
    """
    Trigger nightly maintenance job (partition lifecycle management).
    Protected endpoint for external schedulers (UptimeRobot, Cronjob.org).

    Uses advisory locks to prevent concurrent runs.
    """
    if not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=401, detail="Admin key required")

    structured_logger.log_event(
        "ops.nightly_maintenance.triggered",
        dry_run=dry_run,
        retention_days=retention_days
    )

    try:
        from nightly_maintenance import run_nightly_maintenance

        result = run_nightly_maintenance(retention_days=retention_days, dry_run=dry_run)

        return {
            "ok": True,
            "result": result
        }

    except Exception as e:
        structured_logger.log_event(
            "ops.nightly_maintenance.error",
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(status_code=500, detail=f"Maintenance job failed: {str(e)}")

@app.post("/ops/reconcile")
async def trigger_reconciliation(
    x_admin: str = Header(None),
    dry_run: bool = False,
    max_rows: int = 5000
):
    """
    Trigger hourly reconciliation job (device_last_status consistency repair).
    Protected endpoint for external schedulers.

    Uses advisory locks to prevent concurrent runs.
    """
    if not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=401, detail="Admin key required")

    structured_logger.log_event(
        "ops.reconciliation.triggered",
        dry_run=dry_run,
        max_rows=max_rows
    )

    try:
        from reconciliation_job import run_reconciliation

        result = run_reconciliation(dry_run=dry_run, max_rows=max_rows)

        return {
            "ok": True,
            "result": result
        }

    except Exception as e:
        structured_logger.log_event(
            "ops.reconciliation.error",
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(status_code=500, detail=f"Reconciliation job failed: {str(e)}")

@app.get("/ops/pool_health")
async def get_pool_health(x_admin: str = Header(None)):
    """
    Check connection pool health and saturation levels.
    Protected endpoint for monitoring and alerting systems.

    Returns pool utilization with WARN/CRITICAL thresholds.
    """
    if not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=401, detail="Admin key required")

    try:
        from pool_monitor import check_pool_health, check_postgres_connection_health

        pool_health = check_pool_health()
        pg_health = check_postgres_connection_health()

        return {
            "ok": True,
            "pool": pool_health,
            "postgres": pg_health
        }

    except Exception as e:
        structured_logger.log_event(
            "ops.pool_health.error",
            level="ERROR",
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(status_code=500, detail=f"Pool health check failed: {str(e)}")

@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    if not token:
        await websocket.close(code=1008, reason="Unauthorized - no token")
        return

    # Verify JWT token and authenticate user (with scoped DB session)
    from auth import verify_jwt_token
    try:
        payload = verify_jwt_token(token)
        user_id = payload.get("user_id")

        if not user_id:
            await websocket.close(code=1008, reason="Unauthorized - invalid token")
            return

        # Create scoped DB session only for auth check
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                await websocket.close(code=1008, reason="Unauthorized - user not found")
                return
            username = user.username  # Store username for logging
        finally:
            db.close()  # Close DB session immediately after auth
    except Exception as e:
        await websocket.close(code=1008, reason=f"Unauthorized - {str(e)}")
        return

    await manager.connect(websocket)
    print(f"[WS] Authenticated user {username} connected via JWT")

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print(f"[WS] User {username} disconnected")
    except Exception as e:
        print(f"[WS] Error for user {username}: {e}")
        manager.disconnect(websocket)

@app.websocket("/ws/stream/device/{device_id}")
async def device_stream_endpoint(
    websocket: WebSocket,
    device_id: str,
    token: str = Query(...)
):
    """WebSocket endpoint for devices to stream their screen"""
    # Verify device token with scoped DB session
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            await websocket.close(code=1008, reason="Device not found")
            return

        # Verify device token
        token_hash = hash_token(token)
        if device.token_hash != token_hash:
            await websocket.close(code=1008, reason="Invalid device token")
            return
    finally:
        db.close()  # Close DB session immediately after auth

    await streaming_manager.connect_device_stream(device_id, websocket)

    try:
        while True:
            # Receive screen frame from device
            frame_data = await websocket.receive_bytes()
            # Relay frame to all viewers
            await streaming_manager.relay_frame(device_id, frame_data)
    except WebSocketDisconnect:
        streaming_manager.disconnect_device_stream(device_id)
    except Exception as e:
        print(f"[STREAM] Error for device {device_id}: {e}")
        streaming_manager.disconnect_device_stream(device_id)

@app.websocket("/ws/stream/view/{device_id}")
async def viewer_stream_endpoint(
    websocket: WebSocket,
    device_id: str,
    session_token: Optional[str] = Cookie(None, alias="session_token"),
    token: Optional[str] = None  # Accept session_token as query param too
):
    """WebSocket endpoint for dashboard to view device screen stream"""
    # Accept session_token from either cookie or query parameter (for cross-port WebSocket)
    auth_session_id = session_token or token

    print(f"[STREAM DEBUG] Cookie session_token: {session_token is not None}, Query token: {token is not None}")
    print(f"[STREAM DEBUG] Final auth_session_id: {auth_session_id is not None}")

    # Verify user session with scoped DB session
    if not auth_session_id:
        print(f"[STREAM DEBUG] No auth session - rejecting")
        await websocket.close(code=1008, reason="Unauthorized")
        return

    db = SessionLocal()
    try:
        session = db.query(SessionModel).filter(SessionModel.id == auth_session_id).first()
        if not session or session.expires_at < datetime.now(timezone.utc):
            await websocket.close(code=1008, reason="Unauthorized")
            return

        user = db.query(User).filter(User.id == session.user_id).first()
        if not user:
            await websocket.close(code=1008, reason="Unauthorized")
            return

        # Verify device exists
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            await websocket.close(code=1008, reason="Device not found")
            return

        # Store values we need after closing DB session
        username = user.username
        device_fcm_token = device.fcm_token
    finally:
        db.close()  # Close DB session immediately after auth/verification

    # Check if this is the first viewer - if so, send FCM to start stream
    is_first_viewer = len(streaming_manager.stream_viewers.get(device_id, set())) == 0

    await streaming_manager.connect_viewer(device_id, websocket)
    print(f"[STREAM] User {username} viewing device {device_id}")

    # Send FCM command to device to start streaming (only for first viewer)
    if is_first_viewer and device_fcm_token:
        try:
            import httpx
            access_token = get_access_token()
            project_id = get_firebase_project_id()
            fcm_url = build_fcm_v1_url(project_id)

            message_data = {
                "action": "remote_control",
                "command": "start_stream"
            }

            fcm_message = {
                "message": {
                    "token": device_fcm_token,
                    "data": message_data,
                    "android": {
                        "priority": "high"
                    }
                }
            }

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(fcm_url, json=fcm_message, headers=headers)
                if response.status_code == 200:
                    print(f"[STREAM] Sent start_stream FCM to device {device_id}")
                else:
                    print(f"[STREAM] FCM failed: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"[STREAM] Failed to send FCM start_stream: {e}")

    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        streaming_manager.disconnect_viewer(device_id, websocket)
        print(f"[STREAM] User {username} stopped viewing device {device_id}")
    except Exception as e:
        print(f"[STREAM] Error for viewer on device {device_id}: {e}")
        streaming_manager.disconnect_viewer(device_id, websocket)

@app.post("/api/auth/register")
async def register_user(
    req: Request,
    request: UserRegisterRequest,
    response: Response,
    admin_key: str = Header(..., alias="x-admin-key"),
    db: Session = Depends(get_db)
):
    if not verify_admin_key(admin_key):
        raise HTTPException(status_code=403, detail="Invalid admin key")

    # Rate limiting (BUG FIX #4): Prevent registration abuse
    client_ip = req.client.host if req.client else "unknown"
    if not registration_rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many registration attempts. Please try again later.",
            headers={"Retry-After": "60"}
        )

    if len(request.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")

    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    existing_user = db.query(User).filter(User.username == request.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")

    password_hash = hash_password(request.password)

    user = User(
        username=request.username,
        email=request.email,
        password_hash=password_hash,
        created_at=datetime.now(timezone.utc)
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # Generate JWT token
    from auth import create_jwt_token
    access_token = create_jwt_token(user.id, user.username)

    return {
        "ok": True,
        "access_token": access_token,
        "user": {
            "id": user.id,
            "username": user.username,
            "created_at": user.created_at.isoformat() + "Z"
        }
    }

@app.post("/api/auth/login")
async def login_user(
    request: UserLoginRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == request.username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Generate JWT token
    from auth import create_jwt_token
    access_token = create_jwt_token(user.id, user.username)

    return {
        "ok": True,
        "access_token": access_token,
        "user": {
            "id": user.id,
            "username": user.username,
            "created_at": user.created_at.isoformat() + "Z"
        }
    }

@app.get("/api/auth/user")
async def get_user_info(
    user: User = Depends(get_current_user)
):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "created_at": user.created_at.isoformat() + "Z"
    }

@app.post("/api/auth/logout")
async def logout_user(
    response: Response,
    db: Session = Depends(get_db),
    session_token: Optional[str] = Cookie(None, alias="session_token")
):
    if session_token:
        session = db.query(SessionModel).filter(SessionModel.id == session_token).first()
        if session:
            db.delete(session)
            db.commit()

    response.delete_cookie(key="session_token", samesite="lax")

    return {"ok": True, "message": "Logged out successfully"}

@app.post("/api/auth/signup")
async def signup_user(
    req: Request,
    request: UserRegisterRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """Public signup endpoint - no admin key required"""
    # Rate limiting to prevent abuse
    client_ip = req.client.host if req.client else "unknown"
    if not registration_rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many registration attempts. Please try again later.",
            headers={"Retry-After": "60"}
        )

    if len(request.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")

    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    if request.email:
        if len(request.email) < 3 or "@" not in request.email:
            raise HTTPException(status_code=400, detail="Invalid email address")

        existing_email = db.query(User).filter(User.email == request.email).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already registered")

    existing_user = db.query(User).filter(User.username == request.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")

    password_hash = hash_password(request.password)

    user = User(
        username=request.username,
        email=request.email,
        password_hash=password_hash,
        created_at=datetime.now(timezone.utc)
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    from auth import create_jwt_token
    access_token = create_jwt_token(user.id, user.username)

    return {
        "ok": True,
        "access_token": access_token,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "created_at": user.created_at.isoformat() + "Z"
        }
    }

# Rate limiter for setup endpoints: 10 requests per minute per IP
setup_rate_limiter = RateLimiter(max_requests=10, window_seconds=60)

@app.get("/api/setup/status")
async def get_setup_status(request: Request):
    """
    Check which secrets are configured for the setup wizard.
    Returns status of required and optional configuration.
    Public endpoint - no authentication required.
    """
    # Rate limiting to prevent abuse
    client_ip = request.client.host if request.client else "unknown"
    if not setup_rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": "60"}
        )

    import json

    status = {
        "required": {
            "admin_key": {
                "configured": bool(os.getenv("ADMIN_KEY")),
                "valid": False,
                "message": ""
            },
            "jwt_secret": {
                "configured": bool(os.getenv("SESSION_SECRET")),
                "valid": False,
                "message": ""
            },
            "hmac_secret": {
                "configured": bool(os.getenv("HMAC_SECRET")),
                "valid": False,
                "message": ""
            },
            "firebase": {
                "configured": bool(os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")),
                "valid": False,
                "message": ""
            },
            "database": {
                "configured": False,
                "valid": False,
                "message": "",
                "type": None,
                "connection_tested": False
            }
        },
        "optional": {
            "discord_webhook": {
                "configured": bool(os.getenv("DISCORD_WEBHOOK_URL")),
                "message": ""
            },
            "github_ci": {
                "configured": False,
                "message": ""
            },
            "object_storage": {
                "configured": False,
                "available": False,
                "message": ""
            },
            "email_service": {
                "configured": False,
                "available": False,
                "message": ""
            }
        },
        "ready": False
    }

    # Validate ADMIN_KEY
    admin_key = os.getenv("ADMIN_KEY", "")
    if admin_key:
        if len(admin_key) < 16:
            status["required"]["admin_key"]["valid"] = False
            status["required"]["admin_key"]["message"] = "ADMIN_KEY should be at least 16 characters"
        elif admin_key in ["admin", "changeme", "default"]:
            status["required"]["admin_key"]["valid"] = False
            status["required"]["admin_key"]["message"] = "ADMIN_KEY must not use default/insecure values"
        else:
            status["required"]["admin_key"]["valid"] = True
            status["required"]["admin_key"]["message"] = "✓ Valid"
    else:
        status["required"]["admin_key"]["message"] = "Not configured"

    # Validate SESSION_SECRET
    jwt_secret = os.getenv("SESSION_SECRET", "")
    if jwt_secret:
        if jwt_secret == "dev-secret-change-in-production" or jwt_secret == "default-secret-change-in-production":
            status["required"]["jwt_secret"]["valid"] = False
            status["required"]["jwt_secret"]["message"] = "Using default secret - change for production"
        elif len(jwt_secret) < 32:
            status["required"]["jwt_secret"]["valid"] = False
            status["required"]["jwt_secret"]["message"] = "SESSION_SECRET should be at least 32 characters"
        else:
            status["required"]["jwt_secret"]["valid"] = True
            status["required"]["jwt_secret"]["message"] = "✓ Valid"
    else:
        status["required"]["jwt_secret"]["message"] = "Not configured"

    # Validate HMAC_SECRET
    hmac_secret = os.getenv("HMAC_SECRET", "")
    if hmac_secret:
        if len(hmac_secret) < 32:
            status["required"]["hmac_secret"]["valid"] = False
            status["required"]["hmac_secret"]["message"] = "HMAC_SECRET should be at least 32 characters"
        else:
            status["required"]["hmac_secret"]["valid"] = True
            status["required"]["hmac_secret"]["message"] = "✓ Valid"
    else:
        status["required"]["hmac_secret"]["valid"] = False
        status["required"]["hmac_secret"]["message"] = "Not configured (required for device commands)"

    # Validate Firebase JSON (consistent with validate_firebase_json endpoint)
    firebase_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
    if firebase_json:
        try:
            # Parse JSON (handles whitespace)
            firebase_data = json.loads(firebase_json.strip())
            # Check for required fields
            required_fields = ["type", "project_id", "private_key_id", "private_key", "client_email"]
            missing_fields = [field for field in required_fields if field not in firebase_data]

            if missing_fields:
                status["required"]["firebase"]["valid"] = False
                status["required"]["firebase"]["message"] = f"Missing required fields: {', '.join(missing_fields)}"
            elif firebase_data.get("type") != "service_account":
                status["required"]["firebase"]["valid"] = False
                status["required"]["firebase"]["message"] = "JSON is not a service account type"
            elif not firebase_data.get("project_id") or not firebase_data.get("client_email"):
                status["required"]["firebase"]["valid"] = False
                status["required"]["firebase"]["message"] = "project_id and client_email cannot be empty"
            else:
                # Validate private_key: must be a string and at least 100 characters
                private_key = firebase_data.get("private_key")
                if not private_key or not isinstance(private_key, str) or len(private_key) < 100:
                    status["required"]["firebase"]["valid"] = False
                    status["required"]["firebase"]["message"] = "private_key appears to be invalid or too short"
                else:
                    status["required"]["firebase"]["valid"] = True
                    status["required"]["firebase"]["message"] = "✓ Valid"
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            status["required"]["firebase"]["valid"] = False
            status["required"]["firebase"]["message"] = f"Invalid JSON format or structure: {str(e)}"
    else:
        status["required"]["firebase"]["message"] = "Not configured"

    # Check GitHub CI secrets (optional)
    github_secrets = [
        "ANDROID_KEYSTORE_BASE64",
        "KEYSTORE_PASSWORD",
        "ANDROID_KEY_ALIAS",
        "ANDROID_KEY_ALIAS_PASSWORD",
        "BACKEND_URL",
        "ADMIN_KEY"
    ]
    github_configured = all(os.getenv(secret) for secret in github_secrets)
    status["optional"]["github_ci"]["configured"] = github_configured
    status["optional"]["github_ci"]["message"] = "Configure GitHub Actions secrets for Android CI/CD" if not github_configured else "✓ Configured"

    # Check Object Storage (required for APK storage)
    try:
        from object_storage import get_storage_service
        storage = get_storage_service()
        # Try to list objects to verify storage is accessible
        try:
            # Just check if client is initialized - actual operations may fail if bucket doesn't exist
            # but client initialization failure means integration isn't set up
            status["optional"]["object_storage"]["configured"] = True
            status["optional"]["object_storage"]["available"] = True
            status["optional"]["object_storage"]["message"] = "✓ Object Storage available"
        except Exception as e:
            status["optional"]["object_storage"]["configured"] = True
            status["optional"]["object_storage"]["available"] = False
            status["optional"]["object_storage"]["message"] = f"Object Storage integration found but not accessible: {str(e)[:100]}"
    except Exception as e:
        status["optional"]["object_storage"]["configured"] = False
        status["optional"]["object_storage"]["available"] = False
        status["optional"]["object_storage"]["message"] = "Object Storage integration not set up"

    # Check ReplitMail email service (optional but recommended)
    repl_identity = os.getenv("REPL_IDENTITY")
    web_repl_renewal = os.getenv("WEB_REPL_RENEWAL")
    if repl_identity or web_repl_renewal:
        status["optional"]["email_service"]["configured"] = True
        try:
            from email_service import email_service
            # Just check if service can be initialized
            status["optional"]["email_service"]["available"] = True
            status["optional"]["email_service"]["message"] = "✓ ReplitMail available"
        except Exception as e:
            status["optional"]["email_service"]["configured"] = True
            status["optional"]["email_service"]["available"] = False
            status["optional"]["email_service"]["message"] = f"ReplitMail configured but initialization failed: {str(e)[:100]}"
    else:
        status["optional"]["email_service"]["configured"] = False
        status["optional"]["email_service"]["available"] = False
        status["optional"]["email_service"]["message"] = "ReplitMail integration not set up (recommended for email notifications)"

    # Check database configuration
    db_url = config.get_database_url()
    if db_url and db_url != "sqlite:///./data.db":
        status["required"]["database"]["configured"] = True

        # Detect database type
        if "postgres" in db_url.lower() or "postgresql" in db_url.lower():
            status["required"]["database"]["type"] = "postgresql"
            status["required"]["database"]["message"] = "PostgreSQL configured"
        elif "sqlite" in db_url.lower():
            status["required"]["database"]["type"] = "sqlite"
            status["required"]["database"]["message"] = "SQLite configured"
        else:
            status["required"]["database"]["type"] = "unknown"
            status["required"]["database"]["message"] = "Database URL configured"

        # Try to test database connection (non-blocking, won't fail if DB is down)
        try:
            from models import engine
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            status["required"]["database"]["connection_tested"] = True
            status["required"]["database"]["valid"] = True
            if status["required"]["database"]["message"] != "Database URL configured":
                status["required"]["database"]["message"] += " (connection OK)"
        except Exception as e:
            status["required"]["database"]["connection_tested"] = True
            status["required"]["database"]["valid"] = False
            status["required"]["database"]["message"] = f"Database configured but connection failed: {str(e)[:100]}"
    else:
        status["required"]["database"]["configured"] = False
        status["required"]["database"]["type"] = "sqlite"
        status["required"]["database"]["message"] = "Using default SQLite (PostgreSQL recommended for production)"
        status["required"]["database"]["valid"] = True  # SQLite file-based, assume OK if file exists or can be created

    # Check if all required secrets are valid
    # Database is optional for setup (can use default SQLite), so don't require it
    status["ready"] = all(
        secret["configured"] and secret["valid"]
        for key, secret in status["required"].items()
        if key != "database"  # Database is optional
    )

    return status

@app.post("/api/setup/verify")
async def verify_setup_complete(request: Request):
    """
    End-to-end verification that tests all critical components are working.
    Tests backend, database, object storage, and signup endpoint availability.
    Public endpoint - no authentication required.
    """
    # Rate limiting to prevent abuse
    client_ip = request.client.host if request.client else "unknown"
    if not setup_rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": "60"}
        )

    results = {
        "backend": {"available": False, "message": ""},
        "database": {"available": False, "message": ""},
        "object_storage": {"available": False, "message": ""},
        "signup_endpoint": {"available": False, "message": ""},
        "all_ready": False
    }

    # Test backend health - if this endpoint is reachable, backend is running
    # We can also verify by checking if we can import modules
    try:
        # If we can import and use models, backend is initialized
        from models import engine
        results["backend"]["available"] = True
        results["backend"]["message"] = "Backend is running"
    except Exception as e:
        results["backend"]["available"] = False
        results["backend"]["message"] = f"Backend initialization issue: {str(e)[:100]}"

    # Test database connection
    try:
        from models import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        results["database"]["available"] = True
        results["database"]["message"] = "Database connection OK"
    except Exception as e:
        results["database"]["available"] = False
        results["database"]["message"] = f"Database connection failed: {str(e)[:100]}"

    # Test object storage
    try:
        from object_storage import get_storage_service
        storage = get_storage_service()
        results["object_storage"]["available"] = True
        results["object_storage"]["message"] = "Object Storage available"
    except Exception as e:
        results["object_storage"]["available"] = False
        results["object_storage"]["message"] = f"Object Storage not available: {str(e)[:100]}"

    # Test signup endpoint (just check if route exists, don't actually signup)
    # We can't easily test this without making an actual request, so we'll just check if backend is running
    if results["backend"]["available"]:
        results["signup_endpoint"]["available"] = True
        results["signup_endpoint"]["message"] = "Signup endpoint should be available (backend is running)"
    else:
        results["signup_endpoint"]["available"] = False
        results["signup_endpoint"]["message"] = "Cannot verify signup endpoint (backend not running)"

    # All critical components ready
    results["all_ready"] = (
        results["backend"]["available"] and
        results["database"]["available"] and
        results["object_storage"]["available"]
    )

    return results

@app.post("/api/setup/test-database")
async def test_database_connection(request: Request):
    """
    Test database connection and return status.
    Useful for the setup wizard to verify database connectivity.
    Public endpoint - no authentication required.
    """
    # Rate limiting to prevent abuse
    client_ip = request.client.host if request.client else "unknown"
    if not setup_rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": "60"}
        )

    db_url = config.get_database_url()
    result = {
        "configured": bool(db_url and db_url != "sqlite:///./data.db"),
        "type": None,
        "connected": False,
        "message": "",
        "error": None
    }

    if not db_url or db_url == "sqlite:///./data.db":
        result["type"] = "sqlite"
        result["message"] = "Using default SQLite database"
        result["connected"] = True  # SQLite file-based, assume OK if file exists or can be created
        return result

    # Detect database type
    if "postgres" in db_url.lower() or "postgresql" in db_url.lower():
        result["type"] = "postgresql"
    elif "sqlite" in db_url.lower():
        result["type"] = "sqlite"
    else:
        result["type"] = "unknown"

    # Test database connection
    try:
        from models import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        result["connected"] = True
        result["message"] = f"{result['type'].upper()} connection successful"
    except Exception as e:
        result["connected"] = False
        result["error"] = str(e)
        result["message"] = f"Connection failed: {str(e)[:200]}"

    return result

@app.post("/api/setup/validate-firebase")
async def validate_firebase_json(request: Request):
    """
    Validate Firebase service account JSON without saving it.
    Useful for the setup wizard to check before user adds it to secrets.
    Public endpoint - no authentication required.
    """
    # Rate limiting to prevent abuse
    client_ip = request.client.host if request.client else "unknown"
    if not setup_rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": "60"}
        )

    try:
        data = await request.json()
        firebase_json_str = data.get("firebase_json", "")

        if not firebase_json_str or not firebase_json_str.strip():
            return JSONResponse(
                status_code=400,
                content={"valid": False, "message": "Firebase JSON is required"}
            )

        # Trim whitespace and parse JSON
        firebase_json_str = firebase_json_str.strip()

        # Parse and validate JSON
        try:
            firebase_data = json.loads(firebase_json_str)
        except json.JSONDecodeError as e:
            return JSONResponse(
                status_code=400,
                content={"valid": False, "message": f"Invalid JSON format: {str(e)}"}
            )

        # Check required fields
        required_fields = ["type", "project_id", "private_key_id", "private_key", "client_email"]
        missing_fields = [field for field in required_fields if field not in firebase_data]

        if missing_fields:
            return JSONResponse(
                status_code=400,
                content={
                    "valid": False,
                    "message": f"Missing required fields: {', '.join(missing_fields)}"
                }
            )

        if firebase_data.get("type") != "service_account":
            return JSONResponse(
                status_code=400,
                content={"valid": False, "message": "JSON is not a service account type"}
            )

        # Validate that critical fields are not empty
        if not firebase_data.get("project_id") or not firebase_data.get("client_email"):
            return JSONResponse(
                status_code=400,
                content={"valid": False, "message": "project_id and client_email cannot be empty"}
            )

        # Validate private_key: must be a string and at least 100 characters
        private_key = firebase_data.get("private_key")
        if not private_key or not isinstance(private_key, str) or len(private_key) < 100:
            return JSONResponse(
                status_code=400,
                content={"valid": False, "message": "private_key appears to be invalid or too short"}
            )

        return JSONResponse(
            status_code=200,
            content={"valid": True, "message": "✓ Valid Firebase service account JSON"}
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"valid": False, "message": f"Validation error: {str(e)}"}
        )

@app.put("/api/auth/profile/email")
async def update_user_email(
    new_email: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update the current user's email address"""
    if len(new_email) < 3 or "@" not in new_email:
        raise HTTPException(status_code=400, detail="Invalid email address")

    existing_email = db.query(User).filter(User.email == new_email, User.id != user.id).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    user.email = new_email
    db.commit()

    return {
        "ok": True,
        "message": "Email updated successfully",
        "email": user.email
    }

# Rate limiter for password reset requests
password_reset_limiter = RateLimiter(max_requests=3, window_seconds=3600)  # 3 requests per hour

@app.post("/api/auth/forgot-password")
async def request_password_reset(
    request: Request,
    username_or_email: str = Form(...),
    db: Session = Depends(get_db)
):
    """Request a password reset token be sent to the user's email"""
    # Rate limiting by IP
    client_ip = request.client.host if request.client else "unknown"
    if not password_reset_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Too many password reset requests. Please try again later.")

    # Find user by username or email
    user = db.query(User).filter(
        (User.username == username_or_email) | (User.email == username_or_email)
    ).first()

    # Always return success to prevent user enumeration
    response_message = "If an account exists with that username or email, a password reset link has been sent."

    if user and user.email:
        # Generate reset token
        import secrets
        reset_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        # Store token in database
        password_reset = PasswordResetToken(
            user_id=user.id,
            token=reset_token,
            expires_at=expires_at,
            ip_address=client_ip
        )
        db.add(password_reset)
        db.commit()

        # Send reset email asynchronously
        try:
            base_url = config.server_url
            await email_service.send_password_reset_email(
                to_email=user.email,
                reset_token=reset_token,
                username=user.username,
                base_url=base_url
            )
            print(f"[PASSWORD RESET] Email sent to {user.email[:3]}***")
        except Exception as e:
            print(f"[PASSWORD RESET] Failed to send email: {str(e)}")
            # Don't reveal email sending failures to the user

    return {"ok": True, "message": response_message}

@app.post("/api/auth/reset-password")
async def reset_password(
    token: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Reset password using a valid token"""
    # Find the token
    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == token,
        PasswordResetToken.used == False,
        PasswordResetToken.expires_at > datetime.now(timezone.utc)
    ).first()

    if not reset_token:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    # Get the user
    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    # Update password
    user.password_hash = hash_password(new_password)

    # Mark token as used
    reset_token.used = True
    reset_token.used_at = datetime.now(timezone.utc)

    db.commit()

    # Send confirmation email
    if user.email:
        try:
            await email_service.send_password_reset_success_email(
                to_email=user.email,
                username=user.username
            )
        except Exception as e:
            print(f"[PASSWORD RESET] Failed to send success email: {str(e)}")

    # Generate new JWT token for auto-login
    from auth import create_jwt_token
    access_token = create_jwt_token(user.id, user.username)

    return {
        "ok": True,
        "message": "Password reset successfully",
        "access_token": access_token,
        "user": {
            "id": user.id,
            "username": user.username,
            "created_at": user.created_at.isoformat() + "Z"
        }
    }

@app.get("/api/auth/verify-reset-token")
async def verify_reset_token(
    token: str,
    db: Session = Depends(get_db)
):
    """Verify if a reset token is valid"""
    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == token,
        PasswordResetToken.used == False,
        PasswordResetToken.expires_at > datetime.now(timezone.utc)
    ).first()

    if not reset_token:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    # Get user info
    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    return {
        "ok": True,
        "username": user.username,
        "expires_at": reset_token.expires_at.isoformat() + "Z"
    }

# Admin endpoint to generate reset token manually
@app.post("/api/auth/admin/generate-reset-token")
async def admin_generate_reset_token(
    username: str = Form(...),
    x_admin: str = Header(None),
    db: Session = Depends(get_db)
):
    """Admin endpoint to generate a password reset token for a user"""
    if not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=401, detail="Admin key required")

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate reset token
    import secrets
    reset_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=2)  # Admin tokens last 2 hours

    # Store token in database
    password_reset = PasswordResetToken(
        user_id=user.id,
        token=reset_token,
        expires_at=expires_at,
        ip_address="admin"
    )
    db.add(password_reset)
    db.commit()

    return {
        "ok": True,
        "token": reset_token,
        "username": user.username,
        "expires_at": expires_at.isoformat() + "Z",
        "reset_url": f"{os.getenv('BASE_URL', 'http://localhost:3000')}/reset-password?token={reset_token}"
    }

@app.post("/v1/register", response_model=RegisterResponse)
async def register_device(
    payload: dict,
    request: Request,
    admin_key_verified = Depends(verify_admin_key_header),
    db: Session = Depends(get_db)
):
    """
    Register a device using admin key authentication.

    Uses a semaphore-based queue to limit concurrent registrations to prevent
    connection pool saturation during bulk deployments.
    """
    from models import EnrollmentEvent

    alias = payload.get("alias")
    hardware_id = payload.get("hardware_id", "unknown")

    if not alias:
        raise HTTPException(status_code=422, detail="alias is required")

    # Validate alias length
    if len(alias) > 200:
        raise HTTPException(status_code=422, detail="alias must be 200 characters or less")
    if len(alias) < 1:
        raise HTTPException(status_code=422, detail="alias must be at least 1 character")

    queue_start = time.time()

    # Acquire semaphore to limit concurrent registrations
    async with registration_semaphore:
        queue_wait_ms = (time.time() - queue_start) * 1000

        # Track queue metrics
        queue_depth = REGISTRATION_CONCURRENCY_LIMIT - registration_semaphore._value
        metrics.observe_histogram("registration_queue_wait_ms", queue_wait_ms)
        metrics.set_gauge("registration_queue_depth", queue_depth)
        metrics.set_gauge("registration_active_count", REGISTRATION_CONCURRENCY_LIMIT - registration_semaphore._value)

        structured_logger.log_event(
            "register.request",
            alias=alias,
            auth_method="admin_key",
            route="/v1/register",
            queue_wait_ms=round(queue_wait_ms, 2),
            queue_depth=queue_depth
        )

        try:
            # Check for duplicate alias using database-level locking to prevent race conditions
            # Use SELECT FOR UPDATE to lock the row if it exists
            from sqlalchemy import text
            existing_device = db.query(Device).filter(
                Device.alias == alias
            ).with_for_update(nowait=True).first()

            if existing_device:
                raise HTTPException(
                    status_code=409,
                    detail=f"Device with alias '{alias}' already exists"
                )

            # Generate device token
            device_token = generate_device_token()
            token_hash = hash_token(device_token)
            token_id = compute_token_id(device_token)

            import uuid
            device_id = str(uuid.uuid4())

            # Get monitoring defaults to seed new device
            defaults = monitoring_defaults_cache.get_defaults(db)

            # Create device with monitoring defaults
            device = Device(
                id=device_id,
                alias=alias,
                token_hash=token_hash,
                token_id=token_id,
                created_at=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
                monitor_enabled=defaults["enabled"],
                monitored_package=defaults["package"],
                monitored_app_name=defaults["alias"],
                monitored_threshold_min=defaults["threshold_min"]
            )

            db.add(device)

            # Log enrollment event (using admin key authentication)
            event = EnrollmentEvent(
                event_type='device.registered',
                token_id="admin_key",
                alias=alias,
                device_id=device_id,
                metadata={"hardware_id": hardware_id, "auth_method": "admin_key"}
            )
            db.add(event)

            db.commit()

            # Invalidate cache on device registration
            response_cache.invalidate("/v1/metrics")
            response_cache.invalidate("/v1/devices")

            log_device_event(db, device_id, "device_enrolled", {
                "alias": alias,
                "auth_method": "admin_key"
            })

            structured_logger.log_event(
                "register.success",
                device_id=device_id,
                alias=alias,
                auth_method="admin_key",
                token_id=token_id[-4:] if token_id else None,
                result="success",
                queue_wait_ms=round(queue_wait_ms, 2)
        )

            return RegisterResponse(device_token=device_token, device_id=device_id)

        except HTTPException:
            raise
        except Exception as e:
            structured_logger.log_event(
                "register.fail",
                level="ERROR",
                alias=alias,
                result="error",
                error=str(e)
            )
            raise

@app.post("/v1/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    request: Request,
    payload: HeartbeatPayload,
    device: Device = Depends(verify_device_token),
    db: Session = Depends(get_db)
):
    # Check if device token has been revoked (device deleted)
    if device.token_revoked_at:
        structured_logger.log_event(
            "heartbeat.rejected",
            level="WARN",
            device_id=device.id,
            reason="device_deleted",
            revoked_at=device.token_revoked_at.isoformat()
        )
        raise HTTPException(
            status_code=410,
            detail={"reason": "device_deleted", "message": "Device has been deleted"}
        )

    # Extract heartbeat telemetry for logging
    battery_pct = payload.battery.pct if payload.battery else None
    network_type = payload.network.transport if payload.network else None
    uptime_s = payload.system.uptime_seconds if payload.system else None

    structured_logger.log_event(
        "heartbeat.ingest",
        device_id=device.id,
        alias=device.alias,
        battery_pct=battery_pct,
        network_type=network_type,
        uptime_s=uptime_s,
        status="received"
    )

    metrics.inc_counter("heartbeats_ingested_total")

    print(f"[HEARTBEAT] Received from {device.alias}")

    # Parse previous status for comparison
    prev_status = json.loads(device.last_status) if device.last_status else {}

    # PERFORMANCE OPTIMIZATION: Use async event queue instead of synchronous logging
    from background_tasks import background_tasks

    # Check for status changes (online/offline)
    was_offline = False
    offline_seconds = 0
    if device.last_seen:
        offline_seconds = (datetime.now(timezone.utc) - ensure_utc(device.last_seen)).total_seconds()
        heartbeat_interval = alert_config.HEARTBEAT_INTERVAL_SECONDS
        was_offline = offline_seconds > heartbeat_interval * 3

    if was_offline:
        # Async event logging - doesn't block the response
        background_tasks.event_queue.enqueue(device.id, "status_change", {
            "from": "offline",
            "to": "online",
            "offline_duration_seconds": int(offline_seconds)
        })

    # Check for battery level changes
    prev_battery = prev_status.get("battery", {}).get("pct")
    new_battery = payload.battery.pct if payload.battery else None
    if prev_battery is not None and new_battery is not None:
        if prev_battery >= 20 and new_battery < 20:
            background_tasks.event_queue.enqueue(device.id, "battery_low", {"level": new_battery})
        elif prev_battery >= 15 and new_battery < 15:
            background_tasks.event_queue.enqueue(device.id, "battery_critical", {"level": new_battery})

    # Check for network changes
    prev_network = prev_status.get("network", {}).get("transport")
    new_network = payload.network.transport if payload.network else None
    if prev_network and new_network and prev_network != new_network:
        background_tasks.event_queue.enqueue(device.id, "network_change", {
            "from": prev_network,
            "to": new_network,
            "ssid": payload.network.ssid if new_network == "wifi" else None,
            "carrier": payload.network.carrier if new_network == "cellular" else None
        })

    device.last_seen = datetime.now(timezone.utc)
    # Update device.app_version from heartbeat payload to keep dashboard table in sync
    if payload.app_version:
        device.app_version = payload.app_version

    if payload.fcm_token:
        device.fcm_token = payload.fcm_token

    if payload.system:
        device.model = payload.system.model
        device.manufacturer = payload.system.manufacturer
        device.android_version = payload.system.android_version
        device.sdk_int = payload.system.sdk_int
        device.build_id = payload.system.build_id

    if hasattr(payload, 'is_device_owner') and payload.is_device_owner is not None:
        device.is_device_owner = payload.is_device_owner

    # PERFORMANCE OPTIMIZATION: Persist heartbeat to partitioned table + dual-write to device_last_status
    from db_utils import record_heartbeat_with_bucketing

    # Extract Unity app info (ALWAYS from com.unitynetwork.unityapp)
    unity_running = None
    unity_pkg_version = None
    unity_app_info = payload.app_versions.get("com.unitynetwork.unityapp")
    if unity_app_info and unity_app_info.installed:
        unity_pkg_version = unity_app_info.version_name
        # Android agent sends monitored_foreground_recent_s specifically for Unity
        # Use this directly to determine running status (10 minute threshold = 600 seconds)
        fg_seconds = payload.monitored_foreground_recent_s if hasattr(payload, 'monitored_foreground_recent_s') else None
        if fg_seconds is not None:
            # Unity is running if it was in foreground within the last 10 minutes
            unity_running = fg_seconds < 600
        else:
            # No foreground data available - status unknown
            unity_running = None

    heartbeat_data = {
        'ip': str(payload.network.ip) if payload.network and payload.network.ip else None,
        'status': 'ok',
        'battery_pct': battery_pct,
        'plugged': payload.battery.charging if payload.battery else None,
        'temp_c': int(payload.battery.temperature_c) if payload.battery else None,
        'network_type': network_type,
        'signal_dbm': None,  # Not available in current schema
        'uptime_s': uptime_s,
        'ram_used_mb': payload.memory.total_ram_mb - payload.memory.avail_ram_mb if payload.memory else None,
        'unity_pkg_version': unity_pkg_version,
        'unity_running': unity_running,
        'agent_version': payload.app_version
    }

    # Track heartbeat write latency
    hb_write_start = time.time()
    hb_result = record_heartbeat_with_bucketing(db, device.id, heartbeat_data, bucket_seconds=10)
    hb_write_latency_ms = (time.time() - hb_write_start) * 1000
    metrics.observe_histogram("hb_write_latency_ms", hb_write_latency_ms, {})

    if hb_result['created']:
        metrics.inc_counter("hb_writes_total")
    else:
        metrics.inc_counter("hb_dedupe_total")

    if hb_result.get('last_status_updated'):
        metrics.inc_counter("last_status_upserts_total")

    if payload.is_ping_response and payload.ping_request_id:
        if device.ping_request_id == payload.ping_request_id and device.last_ping_sent:
            device.last_ping_response = datetime.now(timezone.utc)
            latency_ms = int((device.last_ping_response - ensure_utc(device.last_ping_sent)).total_seconds() * 1000)
            print(f"[FCM-PING] ✓ Response from {device.alias}: {latency_ms}ms latency")
            # Async event logging
            background_tasks.event_queue.enqueue(device.id, "ping_response", {"latency_ms": latency_ms})
            # Clear ping state after successful response
            device.ping_request_id = None

    # Service monitoring evaluator: Determine if monitored service is up/down
    # Get effective monitoring settings (device or global defaults)
    from monitoring_helpers import get_effective_monitoring_settings
    monitoring_settings = get_effective_monitoring_settings(db, device)

    service_up = None
    monitored_foreground_recent_s = None

    if monitoring_settings["enabled"] and monitoring_settings["package"]:
        # Check if the monitored app is actually installed
        app_info = payload.app_versions.get(monitoring_settings["package"]) if payload.app_versions else None
        is_app_installed = app_info and app_info.installed if app_info else None

        # Get foreground recency from unified field (monitored_foreground_recent_s)
        # This field now tracks Unity app activity
        monitored_foreground_recent_s = payload.monitored_foreground_recent_s

        print(f"[MONITORING-DEBUG] {device.alias}: monitored_foreground_recent_s={monitored_foreground_recent_s}")

        # Treat -1 as sentinel value for "not available" (normalize to None)
        if monitored_foreground_recent_s is not None and monitored_foreground_recent_s < 0:
            print(f"[MONITORING-DEBUG] {device.alias}: Normalizing {monitored_foreground_recent_s} to None (data unavailable)")
            monitored_foreground_recent_s = None

        # Evaluate service status only if app is installed
        if not is_app_installed:
            # App not installed - service status is unknown
            service_up = None
            structured_logger.log_event(
                "monitoring.evaluate.not_installed",
                level="WARN",
                device_id=device.id,
                alias=device.alias,
                monitored_package=monitoring_settings["package"],
                reason="app_not_installed",
                source=monitoring_settings["source"]
            )
        elif monitored_foreground_recent_s is not None:
            # App installed and we have foreground data - evaluate status
            threshold_seconds = monitoring_settings["threshold_min"] * 60
            service_up = monitored_foreground_recent_s <= threshold_seconds

            structured_logger.log_event(
                "monitoring.evaluate",
                device_id=device.id,
                alias=device.alias,
                monitored_package=monitoring_settings["package"],
                foreground_recent_s=monitored_foreground_recent_s,
                threshold_s=threshold_seconds,
                service_up=service_up,
                source=monitoring_settings["source"]
            )
        else:
            # App installed but foreground data not available - service status is unknown
            service_up = None
            structured_logger.log_event(
                "monitoring.evaluate.unknown",
                level="WARN",
                device_id=device.id,
                alias=device.alias,
                monitored_package=monitoring_settings["package"],
                reason="usage_access_missing",
                source=monitoring_settings["source"]
            )

    # Update DeviceLastStatus with service monitoring data
    last_status_record = db.query(DeviceLastStatus).filter(DeviceLastStatus.device_id == device.id).first()
    if last_status_record:
        # Track previous state for transition detection
        prev_service_up = last_status_record.service_up

        last_status_record.service_up = service_up
        last_status_record.monitored_foreground_recent_s = monitored_foreground_recent_s
        last_status_record.monitored_package = monitoring_settings["package"] if monitoring_settings["enabled"] else None
        last_status_record.monitored_threshold_min = monitoring_settings["threshold_min"] if monitoring_settings["enabled"] else None

        # Detect service state transitions for logging
        if monitoring_settings["enabled"] and prev_service_up is not None and service_up is not None:
            if prev_service_up and not service_up:
                # Service went DOWN
                structured_logger.log_event(
                    "monitoring.service_down",
                    device_id=device.id,
                    alias=device.alias,
                    monitored_package=monitoring_settings["package"],
                    monitored_app_name=monitoring_settings["alias"],
                    foreground_recent_s=monitored_foreground_recent_s,
                    threshold_min=monitoring_settings["threshold_min"],
                    source=monitoring_settings["source"]
                )

            elif not prev_service_up and service_up:
                # Service RECOVERED
                structured_logger.log_event(
                    "monitoring.service_up",
                    device_id=device.id,
                    alias=device.alias,
                    monitored_package=monitoring_settings["package"],
                    monitored_app_name=monitoring_settings["alias"],
                    foreground_recent_s=monitored_foreground_recent_s,
                    source=monitoring_settings["source"]
                )

        # Metrics for monitoring
        if monitoring_settings["enabled"] and service_up is not None:
            metrics.set_gauge("service_up_devices", 1 if service_up else 0, {"device_id": device.id})

    # Enrich last_status with computed monitoring data for frontend
    # Use exclude_none=False to ensure network.ssid and network.carrier are always present (even when None)
    # This allows frontend nullish coalescing to work correctly
    last_status_dict = payload.dict(exclude_none=False)
    last_status_dict["service_up"] = service_up
    last_status_dict["monitored_package"] = monitoring_settings["package"] if monitoring_settings["enabled"] else None
    last_status_dict["monitored_foreground_recent_s"] = monitored_foreground_recent_s
    last_status_dict["monitored_threshold_min"] = monitoring_settings["threshold_min"] if monitoring_settings["enabled"] else None

    # Add unity/agent status for frontend
    # Unity field ALWAYS reflects com.unitynetwork.unityapp, NOT the monitored package
    # Defensive check: ensure app_versions exists before accessing it
    if not payload.app_versions:
        print(f"[UNITY-STATUS-DEBUG] {device.alias}: payload.app_versions is None or empty - defaulting to not_installed")
        last_status_dict["unity"] = {
            "package": "com.unitynetwork.unityapp",
            "status": "not_installed"
        }
    else:
        unity_app_info = payload.app_versions.get("com.unitynetwork.unityapp")

        if not unity_app_info:
            print(f"[UNITY-STATUS-DEBUG] {device.alias}: com.unitynetwork.unityapp key not found in app_versions (available keys: {list(payload.app_versions.keys())}) - defaulting to not_installed")
            last_status_dict["unity"] = {
                "package": "com.unitynetwork.unityapp",
                "status": "not_installed"
            }
        elif unity_app_info.installed:
            # Unity app is installed - determine running status using foreground recency
            # Android agent sends monitored_foreground_recent_s specifically for Unity
            # Use this directly with a 10 minute threshold (600 seconds)
            unity_fg_seconds = payload.monitored_foreground_recent_s if hasattr(payload, 'monitored_foreground_recent_s') else None

            if unity_fg_seconds is not None:
                # Unity is running if it was in foreground within the last 10 minutes
                if unity_fg_seconds < 600:
                    unity_status = "running"
                else:
                    unity_status = "down"
                print(f"[UNITY-STATUS-DEBUG] {device.alias}: Unity installed, fg_seconds={unity_fg_seconds}, status={unity_status}")
            else:
                # No foreground data available - app is installed but not running
                unity_status = "down"
                print(f"[UNITY-STATUS-DEBUG] {device.alias}: Unity installed but no foreground data - status=down")

            last_status_dict["unity"] = {
                "package": "com.unitynetwork.unityapp",
                "version": unity_app_info.version_name or "unknown",
                "status": unity_status
            }
        else:
            # Unity app not installed
            print(f"[UNITY-STATUS-DEBUG] {device.alias}: Unity app not installed (installed=False)")
            last_status_dict["unity"] = {
                "package": "com.unitynetwork.unityapp",
                "status": "not_installed"
            }

    # Agent field always reflects MDM agent version (always running if sending heartbeats)
    last_status_dict["agent"] = {
        "version": payload.app_version or "unknown"
    }

    device.last_status = json.dumps(last_status_dict)

    # Auto-relaunch logic: Check if monitored app is down and auto-relaunch is enabled
    print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: auto_relaunch_enabled={device.auto_relaunch_enabled}, monitored_package={device.monitored_package}")
    if payload.app_versions:
        all_packages = list(payload.app_versions.keys())
        print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: Available packages in payload: {all_packages}")
        for pkg_name, pkg_info in payload.app_versions.items():
            print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: Package '{pkg_name}': installed={pkg_info.installed if pkg_info else 'N/A'}")
    else:
        print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: No app_versions in payload")

    if device.auto_relaunch_enabled and device.monitored_package:
        # Android app now sends full package names as keys (e.g., com.unitynetwork.unityapp)
        # Try primary lookup first, then fallback to com.unitynetwork.unityapp for consistency
        app_info = payload.app_versions.get(device.monitored_package) if payload.app_versions else None
        package_used = device.monitored_package
        used_fallback = False

        # If primary lookup failed, try fallback to com.unitynetwork.unityapp
        if not app_info and device.monitored_package != "com.unitynetwork.unityapp":
            fallback_package = "com.unitynetwork.unityapp"
            app_info = payload.app_versions.get(fallback_package) if payload.app_versions else None
            if app_info:
                package_used = fallback_package
                used_fallback = True
                print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: Primary package '{device.monitored_package}' not found, using fallback '{fallback_package}'")

        if app_info:
            print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: Found app_info for '{package_used}' (fallback={used_fallback}): installed={app_info.installed}")
        else:
            print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: No app_info found for '{device.monitored_package}' or fallback 'com.unitynetwork.unityapp'")

        # Check if app is installed
        if app_info and app_info.installed:
            # Check if app is running using monitored_foreground_recent_s
            # Use the same monitoring threshold as service monitoring evaluation
            fg_seconds = payload.monitored_foreground_recent_s

            # Treat -1 as sentinel value for "not available" (normalize to None)
            if fg_seconds is not None and fg_seconds < 0:
                fg_seconds = None

            if fg_seconds is not None:
                # We have valid foreground data - use monitoring threshold to determine if running
                # Fallback to device threshold or default 10 minutes if monitoring settings unavailable
                threshold_min = monitoring_settings.get("threshold_min") or device.monitored_threshold_min or 10
                threshold_seconds = threshold_min * 60
                is_app_running = fg_seconds <= threshold_seconds
                print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: foreground_recent_seconds={fg_seconds}, threshold={threshold_seconds}s ({threshold_min}min), is_app_running={is_app_running}")
            else:
                # No foreground data available but app is installed - assume down to trigger relaunch
                is_app_running = False
                print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: No foreground data available, app is installed - assuming down (is_app_running=False)")
        else:
            # App not installed or app_info not found - don't try to relaunch
            is_app_running = True  # Prevent relaunch loop for uninstalled apps
            if not app_info:
                print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: App info not found in payload - skipping relaunch (package '{device.monitored_package}' not in app_versions)")
            else:
                print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: App not installed (installed=False) - skipping relaunch")

        # If app is not running, trigger FCM relaunch
        fcm_token_status = "present" if device.fcm_token else "MISSING"
        print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: Final check - is_app_running={is_app_running}, fcm_token={fcm_token_status}")

        if not is_app_running:
            if not device.fcm_token:
                print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: Cannot trigger relaunch - FCM token is MISSING")
            else:
                try:
                    print(f"[AUTO-RELAUNCH] {device.alias}: {package_used} is down, sending relaunch command (using package: {package_used})")
                    asyncio.create_task(send_fcm_launch_app(device.fcm_token, package_used, device.id))
                    log_device_event(db, device.id, "auto_relaunch_triggered", {
                        "package": package_used,
                        "used_fallback": used_fallback,
                        "original_package": device.monitored_package
                    })
                except Exception as e:
                    print(f"[AUTO-RELAUNCH] Failed to send relaunch for {device.alias}: {e}")
        else:
            print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: App is running (is_app_running=True) - skipping relaunch")
    else:
        if not device.auto_relaunch_enabled:
            print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: Auto-relaunch is DISABLED")
        if not device.monitored_package:
            print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: No monitored package configured")

    db.commit()

    # Invalidate cache on device update
    response_cache.invalidate("/v1/metrics")
    response_cache.invalidate("/v1/devices")

    await manager.broadcast({
        "type": "device_update",
        "device_id": device.id
    })

    return HeartbeatResponse(ok=True)

@app.post("/v1/action-result")
async def action_result(
    request: Request,
    payload: ActionResultRequest,
    device: Device = Depends(verify_device_token),
    db: Session = Depends(get_db)
):
    """
    Receive action result from device after executing FCM command.
    Uses authenticated device.id as the authoritative source (not payload.device_id).
    """
    # Use authenticated device.id - don't trust client-provided device_id
    # Log if there's a mismatch for debugging (but don't reject)
    if payload.device_id and payload.device_id != device.id:
        structured_logger.log_event(
            "result.device_id_mismatch",
            level="WARN",
            payload_device_id=payload.device_id,
            auth_device_id=device.id,
            message="Using authenticated device.id"
        )

    from models import FcmDispatch

    dispatch = db.query(FcmDispatch).filter(
        FcmDispatch.request_id == payload.request_id
    ).first()

    if not dispatch:
        structured_logger.log_event(
            "result.unknown",
            level="WARN",
            request_id=payload.request_id,
            device_id=device.id,
            action=payload.action,
            outcome=payload.outcome
        )
        raise HTTPException(status_code=404, detail="request_id not found")

    if dispatch.completed_at:
        structured_logger.log_event(
            "result.duplicate",
            request_id=payload.request_id,
            device_id=device.id,
            action=payload.action,
            outcome=payload.outcome,
            message="idempotent_repost"
        )
        return {"ok": True, "message": "Already processed (idempotent)"}

    dispatch.completed_at = payload.finished_at
    dispatch.result = payload.outcome
    dispatch.result_message = payload.message

    db.commit()

    structured_logger.log_event(
        "result.posted",
        request_id=payload.request_id,
        device_id=device.id,
        action=payload.action,
        outcome=payload.outcome,
        message=payload.message
    )

    log_device_event(db, device.id, "action_completed", {
        "request_id": payload.request_id,
        "action": payload.action,
        "outcome": payload.outcome,
        "message": payload.message
    })

    return {"ok": True, "message": "Result recorded"}

@app.get("/v1/devices/{device_id}/events")
async def get_device_events(
    device_id: str,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    events = db.query(DeviceEvent).filter(
        DeviceEvent.device_id == device_id
    ).order_by(
        DeviceEvent.timestamp.desc()
    ).limit(limit).all()

    return [{
        "id": event.id,
        "event_type": event.event_type,
        "timestamp": event.timestamp.isoformat() + "Z",
        "details": json.loads(event.details) if event.details else None
    } for event in events]

@app.get("/v1/metrics")
async def get_metrics(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get device metrics (total, online, offline, low battery counts).

    NOTE: This endpoint is exempt from rate limiting as it's a read-only
    dashboard endpoint that's heavily cached (60 second TTL). It should never
    be rate limited to ensure dashboard functionality.
    """
    # Check cache first (60 second TTL)
    cache_key = make_cache_key("/v1/metrics")
    cached_result = response_cache.get(cache_key, ttl_seconds=60)
    if cached_result is not None:
        return cached_result

    total_devices = db.query(func.count(Device.id)).scalar()

    heartbeat_interval = alert_config.HEARTBEAT_INTERVAL_SECONDS
    offline_threshold = datetime.now(timezone.utc) - timedelta(seconds=heartbeat_interval * 3)

    # Optimized: Use device_last_status table if available for better performance
    if READ_FROM_LAST_STATUS:
        # Fast path: Use device_last_status table with SQL aggregation
        # Count online devices using device_last_status
        online_count_query = text("""
            SELECT COUNT(*) 
            FROM device_last_status dls
            WHERE dls.last_ts >= :offline_threshold
        """)
        online_count = db.execute(online_count_query, {"offline_threshold": offline_threshold}).scalar() or 0

        offline_count = total_devices - online_count

        # Count low battery devices using SQL aggregation (battery_pct < 15)
        low_battery_query = text("""
            SELECT COUNT(*) 
            FROM device_last_status dls
            WHERE dls.battery_pct IS NOT NULL AND dls.battery_pct < 15
        """)
        low_battery_count = db.execute(low_battery_query).scalar() or 0
    else:
        # Legacy path: Use devices table
        online_count = db.query(func.count(Device.id)).filter(
            Device.last_seen >= offline_threshold
        ).scalar() or 0

        offline_count = total_devices - online_count

        # For low battery, parse JSON from last_status field
        low_battery_count = 0
        battery_statuses = db.query(Device.last_status).filter(
            Device.last_status.isnot(None)
        ).all()

        for (status_json,) in battery_statuses:
            try:
                status = json.loads(status_json)
                battery = status.get("battery", {}).get("level", 100)
                if battery < 15:
                    low_battery_count += 1
            except:
                pass

    result = {
        "total": total_devices,
        "online": online_count,
        "offline": offline_count,
        "low_battery": low_battery_count
    }

    # Cache the result
    response_cache.set(cache_key, result, ttl_seconds=60, path="/v1/metrics")

    return result

@app.get("/v1/devices")
async def list_devices(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List devices with pagination.

    NOTE: This endpoint is exempt from rate limiting as it's a read-only
    dashboard endpoint that's cached (5 minute TTL for first page). It should
    never be rate limited to ensure dashboard functionality.
    """
    # Cache first page only (5 minute TTL) - most common query
    cache_key = None
    if page == 1 and limit == 25:
        cache_key = make_cache_key("/v1/devices", {"page": 1, "limit": 25})
        cached_result = response_cache.get(cache_key, ttl_seconds=300)
        if cached_result is not None:
            return cached_result

    total_count = db.query(func.count(Device.id)).scalar()

    offset = (page - 1) * limit
    devices = db.query(Device).order_by(Device.last_seen.desc()).offset(offset).limit(limit).all()

    # Batch fetch device statuses if using fast reads
    device_statuses = {}
    if READ_FROM_LAST_STATUS:
        device_ids = [d.id for d in devices]
        device_statuses = fast_reads.get_all_device_statuses_fast(db, device_ids)

    result = []
    heartbeat_interval = alert_config.HEARTBEAT_INTERVAL_SECONDS

    for device in devices:
        # Determine online/offline status
        if READ_FROM_LAST_STATUS and device.id in device_statuses:
            # Fast path: O(1) lookup from device_last_status
            fast_status = device_statuses[device.id]
            last_seen = fast_status["last_ts"]
            if last_seen:
                offline_seconds = (datetime.now(timezone.utc) - ensure_utc(last_seen)).total_seconds()
                status = "offline" if offline_seconds > heartbeat_interval * 3 else "online"
            else:
                status = "offline"
        else:
            # Legacy path: use device.last_seen
            status = "online"
            if device.last_seen:
                offline_seconds = (datetime.now(timezone.utc) - ensure_utc(device.last_seen)).total_seconds()
                if offline_seconds > heartbeat_interval * 3:
                    status = "offline"

        ping_status = None
        if device.last_ping_sent:
            if device.last_ping_response and ensure_utc(device.last_ping_response) > ensure_utc(device.last_ping_sent):
                latency_ms = int((ensure_utc(device.last_ping_response) - ensure_utc(device.last_ping_sent)).total_seconds() * 1000)
                ping_status = {
                    "status": "replied",
                    "latency_ms": latency_ms
                }
            else:
                time_since_ping = (datetime.now(timezone.utc) - ensure_utc(device.last_ping_sent)).total_seconds()
                if time_since_ping > 60:
                    ping_status = {
                        "status": "no_reply",
                        "timeout": True
                    }
                else:
                    ping_status = {
                        "status": "waiting",
                        "elapsed_seconds": int(time_since_ping)
                    }

        # Handle last_status - it could be a string (JSON) or already a dict
        last_status_data = None
        if device.last_status:
            if isinstance(device.last_status, str):
                try:
                    last_status_data = json.loads(device.last_status)
                except:
                    last_status_data = None
            elif isinstance(device.last_status, dict):
                last_status_data = device.last_status

        result.append({
            "id": device.id,
            "alias": device.alias,
            "app_version": device.app_version,
            "last_seen": device.last_seen.isoformat() + "Z" if device.last_seen else None,
            "created_at": device.created_at.isoformat() + "Z" if device.created_at else None,
            "status": status,
            "last_status": last_status_data,
            "ping_status": ping_status,
            "model": device.model,
            "manufacturer": device.manufacturer,
            "android_version": device.android_version,
            "sdk_int": device.sdk_int,
            "build_id": device.build_id,
            "is_device_owner": device.is_device_owner,
            "monitored_package": device.monitored_package,
            "monitored_app_name": device.monitored_app_name,
            "auto_relaunch_enabled": device.auto_relaunch_enabled
        })

    total_pages = (total_count + limit - 1) // limit

    response = {
        "devices": result,
        "pagination": {
            "page": page,
            "limit": limit,
            "total_count": total_count,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }
    }

    # Cache first page result
    if cache_key:
        response_cache.set(cache_key, response, ttl_seconds=300, path="/v1/devices")

    return response

@app.get("/v1/devices/{device_id}")
async def get_device(
    device_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    ping_status = None
    if device.last_ping_sent:
        if device.last_ping_response and ensure_utc(device.last_ping_response) > ensure_utc(device.last_ping_sent):
            latency_ms = int((ensure_utc(device.last_ping_response) - ensure_utc(device.last_ping_sent)).total_seconds() * 1000)
            ping_status = {
                "status": "replied",
                "latency_ms": latency_ms,
                "sent_at": ensure_utc(device.last_ping_sent).isoformat(),
                "response_at": ensure_utc(device.last_ping_response).isoformat()
            }
        else:
            time_since_ping = (datetime.now(timezone.utc) - ensure_utc(device.last_ping_sent)).total_seconds()
            if time_since_ping > 60:
                ping_status = {
                    "status": "no_reply",
                    "sent_at": device.last_ping_sent.isoformat() + "Z",
                    "timeout": True
                }
            else:
                ping_status = {
                    "status": "waiting",
                    "sent_at": device.last_ping_sent.isoformat() + "Z",
                    "elapsed_seconds": int(time_since_ping)
                }

    return {
        "id": device.id,
        "alias": device.alias,
        "app_version": device.app_version,
        "last_seen": device.last_seen.isoformat() + "Z" if device.last_seen else None,
        "created_at": device.created_at.isoformat() + "Z" if device.created_at else None,
        "last_status": json.loads(device.last_status) if device.last_status else None,
        "ping_status": ping_status,
        "is_device_owner": device.is_device_owner,
        "monitored_package": device.monitored_package,
        "monitored_app_name": device.monitored_app_name,
        "auto_relaunch_enabled": device.auto_relaunch_enabled
    }

@app.get("/v1/devices/{device_id}/clipboard")
async def get_device_clipboard(
    device_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return {
        "text": device.clipboard_content,
        "updated_at": device.clipboard_updated_at.isoformat() + "Z" if device.clipboard_updated_at else None
    }

@app.post("/v1/devices/{device_id}/clipboard")
async def update_device_clipboard(
    device_id: str,
    request: dict,
    db: Session = Depends(get_db)
):
    """Called by Android device to update its clipboard content"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.clipboard_content = request.get("text", "")
    device.clipboard_updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"ok": True}

@app.delete("/v1/devices/{device_id}")
async def delete_device(
    device_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device_alias = device.alias
    log_device_event(db, device.id, "device_deleted", {"alias": device_alias})

    # Delete all associated events
    db.query(DeviceEvent).filter(DeviceEvent.device_id == device_id).delete()

    # Delete device
    db.delete(device)
    db.commit()

    # Invalidate cache on device deletion
    response_cache.invalidate("/v1/metrics")
    response_cache.invalidate("/v1/devices")

    return {"ok": True, "message": f"Device {device_alias} deleted successfully"}

@app.get("/admin/devices")
async def get_admin_devices(
    alias: Optional[str] = Query(None),
    x_admin_key: Optional[str] = Header(None, alias="x-admin-key"),
    db: Session = Depends(get_db)
):
    """
    Get devices with optional alias filtering.
    Used by enrollment scripts for device verification.
    Requires admin key authentication.
    """
    if not verify_admin_key(x_admin_key or ""):
        raise HTTPException(status_code=403, detail="Admin key required")

    query = db.query(Device)

    if alias:
        query = query.filter(Device.alias == alias)

    devices = query.all()

    heartbeat_interval = alert_config.HEARTBEAT_INTERVAL_SECONDS
    offline_threshold_seconds = heartbeat_interval * 3

    result = []
    for device in devices:
        if device.last_seen:
            offline_seconds = (datetime.now(timezone.utc) - ensure_utc(device.last_seen)).total_seconds()
            status = "online" if offline_seconds <= offline_threshold_seconds else "offline"
        else:
            status = "offline"

        result.append({
            "id": device.id,
            "alias": device.alias,
            "last_seen": device.last_seen.isoformat() + "Z" if device.last_seen else None,
            "model": device.model,
            "manufacturer": device.manufacturer,
            "status": status
        })

    return result

@app.get("/admin/devices/last-alias")
async def get_last_alias(
    x_admin: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Get the highest D# alias number for batch enrollment continuity.
    Returns the next available alias number.
    Requires admin key authentication via X-Admin header (auto-injected by frontend proxy).
    """
    if not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=403, detail="Admin key required")

    # Get all devices
    devices = db.query(Device).all()

    # Find highest D# alias
    max_num = 0
    for device in devices:
        if device.alias and device.alias.startswith("D"):
            try:
                # Extract number from D## format
                num_str = device.alias[1:]  # Remove 'D'
                num = int(num_str)
                if num > max_num:
                    max_num = num
            except ValueError:
                # Skip aliases that don't match D## pattern
                continue

    return {
        "last_alias": f"D{max_num:02d}" if max_num > 0 else None,
        "last_number": max_num,
        "next_alias": f"D{(max_num + 1):02d}",
        "next_number": max_num + 1
    }

@app.get("/admin/config/admin-key")
async def get_admin_key(
    x_admin: str = Header(None)
):
    """
    Get the admin key for batch enrollment script generation.
    Requires admin key authentication via X-Admin header (auto-injected by frontend proxy).
    """
    if not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=403, detail="Admin key required")

    return {
        "admin_key": config.get_admin_key()
    }

@app.post("/admin/devices/selection")
async def create_selection(
    request: Request,
    x_admin: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Create a device selection snapshot for bulk operations.
    Returns selection_id, total_count, and expires_at.
    """
    if not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=403, detail="Admin key required (scope: device_manage)")

    body = await request.json()
    filter_criteria = body.get("filter", {})

    result = bulk_delete.create_device_selection(
        db=db,
        filter_criteria=filter_criteria,
        created_by="admin"
    )

    return result

@app.post("/admin/devices/bulk-delete")
async def bulk_delete_devices_endpoint(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Bulk hard delete devices with optional historical data purging.
    Requires JWT authentication with admin privileges.
    Supports both explicit device_ids and selection_id.
    Rate limited to 10 operations per minute.
    """
    # Verify user is authenticated (JWT is valid)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Rate limiting: 10 bulk delete operations per minute per user
    rate_key = f"bulk_delete:{user.username}"
    allowed, remaining = rate_limiter.check_rate_limit(
        key=rate_key,
        max_requests=10,
        window_minutes=1
    )

    if not allowed:
        structured_logger.log_event(
            "bulk_delete.rate_limited",
            level="WARN",
            username=user.username
        )
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 10 bulk delete operations per minute."
        )

    body = await request.json()
    device_ids = body.get("device_ids")
    selection_id = body.get("selection_id")
    purge_history = body.get("purge_history", True)

    if not device_ids and not selection_id:
        raise HTTPException(status_code=400, detail="Either device_ids or selection_id must be provided")

    result = bulk_delete.bulk_delete_devices(
        db=db,
        device_ids=device_ids,
        selection_id=selection_id,
        purge_history=purge_history,
        admin_user=user.username
    )

    # Invalidate cache on bulk device deletion
    response_cache.invalidate("/v1/metrics")
    response_cache.invalidate("/v1/devices")

    return result

@app.post("/v1/devices/bulk-delete")
async def bulk_delete_devices_legacy(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Legacy bulk delete endpoint (deprecated - use /admin/devices/bulk-delete).
    Maintained for backward compatibility. Redirects to the new implementation.
    """
    body = await request.json()
    device_ids = body.get("device_ids", [])

    if not device_ids:
        raise HTTPException(status_code=400, detail="No device IDs provided")

    # Rate limiting: 10 bulk delete operations per minute per user
    rate_key = f"bulk_delete:{user.username if user else 'anonymous'}"
    allowed, remaining = rate_limiter.check_rate_limit(
        key=rate_key,
        max_requests=10,
        window_minutes=1
    )

    if not allowed:
        structured_logger.log_event(
            "bulk_delete.rate_limited",
            level="WARN",
            username=user.username if user else "anonymous"
        )
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 10 bulk delete operations per minute."
        )

    result = bulk_delete.bulk_delete_devices(
        db=db,
        device_ids=device_ids,
        purge_history=False,  # Legacy endpoint doesn't purge history
        admin_user=user.username if user else None
    )

    # Invalidate cache on bulk device deletion
    response_cache.invalidate("/v1/metrics")
    response_cache.invalidate("/v1/devices")

    return {
        "ok": True,
        "deleted_count": result["deleted"],
        "message": f"{result['deleted']} device(s) deleted successfully"
    }

@app.patch("/v1/devices/{device_id}/alias")
async def update_device_alias(
    device_id: str,
    request: UpdateDeviceAliasRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not request.alias or not request.alias.strip():
        raise HTTPException(status_code=400, detail="Alias cannot be empty")

    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    old_alias = device.alias
    device.alias = request.alias.strip()
    db.commit()
    db.refresh(device)

    log_device_event(db, device.id, "alias_changed", {"old_alias": old_alias, "new_alias": device.alias})

    # Invalidate cache on alias update
    response_cache.invalidate("/v1/metrics")
    response_cache.invalidate("/v1/devices")

    return {
        "ok": True,
        "message": f"Device alias updated from '{old_alias}' to '{device.alias}'",
        "device": {
            "id": device.id,
            "alias": device.alias
        }
    }

@app.patch("/v1/devices/{device_id}/settings")
async def update_device_settings(
    device_id: str,
    request: UpdateDeviceSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    updates = {}

    if request.monitored_package is not None:
        if not request.monitored_package.strip():
            raise HTTPException(status_code=400, detail="Monitored package cannot be empty")
        import re
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$', request.monitored_package.strip()):
            raise HTTPException(status_code=400, detail="Invalid package name format")
        device.monitored_package = request.monitored_package.strip()
        updates["monitored_package"] = device.monitored_package

    if request.monitored_app_name is not None:
        if not request.monitored_app_name.strip():
            raise HTTPException(status_code=400, detail="Monitored app name cannot be empty")
        device.monitored_app_name = request.monitored_app_name.strip()
        updates["monitored_app_name"] = device.monitored_app_name

    if request.monitored_threshold_min is not None:
        if request.monitored_threshold_min < 1 or request.monitored_threshold_min > 1440:
            raise HTTPException(status_code=400, detail="Threshold must be between 1 and 1440 minutes (24 hours)")
        # Warn but allow values > 120 for backward compatibility
        if request.monitored_threshold_min > 120:
            import warnings
            warnings.warn(f"Threshold value {request.monitored_threshold_min} minutes exceeds recommended maximum of 120 minutes. Values > 120 are deprecated.", DeprecationWarning)
        device.monitored_threshold_min = request.monitored_threshold_min
        updates["monitored_threshold_min"] = device.monitored_threshold_min

    if request.monitor_enabled is not None:
        device.monitor_enabled = request.monitor_enabled
        updates["monitor_enabled"] = device.monitor_enabled

    if request.auto_relaunch_enabled is not None:
        device.auto_relaunch_enabled = request.auto_relaunch_enabled
        updates["auto_relaunch_enabled"] = device.auto_relaunch_enabled

    db.commit()
    db.refresh(device)

    log_device_event(db, device.id, "settings_updated", updates)
    structured_logger.log_event("monitoring.update", device_id=device.id, updates=updates)

    # Invalidate cache on settings update
    response_cache.invalidate("/v1/metrics")
    response_cache.invalidate("/v1/devices")

    return {
        "ok": True,
        "message": "Device settings updated successfully",
        "device": {
            "id": device.id,
            "monitored_package": device.monitored_package,
            "monitored_app_name": device.monitored_app_name,
            "monitored_threshold_min": device.monitored_threshold_min,
            "monitor_enabled": device.monitor_enabled,
            "auto_relaunch_enabled": device.auto_relaunch_enabled
        }
    }

@app.get("/admin/devices/{device_id}/monitoring")
async def get_device_monitoring_settings(
    device_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get monitoring configuration for a specific device"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    last_status = db.query(DeviceLastStatus).filter(DeviceLastStatus.device_id == device_id).first()

    return {
        "ok": True,
        "monitoring": {
            "monitor_enabled": device.monitor_enabled,
            "monitored_package": device.monitored_package,
            "monitored_app_name": device.monitored_app_name,
            "monitored_threshold_min": device.monitored_threshold_min,
            "service_up": last_status.service_up if last_status else None,
            "monitored_foreground_recent_s": last_status.monitored_foreground_recent_s if last_status else None,
            "last_seen": device.last_seen.isoformat() if device.last_seen else None
        }
    }

@app.patch("/admin/devices/{device_id}/monitoring")
async def update_device_monitoring_settings(
    device_id: str,
    request: UpdateDeviceSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update monitoring configuration for a specific device"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    updates = {}
    has_monitoring_update = False

    if request.monitored_package is not None:
        if not request.monitored_package.strip():
            raise HTTPException(status_code=400, detail="Monitored package cannot be empty")
        import re
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$', request.monitored_package.strip()):
            raise HTTPException(status_code=400, detail="Invalid package name format")
        device.monitored_package = request.monitored_package.strip()
        updates["monitored_package"] = device.monitored_package
        has_monitoring_update = True

    if request.monitored_app_name is not None:
        if not request.monitored_app_name.strip():
            raise HTTPException(status_code=400, detail="Monitored app name cannot be empty")
        device.monitored_app_name = request.monitored_app_name.strip()
        updates["monitored_app_name"] = device.monitored_app_name
        has_monitoring_update = True

    if request.monitored_threshold_min is not None:
        if request.monitored_threshold_min < 1 or request.monitored_threshold_min > 1440:
            raise HTTPException(status_code=400, detail="Threshold must be between 1 and 1440 minutes (24 hours)")
        # Warn but allow values > 120 for backward compatibility
        if request.monitored_threshold_min > 120:
            import warnings
            warnings.warn(f"Threshold value {request.monitored_threshold_min} minutes exceeds recommended maximum of 120 minutes. Values > 120 are deprecated.", DeprecationWarning)
        device.monitored_threshold_min = request.monitored_threshold_min
        updates["monitored_threshold_min"] = device.monitored_threshold_min
        has_monitoring_update = True

    if request.monitor_enabled is not None:
        device.monitor_enabled = request.monitor_enabled
        updates["monitor_enabled"] = device.monitor_enabled
        has_monitoring_update = True

    if has_monitoring_update:
        device.monitoring_use_defaults = False
        updates["monitoring_use_defaults"] = False

    db.commit()
    db.refresh(device)

    log_device_event(db, device.id, "monitoring_settings_updated", updates)
    structured_logger.log_event("monitoring.update", device_id=device.id, updates=updates)

    # Invalidate cache on monitoring settings update
    response_cache.invalidate("/v1/metrics")
    response_cache.invalidate("/v1/devices")

    return {
        "ok": True,
        "message": "Monitoring settings updated successfully",
        "monitoring": {
            "monitor_enabled": device.monitor_enabled,
            "monitored_package": device.monitored_package,
            "monitored_app_name": device.monitored_app_name,
            "monitored_threshold_min": device.monitored_threshold_min
        }
    }

@app.get("/admin/settings/monitoring-defaults")
async def get_monitoring_defaults(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get global monitoring defaults.
    Returns built-in defaults if no custom settings exist.
    Results are cached for performance.
    """
    start_time = time.time()

    defaults = monitoring_defaults_cache.get_defaults(db)

    latency_ms = (time.time() - start_time) * 1000
    metrics.observe_histogram("monitoring_defaults_get_latency_ms", latency_ms, {})

    structured_logger.log_event(
        "settings.monitoring_defaults.read",
        user=current_user.username,
        latency_ms=latency_ms
    )

    return defaults

class UpdateMonitoringDefaultsRequest(BaseModel):
    enabled: Optional[bool] = None
    package: Optional[str] = None
    alias: Optional[str] = None
    threshold_min: Optional[int] = None

@app.patch("/admin/settings/monitoring-defaults")
async def update_monitoring_defaults(
    request: UpdateMonitoringDefaultsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update global monitoring defaults.
    Requires device_manage scope (admin user).
    Validates inputs and invalidates cache.
    """
    start_time = time.time()

    defaults_record = db.query(MonitoringDefaults).first()

    if not defaults_record:
        defaults_record = MonitoringDefaults()
        db.add(defaults_record)

    updates = {}

    if request.package is not None:
        if not request.package.strip():
            raise HTTPException(status_code=422, detail="Package cannot be empty")
        import re
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$', request.package.strip()):
            raise HTTPException(status_code=422, detail="Invalid package name format")
        defaults_record.package = request.package.strip()
        updates["package"] = defaults_record.package

    if request.alias is not None:
        if not request.alias.strip():
            raise HTTPException(status_code=422, detail="Alias cannot be empty")
        if len(request.alias.strip()) > 64:
            raise HTTPException(status_code=422, detail="Alias must be 64 characters or less")
        defaults_record.alias = request.alias.strip()
        updates["alias"] = defaults_record.alias

    if request.threshold_min is not None:
        if request.threshold_min < 1 or request.threshold_min > 120:
            raise HTTPException(status_code=422, detail="Threshold must be between 1 and 120 minutes")
        defaults_record.threshold_min = request.threshold_min
        updates["threshold_min"] = defaults_record.threshold_min

    if request.enabled is not None:
        defaults_record.enabled = request.enabled
        updates["enabled"] = defaults_record.enabled

    defaults_record.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(defaults_record)

    monitoring_defaults_cache.invalidate()

    latency_ms = (time.time() - start_time) * 1000
    metrics.observe_histogram("monitoring_defaults_update_latency_ms", latency_ms, {})

    structured_logger.log_event(
        "settings.monitoring_defaults.update",
        user=current_user.username,
        updates=updates,
        latency_ms=latency_ms
    )

    return {
        "enabled": defaults_record.enabled,
        "package": defaults_record.package,
        "alias": defaults_record.alias,
        "threshold_min": defaults_record.threshold_min,
        "updated_at": defaults_record.updated_at.isoformat() + "Z"
    }

@app.get("/admin/settings/auto-relaunch-defaults")
async def get_auto_relaunch_defaults(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get global auto-relaunch defaults.
    Returns built-in defaults if no custom settings exist.
    """
    start_time = time.time()

    defaults_record = db.query(AutoRelaunchDefaults).first()

    if defaults_record:
        defaults = {
            "enabled": defaults_record.enabled,
            "package": defaults_record.package,
            "updated_at": defaults_record.updated_at.isoformat() + "Z"
        }
    else:
        defaults = {
            "enabled": False,
            "package": "com.unitynetwork.unityapp",
            "updated_at": None
        }

    latency_ms = (time.time() - start_time) * 1000
    metrics.observe_histogram("auto_relaunch_defaults_get_latency_ms", latency_ms, {})

    structured_logger.log_event(
        "settings.auto_relaunch_defaults.read",
        user=current_user.username,
        latency_ms=latency_ms
    )

    return defaults

class UpdateAutoRelaunchDefaultsRequest(BaseModel):
    enabled: Optional[bool] = None
    package: Optional[str] = None

@app.patch("/admin/settings/auto-relaunch-defaults")
async def update_auto_relaunch_defaults(
    request: UpdateAutoRelaunchDefaultsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update global auto-relaunch defaults.
    Requires device_manage scope (admin user).
    """
    start_time = time.time()

    defaults_record = db.query(AutoRelaunchDefaults).first()

    if not defaults_record:
        defaults_record = AutoRelaunchDefaults()
        db.add(defaults_record)

    updates = {}

    if request.package is not None:
        if not request.package.strip():
            raise HTTPException(status_code=422, detail="Package cannot be empty")
        import re
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$', request.package.strip()):
            raise HTTPException(status_code=422, detail="Invalid package name format")
        defaults_record.package = request.package.strip()
        updates["package"] = defaults_record.package

    if request.enabled is not None:
        defaults_record.enabled = request.enabled
        updates["enabled"] = defaults_record.enabled

    defaults_record.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(defaults_record)

    latency_ms = (time.time() - start_time) * 1000
    metrics.observe_histogram("auto_relaunch_defaults_update_latency_ms", latency_ms, {})

    structured_logger.log_event(
        "settings.auto_relaunch_defaults.update",
        user=current_user.username,
        updates=updates,
        latency_ms=latency_ms
    )

    return {
        "enabled": defaults_record.enabled,
        "package": defaults_record.package,
        "updated_at": defaults_record.updated_at.isoformat() + "Z"
    }

@app.get("/admin/settings/discord")
async def get_discord_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get Discord alert settings.
    Returns enabled status for Discord alerts.
    Defaults to enabled=True if no settings exist.
    """
    start_time = time.time()

    settings_record = db.query(DiscordSettings).first()

    if settings_record:
        settings = {
            "enabled": settings_record.enabled,
            "updated_at": settings_record.updated_at.isoformat() + "Z"
        }
    else:
        settings = {
            "enabled": True,
            "updated_at": None
        }

    latency_ms = (time.time() - start_time) * 1000
    metrics.observe_histogram("discord_settings_get_latency_ms", latency_ms, {})

    structured_logger.log_event(
        "settings.discord.read",
        user=current_user.username,
        latency_ms=latency_ms
    )

    return settings

class UpdateDiscordSettingsRequest(BaseModel):
    enabled: Optional[bool] = None

@app.patch("/admin/settings/discord")
async def update_discord_settings(
    request: UpdateDiscordSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update Discord alert settings.
    Requires device_manage scope (admin user).
    """
    start_time = time.time()

    settings_record = db.query(DiscordSettings).first()

    if not settings_record:
        settings_record = DiscordSettings()
        db.add(settings_record)

    updates = {}

    if request.enabled is not None:
        settings_record.enabled = request.enabled
        updates["enabled"] = settings_record.enabled

    settings_record.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(settings_record)

    discord_settings_cache.invalidate()

    latency_ms = (time.time() - start_time) * 1000
    metrics.observe_histogram("discord_settings_update_latency_ms", latency_ms, {})

    structured_logger.log_event(
        "settings.discord.update",
        user=current_user.username,
        updates=updates,
        latency_ms=latency_ms
    )

    return {
        "enabled": settings_record.enabled,
        "updated_at": settings_record.updated_at.isoformat() + "Z"
    }

@app.get("/v1/settings/wifi")
async def get_wifi_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get WiFi configuration settings.
    Returns the current WiFi SSID, password, and security type.
    """
    wifi_settings = db.query(WiFiSettings).first()

    if not wifi_settings:
        return {
            "ssid": "",
            "password": "",
            "security_type": "wpa2",
            "enabled": False,
            "updated_at": None
        }

    structured_logger.log_event(
        "settings.wifi.read",
        user=current_user.username
    )

    return {
        "ssid": wifi_settings.ssid,
        "password": wifi_settings.password,
        "security_type": wifi_settings.security_type,
        "enabled": wifi_settings.enabled,
        "updated_at": wifi_settings.updated_at.isoformat() + "Z" if wifi_settings.updated_at else None
    }

class UpdateWiFiSettingsRequest(BaseModel):
    ssid: Optional[str] = None
    password: Optional[str] = None
    security_type: Optional[str] = None
    enabled: Optional[bool] = None

@app.post("/v1/settings/wifi")
async def update_wifi_settings(
    request: UpdateWiFiSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update WiFi configuration settings.
    Creates or updates the WiFi settings for device connectivity.
    """
    wifi_settings = db.query(WiFiSettings).first()

    if not wifi_settings:
        wifi_settings = WiFiSettings(
            ssid="",
            password="",
            security_type="wpa2",
            enabled=False
        )
        db.add(wifi_settings)

    updates = {}

    if request.ssid is not None:
        if not request.ssid.strip():
            raise HTTPException(status_code=422, detail="SSID cannot be empty")
        wifi_settings.ssid = request.ssid.strip()
        updates["ssid"] = wifi_settings.ssid

    if request.password is not None:
        wifi_settings.password = request.password
        updates["password_updated"] = True

    if request.security_type is not None:
        valid_types = ["open", "wep", "wpa", "wpa2", "wpa3"]
        if request.security_type not in valid_types:
            raise HTTPException(
                status_code=422,
                detail=f"Security type must be one of: {', '.join(valid_types)}"
            )
        wifi_settings.security_type = request.security_type
        updates["security_type"] = wifi_settings.security_type

    if request.enabled is not None:
        wifi_settings.enabled = request.enabled
        updates["enabled"] = wifi_settings.enabled

    wifi_settings.updated_at = datetime.now(timezone.utc)
    wifi_settings.updated_by = current_user.username

    db.commit()
    db.refresh(wifi_settings)

    structured_logger.log_event(
        "settings.wifi.update",
        user=current_user.username,
        updates=updates
    )

    return {
        "ok": True,
        "message": "WiFi settings updated successfully",
        "settings": {
            "ssid": wifi_settings.ssid,
            "password": wifi_settings.password,
            "security_type": wifi_settings.security_type,
            "enabled": wifi_settings.enabled,
            "updated_at": wifi_settings.updated_at.isoformat() + "Z"
        }
    }

@app.post("/v1/wifi/push-to-devices")
async def push_wifi_to_devices(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Push WiFi credentials to selected devices via FCM.
    Devices must support Android 10+ for cmd wifi connect-network command.
    """
    body = await request.json()
    device_ids = body.get("device_ids", [])

    if not device_ids:
        raise HTTPException(status_code=400, detail="device_ids is required")

    wifi_settings = db.query(WiFiSettings).first()
    if not wifi_settings or not wifi_settings.enabled:
        raise HTTPException(status_code=400, detail="WiFi settings not configured or disabled")

    import httpx

    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FCM authentication failed: {str(e)}")

    fcm_url = build_fcm_v1_url(project_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    print(f"[WIFI-PUSH] Pushing WiFi credentials to {len(device_ids)} device(s)")

    results = []

    async with httpx.AsyncClient() as client:
        for device_id in device_ids:
            device = db.query(Device).filter(Device.id == device_id).first()
            if not device:
                results.append({"device_id": device_id, "alias": None, "ok": False, "error": "Device not found"})
                continue

            if not device.fcm_token:
                results.append({"device_id": device_id, "alias": device.alias, "ok": False, "error": "No FCM token"})
                continue

            request_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc).isoformat()
            hmac_signature = compute_hmac_signature(request_id, device_id, "wifi_connect", timestamp)

            message = {
                "message": {
                    "token": device.fcm_token,
                    "data": {
                        "action": "wifi_connect",
                        "request_id": request_id,
                        "device_id": device_id,
                        "ts": timestamp,
                        "hmac": hmac_signature,
                        "ssid": wifi_settings.ssid,
                        "password": wifi_settings.password,
                        "security_type": wifi_settings.security_type
                    },
                    "android": {
                        "priority": "high"
                    }
                }
            }

            # Create FcmDispatch record before sending
            from db_utils import record_fcm_dispatch
            import time

            fcm_start_time = time.time()

            try:
                response = await client.post(fcm_url, json=message, headers=headers, timeout=10.0)

                latency_ms = (time.time() - fcm_start_time) * 1000
                fcm_result = response.json() if response.status_code == 200 else None
                fcm_message_id = fcm_result.get("name") if fcm_result else None

                # Record FCM dispatch
                try:
                    dispatch_result = record_fcm_dispatch(
                        db=db,
                        request_id=request_id,
                        device_id=device_id,
                        action="wifi_connect",
                        fcm_status="success" if response.status_code == 200 else "failed",
                        latency_ms=int(latency_ms),
                        fcm_message_id=fcm_message_id,
                        http_code=response.status_code,
                        response_json=response.text[:500] if response.text else None
                    )
                except Exception as dispatch_error:
                    print(f"[WIFI-PUSH] WARN: Failed to record FcmDispatch: {dispatch_error}")

                if response.status_code == 200:
                    # FCM delivery successful - device execution status will come via ACK
                    results.append({
                        "device_id": device_id,
                        "alias": device.alias,
                        "ok": True,
                        "fcm_delivered": True,
                        "device_executed": False,  # Will be updated when ACK arrives
                        "request_id": request_id,
                        "message": "WiFi credentials sent to FCM (awaiting device response)"
                    })

                    log_device_event(db, device_id, "wifi_push", {
                        "request_id": request_id,
                        "ssid": wifi_settings.ssid,
                        "security_type": wifi_settings.security_type,
                        "fcm_status": "delivered"
                    })

                    print(f"[WIFI-PUSH] ✓ FCM delivered to {device.alias} ({device_id}), request_id={request_id}")
                else:
                    # FCM delivery failed
                    error_msg = f"FCM error: {response.status_code}"
                    results.append({
                        "device_id": device_id,
                        "alias": device.alias,
                        "ok": False,
                        "fcm_delivered": False,
                        "device_executed": False,
                        "request_id": request_id,
                        "error": error_msg
                    })
                    print(f"[WIFI-PUSH] ✗ FCM failed for {device.alias}: {response.status_code}")
            except Exception as e:
                # Record failed dispatch
                latency_ms = (time.time() - fcm_start_time) * 1000
                try:
                    record_fcm_dispatch(
                        db=db,
                        request_id=request_id,
                        device_id=device_id,
                        action="wifi_connect",
                        fcm_status="failed",
                        latency_ms=int(latency_ms),
                        http_code=None,
                        error_msg=str(e)[:500]
                    )
                except Exception as dispatch_error:
                    print(f"[WIFI-PUSH] WARN: Failed to record failed FcmDispatch: {dispatch_error}")

                results.append({
                    "device_id": device_id,
                    "alias": device.alias,
                    "ok": False,
                    "fcm_delivered": False,
                    "device_executed": False,
                    "request_id": request_id,
                    "error": str(e)
                })
                print(f"[WIFI-PUSH] ✗ Exception for {device.alias}: {str(e)}")

    success_count = sum(1 for r in results if r.get("ok"))
    print(f"[WIFI-PUSH] Complete: {success_count}/{len(device_ids)} successful")

    structured_logger.log_event(
        "wifi.push",
        user=current_user.username,
        total=len(device_ids),
        success=success_count,
        failed=len(device_ids) - success_count
    )

    return {
        "ok": True,
        "ssid": wifi_settings.ssid,
        "total": len(device_ids),
        "success_count": success_count,
        "failed_count": len(device_ids) - success_count,
        "results": results
    }

@app.get("/admin/bloatware-list")
async def get_bloatware_list(
    admin_key: str = Header(..., alias="X-Admin-Key"),
    db: Session = Depends(get_db)
):
    """
    Get list of enabled bloatware packages for enrollment scripts.
    Returns plain text, one package name per line.
    Used by enrollment one-liner scripts to download current bloatware list.
    """
    verify_admin_key(admin_key)

    packages = db.query(BloatwarePackage).filter(BloatwarePackage.enabled == True).order_by(BloatwarePackage.package_name).all()

    package_names = [pkg.package_name for pkg in packages]
    plain_text = "\n".join(package_names)

    structured_logger.log_event(
        "bloatware.list.download",
        count=len(package_names),
        source="enrollment_script"
    )

    return Response(
        content=plain_text,
        media_type="text/plain"
    )

class UpdateBloatwareListRequest(BaseModel):
    packages: list[str]

@app.post("/admin/bloatware-list")
async def update_bloatware_list(
    request: UpdateBloatwareListRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update the bloatware packages list.
    Replaces all existing packages with the provided list.
    Requires admin authentication.
    """
    if not request.packages or len(request.packages) == 0:
        raise HTTPException(status_code=422, detail="Packages list cannot be empty")

    # Validate package names
    import re
    for pkg in request.packages:
        if not pkg or not pkg.strip():
            raise HTTPException(status_code=422, detail="Package names cannot be empty")
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]*)+$', pkg.strip()):
            raise HTTPException(status_code=422, detail=f"Invalid package name format: {pkg}")

    # Delete all existing packages
    db.query(BloatwarePackage).delete()

    # Insert new packages
    for pkg_name in request.packages:
        pkg = BloatwarePackage(
            package_name=pkg_name.strip(),
            enabled=True
        )
        db.add(pkg)

    db.commit()

    structured_logger.log_event(
        "bloatware.list.update",
        user=current_user.username,
        count=len(request.packages)
    )

    return {
        "ok": True,
        "message": f"Updated bloatware list with {len(request.packages)} packages",
        "count": len(request.packages)
    }

@app.get("/admin/bloatware-list/json")
async def get_bloatware_list_json(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get list of bloatware packages in JSON format.
    Returns array of package objects with id, package_name, enabled.
    Used by admin UI for management.
    """
    packages = db.query(BloatwarePackage).order_by(BloatwarePackage.package_name).all()

    return {
        "packages": [
            {
                "id": pkg.id,
                "package_name": pkg.package_name,
                "enabled": pkg.enabled,
                "description": pkg.description
            }
            for pkg in packages
        ],
        "count": len(packages)
    }

class AddBloatwarePackageRequest(BaseModel):
    package_name: str

@app.post("/admin/bloatware-list/add")
async def add_bloatware_package(
    request: AddBloatwarePackageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a single bloatware package to the list"""
    import re

    package_name = request.package_name.strip()

    if not package_name:
        raise HTTPException(status_code=422, detail="Package name cannot be empty")

    if not re.match(r'^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$', package_name):
        raise HTTPException(status_code=422, detail=f"Invalid package name format: {package_name}")

    # Check if already exists
    existing = db.query(BloatwarePackage).filter(BloatwarePackage.package_name == package_name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Package {package_name} already exists")

    # Add package
    pkg = BloatwarePackage(
        package_name=package_name,
        enabled=True
    )
    db.add(pkg)
    db.commit()

    structured_logger.log_event(
        "bloatware.package.add",
        user=current_user.username,
        package=package_name
    )

    return {
        "ok": True,
        "message": f"Added package {package_name}",
        "package": {
            "id": pkg.id,
            "package_name": pkg.package_name,
            "enabled": pkg.enabled
        }
    }

@app.delete("/admin/bloatware-list/{package_name}")
async def delete_bloatware_package(
    package_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a single bloatware package from the list"""
    pkg = db.query(BloatwarePackage).filter(BloatwarePackage.package_name == package_name).first()

    if not pkg:
        raise HTTPException(status_code=404, detail=f"Package {package_name} not found")

    db.delete(pkg)
    db.commit()

    structured_logger.log_event(
        "bloatware.package.delete",
        user=current_user.username,
        package=package_name
    )

    return {
        "ok": True,
        "message": f"Deleted package {package_name}"
    }

@app.post("/admin/bloatware-list/reset")
async def reset_bloatware_list(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reset bloatware list to default baseline packages"""
    # Default bloatware packages from baseline
    default_packages = [
        "com.vzw.hss.myverizon",
        "com.verizon.obdm_permissions",
        "com.vzw.apnlib",
        "com.verizon.mips.services",
        "com.vcast.mediamanager",
        "com.reliancecommunications.vvmclient",
        "com.google.android.apps.youtube.music",
        "com.google.android.youtube",
        "com.google.android.apps.videos",
        "com.google.android.apps.docs",
        "com.google.android.apps.maps",
        "com.google.android.apps.photos",
        "com.google.android.apps.wallpaper",
        "com.google.android.apps.walletnfcrel",
        "com.google.android.apps.nbu.files",
        "com.google.android.apps.keep",
        "com.google.android.apps.googleassistant",
        "com.google.android.apps.tachyon",
        "com.google.android.apps.safetyhub",
        "com.google.android.apps.nbu.paisa.user",
        "com.google.android.apps.chromecast.app",
        "com.google.android.apps.wellbeing",
        "com.google.android.apps.customization.pixel",
        "com.google.android.deskclock",
        "com.google.android.calendar",
        "com.google.android.gm",
        "com.google.android.calculator",
        "com.google.android.projection.gearhead",
        "com.google.android.printservice.recommendation",
        "com.google.android.feedback",
        "com.google.android.marvin.talkback",
        "com.google.android.tts",
        "com.google.android.gms.supervision",
        "com.LogiaGroup.LogiaDeck",
        "com.dti.folderlauncher",
        "com.huub.viper",
        "us.sliide.viper",
        "com.example.sarswitch",
        "com.handmark.expressweather",
        "com.tripledot.solitaire",
        "com.facebook.katana",
        "com.facebook.appmanager",
        "com.discounts.viper",
        "com.android.egg",
        "com.android.dreams.basic",
        "com.android.dreams.phototable",
        "com.android.musicfx",
        "com.android.soundrecorder",
        "com.android.protips",
        "com.android.wallpapercropper",
        "com.android.wallpaper.livepicker",
        "com.android.providers.partnerbookmarks",
        "com.android.bips",
        "com.android.printspooler",
        "com.android.wallpaperbackup",
        "com.android.soundpicker",
    ]

    # Delete all existing packages
    db.query(BloatwarePackage).delete()

    # Insert default packages
    for pkg_name in default_packages:
        pkg = BloatwarePackage(
            package_name=pkg_name,
            enabled=True
        )
        db.add(pkg)

    db.commit()

    structured_logger.log_event(
        "bloatware.list.reset",
        user=current_user.username,
        count=len(default_packages)
    )

    return {
        "ok": True,
        "message": f"Reset bloatware list to {len(default_packages)} default packages",
        "count": len(default_packages)
    }

@app.post("/v1/devices/settings/bulk")
async def update_all_devices_settings(
    request: UpdateDeviceSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update auto-relaunch settings for all devices"""
    if request.auto_relaunch_enabled is None:
        raise HTTPException(status_code=400, detail="auto_relaunch_enabled is required")

    # Optimized: Use bulk update instead of individual updates
    # This is 10-50x faster for bulk operations
    updated_count = db.query(Device).update({
        Device.auto_relaunch_enabled: request.auto_relaunch_enabled
    })

    # Log events for each device (still need individual logging)
    # But we can batch this more efficiently if needed
    devices = db.query(Device).all()
    for device in devices:
        log_device_event(db, device.id, "settings_updated", {
            "auto_relaunch_enabled": request.auto_relaunch_enabled,
            "bulk_update": True
        })

    db.commit()

    # Invalidate cache on bulk update
    response_cache.invalidate("/v1/metrics")
    response_cache.invalidate("/v1/devices")

    return {
        "ok": True,
        "message": f"Auto-relaunch {'enabled' if request.auto_relaunch_enabled else 'disabled'} for {updated_count} devices",
        "updated_count": updated_count
    }

@app.post("/v1/test-alert")
async def send_test_alert(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from discord_webhook import discord_client
    from alert_config import alert_config

    if not alert_config.DISCORD_WEBHOOK_URL:
        raise HTTPException(status_code=400, detail="Discord webhook not configured")

    if not discord_settings_cache.is_enabled(db):
        raise HTTPException(status_code=400, detail="Discord alerts are disabled")

    success = await discord_client.send_alert(
        condition="test",
        device_id="test-device",
        alias="Test Device",
        severity="INFO",
        details="Your NexMDM Discord integration is working correctly!"
    )

    if success:
        return {"ok": True, "message": "Test alert sent to Discord"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send test alert")

@app.post("/v1/devices/fcm-token")
async def update_fcm_token(
    request: Request,
    payload: dict,
    device: Device = Depends(verify_device_token),
    db: Session = Depends(get_db)
):
    fcm_token = payload.get("fcm_token")
    if not fcm_token:
        raise HTTPException(status_code=400, detail="fcm_token is required")

    device.fcm_token = fcm_token
    db.commit()

    return {"ok": True, "message": "FCM token updated successfully"}

@app.post("/v1/devices/{device_id}/commands/ping")
async def ping_device(
    device_id: str,
    x_admin: str = Header(None),
    user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    if not user and not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=401, detail="Authentication required")

    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if not device.fcm_token:
        raise HTTPException(status_code=400, detail="Device does not have FCM token registered")

    if device.last_ping_at:
        time_since_last_ping = (datetime.now(timezone.utc) - ensure_utc(device.last_ping_at)).total_seconds()
        if time_since_last_ping < 15:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit: Please wait {int(15 - time_since_last_ping)} seconds before pinging again"
            )

    correlation_id = str(uuid.uuid4())

    command = DeviceCommand(
        device_id=device_id,
        type="PING",
        status="queued",
        correlation_id=correlation_id,
        payload=None,
        created_by=user.username if user else "admin"
    )
    db.add(command)
    db.flush()

    username = user.username if user else "admin"
    log_device_event(db, device.id, "ping_initiated", {
        "correlation_id": correlation_id,
        "username": username
    })

    structured_logger.log_event(
        "dispatch.request",
        request_id=correlation_id,
        device_id=device_id,
        action="ping",
        username=username
    )

    import httpx

    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FCM authentication failed: {str(e)}")

    fcm_url = build_fcm_v1_url(project_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    timestamp = datetime.now(timezone.utc).isoformat()
    hmac_signature = compute_hmac_signature(correlation_id, device_id, "ping", timestamp)

    message = {
        "message": {
            "token": device.fcm_token,
            "data": {
                "action": "ping",
                "correlation_id": correlation_id,
                "device_id": device_id,
                "ts": timestamp,
                "hmac": hmac_signature,
                "expect_reply_within": "60"
            },
            "android": {
                "priority": "high"
            }
        }
    }

    fcm_start_time = time.time()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(fcm_url, json=message, headers=headers, timeout=10.0)

            latency_ms = (time.time() - fcm_start_time) * 1000

            if response.status_code != 200:
                try:
                    fcm_result = response.json()
                except:
                    fcm_result = {"raw_response": response.text}

                structured_logger.log_event(
                    "dispatch.fail",
                    level="ERROR",
                    request_id=correlation_id,
                    device_id=device_id,
                    action="ping",
                    fcm_http_code=response.status_code,
                    fcm_status="failed",
                    latency_ms=int(latency_ms)
                )

                command.status = "failed"
                command.error = f"FCM request failed with status {response.status_code}"
                device.last_ping_at = datetime.now(timezone.utc)
                db.commit()

                raise HTTPException(status_code=500, detail=f"FCM request failed with status {response.status_code}")

            fcm_result = response.json()

            structured_logger.log_event(
                "dispatch.sent",
                request_id=correlation_id,
                device_id=device_id,
                action="ping",
                fcm_http_code=response.status_code,
                fcm_status="success",
                latency_ms=int(latency_ms)
            )

            metrics.observe_histogram("fcm_dispatch_latency_ms", latency_ms, {
                "action": "ping"
            })

            device.last_ping_at = datetime.now(timezone.utc)
            db.commit()

            return {
                "command_id": str(command.id),
                "status": "queued",
                "correlation_id": correlation_id
            }

        except httpx.TimeoutException:
            latency_ms = (time.time() - fcm_start_time) * 1000
            structured_logger.log_event(
                "dispatch.fail",
                level="ERROR",
                request_id=correlation_id,
                device_id=device_id,
                action="ping",
                fcm_http_code=504,
                fcm_status="timeout",
                latency_ms=int(latency_ms)
            )
            command.status = "failed"
            command.error = "FCM request timed out"
            device.last_ping_at = datetime.now(timezone.utc)
            db.commit()
            raise HTTPException(status_code=504, detail="FCM request timed out")
        except Exception as e:
            latency_ms = (time.time() - fcm_start_time) * 1000
            structured_logger.log_event(
                "dispatch.fail",
                level="ERROR",
                request_id=correlation_id,
                device_id=device_id,
                action="ping",
                fcm_http_code=500,
                fcm_status="error",
                error=str(e),
                latency_ms=int(latency_ms)
            )
            command.status = "failed"
            command.error = str(e)
            device.last_ping_at = datetime.now(timezone.utc)
            db.commit()
            raise HTTPException(status_code=500, detail=f"Failed to send FCM message: {str(e)}")

class RingCommandRequest(BaseModel):
    duration_sec: int = 30
    volume: float = 1.0

@app.post("/v1/devices/{device_id}/commands/ring")
async def ring_device(
    device_id: str,
    payload: RingCommandRequest,
    x_admin: str = Header(None),
    user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    if not user and not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=401, detail="Authentication required")

    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if not device.fcm_token:
        raise HTTPException(status_code=400, detail="Device does not have FCM token registered")

    if payload.duration_sec < 5 or payload.duration_sec > 120:
        raise HTTPException(status_code=400, detail="duration_sec must be between 5 and 120 seconds")

    if payload.volume < 0.0 or payload.volume > 1.0:
        raise HTTPException(status_code=400, detail="volume must be between 0.0 and 1.0")

    now = datetime.now(timezone.utc)
    # Check if device is already ringing (only if ringing_until exists and is in the future)
    if device.ringing_until:
        ringing_until_utc = ensure_utc(device.ringing_until)
        if ringing_until_utc > now:
            raise HTTPException(status_code=400, detail="Device is already ringing")

    correlation_id = str(uuid.uuid4())

    command = DeviceCommand(
        device_id=device_id,
        type="RING",
        status="queued",
        correlation_id=correlation_id,
        payload=json.dumps({"duration_sec": payload.duration_sec, "volume": payload.volume}),
        created_by=user.username if user else "admin"
    )
    db.add(command)
    db.flush()

    username = user.username if user else "admin"
    log_device_event(db, device.id, "ring_initiated", {
        "correlation_id": correlation_id,
        "duration_sec": payload.duration_sec,
        "volume": payload.volume,
        "username": username
    })

    import httpx

    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FCM authentication failed: {str(e)}")

    fcm_url = build_fcm_v1_url(project_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    timestamp = datetime.now(timezone.utc).isoformat()
    hmac_signature = compute_hmac_signature(correlation_id, device_id, "ring", timestamp)

    message = {
        "message": {
            "token": device.fcm_token,
            "data": {
                "action": "ring",
                "duration": str(payload.duration_sec),
                "volume": str(payload.volume),
                "ts": timestamp,
                "hmac": hmac_signature
            },
            "android": {
                "priority": "high"
            }
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(fcm_url, json=message, headers=headers, timeout=10.0)

            if response.status_code != 200:
                command.status = "failed"
                command.error = f"FCM request failed with status {response.status_code}"
                db.commit()

                raise HTTPException(status_code=500, detail=f"FCM error: {response.text}")

            device.last_ring_at = now
            device.ringing_until = now + timedelta(seconds=payload.duration_sec)
            db.commit()

            structured_logger.log_event(
                "device.ring.sent",
                level="INFO",
                device_id=device_id,
                duration=payload.duration_sec,
                alias=device.alias
            )

            return {"ok": True, "message": f"Ring command sent to {device.alias}"}

        except httpx.TimeoutException:
            command.status = "failed"
            command.error = "FCM request timed out"
            db.commit()
            raise HTTPException(status_code=504, detail="FCM request timed out")
        except Exception as e:
            command.status = "failed"
            command.error = str(e)
            db.commit()
            raise HTTPException(status_code=500, detail=f"Failed to send FCM message: {str(e)}")

@app.post("/v1/devices/{device_id}/commands/ring/stop")
async def stop_ringing_device(
    device_id: str,
    x_admin: str = Header(None),
    user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    if not user and not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=401, detail="Authentication required")

    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if not device.fcm_token:
        raise HTTPException(status_code=400, detail="Device does not have FCM token registered")

    now = datetime.now(timezone.utc)
    # Check if device is actually ringing (only if ringing_until exists and is in the future)
    if not device.ringing_until:
        raise HTTPException(status_code=400, detail="Device is not currently ringing")

    ringing_until_utc = ensure_utc(device.ringing_until)
    if ringing_until_utc <= now:
        raise HTTPException(status_code=400, detail="Device is not currently ringing")

    correlation_id = str(uuid.uuid4())

    command = DeviceCommand(
        device_id=device_id,
        type="RING_STOP",
        status="queued",
        correlation_id=correlation_id,
        payload=None,
        created_by=user.username if user else "admin"
    )
    db.add(command)
    db.flush()

    username = user.username if user else "admin"
    log_device_event(db, device.id, "ring_stop_initiated", {
        "correlation_id": correlation_id,
        "username": username
    })

    import httpx

    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FCM authentication failed: {str(e)}")

    fcm_url = build_fcm_v1_url(project_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    timestamp = datetime.now(timezone.utc).isoformat()
    hmac_signature = compute_hmac_signature(correlation_id, device_id, "ring_stop", timestamp)

    message = {
        "message": {
            "token": device.fcm_token,
            "data": {
                "action": "stop_ring",
                "correlation_id": correlation_id,
                "device_id": device_id,
                "ts": timestamp,
                "hmac": hmac_signature
            },
            "android": {
                "priority": "high"
            }
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(fcm_url, json=message, headers=headers, timeout=10.0)

            if response.status_code != 200:
                command.status = "failed"
                command.error = f"FCM request failed with status {response.status_code}"
                db.commit()

                raise HTTPException(status_code=500, detail=f"FCM request failed with status {response.status_code}")

            device.ringing_until = None
            db.commit()

            structured_logger.log_event(
                "device.ring.stopped",
                level="INFO",
                device_id=device_id,
                alias=device.alias
            )

            return {"ok": True, "message": f"Stop ring command sent to {device.alias}"}

        except httpx.TimeoutException:
            command.status = "failed"
            command.error = "FCM request timed out"
            db.commit()
            raise HTTPException(status_code=504, detail="FCM request timed out")
        except Exception as e:
            command.status = "failed"
            command.error = str(e)
            db.commit()
            raise HTTPException(status_code=500, detail=f"Failed to send FCM message: {str(e)}")

class AckRequest(BaseModel):
    correlation_id: Optional[str] = None
    request_id: Optional[str] = None  # For WiFi ACK and other actions that use request_id
    type: str
    status: Optional[str] = None
    message: Optional[str] = None
    battery: Optional[float] = None
    network: Optional[str] = None
    rssi: Optional[int] = None
    charging: Optional[bool] = None
    uptime_ms: Optional[int] = None

    def get_correlation_id(self) -> str:
        """Get correlation_id, falling back to request_id if correlation_id is not set"""
        return self.correlation_id or self.request_id or ""

@app.post("/v1/devices/{device_id}/ack")
async def acknowledge_command(
    request: Request,
    device_id: str,
    payload: AckRequest,
    device: Device = Depends(verify_device_token),
    db: Session = Depends(get_db)
):
    correlation_id = payload.get_correlation_id()
    print(f"[ACK] Received ACK from device_id={device_id}, type={payload.type}, correlation_id={correlation_id}, request_id={payload.request_id}, status={payload.status}, message={payload.message}")

    if device.id != device_id:
        print(f"[ACK] Device ID mismatch: device.id={device.id}, device_id={device_id}")
        raise HTTPException(status_code=403, detail="Device can only acknowledge its own commands")

    # Around line 3996-4010 - Make the endpoint more lenient for WIFI_CONNECT_ACK
    # For WiFi ACK, skip DeviceCommand lookup since it uses FcmDispatch
    if payload.type != "WIFI_CONNECT_ACK":
        if not correlation_id:
            print(f"[ACK] ERROR: Missing correlation_id for type={payload.type}")
            raise HTTPException(status_code=400, detail="correlation_id is required for this ACK type")

        command = db.query(DeviceCommand).filter(
            DeviceCommand.correlation_id == correlation_id
        ).first()

        if not command:
            print(f"[ACK] Command not found for correlation_id={correlation_id}, type={payload.type}")
            raise HTTPException(status_code=404, detail="Command not found with this correlation_id")

        if command.device_id != device_id:
            print(f"[ACK] Command device mismatch: command.device_id={command.device_id}, device_id={device_id}")
            raise HTTPException(status_code=403, detail="Command does not belong to this device")
    else:
        command = None

    if payload.type == "PING_ACK":
        if command:
            command.status = "acknowledged"

        metric = DeviceMetric(
            device_id=device_id,
            ts=datetime.now(timezone.utc),
            battery_pct=int(payload.battery * 100) if payload.battery is not None else None,
            charging=payload.charging,
            network_type=payload.network,
            signal_dbm=payload.rssi,
            uptime_ms=payload.uptime_ms,
            app_version=device.app_version,
            source="ping_ack"
        )
        db.add(metric)

        log_device_event(db, device_id, "ping_acknowledged", {
            "correlation_id": correlation_id,
            "battery": payload.battery,
            "network": payload.network,
            "rssi": payload.rssi
        })

    elif payload.type == "RING_STARTED":
        if command:
            command.status = "acknowledged"

        log_device_event(db, device_id, "ring_started", {
            "correlation_id": correlation_id
        })

    elif payload.type == "RING_STOPPED":
        if command:
            command.status = "completed"

        if device.ringing_until:
            device.ringing_until = None

        log_device_event(db, device_id, "ring_stopped", {
            "correlation_id": payload.correlation_id
        })

    elif payload.type == "LAUNCH_APP_ACK":
        print(f"[ACK] Processing LAUNCH_APP_ACK for correlation_id={payload.correlation_id}")

        cmd_result = db.query(CommandResult).filter(
            CommandResult.correlation_id == payload.correlation_id
        ).first()

        if cmd_result:
            print(f"[ACK] Found CommandResult: id={cmd_result.id}, command_id={cmd_result.command_id}, current_status={cmd_result.status}")
            cmd_result.status = payload.status or "OK"
            cmd_result.message = payload.message
            cmd_result.updated_at = datetime.now(timezone.utc)
            print(f"[ACK] Updated CommandResult: new_status={cmd_result.status}, message={cmd_result.message}")

            bulk_cmd = db.query(BulkCommand).filter(
                BulkCommand.id == cmd_result.command_id
            ).first()

            if bulk_cmd:
                print(f"[ACK] Found BulkCommand: id={bulk_cmd.id}, current_acked_count={bulk_cmd.acked_count}, current_error_count={bulk_cmd.error_count}")
                bulk_cmd.acked_count += 1
                if payload.status and payload.status not in ["OK", "ok"]:
                    bulk_cmd.error_count += 1
                print(f"[ACK] Updated BulkCommand: new_acked_count={bulk_cmd.acked_count}, new_error_count={bulk_cmd.error_count}")
            else:
                print(f"[ACK] BulkCommand not found for command_id={cmd_result.command_id}")

            log_device_event(db, device_id, "launch_app_ack", {
                "correlation_id": correlation_id,
                "status": payload.status,
                "message": payload.message
            })
        else:
            print(f"[ACK] CommandResult not found for correlation_id={correlation_id}")
            if command:
                command.status = "acknowledged"
                print(f"[ACK] Fallback: Marked DeviceCommand as acknowledged")

    elif payload.type == "WIFI_CONNECT_ACK":
        # WiFi ACK uses request_id (which may be in correlation_id or request_id field)
        request_id = payload.request_id or correlation_id
        print(f"[ACK] Processing WIFI_CONNECT_ACK for request_id={request_id}, device_id={device_id}")

        if not request_id:
            print(f"[ACK] ERROR: WIFI_CONNECT_ACK missing both correlation_id and request_id")
            # Don't raise 404, just log and return success to prevent retries
            log_device_event(db, device_id, "wifi_connect_ack_error", {
                "error": "Missing request_id",
                "payload": str(payload.dict())
            })
            return {"ok": True, "warning": "Missing request_id, ACK logged but not processed"}

        from models import FcmDispatch

        # Find FcmDispatch by request_id and device_id to ensure correct device match
        dispatch = db.query(FcmDispatch).filter(
            FcmDispatch.request_id == request_id,
            FcmDispatch.device_id == device_id,
            FcmDispatch.action == "wifi_connect"
        ).first()

        if dispatch:
            print(f"[ACK] Found FcmDispatch: request_id={dispatch.request_id}, device_id={dispatch.device_id}, current_status={dispatch.fcm_status}")

            # Update dispatch with result
            dispatch.completed_at = datetime.now(timezone.utc)
            dispatch.result = payload.status or "UNKNOWN"
            dispatch.result_message = payload.message

            # Update fcm_status based on result
            if payload.status in ["OK", "ok"]:
                dispatch.fcm_status = "completed"
            elif payload.status in ["FAILED", "ERROR", "TIMEOUT"]:
                dispatch.fcm_status = "failed"
            else:
                dispatch.fcm_status = "completed"  # Default to completed even if status is unknown

            print(f"[ACK] Updated FcmDispatch: result={dispatch.result}, message={dispatch.result_message}")

            log_device_event(db, device_id, "wifi_connect_ack", {
                "request_id": dispatch.request_id,
                "status": payload.status,
                "message": payload.message,
                "result": dispatch.result
            })
        else:
            print(f"[ACK] WARN: FcmDispatch not found for request_id={request_id}, action=wifi_connect, device_id={device_id}")
            # Don't raise error - just log it so device doesn't retry
            log_device_event(db, device_id, "wifi_connect_ack", {
                "request_id": request_id,
                "status": payload.status,
                "message": payload.message,
                "note": "FcmDispatch record not found - may have been created before FcmDispatch tracking was added"
            })
            # Return success to prevent device from retrying
            return {"ok": True, "warning": "FcmDispatch not found, but ACK logged"}

    else:
        raise HTTPException(status_code=400, detail=f"Invalid ack type: {payload.type}")

    db.commit()
    print(f"[ACK] Successfully processed {payload.type} for device_id={device_id}, correlation_id={correlation_id}")

    return {"ok": True}

@app.post("/v1/devices/{device_id}/grant-permissions")
async def grant_device_permissions(
    device_id: str,
    x_admin: str = Header(None),
    db: Session = Depends(get_db)
):
    """Trigger device to send list of installed packages for diagnostics"""
    if not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=401, detail="Admin key required")

    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if not device.fcm_token:
        raise HTTPException(status_code=400, detail="Device does not have FCM token registered")

    import httpx

    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FCM authentication failed: {str(e)}")

    fcm_url = build_fcm_v1_url(project_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    message = {
        "message": {
            "token": device.fcm_token,
            "data": {
                "action": "list_packages"
            },
            "android": {
                "priority": "high"
            }
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(fcm_url, json=message, headers=headers, timeout=10.0)

            if response.status_code != 200:
                try:
                    fcm_result = response.json()
                except:
                    fcm_result = {"raw_response": response.text}

                return {
                    "ok": False,
                    "error": f"FCM request failed with status {response.status_code}",
                    "fcm_response": fcm_result
                }

            fcm_result = response.json()

            log_device_event(db, device.id, "list_packages_sent", {})

            return {
                "ok": True,
                "message": f"List packages command sent to {device.alias}. Check logs for results.",
                "fcm_response": fcm_result
            }

        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="FCM request timed out")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to send FCM message: {str(e)}")

@app.post("/v1/diagnostic/packages")
async def receive_package_list(
    request: Request,
    payload: dict,
    device: Device = Depends(verify_device_token),
    db: Session = Depends(get_db)
):
    """Receive package list from device (diagnostic endpoint)"""
    packages = payload.get("packages", [])

    print(f"[DIAGNOSTIC] Received {len(packages)} packages from {device.alias} ({device.id}):")
    for pkg in packages:
        print(f"  - {pkg.get('package_name')} (v{pkg.get('version_name')})")

    # Log event with package info
    log_device_event(db, device.id, "packages_reported", {
        "package_count": len(packages),
        "packages": packages
    })

    return {
        "ok": True,
        "message": f"Received {len(packages)} packages"
    }

@app.post("/v1/remote/command")
async def send_remote_command(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send remote control command to multiple devices via FCM"""

    body = await request.json()
    device_ids = body.get("device_ids", [])
    command = body.get("command")  # tap, swipe, text, key
    params = body.get("params", {})  # command-specific parameters

    if not device_ids:
        raise HTTPException(status_code=400, detail="device_ids is required")

    if not command:
        raise HTTPException(status_code=400, detail="command is required")

    import httpx

    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FCM authentication failed: {str(e)}")

    fcm_url = build_fcm_v1_url(project_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    results = []

    async with httpx.AsyncClient() as client:
        for device_id in device_ids:
            device = db.query(Device).filter(Device.id == device_id).first()
            if not device:
                results.append({"device_id": device_id, "alias": None, "ok": False, "error": "Device not found"})
                continue

            if not device.fcm_token:
                results.append({"device_id": device_id, "alias": device.alias, "ok": False, "error": "No FCM token"})
                continue

            # Build FCM message with command data
            message_data = {
                "action": "remote_control",
                "command": command,
                **{k: str(v) for k, v in params.items()}  # Convert all params to strings for FCM
            }

            message = {
                "message": {
                    "token": device.fcm_token,
                    "data": message_data,
                    "android": {
                        "priority": "high"
                    }
                }
            }

            try:
                response = await client.post(fcm_url, json=message, headers=headers, timeout=10.0)

                if response.status_code == 200:
                    results.append({
                        "device_id": device_id,
                        "alias": device.alias,
                        "ok": True,
                        "message": "Command sent successfully"
                    })

                    # Log the command
                    log_device_event(db, device_id, "remote_command", {
                        "command": command,
                        "params": params
                    })
                else:
                    results.append({
                        "device_id": device_id,
                        "alias": device.alias,
                        "ok": False,
                        "error": f"FCM error: {response.status_code}"
                    })
                    print(f"[REMOTE-EXEC] ✗ Failed {device.alias}: FCM {response.status_code}")
            except Exception as e:
                results.append({
                    "device_id": device_id,
                    "alias": device.alias,
                    "ok": False,
                    "error": str(e)
                })
                print(f"[REMOTE-EXEC] ✗ Failed {device.alias}: {str(e)}")

    success_count = sum(1 for r in results if r.get("ok"))
    return {
        "ok": True,
        "total": len(device_ids),
        "success_count": success_count,
        "failed_count": len(device_ids) - success_count,
        "results": results
    }

@app.post("/v1/remote/launch-app")
async def launch_app_on_devices(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Launch an app on multiple devices via FCM"""

    body = await request.json()
    device_ids = body.get("device_ids", [])
    package_name = body.get("package_name", "").strip()
    intent_uri = body.get("intent_uri", "").strip()  # Optional deep link/intent URI

    if not device_ids:
        raise HTTPException(status_code=400, detail="device_ids is required")

    if not package_name:
        raise HTTPException(status_code=400, detail="package_name is required")

    import httpx

    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FCM authentication failed: {str(e)}")

    fcm_url = build_fcm_v1_url(project_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    print(f"[APP LAUNCH] Launching {package_name} on {len(device_ids)} device(s)")

    results = []

    async with httpx.AsyncClient() as client:
        for device_id in device_ids:
            device = db.query(Device).filter(Device.id == device_id).first()
            if not device:
                results.append({"device_id": device_id, "alias": None, "ok": False, "error": "Device not found"})
                continue

            if not device.fcm_token:
                results.append({"device_id": device_id, "alias": device.alias, "ok": False, "error": "No FCM token"})
                continue

            # Build FCM message with launch_app action
            request_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc).isoformat()
            hmac_signature = compute_hmac_signature(request_id, device_id, "launch_app", timestamp)

            message_data = {
                "action": "launch_app",
                "request_id": request_id,
                "device_id": device_id,
                "ts": timestamp,
                "hmac": hmac_signature,
                "package_name": package_name
            }

            # Add intent URI if provided (for deep linking)
            if intent_uri:
                message_data["intent_uri"] = intent_uri

            message = {
                "message": {
                    "token": device.fcm_token,
                    "data": message_data,
                    "android": {
                        "priority": "high"
                    }
                }
            }

            try:
                response = await client.post(fcm_url, json=message, headers=headers, timeout=10.0)

                if response.status_code == 200:
                    results.append({
                        "device_id": device_id,
                        "alias": device.alias,
                        "ok": True,
                        "message": "Command sent successfully"
                    })

                    # Log the app launch event
                    event_data = {"package_name": package_name}
                    if intent_uri:
                        event_data["intent_uri"] = intent_uri
                    log_device_event(db, device_id, "app_launch", event_data)

                    print(f"[APP LAUNCH] ✓ Sent to {device.alias} ({device_id})")
                else:
                    results.append({
                        "device_id": device_id,
                        "alias": device.alias,
                        "ok": False,
                        "error": f"FCM error: {response.status_code}"
                    })
                    print(f"[APP LAUNCH] ✗ Failed for {device.alias}: FCM {response.status_code}")
            except Exception as e:
                results.append({
                    "device_id": device_id,
                    "alias": device.alias,
                    "ok": False,
                    "error": str(e)
                })
                print(f"[APP LAUNCH] ✗ Failed for {device.alias}: {str(e)}")

    success_count = sum(1 for r in results if r.get("ok"))
    print(f"[APP LAUNCH] Complete: {success_count}/{len(device_ids)} successful")

    return {
        "ok": True,
        "package_name": package_name,
        "total": len(device_ids),
        "success_count": success_count,
        "failed_count": len(device_ids) - success_count,
        "results": results
    }

@app.post("/v1/commands/launch_app")
async def bulk_launch_app(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Bulk launch app command with filtering and dry-run support
    """
    body = await request.json()
    targets = body.get("targets", {})
    command = body.get("command", {})
    dry_run = body.get("dry_run", False)

    package = command.get("package", "").strip()
    activity = command.get("activity")
    wake = command.get("wake", True)
    unlock = command.get("unlock", True)
    flags = command.get("flags", [])
    correlation_id = command.get("correlation_id", str(uuid.uuid4()))

    if not package:
        raise HTTPException(status_code=400, detail="Package name is required")

    query = db.query(Device)

    if targets.get("all"):
        pass
    elif targets.get("filter"):
        filters = targets["filter"]

        if filters.get("groups"):
            pass

        if filters.get("tags"):
            pass

        if filters.get("online") is not None:
            if filters["online"]:
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
                query = query.filter(Device.last_seen >= cutoff)

        if filters.get("android_version"):
            versions = filters["android_version"]
            if isinstance(versions, list) and versions:
                query = query.filter(Device.android_version.in_(versions))

    elif targets.get("device_ids"):
        device_ids_list = targets["device_ids"]
        if not device_ids_list:
            raise HTTPException(status_code=400, detail="device_ids list is empty")
        query = query.filter(Device.id.in_(device_ids_list))

    elif targets.get("device_aliases"):
        aliases_list = targets["device_aliases"]
        if not aliases_list:
            raise HTTPException(status_code=400, detail="device_aliases list is empty")
        query = query.filter(Device.alias.in_(aliases_list))

    else:
        raise HTTPException(status_code=400, detail="Must specify targets: all, filter, device_ids, or device_aliases")

    devices = query.filter(Device.fcm_token.isnot(None)).all()

    if dry_run:
        return {
            "dry_run": True,
            "estimated_count": len(devices),
            "sample_device_ids": [d.id for d in devices[:20]],
            "sample_devices": [{"id": d.id, "alias": d.alias} for d in devices[:20]]
        }

    bulk_cmd = BulkCommand(
        type="launch_app",
        payload=json.dumps(command),
        targets=json.dumps(targets),
        created_by=current_user.username if current_user else "admin",
        total_targets=len(devices),
        status="processing"
    )
    db.add(bulk_cmd)
    db.commit()
    db.refresh(bulk_cmd)

    import httpx

    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
    except Exception as e:
        bulk_cmd.status = "failed"
        bulk_cmd.error_count = len(devices)
        bulk_cmd.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=500, detail=f"FCM authentication failed: {str(e)}")

    fcm_url = build_fcm_v1_url(project_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    print(f"[BULK LAUNCH] Sending {package} to {len(devices)} device(s), command_id={bulk_cmd.id}")

    async with httpx.AsyncClient() as client:
        for idx, device in enumerate(devices):
            device_correlation_id = f"{correlation_id}-{device.id}"

            existing = db.query(CommandResult).filter(
                CommandResult.command_id == bulk_cmd.id,
                CommandResult.device_id == device.id
            ).first()

            if existing:
                continue

            timestamp = datetime.now(timezone.utc).isoformat()
            hmac_signature = compute_hmac_signature(device_correlation_id, device.id, "launch_app", timestamp)

            message_data = {
                "action": "launch_app",
                "correlation_id": device_correlation_id,
                "device_id": device.id,
                "ts": timestamp,
                "hmac": hmac_signature,
                "package_name": package,
                "wake": str(wake).lower(),
                "unlock": str(unlock).lower()
            }

            if activity:
                message_data["activity"] = activity

            if flags:
                message_data["flags"] = ",".join(flags)

            message = {
                "message": {
                    "token": device.fcm_token,
                    "data": message_data,
                    "android": {
                        "priority": "high"
                    }
                }
            }

            cmd_result = CommandResult(
                command_id=bulk_cmd.id,
                device_id=device.id,
                correlation_id=device_correlation_id,
                status="sending"
            )
            db.add(cmd_result)

            try:
                response = await client.post(fcm_url, json=message, headers=headers, timeout=10.0)

                if response.status_code == 200:
                    cmd_result.status = "sent"
                    bulk_cmd.sent_count += 1
                    print(f"[BULK LAUNCH] ✓ Sent to {device.alias} ({device.id})")
                else:
                    cmd_result.status = "failed"
                    cmd_result.message = f"FCM error: {response.status_code}"
                    bulk_cmd.error_count += 1
                    print(f"[BULK LAUNCH] ✗ Failed {device.alias}: FCM {response.status_code}")

            except Exception as e:
                cmd_result.status = "failed"
                cmd_result.message = str(e)
                bulk_cmd.error_count += 1
                print(f"[BULK LAUNCH] ✗ Failed {device.alias}: {str(e)}")

            db.commit()

            if idx < len(devices) - 1:
                await asyncio.sleep(0.05)

    bulk_cmd.status = "completed"
    bulk_cmd.completed_at = datetime.now(timezone.utc)
    db.commit()

    print(f"[BULK LAUNCH] Complete: {bulk_cmd.sent_count}/{len(devices)} sent, {bulk_cmd.error_count} errors")

    return {
        "ok": True,
        "command_id": bulk_cmd.id,
        "total_targets": len(devices),
        "sent_count": bulk_cmd.sent_count,
        "error_count": bulk_cmd.error_count
    }

@app.get("/v1/commands/{command_id}")
async def get_command_status(
    command_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get bulk command status and per-device results
    """
    bulk_cmd = db.query(BulkCommand).filter(BulkCommand.id == command_id).first()

    if not bulk_cmd:
        raise HTTPException(status_code=404, detail="Command not found")

    results = db.query(CommandResult, Device.alias).join(
        Device, CommandResult.device_id == Device.id
    ).filter(CommandResult.command_id == command_id).all()

    result_list = []
    for cmd_result, alias in results:
        result_list.append({
            "device_id": cmd_result.device_id,
            "alias": alias,
            "status": cmd_result.status,
            "exit_code": cmd_result.exit_code,
            "output": cmd_result.output_preview,
            "error": cmd_result.error,
            "sent_at": cmd_result.sent_at.isoformat() if cmd_result.sent_at else None,
            "updated_at": cmd_result.updated_at.isoformat() if cmd_result.updated_at else None
        })

    payload_data = json.loads(bulk_cmd.payload) if bulk_cmd.payload else {}
    targets_data = json.loads(bulk_cmd.targets) if bulk_cmd.targets else {}

    return {
        "command_id": bulk_cmd.id,
        "type": bulk_cmd.type,
        "package": payload_data.get("package"),
        "status": bulk_cmd.status,
        "created_at": bulk_cmd.created_at.isoformat(),
        "created_by": bulk_cmd.created_by,
        "completed_at": bulk_cmd.completed_at.isoformat() if bulk_cmd.completed_at else None,
        "stats": {
            "total_targets": bulk_cmd.total_targets,
            "sent_count": bulk_cmd.sent_count,
            "acked_count": bulk_cmd.acked_count,
            "error_count": bulk_cmd.error_count
        },
        "targets": targets_data,
        "results": result_list
    }

@app.get("/v1/commands")
async def list_commands(
    type: Optional[str] = None,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List recent bulk commands
    """
    query = db.query(BulkCommand)

    if type:
        query = query.filter(BulkCommand.type == type)

    commands = query.order_by(BulkCommand.created_at.desc()).limit(limit).all()

    result = []
    for cmd in commands:
        payload_data = json.loads(cmd.payload) if cmd.payload else {}
        targets_data = json.loads(cmd.targets) if cmd.targets else {}

        scope_desc = "Entire fleet"
        if targets_data.get("filter"):
            scope_desc = "Filtered set"
        elif targets_data.get("device_ids"):
            scope_desc = f"{len(targets_data['device_ids'])} devices"

        result.append({
            "command_id": cmd.id,
            "type": cmd.type,
            "package": payload_data.get("package"),
            "scope": scope_desc,
            "created_at": cmd.created_at.isoformat(),
            "created_by": cmd.created_by,
            "status": cmd.status,
            "stats": {
                "total_targets": cmd.total_targets,
                "sent_count": cmd.sent_count,
                "acked_count": cmd.acked_count,
                "error_count": cmd.error_count
            }
        })

    return {"commands": result}

@app.post("/v1/remote/reboot")
async def reboot_devices(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Reboot (hard restart) multiple devices via FCM"""

    body = await request.json()
    device_ids = body.get("device_ids", [])

    if not device_ids:
        raise HTTPException(status_code=400, detail="device_ids is required")

    import httpx

    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FCM authentication failed: {str(e)}")

    fcm_url = build_fcm_v1_url(project_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    print(f"[REBOOT] Initiating hard restart on {len(device_ids)} device(s)")

    results = []

    async with httpx.AsyncClient() as client:
        for device_id in device_ids:
            device = db.query(Device).filter(Device.id == device_id).first()
            if not device:
                results.append({"device_id": device_id, "alias": None, "ok": False, "error": "Device not found"})
                continue

            if not device.fcm_token:
                results.append({"device_id": device_id, "alias": device.alias, "ok": False, "error": "No FCM token"})
                continue

            # Build FCM message with reboot action
            message_data = {
                "action": "reboot"
            }

            message = {
                "message": {
                    "token": device.fcm_token,
                    "data": message_data,
                    "android": {
                        "priority": "high"
                    }
                }
            }

            try:
                response = await client.post(fcm_url, json=message, headers=headers, timeout=10.0)

                if response.status_code == 200:
                    results.append({
                        "device_id": device_id,
                        "alias": device.alias,
                        "ok": True,
                        "message": "Reboot command sent successfully"
                    })

                    # Log the reboot event
                    log_device_event(db, device_id, "device_reboot", {"type": "hard_restart"})

                    print(f"[REBOOT] ✓ Sent to {device.alias} ({device_id})")
                else:
                    results.append({
                        "device_id": device_id,
                        "alias": device.alias,
                        "ok": False,
                        "error": f"FCM error: {response.status_code}"
                    })
                    print(f"[REBOOT] ✗ Failed for {device.alias}: FCM {response.status_code}")
            except Exception as e:
                results.append({
                    "device_id": device_id,
                    "alias": device.alias,
                    "ok": False,
                    "error": str(e)
                })
                print(f"[REBOOT] ✗ Failed for {device.alias}: {str(e)}")

    success_count = sum(1 for r in results if r.get("ok"))
    print(f"[REBOOT] Complete: {success_count}/{len(device_ids)} successful")

    return {
        "ok": True,
        "total": len(device_ids),
        "success_count": success_count,
        "failed_count": len(device_ids) - success_count,
        "results": results
    }

@app.post("/v1/remote/restart-app")
async def restart_app_on_devices(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Restart NexMDM app (soft restart) on multiple devices via FCM"""

    body = await request.json()
    device_ids = body.get("device_ids", [])

    if not device_ids:
        raise HTTPException(status_code=400, detail="device_ids is required")

    import httpx

    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FCM authentication failed: {str(e)}")

    fcm_url = build_fcm_v1_url(project_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    print(f"[APP RESTART] Initiating soft restart on {len(device_ids)} device(s)")

    results = []

    async with httpx.AsyncClient() as client:
        for device_id in device_ids:
            device = db.query(Device).filter(Device.id == device_id).first()
            if not device:
                results.append({"device_id": device_id, "alias": None, "ok": False, "error": "Device not found"})
                continue

            if not device.fcm_token:
                results.append({"device_id": device_id, "alias": device.alias, "ok": False, "error": "No FCM token"})
                continue

            # Build FCM message with restart_app action
            message_data = {
                "action": "restart_app"
            }

            message = {
                "message": {
                    "token": device.fcm_token,
                    "data": message_data,
                    "android": {
                        "priority": "high"
                    }
                }
            }

            try:
                response = await client.post(fcm_url, json=message, headers=headers, timeout=10.0)

                if response.status_code == 200:
                    results.append({
                        "device_id": device_id,
                        "alias": device.alias,
                        "ok": True,
                        "message": "App restart command sent successfully"
                    })

                    # Log the app restart event
                    log_device_event(db, device_id, "app_restart", {"type": "soft_restart"})

                    print(f"[APP RESTART] ✓ Sent to {device.alias} ({device_id})")
                else:
                    results.append({
                        "device_id": device_id,
                        "alias": device.alias,
                        "ok": False,
                        "error": f"FCM error: {response.status_code}"
                    })
                    print(f"[APP RESTART] ✗ Failed for {device.alias}: FCM {response.status_code}")
            except Exception as e:
                results.append({
                    "device_id": device_id,
                    "alias": device.alias,
                    "ok": False,
                    "error": str(e)
                })
                print(f"[APP RESTART] ✗ Failed for {device.alias}: {str(e)}")

    success_count = sum(1 for r in results if r.get("ok"))
    print(f"[APP RESTART] Complete: {success_count}/{len(device_ids)} successful")

    return {
        "ok": True,
        "total": len(device_ids),
        "success_count": success_count,
        "failed_count": len(device_ids) - success_count,
        "results": results
    }

@app.post("/v1/remote-exec")
async def create_remote_exec(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Execute remote command (FCM or Shell) on devices with dry-run support
    """
    body = await request.json()
    mode = body.get("mode")
    targets = body.get("targets", {})
    payload = body.get("payload")
    command = body.get("command")
    dry_run = body.get("dry_run", False)

    if mode not in ["fcm", "shell"]:
        raise HTTPException(status_code=400, detail="Mode must be 'fcm' or 'shell'")

    if mode == "fcm" and not payload:
        raise HTTPException(status_code=400, detail="FCM mode requires 'payload' field")

    if mode == "shell" and not command:
        raise HTTPException(status_code=400, detail="Shell mode requires 'command' field")

    if mode == "shell":
        is_valid, error_msg = validate_shell_command(command)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    query = db.query(Device)

    if targets.get("all"):
        pass
    elif targets.get("filter"):
        filters = targets["filter"]

        if filters.get("groups"):
            pass

        if filters.get("tags"):
            pass

        if filters.get("online") is not None:
            if filters["online"]:
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
                query = query.filter(Device.last_seen >= cutoff)

        if filters.get("android_version"):
            versions = filters["android_version"]
            if isinstance(versions, list) and versions:
                query = query.filter(Device.android_version.in_(versions))

    elif targets.get("aliases"):
        aliases_list = targets["aliases"]
        if not aliases_list:
            raise HTTPException(status_code=400, detail="aliases list is empty")
        query = query.filter(Device.alias.in_(aliases_list))

    else:
        raise HTTPException(status_code=400, detail="Must specify targets: all, filter, device_ids, or device_aliases")

    devices = query.filter(Device.fcm_token.isnot(None)).all()

    # Validate that we have devices after filtering
    if not devices:
        raise HTTPException(
            status_code=400,
            detail="No devices match the specified criteria or no devices have FCM tokens registered"
        )

    if dry_run:
        return {
            "dry_run": True,
            "estimated_count": len(devices),
            "sample_aliases": [{"id": d.id, "alias": d.alias} for d in devices[:20]]
        }

    import hashlib
    payload_str = json.dumps(payload if mode == "fcm" else {"command": command}, sort_keys=True)
    payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()

    client_ip = request.client.host if request.client else None

    exec_record = RemoteExec(
        mode=mode,
        raw_request=json.dumps(body),
        targets=json.dumps(targets),
        created_by=current_user.username if current_user else "admin",
        created_by_ip=client_ip,
        payload_hash=payload_hash,
        total_targets=len(devices),
        status="processing"
    )
    db.add(exec_record)
    db.commit()
    db.refresh(exec_record)

    print(f"[REMOTE-EXEC] Started exec_id={exec_record.id}, mode={mode}, targets={len(devices)}")

    import httpx

    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
    except Exception as e:
        exec_record.status = "failed"
        exec_record.error_count = len(devices)
        exec_record.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=500, detail=f"FCM authentication failed: {str(e)}")

    fcm_url = build_fcm_v1_url(project_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        for idx, device in enumerate(devices):
            device_correlation_id = f"{exec_record.id}-{device.id}"

            existing = db.query(RemoteExecResult).filter(
                RemoteExecResult.exec_id == exec_record.id,
                RemoteExecResult.device_id == device.id
            ).first()

            if existing:
                continue

            timestamp = datetime.now(timezone.utc).isoformat()
            action = "remote_exec_fcm" if mode == "fcm" else "remote_exec_shell"
            hmac_signature = compute_hmac_signature(device_correlation_id, device.id, action, timestamp)

            message_data = {
                "action": action,
                "correlation_id": device_correlation_id,
                "device_id": device.id,
                "ts": timestamp,
                "hmac": hmac_signature,
                "exec_id": exec_record.id,
                "mode": mode
            }

            if mode == "fcm":
                message_data.update({k: str(v) for k, v in payload.items()})
            else:
                message_data["command"] = command

            message = {
                "message": {
                    "token": device.fcm_token,
                    "data": message_data,
                    "android": {
                        "priority": "high"
                    }
                }
            }

            exec_result = RemoteExecResult(
                exec_id=exec_record.id,
                device_id=device.id,
                alias=device.alias,
                correlation_id=device_correlation_id,
                status="sending"
            )
            db.add(exec_result)

            try:
                response = await client.post(fcm_url, json=message, headers=headers, timeout=5.0)

                if response.status_code == 200:
                    exec_result.status = "sent"
                    exec_record.sent_count += 1
                    print(f"[REMOTE-EXEC] ✓ Sent to {device.alias} ({device.id})")
                else:
                    exec_result.status = "failed"
                    exec_result.error = f"FCM error: {response.status_code}"
                    exec_record.error_count += 1
                    print(f"[REMOTE-EXEC] ✗ Failed {device.alias}: FCM {response.status_code}")

            except httpx.TimeoutException:
                exec_result.status = "failed"
                exec_result.error = "FCM request timeout"
                exec_record.error_count += 1
                print(f"[REMOTE-EXEC] ✗ Timeout {device.alias}")

            except Exception as e:
                exec_result.status = "failed"
                exec_result.error = str(e)
                exec_record.error_count += 1
                print(f"[REMOTE-EXEC] ✗ Failed {device.alias}: {str(e)}")

            db.commit()

            if idx < len(devices) - 1:
                await asyncio.sleep(0.05)

    exec_record.status = "completed"
    exec_record.completed_at = datetime.now(timezone.utc)
    db.commit()

    print(f"[REMOTE-EXEC] Complete: {exec_record.sent_count}/{len(devices)} sent, {exec_record.error_count} errors")

    return {
        "ok": True,
        "exec_id": exec_record.id,
        "mode": mode,
        "total_targets": len(devices),
        "sent_count": exec_record.sent_count,
        "error_count": exec_record.error_count
    }

@app.get("/v1/remote-exec/{exec_id}")
async def get_remote_exec_status(
    exec_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get execution status and per-device results"""
    exec_record = db.query(RemoteExec).filter(RemoteExec.id == exec_id).first()

    if not exec_record:
        raise HTTPException(status_code=404, detail="Execution not found")

    results = db.query(RemoteExecResult).filter(
        RemoteExecResult.exec_id == exec_id
    ).all()

    result_list = []
    for result in results:
        result_list.append({
            "device_id": result.device_id,
            "alias": result.alias,
            "status": result.status,
            "exit_code": result.exit_code,
            "output": result.output_preview,
            "error": result.error,
            "sent_at": result.sent_at.isoformat() if result.sent_at else None,
            "updated_at": result.updated_at.isoformat() if result.updated_at else None
        })

    return {
        "exec_id": exec_record.id,
        "mode": exec_record.mode,
        "status": exec_record.status,
        "created_at": exec_record.created_at.isoformat(),
        "created_by": exec_record.created_by,
        "completed_at": exec_record.completed_at.isoformat() if exec_record.completed_at else None,
        "stats": {
            "total_targets": exec_record.total_targets,
            "sent_count": exec_record.sent_count,
            "acked_count": exec_record.acked_count,
            "error_count": exec_record.error_count
        },
        "results": result_list
    }

@app.get("/v1/remote-exec")
async def list_recent_executions(
    limit: int = Query(default=10, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List recent remote executions"""
    executions = db.query(RemoteExec).order_by(
        RemoteExec.created_at.desc()
    ).limit(limit).all()

    exec_list = []
    for exec in executions:
        payload_data = json.loads(exec.payload) if exec.payload else {}
        targets_data = json.loads(exec.targets) if exec.targets else {}

        scope_desc = "Entire fleet"
        if targets_data.get("filter"):
            scope_desc = "Filtered set"
        elif targets_data.get("device_ids"):
            scope_desc = f"{len(targets_data['device_ids'])} devices"

        exec_list.append({
            "exec_id": exec.id,
            "mode": exec.mode,
            "status": exec.status,
            "created_at": exec.created_at.isoformat(),
            "created_by": exec.created_by,
            "stats": {
                "total_targets": exec.total_targets,
                "sent_count": exec.sent_count,
                "acked_count": exec.acked_count,
                "error_count": exec.error_count
            }
        })

    return {"executions": exec_list, "count": len(exec_list)}

@app.post("/v1/remote-exec/ack")
async def remote_exec_ack(
    request: Request,
    db: Session = Depends(get_db)
):
    """Receive ACK from device for remote execution"""
    # Authenticate device via token
    x_device_token = request.headers.get("X-Device-Token")
    if not x_device_token:
        raise HTTPException(status_code=401, detail="Missing X-Device-Token header")

    device = get_device_by_token(x_device_token, db)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid device token")

    body = await request.json()

    exec_id = body.get("exec_id")
    device_id = body.get("device_id")
    correlation_id = body.get("correlation_id")
    status = body.get("status")
    exit_code = body.get("exit_code")
    output = body.get("output", "")

    if not all([exec_id, device_id, correlation_id, status]):
        missing_fields = []
        if not exec_id: missing_fields.append("exec_id")
        if not device_id: missing_fields.append("device_id")
        if not correlation_id: missing_fields.append("correlation_id")
        if not status: missing_fields.append("status")

        error_msg = f"Missing required fields: {', '.join(missing_fields)}"
        structured_logger.log_event(
            "remote_exec.ack.validation_error",
            level="WARN",
            device_id=device_id,
            missing_fields=missing_fields
        )
        raise HTTPException(status_code=400, detail=error_msg)

    # Validate device_id matches authenticated device
    if device_id != device.id:
        raise HTTPException(
            status_code=403,
            detail="Device ID in payload does not match authenticated device"
        )

    # Validate correlation_id format and ownership
    expected_correlation_id = f"{exec_id}-{device.id}"
    if correlation_id != expected_correlation_id:
        raise HTTPException(
            status_code=403,
            detail="Correlation ID does not match expected format or device"
        )

    result = db.query(RemoteExecResult).filter(
        RemoteExecResult.correlation_id == correlation_id
    ).first()

    if not result:
        structured_logger.log_event(
            "remote_exec.ack.result_not_found",
            level="WARN",
            correlation_id=correlation_id,
            device_id=device_id
        )
        return {"ok": False, "error": "Result not found"}

    # Additional validation: verify result belongs to authenticated device
    if result.device_id != device.id:
        raise HTTPException(
            status_code=403,
            detail="Correlation ID does not belong to authenticated device"
        )

    try:
        # Update result record
        result.status = status.upper()
        result.exit_code = exit_code
        result.output_preview = output[:2000] if output else None
        result.error = body.get("error")
        result.updated_at = datetime.now(timezone.utc)

        # Use atomic SQL updates to prevent race conditions
        from sqlalchemy import update
        if status.upper() == "OK":
            db.execute(
                update(RemoteExec)
                .where(RemoteExec.id == exec_id)
                .values(acked_count=RemoteExec.acked_count + 1)
            )
        elif status.upper() in ["FAILED", "DENIED", "TIMEOUT"]:
            db.execute(
                update(RemoteExec)
                .where(RemoteExec.id == exec_id)
                .values(error_count=RemoteExec.error_count + 1)
            )

        # Single commit after all operations
        db.commit()

        structured_logger.log_event(
            "remote_exec.ack.success",
            level="INFO",
            device_id=device_id,
            exec_id=exec_id,
            status=status.upper(),
            exit_code=exit_code
        )

        return {"ok": True}
    except Exception as e:
        db.rollback()
        structured_logger.log_event(
            "remote_exec.ack.error",
            level="ERROR",
            device_id=device_id,
            exec_id=exec_id,
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(status_code=500, detail="Failed to process ACK")

@app.get("/v1/apk/download-optimized/{apk_id}")
async def download_apk_optimized_endpoint(
    apk_id: int,
    request: Request,
    x_device_token: Optional[str] = Header(None),
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
    installation_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Optimized APK download endpoint with caching and telemetry.

    Features:
    - In-memory caching (200MB, 1hr TTL)
    - Download telemetry tracking  
    - SHA-256 in response headers for client-side caching
    - No rate limiting for deployments

    Requires device token or admin key authentication.
    """
    device = None
    device_id = None

    # Authenticate
    if x_admin_key and verify_admin_key(x_admin_key):
        pass  # Admin authenticated
    elif x_device_token:
        device = get_device_by_token(x_device_token, db)
        if device:
            device_id = device.id
        else:
            raise HTTPException(status_code=401, detail="Invalid device token")
    else:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Use optimized download service
    return await download_apk_optimized(
        apk_id=apk_id,
        db=db,
        device_id=device_id,
        installation_id=installation_id,
        use_cache=True
    )

def build_batch_bloatware_disable_command(package_names: list[str]) -> str:
    """
    Build a shell script that disables a list of packages gracefully.
    Uses a loop over a temp file to avoid command-line length limits.  
    Skips packages that don't exist or are already disabled.

    Returns the complete shell script as a single string.

    Note: Does NOT wrap in 'sh -c' because the Android app adds that wrapper automatically.
    """
    # Use variable-based approach that matches validation expectations
    script = """TMP_DIR="/data/data/com.nexmdm/files"
LIST_FILE="$TMP_DIR/bloat_list.txt"

mkdir -p "$TMP_DIR"
cat > "$LIST_FILE" << 'EOF'
{chr(10).join(package_names)}
EOF

count=0
failed=0
while IFS= read -r pkg; do
  if [ -z "$pkg" ]; then
    continue
  fi
  if pm disable-user --user 0 "$pkg" 2>/dev/null; then
    count=$((count + 1))
  else
    failed=$((failed + 1))
  fi
done < "$LIST_FILE"

rm -f "$LIST_FILE"

echo "Disabled $count packages ($failed skipped or failed)" """

    return script
def validate_single_command(cmd: str) -> tuple[bool, Optional[str]]:
    """
    Validate a single shell command (without && chaining).
    Returns (is_valid, error_message)
    """
    import re
    import shlex

    cmd = cmd.strip()
    if not cmd:
        return False, "Command is empty"

    # Tokenize the command safely
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return False, "Invalid command syntax"

    if not tokens:
        return False, "Command is empty"

    # Special handling for cmd jobscheduler (token-based validation)
    if len(tokens) >= 4 and tokens[0] == "cmd" and tokens[1] == "jobscheduler" and tokens[2] == "run":
        # Extract tokens after "cmd jobscheduler run"
        remaining = tokens[3:]

        # Check for -f flag
        has_f_flag = False
        if remaining and remaining[0] == "-f":
            has_f_flag = True
            remaining = remaining[1:]

        # Must have at least service and job_id
        if len(remaining) < 2:
            return False, "Invalid jobscheduler command format"

        service_name = remaining[0]
        job_id = remaining[1]

        # Verify no extra arguments
        if len(remaining) > 2:
            return False, "Unexpected arguments in jobscheduler command"

        # Validate service name (only SystemUpdateService allowed)
        if service_name != "android/com.android.server.update.SystemUpdateService":
            return False, "Only SystemUpdateService is allowed for jobscheduler"

        # Validate job_id is numeric
        if not job_id.isdigit():
            return False, "Job ID must be numeric"

        return True, None

    # Special handling for getprop (token-based validation)
    if len(tokens) == 2 and tokens[0] == "getprop":
        allowed_props = ["ro.build.version.release", "ro.build.version.security_patch"]
        if tokens[1] in allowed_props:
            return True, None
        return False, f"Only {', '.join(allowed_props)} are allowed for getprop"

    # Allow disabling packages that are in the managed bloatware list
    disable_match = re.match(r'^pm\s+disable-user\s+--user\s+0\s+([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)$', cmd)
    if disable_match:
        package_name = disable_match.group(1)
        db = None
        try:
            db = SessionLocal()
            exists = (
                db.query(BloatwarePackage)
                .filter(
                    BloatwarePackage.package_name == package_name,
                    BloatwarePackage.enabled == True
                )
                .first()
                is not None
            )
        except Exception as e:
            print(f"[REMOTE-EXEC] Failed to validate bloatware package {package_name}: {e}")
            exists = False
        finally:
            if db:
                db.close()

        if exists:
            return True, None
        return False, f"Package {package_name} is not in the enabled bloatware list"

    # Regex-based validation for other commands
    allow_patterns = [
        r'^am\s+start\s+(-[nWDR]\s+[A-Za-z0-9._/:]+\s*)+$',  # More restrictive: specific flags only, no shell injection
        r'^am\s+force-stop\s+[A-Za-z0-9._]+$',
        r'^cmd\s+package\s+(list|resolve-activity)\s+[A-Za-z0-9._\s-]*$',  # More restrictive
        r'^settings\s+(get|put)\s+(secure|system|global)\s+[A-Za-z0-9._]+(\s+[A-Za-z0-9._]+)?$',  # More restrictive
        r'^input\s+(keyevent|tap|swipe)\s+[0-9\s]+$',  # Numbers only for input commands
        r'^svc\s+(wifi|data)\s+(enable|disable)$',
        r'^pm\s+list\s+packages(\s+-[a-z]+)*$',  # Allow flags like -s, -d, etc
    ]

    for pattern in allow_patterns:
        if re.match(pattern, cmd):
            return True, None

    return False, "Command not in allow-list. Only safe, pre-approved commands are permitted."
def validate_batch_bloatware_script(command: str) -> tuple[bool, Optional[str]]:
    """
    Validate a batch bloatware disable script.
    These scripts use heredoc syntax and variables, which requires more specific validation
    than the generic shell command checks.

    Returns (is_valid, error_message)
    """
    import re

    # --- Structure and Security Checks ---

    # 1. Check for key components of the script
    required_substrings = [
        'mkdir -p',
        'cat >',
        "<< 'EOF'",
        'while IFS= read -r pkg',
        'pm disable-user --user 0',
        'done <',
        'rm -f'
    ]
    for sub in required_substrings:
        if sub not in command:
            return False, f"Invalid batch script: missing required component '{sub}'"

    # 2. Extract and validate variable definitions (if present)
    lines = command.split('\n')

    # Check for TMP_DIR variable or hardcoded path
    tmp_dir_match = re.search(r'TMP_DIR=(["\']?)(.*?)\1', command)
    if tmp_dir_match:
        tmp_dir = tmp_dir_match.group(2)
        # Validate that TMP_DIR is an allowed path
        allowed_dirs = ["/data/local/tmp", "/data/data/com.nexmdm/files"]
        if tmp_dir not in allowed_dirs:
            return False, f"TMP_DIR ('{tmp_dir}') is not in an allowed directory"
    else:
        # Check for hardcoded path
        if '/data/data/com.nexmdm/files' not in command:
            return False, "Script must use /data/data/com.nexmdm/files directory"

    # 3. Verify consistent use of paths
    if tmp_dir_match:
        # Variable-based script - check for consistent variable usage
        expected_patterns = [
            rf'mkdir -p ["\']?\$TMP_DIR["\']?',
            rf'cat > ["\']?\$LIST_FILE["\']?',
            rf'done < ["\']?\$LIST_FILE["\']?',
            rf'rm -f ["\']?\$LIST_FILE["\']?'
        ]
        for pattern in expected_patterns:
            if not re.search(pattern, command):
                return False, f"Script validation failed: inconsistent variable usage or missing pattern '{pattern}'"
    else:
        # Hardcoded path script - check for consistent path usage
        expected_patterns = [
            r'mkdir -p ["\']?/data/data/com\.nexmdm/files["\']?',
            r'cat > ["\']?/data/data/com\.nexmdm/files/bloat_list\.txt["\']?',
            r'done < ["\']?/data/data/com\.nexmdm/files/bloat_list\.txt["\']?',
            r'rm -f ["\']?/data/data/com\.nexmdm/files/bloat_list\.txt["\']?'
        ]
        for pattern in expected_patterns:
            if not re.search(pattern, command):
                return False, f"Script validation failed: inconsistent path usage or missing pattern '{pattern}'"

    # 4. Check for the pm disable command (accept both with and without output capturing)
    pm_command_patterns = [
        r'pm disable-user --user 0 ["\']?\$pkg["\']? 2>/dev/null',
        r'output=\$\(pm disable-user --user 0 ["\']?\$pkg["\']? 2>&1\)'
    ]
    if not any(re.search(pattern, command) for pattern in pm_command_patterns):
        return False, "Script does not use the expected 'pm disable-user' command"

    # --- Package List Validation ---

    # 5. Extract package names from the heredoc
    eof_pattern = r"<< 'EOF'\n(.*?)\nEOF"
    match = re.search(eof_pattern, command, re.DOTALL)
    if not match:
        return False, "Invalid script format: could not find package list in heredoc"

    package_list_text = match.group(1)
    packages = [line.strip() for line in package_list_text.split('\n') if line.strip()]

    if not packages:
        return False, "No packages found in script"

    # 6. Verify all packages are in the enabled bloatware database
    db = None
    try:
        db = SessionLocal()
        for package_name in packages:
            if not re.match(r'^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$', package_name):
                return False, f"Invalid package name format: {package_name}"

            exists = db.query(BloatwarePackage).filter(
                BloatwarePackage.package_name == package_name,
                BloatwarePackage.enabled == True
            ).first() is not None

            if not exists:
                return False, f"Package '{package_name}' is not in the enabled bloatware list"

        db.close()
    except Exception as e:
        if db:
            db.close()
        return False, f"Database error during package validation: {str(e)}"

    return True, None

def validate_shell_command(command: str) -> tuple[bool, Optional[str]]:
    """
    Validate shell command against allow-list, supporting && chaining.
    Returns (is_valid, error_message)
    """
    command = command.strip()
    if not command:
        return False, "Command is empty"

    # Heuristic to detect bloatware batch scripts before applying generic security checks
    # Look for key patterns: heredoc syntax, pm disable-user, and file operations
    looks_like_bloatware_script = (
        'cat >' in command and
        "<< 'EOF'" in command and
        'pm disable-user' in command and
        ('done <' in command or 'while' in command)
    )

    # If it looks like a bloatware script, validate it with the specialized validator
    if looks_like_bloatware_script:
        is_batch_script, batch_error = validate_batch_bloatware_script(command)
        if is_batch_script:
            # This is a valid batch bloatware script, allow it
            return True, None
        else:
            # It looked like a bloatware script but validation failed, return specific error
            return False, batch_error or "Invalid bloatware batch script"

    # For non-batch commands, apply standard validation
    # Detect dangerous shell metacharacters (but allow &&)
    # Block: |, ;, >, <, `, $, newlines, and single & (but allow &&)
    dangerous_chars = ['|', ';', '>', '<', '`', '$', '\n', '\r']
    if any(char in command for char in dangerous_chars):
        return False, "Dangerous shell metacharacters not allowed"

    # Check for single & (not &&) - this prevents & for backgrounding
    if '&' in command and '&&' not in command:
        return False, "Single & not allowed (only && for chaining)"

    # If command contains &&, split and validate each subcommand
    if '&&' in command:
        subcommands = command.split('&&')
        for i, subcmd in enumerate(subcommands):
            is_valid, error_msg = validate_single_command(subcmd)
            if not is_valid:
                return False, f"Subcommand {i+1} failed validation: {error_msg}"
        return True, None
    else:
        # Single command, validate directly
        return validate_single_command(command)

@app.post("/v1/remote-exec")
async def create_remote_exec(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Execute remote command (FCM or Shell) on devices with dry-run support
    """
    body = await request.json()
    mode = body.get("mode")
    targets = body.get("targets", {})
    payload = body.get("payload")
    command = body.get("command")
    dry_run = body.get("dry_run", False)

    if mode not in ["fcm", "shell"]:
        raise HTTPException(status_code=400, detail="Mode must be 'fcm' or 'shell'")

    if mode == "fcm" and not payload:
        raise HTTPException(status_code=400, detail="FCM mode requires 'payload' field")

    if mode == "shell" and not command:
        raise HTTPException(status_code=400, detail="Shell mode requires 'command' field")

    if mode == "shell":
        is_valid, error_msg = validate_shell_command(command)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    query = db.query(Device)

    if targets.get("all"):
        pass
    elif targets.get("filter"):
        filters = targets["filter"]

        if filters.get("groups"):
            pass

        if filters.get("tags"):
            pass

        if filters.get("online") is not None:
            if filters["online"]:
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
                query = query.filter(Device.last_seen >= cutoff)

        if filters.get("android_version"):
            versions = filters["android_version"]
            if isinstance(versions, list) and versions:
                query = query.filter(Device.android_version.in_(versions))

    elif targets.get("aliases"):
        aliases_list = targets["aliases"]
        if not aliases_list:
            raise HTTPException(status_code=400, detail="aliases list is empty")
        query = query.filter(Device.alias.in_(aliases_list))

    else:
        raise HTTPException(status_code=400, detail="Must specify targets: all, filter, device_ids, or device_aliases")

    devices = query.filter(Device.fcm_token.isnot(None)).all()

    # Validate that we have devices after filtering
    if not devices:
        raise HTTPException(
            status_code=400,
            detail="No devices match the specified criteria or no devices have FCM tokens registered"
        )

    if dry_run:
        return {
            "dry_run": True,
            "estimated_count": len(devices),
            "sample_aliases": [{"id": d.id, "alias": d.alias} for d in devices[:20]]
        }

    import hashlib
    payload_str = json.dumps(payload if mode == "fcm" else {"command": command}, sort_keys=True)
    payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()

    client_ip = request.client.host if request.client else None

    exec_record = RemoteExec(
        mode=mode,
        raw_request=json.dumps(body),
        targets=json.dumps(targets),
        created_by=current_user.username if current_user else "admin",
        created_by_ip=client_ip,
        payload_hash=payload_hash,
        total_targets=len(devices),
        status="processing"
    )
    db.add(exec_record)
    db.commit()
    db.refresh(exec_record)

    print(f"[REMOTE-EXEC] Started exec_id={exec_record.id}, mode={mode}, targets={len(devices)}")

    import httpx

    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
    except Exception as e:
        exec_record.status = "failed"
        exec_record.error_count = len(devices)
        exec_record.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=500, detail=f"FCM authentication failed: {str(e)}")

    fcm_url = build_fcm_v1_url(project_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        for idx, device in enumerate(devices):
            device_correlation_id = f"{exec_record.id}-{device.id}"

            existing = db.query(RemoteExecResult).filter(
                RemoteExecResult.exec_id == exec_record.id,
                RemoteExecResult.device_id == device.id
            ).first()

            if existing:
                continue

            timestamp = datetime.now(timezone.utc).isoformat()
            action = "remote_exec_fcm" if mode == "fcm" else "remote_exec_shell"
            hmac_signature = compute_hmac_signature(device_correlation_id, device.id, action, timestamp)

            message_data = {
                "action": action,
                "correlation_id": device_correlation_id,
                "device_id": device.id,
                "ts": timestamp,
                "hmac": hmac_signature,
                "exec_id": exec_record.id,
                "mode": mode
            }

            if mode == "fcm":
                message_data.update({k: str(v) for k, v in payload.items()})
            else:
                message_data["command"] = command

            message = {
                "message": {
                    "token": device.fcm_token,
                    "data": message_data,
                    "android": {
                        "priority": "high"
                    }
                }
            }

            exec_result = RemoteExecResult(
                exec_id=exec_record.id,
                device_id=device.id,
                alias=device.alias,
                correlation_id=device_correlation_id,
                status="sending"
            )
            db.add(exec_result)

            try:
                response = await client.post(fcm_url, json=message, headers=headers, timeout=5.0)

                if response.status_code == 200:
                    exec_result.status = "sent"
                    exec_record.sent_count += 1
                    print(f"[REMOTE-EXEC] ✓ Sent to {device.alias} ({device.id})")
                else:
                    exec_result.status = "failed"
                    exec_result.error = f"FCM error: {response.status_code}"
                    exec_record.error_count += 1
                    print(f"[REMOTE-EXEC] ✗ Failed {device.alias}: FCM {response.status_code}")

            except httpx.TimeoutException:
                exec_result.status = "failed"
                exec_result.error = "FCM request timeout"
                exec_record.error_count += 1
                print(f"[REMOTE-EXEC] ✗ Timeout {device.alias}")

            except Exception as e:
                exec_result.status = "failed"
                exec_result.error = str(e)
                exec_record.error_count += 1
                print(f"[REMOTE-EXEC] ✗ Failed {device.alias}: {str(e)}")

            db.commit()

            if idx < len(devices) - 1:
                await asyncio.sleep(0.05)

    exec_record.status = "completed"
    exec_record.completed_at = datetime.now(timezone.utc)
    db.commit()

    print(f"[REMOTE-EXEC] Complete: {exec_record.sent_count}/{len(devices)} sent, {exec_record.error_count} errors")

    return {
        "ok": True,
        "exec_id": exec_record.id,
        "mode": mode,
        "total_targets": len(devices),
        "sent_count": exec_record.sent_count,
        "error_count": exec_record.error_count
    }

@app.get("/v1/remote-exec/{exec_id}")
async def get_remote_exec_status(
    exec_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get execution status and per-device results"""
    exec_record = db.query(RemoteExec).filter(RemoteExec.id == exec_id).first()

    if not exec_record:
        raise HTTPException(status_code=404, detail="Execution not found")

    results = db.query(RemoteExecResult).filter(
        RemoteExecResult.exec_id == exec_id
    ).all()

    result_list = []
    for result in results:
        result_list.append({
            "device_id": result.device_id,
            "alias": result.alias,
            "status": result.status,
            "exit_code": result.exit_code,
            "output": result.output_preview,
            "error": result.error,
            "sent_at": result.sent_at.isoformat() if result.sent_at else None,
            "updated_at": result.updated_at.isoformat() if result.updated_at else None
        })

    return {
        "exec_id": exec_record.id,
        "mode": exec_record.mode,
        "status": exec_record.status,
        "created_at": exec_record.created_at.isoformat(),
        "created_by": exec_record.created_by,
        "completed_at": exec_record.completed_at.isoformat() if exec_record.completed_at else None,
        "stats": {
            "total_targets": exec_record.total_targets,
            "sent_count": exec_record.sent_count,
            "acked_count": exec_record.acked_count,
            "error_count": exec_record.error_count
        },
        "results": result_list
    }

@app.get("/v1/remote-exec")
async def list_recent_executions(
    limit: int = Query(default=10, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List recent remote executions"""
    executions = db.query(RemoteExec).order_by(
        RemoteExec.created_at.desc()
    ).limit(limit).all()

    exec_list = []
    for exec in executions:
        payload_data = json.loads(exec.payload) if exec.payload else {}
        targets_data = json.loads(exec.targets) if exec.targets else {}

        scope_desc = "Entire fleet"
        if targets_data.get("filter"):
            scope_desc = "Filtered set"
        elif targets_data.get("device_ids"):
            scope_desc = f"{len(targets_data['device_ids'])} devices"

        exec_list.append({
            "exec_id": exec.id,
            "mode": exec.mode,
            "status": exec.status,
            "created_at": exec.created_at.isoformat(),
            "created_by": exec.created_by,
            "stats": {
                "total_targets": exec.total_targets,
                "sent_count": exec.sent_count,
                "acked_count": exec.acked_count,
                "error_count": exec.error_count
            }
        })

    return {"executions": exec_list, "count": len(exec_list)}

@app.post("/v1/remote-exec/ack")
async def remote_exec_ack(
    request: Request,
    db: Session = Depends(get_db)
):
    """Receive ACK from device for remote execution"""
    # Authenticate device via token
    x_device_token = request.headers.get("X-Device-Token")
    if not x_device_token:
        raise HTTPException(status_code=401, detail="Missing X-Device-Token header")

    device = get_device_by_token(x_device_token, db)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid device token")

    body = await request.json()

    exec_id = body.get("exec_id")
    device_id = body.get("device_id")
    correlation_id = body.get("correlation_id")
    status = body.get("status")
    exit_code = body.get("exit_code")
    output = body.get("output", "")

    if not all([exec_id, device_id, correlation_id, status]):
        missing_fields = []
        if not exec_id: missing_fields.append("exec_id")
        if not device_id: missing_fields.append("device_id")
        if not correlation_id: missing_fields.append("correlation_id")
        if not status: missing_fields.append("status")

        error_msg = f"Missing required fields: {', '.join(missing_fields)}"
        structured_logger.log_event(
            "remote_exec.ack.validation_error",
            level="WARN",
            device_id=device_id,
            missing_fields=missing_fields
        )
        raise HTTPException(status_code=400, detail=error_msg)

    # Validate device_id matches authenticated device
    if device_id != device.id:
        raise HTTPException(
            status_code=403,
            detail="Device ID in payload does not match authenticated device"
        )

    # Validate correlation_id format and ownership
    expected_correlation_id = f"{exec_id}-{device.id}"
    if correlation_id != expected_correlation_id:
        raise HTTPException(
            status_code=403,
            detail="Correlation ID does not match expected format or device"
        )

    result = db.query(RemoteExecResult).filter(
        RemoteExecResult.correlation_id == correlation_id
    ).first()

    if not result:
        structured_logger.log_event(
            "remote_exec.ack.result_not_found",
            level="WARN",
            correlation_id=correlation_id,
            device_id=device_id
        )
        return {"ok": False, "error": "Result not found"}

    # Validate that result belongs to authenticated device
    if result.device_id != device.id:
        raise HTTPException(
            status_code=403,
            detail="Correlation ID does not belong to authenticated device"
        )

    try:
        # Update result record
        result.status = status.upper()
        result.exit_code = exit_code
        result.output_preview = output[:2000] if output else None
        result.error = body.get("error")
        result.updated_at = datetime.now(timezone.utc)

        # Use atomic SQL updates to prevent race conditions
        from sqlalchemy import update
        if status.upper() == "OK":
            db.execute(
                update(RemoteExec)
                .where(RemoteExec.id == exec_id)
                .values(acked_count=RemoteExec.acked_count + 1)
            )
        elif status.upper() in ["FAILED", "DENIED", "TIMEOUT"]:
            db.execute(
                update(RemoteExec)
                .where(RemoteExec.id == exec_id)
                .values(error_count=RemoteExec.error_count + 1)
            )

        # Single commit after all operations
        db.commit()

        structured_logger.log_event(
            "remote_exec.ack.success",
            level="INFO",
            device_id=device_id,
            exec_id=exec_id,
            status=status.upper(),
            exit_code=exit_code
        )

        return {"ok": True}
    except Exception as e:
        db.rollback()
        structured_logger.log_event(
            "remote_exec.ack.error",
            level="ERROR",
            device_id=device_id,
            exec_id=exec_id,
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(status_code=500, detail="Failed to process ACK")

@app.get("/v1/apk/download-optimized/{apk_id}")
async def download_apk_optimized_endpoint(
    apk_id: int,
    request: Request,
    x_device_token: Optional[str] = Header(None),
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
    installation_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Optimized APK download endpoint with caching and telemetry.

    Features:
    - In-memory caching (200MB, 1hr TTL)
    - Download telemetry tracking  
    - SHA-256 in response headers for client-side caching
    - No rate limiting for deployments

    Requires device token or admin key authentication.
    """
    device = None
    device_id = None

    # Authenticate
    if x_admin_key and verify_admin_key(x_admin_key):
        pass  # Admin authenticated
    elif x_device_token:
        device = get_device_by_token(x_device_token, db)
        if device:
            device_id = device.id
        else:
            raise HTTPException(status_code=401, detail="Invalid device token")
    else:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Use optimized download service
    return await download_apk_optimized(
        apk_id=apk_id,
        db=db,
        device_id=device_id,
        installation_id=installation_id,
        use_cache=True
    )

def build_batch_bloatware_disable_command(package_names: list[str]) -> str:
    """
    Build a shell script that disables a list of packages gracefully.
    Uses a loop over a temp file to avoid command-line length limits.  
    Skips packages that don't exist or are already disabled.

    Returns the complete shell script as a single string.

    Note: Does NOT wrap in 'sh -c' because the Android app adds that wrapper automatically.
    """
    # Use variable-based approach that matches validation expectations
    script = """TMP_DIR="/data/data/com.nexmdm/files"
LIST_FILE="$TMP_DIR/bloat_list.txt"

mkdir -p "$TMP_DIR"
cat > "$LIST_FILE" << 'EOF'
{chr(10).join(package_names)}
EOF

count=0
failed=0
while IFS= read -r pkg; do
  if [ -z "$pkg" ]; then
    continue
  fi
  if pm disable-user --user 0 "$pkg" 2>/dev/null; then
    count=$((count + 1))
  else
    failed=$((failed + 1))
  fi
done < "$LIST_FILE"

rm -f "$LIST_FILE"

echo "Disabled $count packages ($failed skipped or failed)" """

    return script
def validate_batch_bloatware_script(command: str) -> tuple[bool, Optional[str]]:
    """
    Validate a batch bloatware disable script.
    These scripts use heredoc syntax and variables, which requires more specific validation
    than the generic shell command checks.

    Returns (is_valid, error_message)
    """
    import re

    # --- Structure and Security Checks ---

    # 1. Check for key components of the script
    required_substrings = [
        'mkdir -p',
        'cat >',
        "<< 'EOF'",
        'while IFS= read -r pkg',
        'pm disable-user --user 0',
        'done <',
        'rm -f'
    ]
    for sub in required_substrings:
        if sub not in command:
            return False, f"Invalid batch script: missing required component '{sub}'"

    # 2. Extract and validate variable definitions (if present)
    lines = command.split('\n')

    # Check for TMP_DIR variable or hardcoded path
    tmp_dir_match = re.search(r'TMP_DIR=(["\']?)(.*?)\1', command)
    if tmp_dir_match:
        tmp_dir = tmp_dir_match.group(2)
        # Validate that TMP_DIR is an allowed path
        allowed_dirs = ["/data/local/tmp", "/data/data/com.nexmdm/files"]
        if tmp_dir not in allowed_dirs:
            return False, f"TMP_DIR ('{tmp_dir}') is not in an allowed directory"
    else:
        # Check for hardcoded path
        if '/data/data/com.nexmdm/files' not in command:
            return False, "Script must use /data/data/com.nexmdm/files directory"

    # 3. Verify consistent use of paths
    if tmp_dir_match:
        # Variable-based script - check for consistent variable usage
        expected_patterns = [
            rf'mkdir -p ["\']?\$TMP_DIR["\']?',
            rf'cat > ["\']?\$LIST_FILE["\']?',
            rf'done < ["\']?\$LIST_FILE["\']?',
            rf'rm -f ["\']?\$LIST_FILE["\']?'
        ]
        for pattern in expected_patterns:
            if not re.search(pattern, command):
                return False, f"Script validation failed: inconsistent variable usage or missing pattern '{pattern}'"
    else:
        # Hardcoded path script - check for consistent path usage
        expected_patterns = [
            r'mkdir -p ["\']?/data/data/com\.nexmdm/files["\']?',
            r'cat > ["\']?/data/data/com\.nexmdm/files/bloat_list\.txt["\']?',
            r'done < ["\']?/data/data/com\.nexmdm/files/bloat_list\.txt["\']?',
            r'rm -f ["\']?/data/data/com\.nexmdm/files/bloat_list\.txt["\']?'
        ]
        for pattern in expected_patterns:
            if not re.search(pattern, command):
                return False, f"Script validation failed: inconsistent path usage or missing pattern '{pattern}'"

    # 4. Check for the pm disable command (accept both with and without output capturing)
    pm_command_patterns = [
        r'pm disable-user --user 0 ["\']?\$pkg["\']? 2>/dev/null',
        r'output=\$\(pm disable-user --user 0 ["\']?\$pkg["\']? 2>&1\)'
    ]
    if not any(re.search(pattern, command) for pattern in pm_command_patterns):
        return False, "Script does not use the expected 'pm disable-user' command"

    # --- Package List Validation ---

    # 5. Extract package names from the heredoc
    eof_pattern = r"<< 'EOF'\n(.*?)\nEOF"
    match = re.search(eof_pattern, command, re.DOTALL)
    if not match:
        return False, "Invalid script format: could not find package list in heredoc"

    package_list_text = match.group(1)
    packages = [line.strip() for line in package_list_text.split('\n') if line.strip()]

    if not packages:
        return False, "No packages found in script"

    # 6. Verify all packages are in the enabled bloatware database
    db = None
    try:
        db = SessionLocal()
        for package_name in packages:
            if not re.match(r'^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$', package_name):
                return False, f"Invalid package name format: {package_name}"

            exists = db.query(BloatwarePackage).filter(
                BloatwarePackage.package_name == package_name,
                BloatwarePackage.enabled == True
            ).first() is not None

            if not exists:
                return False, f"Package '{package_name}' is not in the enabled bloatware list"

        db.close()
    except Exception as e:
        if db:
            db.close()
        return False, f"Database error during package validation: {str(e)}"

    return True, None

def validate_shell_command(command: str) -> tuple[bool, Optional[str]]:
    """
    Validate shell command against allow-list, supporting && chaining.
    Returns (is_valid, error_message)
    """
    command = command.strip()
    if not command:
        return False, "Command is empty"

    # Heuristic to detect bloatware batch scripts before applying generic security checks
    # Look for key patterns: heredoc syntax, pm disable-user, and file operations
    looks_like_bloatware_script = (
        'cat >' in command and
        "<< 'EOF'" in command and
        'pm disable-user' in command and
        ('done <' in command or 'while' in command)
    )

    # If it looks like a bloatware script, validate it with the specialized validator
    if looks_like_bloatware_script:
        is_batch_script, batch_error = validate_batch_bloatware_script(command)
        if is_batch_script:
            # This is a valid batch bloatware script, allow it
            return True, None
        else:
            # It looked like a bloatware script but validation failed, return specific error
            return False, batch_error or "Invalid bloatware batch script"

    # For non-batch commands, apply standard validation
    # Detect dangerous shell metacharacters (but allow &&)
    # Block: |, ;, >, <, `, $, newlines, and single & (but allow &&)
    dangerous_chars = ['|', ';', '>', '<', '`', '$', '\n', '\r']
    if any(char in command for char in dangerous_chars):
        return False, "Dangerous shell metacharacters not allowed"

    # Check for single & (not &&) - this prevents & for backgrounding
    if '&' in command and '&&' not in command:
        return False, "Single & not allowed (only && for chaining)"

    # If command contains &&, split and validate each subcommand
    if '&&' in command:
        subcommands = command.split('&&')
        for i, subcmd in enumerate(subcommands):
            is_valid, error_msg = validate_single_command(subcmd)
            if not is_valid:
                return False, f"Subcommand {i+1} failed validation: {error_msg}"
        return True, None
    else:
        # Single command, validate directly
        return validate_single_command(command)

@app.post("/v1/remote-exec")
async def create_remote_exec(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Execute remote command (FCM or Shell) on devices with dry-run support
    """
    body = await request.json()
    mode = body.get("mode")
    targets = body.get("targets", {})
    payload = body.get("payload")
    command = body.get("command")
    dry_run = body.get("dry_run", False)

    if mode not in ["fcm", "shell"]:
        raise HTTPException(status_code=400, detail="Mode must be 'fcm' or 'shell'")

    if mode == "fcm" and not payload:
        raise HTTPException(status_code=400, detail="FCM mode requires 'payload' field")

    if mode == "shell" and not command:
        raise HTTPException(status_code=400, detail="Shell mode requires 'command' field")

    if mode == "shell":
        is_valid, error_msg = validate_shell_command(command)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    query = db.query(Device)

    if targets.get("all"):
        pass
    elif targets.get("filter"):
        filters = targets["filter"]

        if filters.get("groups"):
            pass

        if filters.get("tags"):
            pass

        if filters.get("online") is not None:
            if filters["online"]:
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
                query = query.filter(Device.last_seen >= cutoff)

        if filters.get("android_version"):
            versions = filters["android_version"]
            if isinstance(versions, list) and versions:
                query = query.filter(Device.android_version.in_(versions))

    elif targets.get("aliases"):
        aliases_list = targets["aliases"]
        if not aliases_list:
            raise HTTPException(status_code=400, detail="aliases list is empty")
        query = query.filter(Device.alias.in_(aliases_list))

    else:
        raise HTTPException(status_code=400, detail="Must specify targets: all, filter, device_ids, or device_aliases")

    devices = query.filter(Device.fcm_token.isnot(None)).all()

    # Validate that we have devices after filtering
    if not devices:
        raise HTTPException(
            status_code=400,
            detail="No devices match the specified criteria or no devices have FCM tokens registered"
        )

    if dry_run:
        return {
            "dry_run": True,
            "estimated_count": len(devices),
            "sample_aliases": [{"id": d.id, "alias": d.alias} for d in devices[:20]]
        }

    import hashlib
    payload_str = json.dumps(payload if mode == "fcm" else {"command": command}, sort_keys=True)
    payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()

    client_ip = request.client.host if request.client else None

    exec_record = RemoteExec(
        mode=mode,
        raw_request=json.dumps(body),
        targets=json.dumps(targets),
        created_by=current_user.username if current_user else "admin",
        created_by_ip=client_ip,
        payload_hash=payload_hash,
        total_targets=len(devices),
        status="processing"
    )
    db.add(exec_record)
    db.commit()
    db.refresh(exec_record)

    print(f"[REMOTE-EXEC] Started exec_id={exec_record.id}, mode={mode}, targets={len(devices)}")

    import httpx

    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
    except Exception as e:
        exec_record.status = "failed"
        exec_record.error_count = len(devices)
        exec_record.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=500, detail=f"FCM authentication failed: {str(e)}")

    fcm_url = build_fcm_v1_url(project_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        for idx, device in enumerate(devices):
            device_correlation_id = f"{exec_record.id}-{device.id}"

            existing = db.query(RemoteExecResult).filter(
                RemoteExecResult.exec_id == exec_record.id,
                RemoteExecResult.device_id == device.id
            ).first()

            if existing:
                continue

            timestamp = datetime.now(timezone.utc).isoformat()
            action = "remote_exec_fcm" if mode == "fcm" else "remote_exec_shell"
            hmac_signature = compute_hmac_signature(device_correlation_id, device.id, action, timestamp)

            message_data = {
                "action": action,
                "correlation_id": device_correlation_id,
                "device_id": device.id,
                "ts": timestamp,
                "hmac": hmac_signature,
                "exec_id": exec_record.id,
                "mode": mode
            }

            if mode == "fcm":
                message_data.update({k: str(v) for k, v in payload.items()})
            else:
                message_data["command"] = command

            message = {
                "message": {
                    "token": device.fcm_token,
                    "data": message_data,
                    "android": {
                        "priority": "high"
                    }
                }
            }

            exec_result = RemoteExecResult(
                exec_id=exec_record.id,
                device_id=device.id,
                alias=device.alias,
                correlation_id=device_correlation_id,
                status="sending"
            )
            db.add(exec_result)

            try:
                response = await client.post(fcm_url, json=message, headers=headers, timeout=5.0)

                if response.status_code == 200:
                    exec_result.status = "sent"
                    exec_record.sent_count += 1
                    print(f"[REMOTE-EXEC] ✓ Sent to {device.alias} ({device.id})")
                else:
                    exec_result.status = "failed"
                    exec_result.error = f"FCM error: {response.status_code}"
                    exec_record.error_count += 1
                    print(f"[REMOTE-EXEC] ✗ Failed {device.alias}: FCM {response.status_code}")

            except httpx.TimeoutException:
                exec_result.status = "failed"
                exec_result.error = "FCM request timeout"
                exec_record.error_count += 1
                print(f"[REMOTE-EXEC] ✗ Timeout {device.alias}")

            except Exception as e:
                exec_result.status = "failed"
                exec_result.error = str(e)
                exec_record.error_count += 1
                print(f"[REMOTE-EXEC] ✗ Failed {device.alias}: {str(e)}")

            db.commit()

            if idx < len(devices) - 1:
                await asyncio.sleep(0.05)

    exec_record.status = "completed"
    exec_record.completed_at = datetime.now(timezone.utc)
    db.commit()

    print(f"[REMOTE-EXEC] Complete: {exec_record.sent_count}/{len(devices)} sent, {exec_record.error_count} errors")

    return {
        "ok": True,
        "exec_id": exec_record.id,
        "mode": mode,
        "total_targets": len(devices),
        "sent_count": exec_record.sent_count,
        "error_count": exec_record.error_count
    }

@app.get("/v1/remote-exec/{exec_id}")
async def get_remote_exec_status(
    exec_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get execution status and per-device results"""
    exec_record = db.query(RemoteExec).filter(RemoteExec.id == exec_id).first()

    if not exec_record:
        raise HTTPException(status_code=404, detail="Execution not found")

    results = db.query(RemoteExecResult).filter(
        RemoteExecResult.exec_id == exec_id
    ).all()

    result_list = []
    for result in results:
        result_list.append({
            "device_id": result.device_id,
            "alias": result.alias,
            "status": result.status,
            "exit_code": result.exit_code,
            "output": result.output_preview,
            "error": result.error,
            "sent_at": result.sent_at.isoformat() if result.sent_at else None,
            "updated_at": result.updated_at.isoformat() if result.updated_at else None
        })

    return {
        "exec_id": exec_record.id,
        "mode": exec_record.mode,
        "status": exec_record.status,
        "created_at": exec_record.created_at.isoformat(),
        "created_by": exec_record.created_by,
        "completed_at": exec_record.completed_at.isoformat() if exec_record.completed_at else None,
        "stats": {
            "total_targets": exec_record.total_targets,
            "sent_count": exec_record.sent_count,
            "acked_count": exec_record.acked_count,
            "error_count": exec_record.error_count
        },
        "results": result_list
    }

@app.get("/v1/remote-exec")
async def list_recent_executions(
    limit: int = Query(default=10, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List recent remote executions"""
    executions = db.query(RemoteExec).order_by(
        RemoteExec.created_at.desc()
    ).limit(limit).all()

    exec_list = []
    for exec in executions:
        payload_data = json.loads(exec.payload) if exec.payload else {}
        targets_data = json.loads(exec.targets) if exec.targets else {}

        scope_desc = "Entire fleet"
        if targets_data.get("filter"):
            scope_desc = "Filtered set"
        elif targets_data.get("device_ids"):
            scope_desc = f"{len(targets_data['device_ids'])} devices"

        exec_list.append({
            "exec_id": exec.id,
            "mode": exec.mode,
            "status": exec.status,
            "created_at": exec.created_at.isoformat(),
            "created_by": exec.created_by,
            "stats": {
                "total_targets": exec.total_targets,
                "sent_count": exec.sent_count,
                "acked_count": exec.acked_count,
                "error_count": exec.error_count
            }
        })

    return {"executions": exec_list, "count": len(exec_list)}

@app.post("/v1/remote-exec/ack")
async def remote_exec_ack(
    request: Request,
    db: Session = Depends(get_db)
):
    """Receive ACK from device for remote execution"""
    # Authenticate device via token
    x_device_token = request.headers.get("X-Device-Token")
    if not x_device_token:
        raise HTTPException(status_code=401, detail="Missing X-Device-Token header")

    device = get_device_by_token(x_device_token, db)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid device token")

    body = await request.json()

    exec_id = body.get("exec_id")
    device_id = body.get("device_id")
    correlation_id = body.get("correlation_id")
    status = body.get("status")
    exit_code = body.get("exit_code")
    output = body.get("output", "")

    if not all([exec_id, device_id, correlation_id, status]):
        missing_fields = []
        if not exec_id: missing_fields.append("exec_id")
        if not device_id: missing_fields.append("device_id")
        if not correlation_id: missing_fields.append("correlation_id")
        if not status: missing_fields.append("status")

        error_msg = f"Missing required fields: {', '.join(missing_fields)}"
        structured_logger.log_event(
            "remote_exec.ack.validation_error",
            level="WARN",
            device_id=device_id,
            missing_fields=missing_fields
        )
        raise HTTPException(status_code=400, detail=error_msg)

    # Validate device_id matches authenticated device
    if device_id != device.id:
        raise HTTPException(
            status_code=403,
            detail="Device ID in payload does not match authenticated device"
        )

    # Validate correlation_id format and ownership
    expected_correlation_id = f"{exec_id}-{device.id}"
    if correlation_id != expected_correlation_id:
        raise HTTPException(
            status_code=403,
            detail="Correlation ID does not match expected format or device"
        )

    result = db.query(RemoteExecResult).filter(
        RemoteExecResult.correlation_id == correlation_id
    ).first()

    if not result:
        structured_logger.log_event(
            "remote_exec.ack.result_not_found",
            level="WARN",
            correlation_id=correlation_id,
            device_id=device_id
        )
        return {"ok": False, "error": "Result not found"}

    # Validate that result belongs to authenticated device
    if result.device_id != device.id:
        raise HTTPException(
            status_code=403,
            detail="Correlation ID does not belong to authenticated device"
        )

    try:
        # Update result record
        result.status = status.upper()
        result.exit_code = exit_code
        result.output_preview = output[:2000] if output else None
        result.error = body.get("error")
        result.updated_at = datetime.now(timezone.utc)

        # Use atomic SQL updates to prevent race conditions
        from sqlalchemy import update
        if status.upper() == "OK":
            db.execute(
                update(RemoteExec)
                .where(RemoteExec.id == exec_id)
                .values(acked_count=RemoteExec.acked_count + 1)
            )
        elif status.upper() in ["FAILED", "DENIED", "TIMEOUT"]:
            db.execute(
                update(RemoteExec)
                .where(RemoteExec.id == exec_id)
                .values(error_count=RemoteExec.error_count + 1)
            )

        # Single commit after all operations
        db.commit()

        structured_logger.log_event(
            "remote_exec.ack.success",
            level="INFO",
            device_id=device_id,
            exec_id=exec_id,
            status=status.upper(),
            exit_code=exit_code
        )

        return {"ok": True}
    except Exception as e:
        db.rollback()
        structured_logger.log_event(
            "remote_exec.ack.error",
            level="ERROR",
            device_id=device_id,
            exec_id=exec_id,
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(status_code=500, detail="Failed to process ACK")

# ==================== Enrollment Scripts ====================

@app.get("/v1/scripts/enroll.cmd")
async def get_windows_enroll_script(
    alias: str = Query(...),
    agent_pkg: str = Query("com.nexmdm"),
    unity_pkg: str = Query("com.unitynetwork.unityapp"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate zero-tap Windows enrollment script with enhanced debugging"""
    from models import EnrollmentEvent
    
    server_url = config.server_url
    
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY environment variable not set")
    
    event = EnrollmentEvent(
        event_type='script.render',
        token_id=None,
        alias=alias,
        details=json.dumps({
            "platform": "windows",
            "agent_pkg": agent_pkg,
            "unity_pkg": unity_pkg,
            "generated_by": current_user.username
        })
    )
    db.add(event)
    db.commit()
    
    from models import WiFiSettings
    wifi_settings = db.query(WiFiSettings).first()
    wifi_configured = wifi_settings and wifi_settings.enabled and wifi_settings.ssid and wifi_settings.ssid.strip()
    wifi_ssid = wifi_settings.ssid if wifi_settings else ""
    
    script_content = f'''@echo off
REM ============================================================
REM UnityMDM Zero-Tap Device Enrollment Script (Windows)
REM Device Alias: {alias}
REM Package: {agent_pkg}
REM ============================================================

setlocal enabledelayedexpansion

set PKG={agent_pkg}
set ALIAS={alias}
set RECEIVER=.NexDeviceAdminReceiver
set BASE_URL={server_url}
set ADMIN_KEY={admin_key}
set APK_PATH=%TEMP%\\unitymdm.apk
set DEVICE_ALIAS={alias}

echo ================================================
echo UnityMDM Zero-Tap Enrollment
echo Device: !ALIAS!
echo ================================================
echo.

echo [Step 0/7] Checking prerequisites...
echo    Checking for ADB...
where adb >nul 2>&1
if errorlevel 1 (
    echo ❌ ADB not found in PATH
    echo    Fix: Install Android Platform Tools and add to PATH
    echo    Download: https://developer.android.com/tools/releases/platform-tools
    echo    After installing, add to PATH or run from platform-tools directory
    set EXITCODE=1
    goto :end
)
echo ✅ ADB found

REM Show ADB version for debugging
for /f "tokens=*" %%A in ('adb version 2^>nul ^| findstr /C:"Android Debug Bridge"') do echo    Version: %%A

REM Show connected devices
echo    Listing devices...
adb devices -l
echo.

echo [Step 1/7] Wait for device...
echo    Waiting up to 60 seconds for device connection...
adb wait-for-device
if errorlevel 1 (
    echo ❌ No device found
    echo    Fix: Check USB cable, ensure USB debugging enabled
    echo    Current devices:
    adb devices -l
    set EXITCODE=2
    goto :end
)

REM Verify we actually have a device
for /f "skip=1 tokens=1,2" %%A in ('adb devices 2^>nul') do (
    if "%%B"=="device" (
        set DEVICE_FOUND=1
        echo ✅ Device connected: %%A
    )
)
if not defined DEVICE_FOUND (
    echo ❌ No authorized device found
    echo    Current status:
    adb devices -l
    echo.
    echo    Fix: Check if device shows "unauthorized" and accept the prompt on device
    set EXITCODE=2
    goto :end
)
echo.

echo [Step 2/10] Check Android version compatibility...
set MIN_SDK=30
for /f "tokens=*" %%A in ('adb shell getprop ro.build.version.sdk 2^>nul') do set DEVICE_SDK=%%A
set DEVICE_SDK=!DEVICE_SDK: =!
for /f "tokens=*" %%A in ('adb shell getprop ro.build.version.release 2^>nul') do set DEVICE_VER=%%A
set DEVICE_VER=!DEVICE_VER: =!

echo    Device SDK: !DEVICE_SDK! (Android !DEVICE_VER!)
echo    Required: SDK !MIN_SDK!+ (Android 11+)

if "!DEVICE_SDK!"=="" (
    echo ❌ Could not detect device SDK version
    set EXITCODE=2
    goto :end
)

if !DEVICE_SDK! LSS !MIN_SDK! (
    echo.
    echo ❌ INCOMPATIBLE DEVICE
    echo    This device runs Android !DEVICE_VER! (SDK !DEVICE_SDK!)
    echo    NexMDM requires Android 11+ (SDK 30+)
    echo.
    echo    Options:
    echo    1. Use a device with Android 11 or newer
    echo    2. Update this device's OS if possible
    set EXITCODE=2
    goto :end
)
echo ✅ Android version compatible
echo.

echo [Step 3/10] Download latest APK...
curl -L -H "X-Admin-Key: !ADMIN_KEY!" "!BASE_URL!/v1/apk/download-latest" -o "!APK_PATH!" >nul 2>&1
if errorlevel 1 (
    echo ❌ APK download failed
    echo    Fix: Check network connection and server availability
    set EXITCODE=3
    goto :end
)
echo ✅ APK downloaded
echo.

echo [Step 4/10] Install APK...
adb install -r -g "!APK_PATH!" >nul 2>&1
if errorlevel 1 (
    echo    Retrying with uninstall first...
    adb uninstall !PKG! >nul 2>&1
    adb install -r -g -t "!APK_PATH!" >nul 2>&1
    if errorlevel 1 (
        echo ❌ APK installation failed
        set EXITCODE=4
        goto :end
    )
)
echo ✅ APK installed
echo.

echo [Step 5/10] Set Device Owner...
adb shell dpm set-device-owner !PKG!/!RECEIVER! >nul 2>&1
if errorlevel 1 (
    echo ❌ Device Owner setup failed
    echo    Fix: Factory reset the device and try again
    set EXITCODE=5
    goto :end
)
echo ✅ Device Owner confirmed
echo.

echo [Step 6/10] Grant permissions...
adb shell pm grant !PKG! android.permission.POST_NOTIFICATIONS >nul 2>&1
adb shell pm grant !PKG! android.permission.ACCESS_FINE_LOCATION >nul 2>&1
adb shell pm grant !PKG! android.permission.CAMERA >nul 2>&1
adb shell appops set !PKG! RUN_ANY_IN_BACKGROUND allow >nul 2>&1
adb shell appops set !PKG! GET_USAGE_STATS allow >nul 2>&1
adb shell dumpsys deviceidle whitelist +!PKG! >nul 2>&1
echo ✅ Permissions granted
echo.

echo [Step 7/10] Disable bloatware...
set BLOAT_FILE=!TEMP!\mdm_bloatware.txt
curl -s -H "X-Admin-Key: !ADMIN_KEY!" "!BASE_URL!/admin/bloatware-list" -o "!BLOAT_FILE!" >nul 2>&1
if exist "!BLOAT_FILE!" (
    set BLOAT_COUNT=0
    for /f "delims=" %%P in (!BLOAT_FILE!) do (
        adb shell pm disable-user --user 0 %%P >nul 2>&1
        set /a BLOAT_COUNT+=1
    )
    echo ✅ Disabled !BLOAT_COUNT! bloatware packages
    del "!BLOAT_FILE!" >nul 2>&1
) else (
    echo ⚠️  Bloatware list download failed - continuing
)
echo.

echo [Step 8/10] Apply system tweaks...
adb shell settings put global app_standby_enabled 0 >nul 2>&1
adb shell settings put global battery_tip_constants app_restriction_enabled=false >nul 2>&1
adb shell settings put system screen_brightness_mode 0 >nul 2>&1
adb shell settings put system ambient_tilt_to_wake 1 >nul 2>&1
adb shell settings put system ambient_touch_to_wake 1 >nul 2>&1
echo ✅ System tweaks applied
echo.

echo [Step 9/10] Auto-enroll and launch...
adb shell am broadcast -a com.nexmdm.CONFIGURE -n !PKG!/.ConfigReceiver --receiver-foreground --es server_url "!BASE_URL!" --es admin_key "!ADMIN_KEY!" --es alias "!ALIAS!" >nul 2>&1
if errorlevel 1 (
    echo ❌ Broadcast failed
    set EXITCODE=7
    goto :end
)
echo ✅ Auto-enrollment initiated
adb shell monkey -p !PKG! -c android.intent.category.LAUNCHER 1 >nul 2>&1
echo.

echo [Step 10/10] Verify service...
timeout /t 3 /nobreak >nul
adb shell pidof !PKG! >nul 2>&1
if errorlevel 1 (
    echo ❌ Service not running
    set EXITCODE=8
    goto :end
)
echo ✅ Service running
echo.

echo Verify registration...
echo Waiting 10 seconds for first heartbeat...
timeout /t 10 /nobreak >nul
echo Checking backend for device "!ALIAS!"...
set API_FILE=!TEMP!\mdm_verify.txt
curl -s -H "X-Admin-Key: !ADMIN_KEY!" "!BASE_URL!/admin/devices?alias=!ALIAS!" -o "!API_FILE!" 2>nul
findstr /C:"\"alias\":\"!ALIAS!\"" "!API_FILE!" >nul 2>&1
if errorlevel 1 (
    echo ❌ Device NOT found in backend
    type "!API_FILE!"
    del "!API_FILE!" >nul 2>&1
    echo.
    echo ================================================
    echo ❌❌❌ ENROLLMENT FAILED ❌❌❌
    echo ================================================
    echo Device: !ALIAS! did not register
    echo Check server logs
    echo ================================================
    set EXITCODE=9
    goto :end
)
del "!API_FILE!" >nul 2>&1
echo ✅ Device registered!
echo.
echo ================================================
echo ✅✅✅ ENROLLMENT SUCCESS ✅✅✅
echo ================================================
echo 📱 Device "!ALIAS!" enrolled and verified!
echo 🔍 Check dashboard now - device is online
echo.
echo ⚠️  MANUAL STEPS REQUIRED ON DEVICE:
echo.
echo 1. Enable Usage Access:
echo    Settings → Apps → Special app access → Usage access → NexMDM → Allow
echo.
echo 2. Enable Full Screen Intents (Android 14+):
echo    Settings → Apps → NexMDM → Notifications → Use full screen intents → Allow
echo.
echo 💡 These permissions enable battery/RAM monitoring and alert notifications.
echo    The device will send metrics to the dashboard within 60 seconds.
echo ================================================
set EXITCODE=0

:end
echo.
if not "!EXITCODE!"=="0" (
    echo [Diagnostics] Capturing ADB logs...
    set DIAG_FILE=!TEMP!\mdm_enroll_diag.txt
    echo NexMDM Enrollment Diagnostics > "!DIAG_FILE!"
    echo Generated: %DATE% %TIME% >> "!DIAG_FILE!"
    echo Device Alias: !ALIAS! >> "!DIAG_FILE!"
    echo Exit Code: !EXITCODE! >> "!DIAG_FILE!"
    echo. >> "!DIAG_FILE!"
    echo ===== ADB Logcat ===== >> "!DIAG_FILE!"
    adb logcat -d | findstr /i "nexmdm usage appops standby deviceidle" >> "!DIAG_FILE!" 2>&1
    echo. >> "!DIAG_FILE!"
    echo Diagnostics saved to: !DIAG_FILE!
    echo.
)
pause
exit /b !EXITCODE!
'''
    
    return Response(
        content=script_content,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="enroll-{alias}.cmd"'
        }
    )

@app.get("/v1/scripts/enroll.sh")
async def get_bash_enroll_script(
    alias: str = Query(...),
    agent_pkg: str = Query("com.nexmdm"),
    unity_pkg: str = Query("com.unitynetwork.unityapp"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate zero-tap Bash enrollment script with enhanced debugging"""
    from models import EnrollmentEvent
    
    server_url = config.server_url
    
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY environment variable not set")
    
    event = EnrollmentEvent(
        event_type='script.render',
        token_id=None,
        alias=alias,
        details=json.dumps({
            "platform": "bash",
            "agent_pkg": agent_pkg,
            "unity_pkg": unity_pkg,
            "generated_by": current_user.username
        })
    )
    db.add(event)
    db.commit()
    
    script_content = f'''#!/bin/bash
# ============================================================
# UnityMDM Zero-Tap Device Enrollment Script (Bash/POSIX)
# Device Alias: {alias}
# Package: {agent_pkg}
# ============================================================

set -e

PKG="{agent_pkg}"
ALIAS="{alias}"
RECEIVER=".NexDeviceAdminReceiver"
BASE_URL="{server_url}"
ADMIN_KEY="{admin_key}"
APK_PATH="/tmp/unitymdm.apk"
DEVICE_ALIAS="{alias}"

echo "================================================"
echo "UnityMDM Zero-Tap Enrollment"
echo "Device: $ALIAS"
echo "================================================"
echo

echo "[Step 0/10] Checking prerequisites..."
echo "   Checking for ADB..."
if ! command -v adb &> /dev/null; then
    echo "❌ ADB not found in PATH"
    echo "   Fix: Install Android Platform Tools and add to PATH"
    echo "   Download: https://developer.android.com/tools/releases/platform-tools"
    echo "   macOS: brew install android-platform-tools"
    echo "   Linux: sudo apt-get install android-tools-adb"
    exit 1
fi
echo "✅ ADB found"

ADB_VERSION=$(adb version 2>&1 | head -1)
echo "   Version: $ADB_VERSION"

echo "   Listing devices..."
adb devices -l
echo

echo "[Step 1/10] Wait for device..."
echo "   Waiting up to 60 seconds for device connection..."
if ! adb wait-for-device; then
    echo "❌ No device found"
    echo "   Fix: Check USB cable, ensure USB debugging enabled"
    echo "   Current devices:"
    adb devices -l
    exit 2
fi

DEVICE_COUNT=$(adb devices | grep -c "device$" || true)
if [ "$DEVICE_COUNT" -eq 0 ]; then
    echo "❌ No authorized device found"
    echo "   Current status:"
    adb devices -l
    echo
    echo "   Fix: Check if device shows 'unauthorized' and accept the prompt on device"
    exit 2
fi

DEVICE_SERIAL=$(adb devices | grep "device$" | head -1 | awk '{{print $1}}')
echo "✅ Device connected: $DEVICE_SERIAL"
echo

echo "[Step 2/10] Check Android version compatibility..."
MIN_SDK=30
DEVICE_SDK=$(adb shell getprop ro.build.version.sdk 2>/dev/null | tr -d '\\r')
DEVICE_VER=$(adb shell getprop ro.build.version.release 2>/dev/null | tr -d '\\r')

echo "   Device SDK: $DEVICE_SDK (Android $DEVICE_VER)"
echo "   Required: SDK $MIN_SDK+ (Android 11+)"

if [ -z "$DEVICE_SDK" ]; then
    echo "❌ Could not detect device SDK version"
    exit 2
fi

if [ "$DEVICE_SDK" -lt "$MIN_SDK" ] 2>/dev/null; then
    echo
    echo "❌ INCOMPATIBLE DEVICE"
    echo "   This device runs Android $DEVICE_VER (SDK $DEVICE_SDK)"
    echo "   NexMDM requires Android 11+ (SDK 30+)"
    echo
    echo "   Options:"
    echo "   1. Use a device with Android 11 or newer"
    echo "   2. Update this device's OS if possible"
    exit 2
fi
echo "✅ Android version compatible"
echo

echo "[Step 3/10] Download latest APK..."
if ! curl -L -H "X-Admin-Key: $ADMIN_KEY" "$BASE_URL/v1/apk/download-latest" -o "$APK_PATH" 2>/dev/null; then
    echo "❌ APK download failed"
    echo "   Fix: Check network connection and server availability"
    exit 3
fi
echo "✅ APK downloaded"
echo

echo "[Step 4/10] Install APK..."
if ! adb install -r -g "$APK_PATH" 2>/dev/null; then
    echo "   Retrying with uninstall first..."
    adb uninstall "$PKG" 2>/dev/null || true
    if ! adb install -r -g -t "$APK_PATH" 2>/dev/null; then
        echo "❌ APK installation failed"
        exit 4
    fi
fi
echo "✅ APK installed"
echo

echo "[Step 5/10] Set Device Owner..."
if ! adb shell dpm set-device-owner "$PKG/$RECEIVER" 2>/dev/null; then
    echo "❌ Device Owner setup failed"
    echo "   Fix: Factory reset the device and try again"
    exit 5
fi
echo "✅ Device Owner confirmed"
echo

echo "[Step 6/10] Grant permissions..."
adb shell pm grant "$PKG" android.permission.POST_NOTIFICATIONS 2>/dev/null || true
adb shell pm grant "$PKG" android.permission.ACCESS_FINE_LOCATION 2>/dev/null || true
adb shell pm grant "$PKG" android.permission.CAMERA 2>/dev/null || true
adb shell appops set "$PKG" RUN_ANY_IN_BACKGROUND allow 2>/dev/null || true
adb shell appops set "$PKG" GET_USAGE_STATS allow 2>/dev/null || true
adb shell dumpsys deviceidle whitelist +"$PKG" 2>/dev/null || true
echo "✅ Permissions granted"
echo

echo "[Step 7/10] Disable bloatware..."
BLOAT_FILE="/tmp/mdm_bloatware.txt"
if curl -s -H "X-Admin-Key: $ADMIN_KEY" "$BASE_URL/admin/bloatware-list" -o "$BLOAT_FILE" 2>/dev/null; then
    BLOAT_COUNT=0
    while IFS= read -r PKG_TO_DISABLE; do
        [ -n "$PKG_TO_DISABLE" ] && adb shell pm disable-user --user 0 "$PKG_TO_DISABLE" 2>/dev/null && BLOAT_COUNT=$((BLOAT_COUNT+1))
    done < "$BLOAT_FILE"
    echo "✅ Disabled $BLOAT_COUNT bloatware packages"
    rm -f "$BLOAT_FILE"
else
    echo "⚠️  Bloatware list download failed - continuing"
fi
echo

echo "[Step 8/10] Apply system tweaks..."
adb shell settings put global app_standby_enabled 0 2>/dev/null || true
adb shell settings put global battery_tip_constants app_restriction_enabled=false 2>/dev/null || true
adb shell settings put system screen_brightness_mode 0 2>/dev/null || true
adb shell settings put system ambient_tilt_to_wake 1 2>/dev/null || true
adb shell settings put system ambient_touch_to_wake 1 2>/dev/null || true
echo "✅ System tweaks applied"
echo

echo "[Step 9/10] Auto-enroll and launch..."
if ! adb shell am broadcast -a com.nexmdm.CONFIGURE -n "$PKG/.ConfigReceiver" --receiver-foreground --es server_url "$BASE_URL" --es admin_key "$ADMIN_KEY" --es alias "$ALIAS" 2>/dev/null; then
    echo "❌ Broadcast failed"
    exit 7
fi
echo "✅ Auto-enrollment initiated"
adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
echo

echo "[Step 10/10] Verify service..."
sleep 3
if ! adb shell pidof "$PKG" 2>/dev/null; then
    echo "❌ Service not running"
    exit 8
fi
echo "✅ Service running"
echo

echo "Verify registration..."
echo "Waiting 10 seconds for first heartbeat..."
sleep 10
echo "Checking backend for device \\"$ALIAS\\"..."
API_RESP=$(curl -s -H "X-Admin-Key: $ADMIN_KEY" "$BASE_URL/admin/devices?alias=$ALIAS" 2>/dev/null)
if echo "$API_RESP" | grep -q "\\"alias\\":\\"$ALIAS\\""; then
    echo "✅ Device registered!"
    echo
    echo "================================================"
    echo "✅✅✅ ENROLLMENT SUCCESS ✅✅✅"
    echo "================================================"
    echo "📱 Device \\"$ALIAS\\" enrolled and verified!"
    echo "🔍 Check dashboard now - device is online"
    echo
    echo "⚠️  MANUAL STEPS REQUIRED ON DEVICE:"
    echo
    echo "1. Enable Usage Access:"
    echo "   Settings → Apps → Special app access → Usage access → NexMDM → Allow"
    echo
    echo "2. Enable Full Screen Intents (Android 14+):"
    echo "   Settings → Apps → NexMDM → Notifications → Use full screen intents → Allow"
    echo
    echo "💡 These permissions enable battery/RAM monitoring and alert notifications."
    echo "   The device will send metrics to the dashboard within 60 seconds."
    echo "================================================"
else
    echo "❌ Device NOT found in backend"
    echo "   API Response: $API_RESP"
    echo
    DIAG_FILE="/tmp/mdm_enroll_diag.txt"
    echo "NexMDM Enrollment Diagnostics" > "$DIAG_FILE"
    echo "Generated: $(date)" >> "$DIAG_FILE"
    echo "Device Alias: $ALIAS" >> "$DIAG_FILE"
    echo "Exit Code: 9" >> "$DIAG_FILE"
    echo "API Response: $API_RESP" >> "$DIAG_FILE"
    echo "" >> "$DIAG_FILE"
    echo "===== ADB Logcat =====" >> "$DIAG_FILE"
    adb logcat -d 2>&1 | grep -i "nexmdm\\|usage\\|appops\\|standby\\|deviceidle" >> "$DIAG_FILE" 2>&1 || true
    echo "" >> "$DIAG_FILE"
    echo "Diagnostics saved to: $DIAG_FILE"
    echo
    echo "================================================"
    echo "❌❌❌ ENROLLMENT FAILED ❌❌❌"
    echo "================================================"
    echo "📱 Device \\"$ALIAS\\" did not register"
    echo "🔍 Check server logs for errors"
    echo "   Debug: Check /v1/register endpoint"
    echo "   Diagnostics saved to: $DIAG_FILE"
    echo "================================================"
    exit 9
fi
'''
    
    return Response(
        content=script_content,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="enroll-{alias}.sh"'
        }
    )

@app.get("/v1/scripts/enroll.one-liner.cmd")
async def get_windows_one_liner_script(
    alias: str = Query(...),
    agent_pkg: str = Query("com.nexmdm"),
    unity_pkg: str = Query("com.unitynetwork.unityapp"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate zero-tap Windows one-liner enrollment command with enhanced debugging"""
    from models import EnrollmentEvent
    
    server_url = config.server_url
    
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY environment variable not set")
    
    event = EnrollmentEvent(
        event_type='script.render_one_liner',
        token_id=None,
        alias=alias,
        details=json.dumps({
            "platform": "windows_oneliner",
            "agent_pkg": agent_pkg,
            "unity_pkg": unity_pkg,
            "generated_by": current_user.username
        })
    )
    db.add(event)
    db.commit()
    
    structured_logger.log_event(
        "script.render_one_liner",
        token_id=None,
        alias=alias,
        platform="windows",
        generated_by=current_user.username
    )
    
    metrics.inc_counter("script_oneliner_copies_total", {"platform": "windows", "alias": alias})
    
    apk_path = "%TEMP%\\\\unitymdm.apk"
    bloat_file = "%TEMP%\\\\mdm_bloatware.txt"
    
    one_liner = f'''cmd.exe /K "echo ============================================ & echo UnityMDM Zero-Tap Enrollment v3 - {alias} & echo ============================================ & echo. & echo [Step 0/10] Check prerequisites... & where adb & echo. & echo [Step 1/10] Wait for device... & adb wait-for-device & adb devices -l & echo. & echo [Step 2/10] Check Android version... & adb shell getprop ro.build.version.release & adb shell getprop ro.build.version.sdk & echo. & echo [Step 3/10] Download APK... & curl -L -H X-Admin-Key:{admin_key} {server_url}/v1/apk/download-latest -o {apk_path} & echo. & echo [Step 4/10] Install APK... & adb install -r -g {apk_path} & echo. & echo [Step 5/10] Verify package installed... & adb shell pm path {agent_pkg} & echo. & echo [Step 6/10] Set Device Owner... & adb shell dpm set-device-owner {agent_pkg}/.NexDeviceAdminReceiver & echo. & echo [Step 7/10] Grant permissions... & adb shell pm grant {agent_pkg} android.permission.POST_NOTIFICATIONS & adb shell pm grant {agent_pkg} android.permission.ACCESS_FINE_LOCATION & adb shell appops set {agent_pkg} RUN_ANY_IN_BACKGROUND allow & adb shell appops set {agent_pkg} GET_USAGE_STATS allow & adb shell dumpsys deviceidle whitelist +{agent_pkg} & echo. & echo [Step 8/10] Apply system tweaks... & adb shell settings put global app_standby_enabled 0 & echo. & echo [Step 9/10] Auto-enroll and launch... & adb shell am broadcast -a com.nexmdm.CONFIGURE -n {agent_pkg}/.ConfigReceiver --receiver-foreground --es server_url {server_url} --es admin_key {admin_key} --es alias {alias} & adb shell monkey -p {agent_pkg} -c android.intent.category.LAUNCHER 1 & echo. & echo [Step 10/10] Verify service... & timeout /t 5 /nobreak >nul & adb shell pidof {agent_pkg} & echo. & echo ============================================ & echo Enrollment complete for {alias} & echo ============================================"'''
    
    return Response(
        content=one_liner,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'inline; filename="enroll-{alias}-oneliner.cmd"'
        }
    )

@app.get("/v1/scripts/enroll.one-liner.sh")
async def get_bash_one_liner_script(
    alias: str = Query(...),
    agent_pkg: str = Query("com.nexmdm"),
    unity_pkg: str = Query("com.unitynetwork.unityapp"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate zero-tap Bash one-liner enrollment command with enhanced debugging"""
    from models import EnrollmentEvent
    
    server_url = config.server_url
    
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY environment variable not set")
    
    event = EnrollmentEvent(
        event_type='script.render_one_liner',
        token_id=None,
        alias=alias,
        details=json.dumps({
            "platform": "bash_oneliner",
            "agent_pkg": agent_pkg,
            "unity_pkg": unity_pkg,
            "generated_by": current_user.username
        })
    )
    db.add(event)
    db.commit()
    
    structured_logger.log_event(
        "script.render_one_liner",
        token_id=None,
        alias=alias,
        platform="bash",
        generated_by=current_user.username
    )
    
    metrics.inc_counter("script_oneliner_copies_total", {"platform": "bash", "alias": alias})
    
    one_liner = f'''PKG="{agent_pkg}" ALIAS="{alias}" BASE_URL="{server_url}" ADMIN_KEY="{admin_key}" APK="/tmp/unitymdm.apk" BLOAT_FILE="/tmp/mdm_bloatware.txt" MIN_SDK=30 && echo "================================================" && echo "UnityMDM Zero-Tap Enrollment v3 - $ALIAS" && echo "Supports: Android 11+ (SDK 30+)" && echo "================================================" && echo && echo "[Step 0/10] Check prerequisites..." && (command -v adb &>/dev/null && echo "✅ ADB found: $(adb version 2>&1 | head -1)") || (echo "❌ ADB not found in PATH" && echo "Fix: Install Android Platform Tools" && echo "Download: https://developer.android.com/tools/releases/platform-tools" && exit 1) && echo "Listing devices:" && adb devices -l && echo && echo "[Step 1/10] Wait for device..." && (adb wait-for-device 2>/dev/null && echo "✅ Device connected") || (echo "❌ No device found. Fix: Check USB cable" && adb devices -l && exit 2) && echo && echo "[Step 2/10] Check Android version..." && DEVICE_SDK=$(adb shell getprop ro.build.version.sdk 2>/dev/null | tr -d '\\r') && DEVICE_VER=$(adb shell getprop ro.build.version.release 2>/dev/null | tr -d '\\r') && echo "Device: Android $DEVICE_VER (SDK $DEVICE_SDK)" && echo "Required: SDK $MIN_SDK+ (Android 11+)" && ([ "$DEVICE_SDK" -ge "$MIN_SDK" ] 2>/dev/null && echo "✅ Compatible") || (echo "❌ INCOMPATIBLE - Requires Android 11+ (SDK 30+)" && exit 2) && echo && echo "[Step 3/10] Download latest APK..." && (curl -L -H "X-Admin-Key: $ADMIN_KEY" "$BASE_URL/v1/apk/download-latest" -o "$APK" 2>/dev/null && echo "✅ APK downloaded") || (echo "❌ Download failed. Fix: Check network" && exit 3) && echo && echo "[Step 4/10] Install APK..." && (adb install -r -g "$APK" 2>/dev/null && echo "✅ APK installed") || (adb uninstall "$PKG" 2>/dev/null; (adb install -r -g -t "$APK" 2>/dev/null && echo "✅ APK installed") || (echo "❌ Install failed" && exit 4)) && echo && echo "[Step 5/10] Set Device Owner..." && (adb shell dpm set-device-owner "$PKG/.NexDeviceAdminReceiver" 2>/dev/null && echo "✅ Device Owner confirmed") || (echo "❌ Device Owner failed. Fix: Factory reset device" && exit 5) && echo && echo "[Step 6/10] Grant permissions..." && adb shell pm grant "$PKG" android.permission.POST_NOTIFICATIONS 2>/dev/null; adb shell pm grant "$PKG" android.permission.ACCESS_FINE_LOCATION 2>/dev/null; adb shell pm grant "$PKG" android.permission.CAMERA 2>/dev/null; adb shell appops set "$PKG" RUN_ANY_IN_BACKGROUND allow 2>/dev/null; adb shell appops set "$PKG" GET_USAGE_STATS allow 2>/dev/null; adb shell dumpsys deviceidle whitelist +"$PKG" 2>/dev/null && echo "✅ Permissions granted" && echo && echo "[Step 7/10] Disable bloatware..." && curl -s -H "X-Admin-Key: $ADMIN_KEY" "$BASE_URL/admin/bloatware-list" -o "$BLOAT_FILE" 2>/dev/null && (BLOAT_COUNT=0 && while IFS= read -r PKG_TO_DISABLE; do [ -n "$PKG_TO_DISABLE" ] && adb shell pm disable-user --user 0 "$PKG_TO_DISABLE" 2>/dev/null && BLOAT_COUNT=$((BLOAT_COUNT+1)); done < "$BLOAT_FILE" && echo "✅ Disabled $BLOAT_COUNT bloatware packages" && rm -f "$BLOAT_FILE") || echo "⚠️  Bloatware list download failed - continuing" && echo && echo "[Step 8/10] Apply system tweaks..." && adb shell settings put global app_standby_enabled 0 2>/dev/null; adb shell settings put global battery_tip_constants app_restriction_enabled=false 2>/dev/null; adb shell settings put system screen_brightness_mode 0 2>/dev/null; adb shell settings put system ambient_tilt_to_wake 1 2>/dev/null; adb shell settings put system ambient_touch_to_wake 1 2>/dev/null && echo "✅ System tweaks applied" && echo && echo "[Step 9/10] Auto-enroll and launch..." && (adb shell am broadcast -a com.nexmdm.CONFIGURE -n "$PKG/.ConfigReceiver" --receiver-foreground --es server_url "$BASE_URL" --es admin_key "$ADMIN_KEY" --es alias "$ALIAS" 2>/dev/null && echo "✅ Auto-enrollment initiated" && adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1) || (echo "❌ Broadcast failed" && exit 7) && echo && echo "[Step 10/10] Verify service..." && sleep 3 && (adb shell pidof "$PKG" 2>/dev/null && echo "✅ Service running") || (echo "❌ Service not running" && exit 8) && echo && echo "Verify registration..." && echo "Waiting 10 seconds for first heartbeat..." && sleep 10 && echo "Checking backend for device \\"$ALIAS\\"..." && API_RESP=$(curl -s -H "X-Admin-Key: $ADMIN_KEY" "$BASE_URL/admin/devices?alias=$ALIAS" 2>/dev/null) && if echo "$API_RESP" | grep -q "\\"alias\\":\\"$ALIAS\\""; then echo "✅ Device registered!" && echo && echo "================================================" && echo "✅✅✅ ENROLLMENT SUCCESS ✅✅✅" && echo "================================================" && echo "📱 Device \\"$ALIAS\\" enrolled and verified!" && echo "🔍 Check dashboard - device should be online" && echo "================================================"; else echo "❌ Device NOT found in backend" && echo "API Response: $API_RESP" && echo && echo "================================================" && echo "❌❌❌ ENROLLMENT FAILED ❌❌❌" && echo "================================================" && echo "📱 Device \\"$ALIAS\\" did not register" && echo "🔍 Check server logs" && echo "================================================" && exit 9; fi'''
    
    return Response(
        content=one_liner,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'inline; filename="enroll-{alias}-oneliner.sh"'
        }
    )

# ==================== APK Management ====================

@app.post("/v1/apk/upload")
async def upload_apk(
    file: UploadFile = File(...),
    package_name: str = Form(...),
    version_name: str = Form(...),
    version_code: int = Form(...),
    notes: Optional[str] = Form(None),
    api_key: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Upload a new APK version (supports API key as form field or session auth)"""
    # Verify API key OR user session
    if api_key:
        admin_key = os.getenv("ADMIN_KEY", "")
        print(f"[DEBUG APK UPLOAD] Received API key length: {len(api_key) if api_key else 0}")
        print(f"[DEBUG APK UPLOAD] Expected API key length: {len(admin_key) if admin_key else 0}")
        print(f"[DEBUG APK UPLOAD] First 10 chars of received: {api_key[:10] if api_key else 'None'}")
        print(f"[DEBUG APK UPLOAD] First 10 chars of expected: {admin_key[:10] if admin_key else 'None'}")
        print(f"[DEBUG APK UPLOAD] Keys match: {api_key == admin_key}")

        if not admin_key or api_key != admin_key:
            raise HTTPException(status_code=401, detail="Invalid API key")
        username = "github-actions"
    elif current_user:
        username = current_user.username
    else:
        raise HTTPException(status_code=401, detail="Authentication required (API key or session)")

    apk_version = await save_apk_file(
        file=file,
        package_name=package_name,
        version_name=version_name,
        version_code=version_code,
        db=db,
        uploaded_by=username,
        notes=notes
    )

    base_url = config.server_url

    return {
        "id": apk_version.id,
        "package_name": apk_version.package_name,
        "version_name": apk_version.version_name,
        "version_code": apk_version.version_code,
        "file_size": apk_version.file_size,
        "uploaded_at": apk_version.uploaded_at.isoformat(),
        "uploaded_by": apk_version.uploaded_by,
        "download_url": get_apk_download_url(apk_version, base_url),
        "notes": apk_version.notes
    }

@app.post("/v1/apk/upload-chunk")
async def upload_apk_chunk(
    file: UploadFile = File(...),
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    filename: str = Form(...),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Upload a single chunk of an APK file"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    from pathlib import Path
    import re

    if not re.match(r'^[a-zA-Z0-9\-_]+$', upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload_id format")

    CHUNK_SIZE = 5 * 1024 * 1024
    dest_dir = Path("/tmp/apk_uploads") / upload_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    chunk_path = dest_dir / f"part_{chunk_index}"

    try:
        with open(chunk_path, "wb") as f:
            while data := await file.read(CHUNK_SIZE):
                f.write(data)

        structured_logger.log_event(
            "apk.chunk_uploaded",
            upload_id=upload_id,
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            filename=filename,
            user=current_user.username
        )

        return {"status": "ok", "chunk_index": chunk_index}
    except Exception as e:
        structured_logger.log_event(
            "apk.chunk_upload_failed",
            level="ERROR",
            upload_id=upload_id,
            chunk_index=chunk_index,
            error=str(e),
            user=current_user.username
        )
        raise HTTPException(status_code=500, detail=f"Failed to save chunk: {str(e)}")

@app.post("/v1/apk/complete")
async def complete_apk_upload(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Complete a chunked APK upload by merging chunks and creating database entry"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    from pathlib import Path
    import shutil
    import re

    body = await request.json()
    upload_id = body.get("upload_id")
    package_name = body.get("package_name")
    version_name = body.get("version_name")
    version_code = body.get("version_code")
    filename = body.get("filename")
    total_chunks = body.get("total_chunks")
    build_type = body.get("build_type", "release")

    if not all([upload_id, package_name, version_name, version_code, filename, total_chunks]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    if not re.match(r'^[a-zA-Z0-9\-_]+$', upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload_id format")

    start_time = time.time()
    dest_dir = Path("/tmp/apk_uploads") / upload_id

    try:

        if not dest_dir.exists():
            raise HTTPException(status_code=404, detail="Upload not found")

        for i in range(total_chunks):
            chunk_path = dest_dir / f"part_{i}"
            if not chunk_path.exists():
                raise HTTPException(status_code=400, detail=f"Missing chunk {i}")

        merged_path = dest_dir / "merged.apk"

        with open(merged_path, "wb") as outfile:
            for i in range(total_chunks):
                chunk_path = dest_dir / f"part_{i}"
                with open(chunk_path, "rb") as infile:
                    shutil.copyfileobj(infile, outfile)

        file_size = merged_path.stat().st_size

        sha256_hash = hashlib.sha256()
        with open(merged_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        sha256 = sha256_hash.hexdigest()

        original_version_code = version_code
        while True:
            existing = db.query(ApkVersion).filter(
                ApkVersion.package_name == package_name,
                ApkVersion.version_code == version_code
            ).first()

            if not existing:
                break

            version_code += 1

        if version_code != original_version_code:
            structured_logger.log_event(
                "apk.version_code_incremented",
                level="INFO",
                package_name=package_name,
                original_version_code=original_version_code,
                new_version_code=version_code,
                user=current_user.username
            )

        with open(merged_path, "rb") as f:
            content = f.read()

        storage = get_storage_service()
        final_filename = f"{package_name}_{version_code}.apk"
        object_path = storage.upload_file(
            file_data=content,
            filename=final_filename,
            content_type="application/vnd.android.package-archive"
        )

        apk_version = ApkVersion(
            version_name=version_name,
            version_code=version_code,
            file_path=object_path,
            file_size=file_size,
            package_name=package_name,
            uploaded_at=datetime.now(timezone.utc),
            uploaded_by=current_user.username,
            is_active=True,
            sha256=sha256,
            build_type=build_type
        )

        db.add(apk_version)
        db.commit()
        db.refresh(apk_version)

        shutil.rmtree(dest_dir)

        duration = time.time() - start_time

        log_dir = Path("/tmp/logs")
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "apk_uploads.log"

        with open(log_file, "a") as f:
            log_entry = (
                f"{datetime.now(timezone.utc).isoformat()} | "
                f"SUCCESS | {filename} | "
                f"uploader={current_user.username} | "
                f"size={file_size} bytes | "
                f"duration={duration:.2f}s | "
                f"sha256={sha256}\n"
            )
            f.write(log_entry)

        structured_logger.log_event(
            "apk.upload_completed",
            upload_id=upload_id,
            filename=filename,
            package_name=package_name,
            version_name=version_name,
            version_code=version_code,
            file_size=file_size,
            duration_seconds=duration,
            user=current_user.username,
            sha256=sha256
        )

        base_url = config.server_url

        return {
            "id": apk_version.id,
            "package_name": apk_version.package_name,
            "version_name": apk_version.version_name,
            "version_code": apk_version.version_code,
            "file_size": apk_version.file_size,
            "uploaded_at": apk_version.uploaded_at.isoformat(),
            "uploaded_by": apk_version.uploaded_by,
            "download_url": get_apk_download_url(apk_version, base_url),
            "sha256": sha256
        }

    except HTTPException:
        raise
    except Exception as e:
        duration = time.time() - start_time

        log_dir = Path("/tmp/logs")
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "apk_uploads.log"

        with open(log_file, "a") as f:
            log_entry = (
                f"{datetime.now(timezone.utc).isoformat()} | "
                f"FAILED | {filename} | "
                f"uploader={current_user.username} | "
                f"duration={duration:.2f}s | "
                f"error={str(e)}\n"
            )
            f.write(log_entry)

        structured_logger.log_event(
            "apk.upload_failed",
            level="ERROR",
            upload_id=upload_id,
            filename=filename,
            error=str(e),
            duration_seconds=duration,
            user=current_user.username
        )

        if dest_dir.exists():
            shutil.rmtree(dest_dir)

        raise HTTPException(status_code=500, detail=f"Failed to complete upload: {str(e)}")

@app.get("/v1/apk/list")
async def list_apk_versions(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """List all uploaded APK versions with OTA deployment info"""
    from models import ApkDeploymentStats

    apks = db.query(ApkVersion).filter(ApkVersion.is_active == True).order_by(ApkVersion.uploaded_at.desc()).all()

    base_url = config.server_url

    result = []
    for apk in apks:
        stats = db.query(ApkDeploymentStats).filter(
            ApkDeploymentStats.build_id == apk.id
        ).first()

        apk_data = {
            "id": apk.id,
            "package_name": apk.package_name,
            "version_name": apk.version_name,
            "version_code": apk.version_code,
            "file_size": apk.file_size,
            "uploaded_at": apk.uploaded_at.isoformat(),
            "uploaded_by": apk.uploaded_by,
            "download_url": get_apk_download_url(apk, base_url),
            "notes": apk.notes,
            "is_current": apk.is_current,
            "staged_rollout_percent": apk.staged_rollout_percent if apk.is_current else None,
            "promoted_at": apk.promoted_at.isoformat() if apk.promoted_at else None,
            "promoted_by": apk.promoted_by,
            "wifi_only": apk.wifi_only,
            "must_install": apk.must_install,
            "signer_fingerprint": apk.signer_fingerprint
        }

        if stats:
            apk_data["deployment_stats"] = {
                "total_checks": stats.total_checks,
                "total_eligible": stats.total_eligible,
                "total_downloads": stats.total_downloads,
                "installs_success": stats.installs_success,
                "installs_failed": stats.installs_failed,
                "verify_failed": stats.verify_failed,
                "adoption_rate": round((stats.installs_success / stats.total_eligible * 100), 2) if stats.total_eligible > 0 else 0
            }
        else:
            apk_data["deployment_stats"] = None

        result.append(apk_data)

    return result

@app.get("/v1/apk/download/{apk_id}")
async def download_apk_version(
    apk_id: str,
    request: Request,
    x_device_token: Optional[str] = Header(None),
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
    installation_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """Download a specific APK version (requires device token or admin authentication)"""
    from models import ApkDownloadEvent

    device = None
    token_id_last4 = "anon"
    auth_source = "unknown"

    # Try admin key authentication first
    if x_admin_key:
        admin_key = os.getenv("ADMIN_KEY", "")
        if admin_key and x_admin_key == admin_key:
            auth_source = "admin"
            token_id_last4 = "admin"

    # Try device token authentication if not admin
    if auth_source != "admin" and x_device_token:
        device = get_device_by_token(x_device_token, db)
        if device:
            token_id_last4 = device.token_id[-4:] if device.token_id else "none"
            auth_source = "device"

    # Require valid authentication (either admin key or device token)
    if auth_source not in ["admin", "device"]:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    # Handle "latest" as special case
    if apk_id.lower() == "latest":
        apk = db.query(ApkVersion).filter(
            ApkVersion.is_active == True
        ).order_by(ApkVersion.uploaded_at.desc()).first()
        if not apk:
            raise HTTPException(status_code=404, detail="No APK versions available")
    else:
        try:
            apk_id_int = int(apk_id)
            apk = db.query(ApkVersion).filter(ApkVersion.id == apk_id_int).first()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid APK ID format")

        if not apk:
            raise HTTPException(status_code=404, detail="APK not found")

    # Validate that file_path exists (not empty or None)
    if not apk.file_path or apk.file_path.strip() == "":
        structured_logger.log_event(
            "apk.download.error",
            error="missing_file_path",
            build_id=apk.id,
            version_code=apk.version_code,
            package_name=apk.package_name
        )
        raise HTTPException(
            status_code=500,
            detail=f"APK file path is missing in database. This APK was not uploaded successfully. Please re-upload APK {apk.id}."
        )

    # Download from App Storage
    try:
        storage = get_storage_service()
        file_data, content_type, file_size = storage.download_file(apk.file_path)
    except ObjectNotFoundError:
        raise HTTPException(status_code=404, detail="APK file not found in storage")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download APK: {str(e)}")

    structured_logger.log_event(
        "apk.download",
        build_id=apk.id,
        version_code=apk.version_code,
        version_name=apk.version_name,
        build_type=apk.build_type or "unknown",
        token_id=token_id_last4,
        source=auth_source,
        device_id=device.id if device else None
    )

    download_event = ApkDownloadEvent(
        build_id=apk.id,
        source=auth_source,
        token_id=token_id_last4,
        admin_user=None,
        ip=request.client.host if request.client else None
    )
    db.add(download_event)
    db.commit()

    metrics.inc_counter("apk_download_total", {
        "build_type": apk.build_type or "unknown",
        "source": auth_source
    })

    if device:
        print(f"[APK DOWNLOAD] Device {device.id} ({device.alias}) downloading APK {apk.package_name} v{apk.version_code}")
    else:
        print(f"[APK DOWNLOAD] Enrollment token download: APK {apk.package_name} v{apk.version_code}")

    return Response(
        content=file_data,
        media_type="application/vnd.android.package-archive",
        headers={
            "Content-Disposition": f'attachment; filename="{apk.package_name}_{apk.version_code}.apk"',
            "Content-Length": str(file_size)
        }
    )

@app.get("/v1/apk/download-web/{apk_id}")
async def download_apk_web(
    apk_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Download APK to local machine (requires user authentication) - For dashboard users"""
    apk = db.query(ApkVersion).filter(ApkVersion.id == apk_id).first()
    if not apk:
        raise HTTPException(status_code=404, detail="APK not found")

    # Validate that file_path exists (not empty or None)
    if not apk.file_path or apk.file_path.strip() == "":
        raise HTTPException(
            status_code=500,
            detail=f"APK file path is missing in database. This APK was not uploaded successfully. Please re-upload APK {apk.id}."
        )

    # Download from App Storage
    try:
        storage = get_storage_service()
        file_data, content_type, file_size = storage.download_file(apk.file_path)
    except ObjectNotFoundError:
        raise HTTPException(status_code=404, detail="APK file not found in storage")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download APK: {str(e)}")

    print(f"[APK WEB DOWNLOAD] User {current_user.username} downloading APK {apk.package_name} v{apk.version_code}")

    return Response(
        content=file_data,
        media_type="application/vnd.android.package-archive",
        headers={
            "Content-Disposition": f'attachment; filename="{apk.package_name}_{apk.version_code}.apk"',
            "Content-Length": str(file_size)
        }
    )

@app.get("/v1/apk/download-latest")
async def download_latest_apk(
    request: Request,
    x_admin_key: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Download the latest APK version (requires X-Admin-Key) - For ADB enrollment scripts"""
    from models import ApkDownloadEvent

    # Verify admin key
    if not x_admin_key or not verify_admin_key(x_admin_key):
        raise HTTPException(status_code=401, detail="Admin key required")

    # Get the latest active APK with package name starting with 'com.nexmdm'
    apk = db.query(ApkVersion).filter(
        ApkVersion.is_active == True,
        ApkVersion.package_name.like("com.nexmdm%")
    ).order_by(
        ApkVersion.uploaded_at.desc()
    ).first()

    if not apk:
        raise HTTPException(status_code=404, detail="No NexMDM APK versions available (package must start with com.nexmdm)")

    # Validate that file_path exists (not empty or None)
    if not apk.file_path or apk.file_path.strip() == "":
        raise HTTPException(
            status_code=500,
            detail=f"APK file path is missing in database. This APK was not uploaded successfully. Please re-upload APK {apk.id}."
        )

    # Download from App Storage
    try:
        storage = get_storage_service()
        file_data, content_type, file_size = storage.download_file(apk.file_path)
    except ObjectNotFoundError:
        raise HTTPException(status_code=404, detail="APK file not found in storage")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download APK: {str(e)}")

    structured_logger.log_event(
        "apk.download",
        build_id=apk.id,
        version_code=apk.version_code,
        version_name=apk.version_name,
        build_type=apk.build_type or "unknown",
        token_id="admin",
        source="enrollment",
        auth_method="admin_key"
    )

    download_event = ApkDownloadEvent(
        build_id=apk.id,
        source="enrollment",
        token_id="admin",
        admin_user="admin_key",
        ip=request.client.host if request.client else None
    )
    db.add(download_event)
    db.commit()

    metrics.inc_counter("apk_download_total", {
        "build_type": apk.build_type or "unknown",
        "source": "enrollment"
    })

    print(f"[APK LATEST DOWNLOAD] Downloading latest APK {apk.package_name} v{apk.version_code} via admin key")

    return Response(
        content=file_data,
        media_type="application/vnd.android.package-archive",
        headers={
            "Content-Disposition": f'attachment; filename="{apk.package_name}_{apk.version_code}.apk"',
            "Content-Length": str(file_size)
        }
    )

async def send_fcm_to_device(device, installation, apk, download_url, current_user, db):
    """Send FCM message to a single device (for parallel execution)"""
    message_data = {
        "action": "install_apk",
        "apk_id": str(apk.id),
        "installation_id": str(installation.id),
        "download_url": download_url,
        "package_name": apk.package_name,
        "version_name": apk.version_name,
        "version_code": str(apk.version_code),
        "file_size": str(apk.file_size),
        "sha256": apk.sha256 or ""
    }

    access_token = get_access_token()
    project_id = get_firebase_project_id()
    fcm_url = build_fcm_v1_url(project_id)

    message_payload = {
        "message": {
            "token": device.fcm_token,
            "data": message_data,
            "android": {
                "priority": "high"
            }
        }
    }

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                fcm_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json=message_payload,
                timeout=10.0
            )

            if response.status_code == 200:
                log_device_event(db, device.id, "apk_deploy_initiated", {
                    "apk_id": apk.id,
                    "package_name": apk.package_name,
                    "version": apk.version_name,
                    "initiated_by": current_user.username
                })
                return {"success": True, "installation_id": installation.id, "device": device}
            else:
                installation.status = "failed"
                installation.error_message = f"FCM error: {response.status_code}"
                installation.completed_at = datetime.now(timezone.utc)
                return {
                    "success": False,
                    "device": device,
                    "reason": f"FCM error: {response.status_code}"
                }
    except Exception as e:
        installation.status = "failed"
        installation.error_message = str(e)
        installation.completed_at = datetime.now(timezone.utc)
        return {
            "success": False,
            "device": device,
            "reason": str(e)
        }

@app.post("/v1/apk/deploy")
async def deploy_apk_to_devices(
    request: DeployApkRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Deploy APK to specific devices or all devices via FCM (with parallel broadcasting)"""
    apk = db.query(ApkVersion).filter(ApkVersion.id == request.apk_id).first()
    if not apk:
        raise HTTPException(status_code=404, detail="APK not found")

    if request.device_ids:
        devices = db.query(Device).filter(Device.id.in_(request.device_ids)).all()
    else:
        devices = db.query(Device).all()

    if not devices:
        raise HTTPException(status_code=400, detail="No devices found")

    base_url = config.server_url

    download_url = get_apk_download_url(apk, base_url)

    # Step 1: Create installation records for all devices and filter out devices without FCM token
    tasks = []
    failed_devices = []

    for device in devices:
        if not device.fcm_token:
            failed_devices.append({
                "device_id": device.id,
                "alias": device.alias,
                "reason": "No FCM token"
            })
            continue

        installation = ApkInstallation(
            device_id=device.id,
            apk_version_id=apk.id,
            status="pending",
            initiated_at=datetime.now(timezone.utc),
            initiated_by=current_user.username,
            download_progress=0
        )
        db.add(installation)
        db.flush()

        # Prepare parallel FCM task
        tasks.append(send_fcm_to_device(device, installation, apk, download_url, current_user, db))

    # Step 2: Send all FCM messages in parallel using asyncio.gather
    print(f"[APK DEPLOY] Broadcasting to {len(tasks)} devices in parallel...")
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Step 3: Process results
    success_count = 0
    installation_ids = []
    installations = []

    for result in results:
        if isinstance(result, Exception):
            print(f"[APK DEPLOY ERROR] {result}")
            continue

        if not isinstance(result, dict):
            print(f"[APK DEPLOY ERROR] Unexpected result type: {type(result)}")
            continue

        if result.get("success"):
            success_count += 1
            installation_ids.append(result["installation_id"])
            # Include device details for successful deployments
            device = result.get("device")
            if device:
                installations.append({
                    "installation_id": result["installation_id"],
                    "device": {
                        "id": device.id,
                        "alias": device.alias or "Unknown"
                    }
                })
        else:
            failed_devices.append({
                "device_id": result["device"].id,
                "alias": result["device"].alias,
                "reason": result.get("reason", "Unknown error")
            })

    db.commit()

    print(f"[APK DEPLOY] Complete: {success_count} successful, {len(failed_devices)} failed")

    return {
        "success": True,
        "total_devices": len(devices),
        "success_count": success_count,
        "failed_count": len(failed_devices),
        "installations": installations,
        "failed_devices": failed_devices,
        "installation_ids": installation_ids,
        "apk": {
            "id": apk.id,
            "package_name": apk.package_name,
            "version_name": apk.version_name,
            "version_code": apk.version_code
        }
    }

@app.delete("/v1/apk/{apk_id}")
async def delete_apk(
    apk_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an APK version"""
    apk = db.query(ApkVersion).filter(ApkVersion.id == apk_id).first()
    if not apk:
        raise HTTPException(status_code=404, detail="APK not found")

    storage_dir = os.path.join(os.path.dirname(__file__), "apk_storage")
    apk_file_path = os.path.join(storage_dir, f"{apk.package_name}_{apk.version_code}.apk")

    if os.path.exists(apk_file_path):
        try:
            os.remove(apk_file_path)
            print(f"Deleted APK file: {apk_file_path}")
        except Exception as e:
            print(f"Failed to delete APK file: {e}")

    db.query(ApkInstallation).filter(ApkInstallation.apk_version_id == apk_id).delete()

    db.delete(apk)
    db.commit()

    return {"success": True, "message": "APK deleted successfully"}

@app.get("/v1/apk/installations/{device_id}")
async def get_device_installation_status(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get installation history for a specific device"""
    installations = db.query(ApkInstallation).filter(
        ApkInstallation.device_id == device_id
    ).order_by(ApkInstallation.initiated_at.desc()).all()

    return [{
        "id": inst.id,
        "apk_version_id": inst.apk_version_id,
        "status": inst.status,
        "initiated_at": inst.initiated_at.isoformat(),
        "completed_at": inst.completed_at.isoformat() if inst.completed_at else None,
        "download_progress": inst.download_progress,
        "error_message": inst.error_message,
        "initiated_by": inst.initiated_by
    } for inst in installations]

@app.get("/v1/apk/installations")
async def get_all_installation_status(
    apk_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get installation status across all devices, optionally filtered by APK or status"""
    query = db.query(ApkInstallation)

    if apk_id:
        query = query.filter(ApkInstallation.apk_version_id == apk_id)
    if status:
        query = query.filter(ApkInstallation.status == status)

    installations = query.order_by(ApkInstallation.initiated_at.desc()).all()

    return [{
        "id": inst.id,
        "device_id": inst.device_id,
        "apk_version_id": inst.apk_version_id,
        "status": inst.status,
        "initiated_at": inst.initiated_at.isoformat(),
        "completed_at": inst.completed_at.isoformat() if inst.completed_at else None,
        "download_progress": inst.download_progress,
        "error_message": inst.error_message,
        "initiated_by": inst.initiated_by
    } for inst in installations]

class InstallationUpdateRequest(BaseModel):
    installation_id: int
    status: str
    download_progress: Optional[int] = None
    error_message: Optional[str] = None

@app.post("/v1/apk/installation/update")
async def update_installation_status(
    payload: InstallationUpdateRequest,
    x_device_token: str = Header(...),
    db: Session = Depends(get_db)
):
    """Update installation status from device"""
    # Rate limiting: prevent flooding from devices
    rate_limit_key = f"apk_update_{payload.installation_id}"
    if not apk_rate_limiter.is_allowed(rate_limit_key):
        raise HTTPException(status_code=429, detail="Too many update requests, slow down")

    # Optimize: Only fetch installations first to get device_id, then verify
    installation = db.query(ApkInstallation).filter(
        ApkInstallation.id == payload.installation_id
    ).first()

    if not installation:
        raise HTTPException(status_code=404, detail="Installation not found")

    # Only verify against the specific device (much faster)
    device = db.query(Device).filter(Device.id == installation.device_id).first()

    if not device or not verify_token(x_device_token, device.token_hash):
        raise HTTPException(status_code=401, detail="Invalid device token")

    installation = db.query(ApkInstallation).filter(
        ApkInstallation.id == payload.installation_id,
        ApkInstallation.device_id == device.id
    ).first()

    if not installation:
        raise HTTPException(status_code=404, detail="Installation not found")

    installation.status = payload.status
    if payload.download_progress is not None:
        installation.download_progress = payload.download_progress
    if payload.error_message:
        installation.error_message = payload.error_message
    if payload.status in ["completed", "failed"]:
        installation.completed_at = datetime.now(timezone.utc)

        event_type = "apk_install_success" if payload.status == "completed" else "apk_install_failed"
        details = {"installation_id": payload.installation_id, "status": payload.status}
        if payload.error_message:
            details["error"] = payload.error_message
        log_device_event(db, device.id, event_type, details)

    db.commit()

    await manager.broadcast({
        "type": "installation_update",
        "device_id": device.id,
        "installation_id": payload.installation_id,
        "status": payload.status,
        "progress": payload.download_progress
    })

    return {"success": True}

# ==================== OTA Update Management ====================

@app.get("/v1/agent/update")
async def agent_update_check(
    request: Request,
    x_device_token: str = Header(...),
    current_version_code: Optional[int] = Header(None, alias="x-current-version-code"),
    db: Session = Depends(get_db)
):
    """
    Agent OTA update check endpoint.
    Returns update manifest if device is eligible for rollout, 304 if no update available.
    """
    from ota_utils import get_current_build, is_device_eligible_for_rollout, increment_deployment_stat, log_ota_event, calculate_sha256
    from models import ApkDownloadEvent

    device = get_device_by_token(x_device_token, db)

    if not device:
        metrics.inc_counter("ota_checks_total", {"status": "unauthorized"})
        raise HTTPException(status_code=401, detail="Invalid device token")

    current_build = get_current_build(db, package_name="com.nexmdm.agent")

    if not current_build:
        log_ota_event("ota.manifest.304", device_id=device.id, reason="no_current_build")
        metrics.inc_counter("ota_checks_total", {"status": "no_build"})
        raise HTTPException(status_code=304, detail="No current build available")

    increment_deployment_stat(db, current_build.id, "total_checks")

    if current_version_code and current_version_code >= current_build.version_code:
        log_ota_event("ota.manifest.304", device_id=device.id, build_id=current_build.id,
                     current_version=current_version_code, reason="up_to_date")
        metrics.inc_counter("ota_checks_total", {"status": "up_to_date"})
        raise HTTPException(status_code=304, detail="Already on current version")

    if not is_device_eligible_for_rollout(device.id, current_build.staged_rollout_percent):
        log_ota_event("ota.manifest.304", device_id=device.id, build_id=current_build.id,
                     rollout_percent=current_build.staged_rollout_percent, reason="cohort_ineligible")
        metrics.inc_counter("ota_checks_total", {"status": "cohort_ineligible"})
        raise HTTPException(status_code=304, detail="Not in rollout cohort")

    increment_deployment_stat(db, current_build.id, "total_eligible")

    base_url = config.server_url

    download_url = f"{base_url}/v1/apk/download/{current_build.id}"

    sha256_checksum = None
    if os.path.exists(current_build.file_path):
        try:
            sha256_checksum = calculate_sha256(current_build.file_path)
        except Exception as e:
            print(f"Failed to calculate SHA256 for build {current_build.id}: {e}")

    log_ota_event("ota.manifest.200", device_id=device.id, build_id=current_build.id,
                 version_code=current_build.version_code, rollout_percent=current_build.staged_rollout_percent)
    metrics.inc_counter("ota_checks_total", {"status": "update_available"})

    return {
        "update_available": True,
        "build_id": current_build.id,
        "version_code": current_build.version_code,
        "version_name": current_build.version_name,
        "url": download_url,
        "file_size": current_build.file_size,
        "sha256": sha256_checksum,
        "signer_fingerprint": current_build.signer_fingerprint,
        "wifi_only": current_build.wifi_only,
        "must_install": current_build.must_install,
        "staged_rollout_percent": current_build.staged_rollout_percent,
        "package_name": current_build.package_name
    }

class PromoteApkRequest(BaseModel):
    staged_rollout_percent: int = 100
    wifi_only: bool = True
    must_install: bool = False

@app.post("/v1/apk/{apk_id}/promote")
async def promote_apk_build(
    apk_id: int,
    payload: PromoteApkRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Promote an APK build to current with staged rollout.
    Demotes any previously promoted build for the same package.
    """
    from ota_utils import log_ota_event, get_or_create_deployment_stats

    apk = db.query(ApkVersion).filter(ApkVersion.id == apk_id).first()
    if not apk:
        raise HTTPException(status_code=404, detail="APK not found")

    if not apk.is_active:
        raise HTTPException(status_code=400, detail="Cannot promote inactive APK")

    if payload.staged_rollout_percent < 0 or payload.staged_rollout_percent > 100:
        raise HTTPException(status_code=400, detail="Rollout percent must be between 0 and 100")

    previous_current = db.query(ApkVersion).filter(
        ApkVersion.package_name == apk.package_name,
        ApkVersion.is_current == True
    ).first()

    if previous_current:
        previous_current.is_current = False
        log_ota_event("ota.demote", build_id=previous_current.id,
                     version_code=previous_current.version_code, promoted_to=apk.id)

    apk.is_current = True
    apk.staged_rollout_percent = payload.staged_rollout_percent
    apk.wifi_only = payload.wifi_only
    apk.must_install = payload.must_install
    apk.promoted_at = datetime.now(timezone.utc)
    apk.promoted_by = current_user.username
    if previous_current:
        apk.rollback_from_build_id = previous_current.id

    get_or_create_deployment_stats(db, apk.id)

    db.commit()

    log_ota_event("ota.promote", build_id=apk.id, version_code=apk.version_code,
                 rollout_percent=payload.staged_rollout_percent, promoted_by=current_user.username,
                 wifi_only=payload.wifi_only, must_install=payload.must_install)
    metrics.inc_counter("ota_promotions_total", {"package": apk.package_name})

    structured_logger.log_event(
        "ota.promote",
        build_id=apk.id,
        version_code=apk.version_code,
        version_name=apk.version_name,
        rollout_percent=payload.staged_rollout_percent,
        promoted_by=current_user.username
    )

    return {
        "success": True,
        "build_id": apk.id,
        "version_code": apk.version_code,
        "version_name": apk.version_name,
        "staged_rollout_percent": apk.staged_rollout_percent,
        "promoted_at": apk.promoted_at.isoformat(),
        "promoted_by": apk.promoted_by,
        "previous_build_id": previous_current.id if previous_current else None
    }

class UpdateRolloutRequest(BaseModel):
    staged_rollout_percent: int

@app.post("/v1/apk/{apk_id}/rollout")
async def update_rollout_percentage(
    apk_id: int,
    payload: UpdateRolloutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update staged rollout percentage for the current build.
    """
    from ota_utils import log_ota_event

    apk = db.query(ApkVersion).filter(ApkVersion.id == apk_id).first()
    if not apk:
        raise HTTPException(status_code=404, detail="APK not found")

    if not apk.is_current:
        raise HTTPException(status_code=400, detail="APK is not the current build")

    if payload.staged_rollout_percent < 0 or payload.staged_rollout_percent > 100:
        raise HTTPException(status_code=400, detail="Rollout percent must be between 0 and 100")

    old_percent = apk.staged_rollout_percent
    apk.staged_rollout_percent = payload.staged_rollout_percent

    db.commit()

    log_ota_event("ota.rollout.update", build_id=apk.id,
                 version_code=apk.version_code,
                 old_percent=old_percent, new_percent=payload.staged_rollout_percent,
                 updated_by=current_user.username)

    structured_logger.log_event(
        "ota.rollout.update",
        build_id=apk.id,
        version_code=apk.version_code,
        old_percent=old_percent,
        new_percent=apk.staged_rollout_percent,
        updated_by=current_user.username
    )

    return {
        "success": True,
        "build_id": apk.id,
        "version_code": apk.version_code,
        "old_rollout_percent": old_percent,
        "new_rollout_percent": apk.staged_rollout_percent
    }

class RollbackRequest(BaseModel):
    force_downgrade: bool = False

@app.post("/v1/apk/rollback")
async def rollback_to_previous_build(
    payload: RollbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Rollback to the previous safe build.
    Sets the rollback_from build as current again.
    """
    from ota_utils import log_ota_event

    current_build = db.query(ApkVersion).filter(
        ApkVersion.is_current == True
    ).first()

    if not current_build:
        raise HTTPException(status_code=404, detail="No current build to rollback from")

    if not current_build.rollback_from_build_id:
        raise HTTPException(status_code=400, detail="No previous build available for rollback")

    previous_build = db.query(ApkVersion).filter(
        ApkVersion.id == current_build.rollback_from_build_id
    ).first()

    if not previous_build:
        raise HTTPException(status_code=404, detail="Previous build not found")

    current_build.is_current = False
    previous_build.is_current = True
    previous_build.promoted_at = datetime.now(timezone.utc)
    previous_build.promoted_by = f"{current_user.username} (rollback)"

    if payload.force_downgrade:
        previous_build.must_install = True

    db.commit()

    log_ota_event("ota.rollback", build_id=previous_build.id,
                 version_code=previous_build.version_code,
                 rolled_back_from=current_build.id,
                 force_downgrade=payload.force_downgrade,
                 performed_by=current_user.username)
    metrics.inc_counter("ota_rollbacks_total", {"package": previous_build.package_name})

    structured_logger.log_event(
        "ota.rollback",
        from_build_id=current_build.id,
        from_version_code=current_build.version_code,
        to_build_id=previous_build.id,
        to_version_code=previous_build.version_code,
        force_downgrade=payload.force_downgrade,
        performed_by=current_user.username
    )

    return {
        "success": True,
        "rolled_back_to": {
            "build_id": previous_build.id,
            "version_code": previous_build.version_code,
            "version_name": previous_build.version_name
        },
        "rolled_back_from": {
            "build_id": current_build.id,
            "version_code": current_build.version_code,
            "version_name": current_build.version_name
        },
        "force_downgrade": payload.force_downgrade
    }

@app.get("/v1/apk/{apk_id}/deployment-stats")
async def get_deployment_stats(
    apk_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get deployment statistics for a specific build.
    """
    from models import ApkDeploymentStats

    apk = db.query(ApkVersion).filter(ApkVersion.id == apk_id).first()
    if not apk:
        raise HTTPException(status_code=404, detail="APK not found")

    stats = db.query(ApkDeploymentStats).filter(
        ApkDeploymentStats.build_id == apk_id
    ).first()

    if not stats:
        return {
            "build_id": apk_id,
            "total_checks": 0,
            "total_eligible": 0,
            "total_downloads": 0,
            "installs_success": 0,
            "installs_failed": 0,
            "verify_failed": 0,
            "last_updated": None
        }

    return {
        "build_id": stats.build_id,
        "total_checks": stats.total_checks,
        "total_eligible": stats.total_eligible,
        "total_downloads": stats.total_downloads,
        "installs_success": stats.installs_success,
        "installs_failed": stats.installs_failed,
        "verify_failed": stats.verify_failed,
        "last_updated": stats.last_updated.isoformat() if stats.last_updated else None,
        "adoption_rate": round((stats.installs_success / stats.total_eligible * 100), 2) if stats.total_eligible > 0 else 0
    }

class NudgeUpdateRequest(BaseModel):
    device_ids: Optional[List[str]] = None

@app.post("/v1/apk/nudge-update")
async def nudge_update_check(
    payload: NudgeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Send FCM 'update' command to trigger immediate OTA update check on devices.
    If device_ids is None, sends to all devices with FCM tokens.
    """
    import httpx

    if payload.device_ids:
        devices = db.query(Device).filter(Device.id.in_(payload.device_ids)).all()
    else:
        devices = db.query(Device).filter(Device.fcm_token.isnot(None)).all()

    if not devices:
        raise HTTPException(status_code=404, detail="No devices found")

    # Get FCM credentials
    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
        fcm_url = build_fcm_v1_url(project_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FCM configuration error: {str(e)}")

    success_count = 0
    failed_devices = []

    for device in devices:
        if not device.fcm_token:
            failed_devices.append({
                "device_id": device.id,
                "alias": device.alias,
                "reason": "No FCM token"
            })
            continue

        try:
            request_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc).isoformat()
            hmac_sig = compute_hmac_signature(request_id, device.id, "update", timestamp)

            message = {
                "message": {
                    "token": device.fcm_token,
                    "data": {
                        "action": "update",
                        "request_id": request_id,
                        "device_id": device.id,
                        "ts": timestamp,
                        "hmac": hmac_sig
                    },
                    "android": {
                        "priority": "high"
                    }
                }
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(fcm_url, json=message, headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                })
                result = {"success": response.status_code == 200}

            if result.get("success"):
                success_count += 1
                log_device_event(db, device.id, "ota_update_nudge_sent", {
                    "request_id": request_id,
                    "initiated_by": current_user.username
                })
            else:
                failed_devices.append({
                    "device_id": device.id,
                    "alias": device.alias,
                    "reason": result.get("error", "FCM send failed")
                })

        except Exception as e:
            failed_devices.append({
                "device_id": device.id,
                "alias": device.alias,
                "reason": str(e)
            })

    structured_logger.log_event(
        "ota.nudge.sent",
        total_devices=len(devices),
        success_count=success_count,
        failed_count=len(failed_devices),
        initiated_by=current_user.username
    )

    metrics.inc_counter("ota_nudge_total", {"status": "sent"}, value=success_count)

    return {
        "success": True,
        "total_devices": len(devices),
        "success_count": success_count,
        "failed_count": len(failed_devices),
        "failed_devices": failed_devices
    }

# ==================== Admin APK Management (CI Integration) ====================

class RegisterApkBuildRequest(BaseModel):
    build_id: str
    version_code: int
    version_name: str
    build_type: str
    file_size_bytes: int
    sha256: Optional[str] = None
    signer_fingerprint: Optional[str] = None
    storage_url: Optional[str] = None
    ci_run_id: Optional[str] = None
    git_sha: Optional[str] = None
    package_name: str = "com.nexmdm.agent"

@app.post("/admin/apk/register")
async def register_apk_build(
    payload: RegisterApkBuildRequest,
    x_admin: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Register a new APK build from CI without uploading the file.
    Used by GitHub Actions to register debug builds after uploading to storage.
    Requires admin authentication.
    """
    if not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=403, detail="Admin key required")

    existing = db.query(ApkVersion).filter(
        ApkVersion.package_name == payload.package_name,
        ApkVersion.version_code == payload.version_code,
        ApkVersion.build_type == payload.build_type
    ).first()

    if existing:
        existing.version_name = payload.version_name
        existing.file_size = payload.file_size_bytes
        existing.signer_fingerprint = payload.signer_fingerprint
        existing.storage_url = payload.storage_url
        existing.ci_run_id = payload.ci_run_id
        existing.git_sha = payload.git_sha
        existing.uploaded_at = datetime.now(timezone.utc)
        existing.uploaded_by = "ci-github-actions"
        db.commit()
        db.refresh(existing)
        apk_version = existing
        action = "updated"
    else:
        apk_version = ApkVersion(
            version_name=payload.version_name,
            version_code=payload.version_code,
            file_path="",
            file_size=payload.file_size_bytes,
            package_name=payload.package_name,
            uploaded_at=datetime.now(timezone.utc),
            uploaded_by="ci-github-actions",
            is_active=True,
            build_type=payload.build_type,
            ci_run_id=payload.ci_run_id,
            git_sha=payload.git_sha,
            signer_fingerprint=payload.signer_fingerprint,
            storage_url=payload.storage_url
        )
        db.add(apk_version)
        db.commit()
        db.refresh(apk_version)
        action = "registered"

    structured_logger.log_event(
        "apk.register",
        build_id=apk_version.id,
        version_code=payload.version_code,
        version_name=payload.version_name,
        build_type=payload.build_type,
        ci_run_id=payload.ci_run_id,
        git_sha=payload.git_sha,
        action=action
    )

    metrics.inc_counter("apk_builds_total", {
        "build_type": payload.build_type,
        "action": action
    })

    return {
        "success": True,
        "action": action,
        "build_id": apk_version.id,
        "version_code": apk_version.version_code,
        "version_name": apk_version.version_name,
        "uploaded_at": apk_version.uploaded_at.isoformat()
    }

@app.post("/admin/apk/upload")
async def upload_apk_file(
    file: UploadFile = File(...),
    build_id: str = Form(...),
    version_code: int = Form(...),
    version_name: str = Form(...),
    build_type: str = Form(...),
    package_name: str = Form("com.nexmdm.agent"),
    x_admin: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Upload APK file binary to Replit Object Storage.

    **IMPORTANT:** This endpoint requires multipart/form-data encoding.
    All metadata fields must be sent as form fields alongside the file.

    **Two-Step Upload Process:**
    1. Call /admin/apk/register to register APK metadata
    2. Call /admin/apk/upload to upload the actual APK file

    **Required Form Fields:**
    - file: APK binary file (multipart/form-data, must end with .apk)
    - build_id: Unique build identifier (must match registered build)
    - version_code: Integer version code (e.g., 123)
    - version_name: Human-readable version (e.g., "1.2.3")
    - build_type: Build type ("debug" or "release")
    - package_name: Android package name (default: "com.nexmdm.agent")

    **Authentication:**
    - X-Admin header with admin key required

    **File Constraints:**
    - Maximum size: 120MB (enforced by object storage)
    - Must be a valid .apk file
    - Build metadata must be registered first via /admin/apk/register

    **Example - Python with requests:**
    ```python
    files = {
        'file': ('app.apk', open('app-debug.apk', 'rb'), 'application/vnd.android.package-archive')
    }
    data = {
        'build_id': 'build_001',
        'version_code': '123',
        'version_name': '1.2.3',
        'build_type': 'debug',
        'package_name': 'com.nexmdm.agent'
    }
    response = requests.post(
        'https://your-app.repl.co/admin/apk/upload',
        headers={'X-Admin': 'your-admin-key'},
        files=files,
        data=data
    )
    ```

    **Example - curl:**
    ```bash
    curl -X POST https://your-app.repl.co/admin/apk/upload \
      -H "X-Admin: your-admin-key" \
      -F "file=@app-debug.apk" \
      -F "build_id=build_001" \
      -F "version_code=123" \
      -F "version_name=1.2.3" \
      -F "build_type=debug" \
      -F "package_name=com.nexmdm.agent"
    ```

    **Response Codes:**
    - 200: Upload successful
    - 400: Invalid file type (not .apk)
    - 403: Admin key required or invalid
    - 404: Build not registered (call /admin/apk/register first)
    - 413: File too large (>120MB)
    - 500: Storage upload failed

    **Storage:**
    Files are stored in Replit Object Storage with automatic sidecar authentication.
    Storage path format: storage://apk/{build_type}/{uuid}_{filename}.apk
    """
    if not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=403, detail="Admin key required")

    if not file.filename or not file.filename.endswith('.apk'):
        raise HTTPException(status_code=400, detail="Invalid file type. Must be .apk")

    existing = db.query(ApkVersion).filter(
        ApkVersion.package_name == package_name,
        ApkVersion.version_code == version_code,
        ApkVersion.build_type == build_type
    ).first()

    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"APK build not found. Please call /admin/apk/register first to register metadata."
        )

    # Upload to App Storage
    try:
        content = await file.read()
        file_size = len(content)

        storage = get_storage_service()
        final_filename = f"{package_name}_{version_code}.apk"
        object_path = storage.upload_file(
            file_data=content,
            filename=final_filename,
            content_type="application/vnd.android.package-archive"
        )

        existing.file_path = object_path
        existing.file_size = file_size
        db.commit()
        db.refresh(existing)

        structured_logger.log_event(
            "apk.upload",
            build_id=existing.id,
            version_code=version_code,
            version_name=version_name,
            build_type=build_type,
            file_size=file_size,
            file_path=object_path
        )

        metrics.inc_counter("apk_uploads_total", {"build_type": build_type})

        return {
            "success": True,
            "build_id": existing.id,
            "file_path": object_path,
            "file_size": file_size,
            "message": "APK file uploaded successfully"
        }
    except Exception as e:
        structured_logger.log_event(
            "apk.upload.error",
            error=str(e),
            package_name=package_name,
            version_code=version_code
        )
        raise HTTPException(status_code=500, detail=f"Failed to save APK file: {str(e)}")

@app.get("/admin/apk/builds")
async def list_apk_builds(
    build_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    order: str = Query("desc"),
    x_admin: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    List APK builds with optional filtering by build_type.
    Used by the APK Management frontend to show available builds.
    Requires admin authentication.
    """
    if not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=403, detail="Admin key required")

    query = db.query(ApkVersion).filter(ApkVersion.is_active == True)

    if build_type:
        query = query.filter(ApkVersion.build_type == build_type)

    if order == "asc":
        query = query.order_by(ApkVersion.uploaded_at.asc())
    else:
        query = query.order_by(ApkVersion.uploaded_at.desc())

    apks = query.limit(limit).all()

    builds = []
    for apk in apks:
        builds.append({
            "build_id": apk.id,
            "filename": f"{apk.package_name}-{apk.version_name}.apk",
            "version_name": apk.version_name,
            "version_code": apk.version_code,
            "file_size_bytes": apk.file_size,
            "uploaded_at": apk.uploaded_at.isoformat(),
            "uploaded_by": apk.uploaded_by,
            "build_type": apk.build_type,
            "ci_run_id": apk.ci_run_id,
            "git_sha": apk.git_sha,
            "signer_fingerprint": apk.signer_fingerprint,
            "package_name": apk.package_name
        })

    structured_logger.log_event(
        "apk.list",
        build_type=build_type,
        count=len(builds),
        limit=limit
    )

    return {"builds": builds}

@app.get("/admin/apk/download/{build_id}")
async def download_apk_build_admin(
    build_id: int,
    request: Request,
    x_admin: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Download a specific APK build by ID.
    Used by APK Management frontend for admin downloads.
    Requires admin authentication and logs the download event.
    """
    structured_logger.log_event(
        "apk.download.request",
        build_id=build_id,
        source="admin",
        ip=request.client.host if request.client else None
    )

    if not verify_admin_key(x_admin or ""):
        structured_logger.log_event(
            "apk.download.auth_failed",
            build_id=build_id,
            reason="missing_or_invalid_admin_key"
        )
        raise HTTPException(status_code=403, detail="Admin key required")

    apk = db.query(ApkVersion).filter(ApkVersion.id == build_id).first()
    if not apk:
        structured_logger.log_event(
            "apk.download.not_found",
            build_id=build_id,
            reason="apk_record_not_in_database"
        )
        raise HTTPException(status_code=404, detail="APK build not found")

    structured_logger.log_event(
        "apk.download.found",
        build_id=build_id,
        file_path=apk.file_path,
        version_code=apk.version_code,
        version_name=apk.version_name,
        package_name=apk.package_name
    )

    # Determine if file is in local storage or object storage
    file_data = None
    file_size = 0
    is_local_file = apk.file_path and (
        apk.file_path.startswith("./") or
        apk.file_path.startswith("/") and not apk.file_path.startswith("/nexmdm-apks")
    )

    if is_local_file:
        # Handle local file storage (legacy)
        structured_logger.log_event(
            "apk.download.local_file",
            build_id=build_id,
            file_path=apk.file_path
        )
        try:
            import os
            if not os.path.exists(apk.file_path):
                structured_logger.log_event(
                    "apk.download.error",
                    build_id=build_id,
                    error="local_file_not_found",
                    file_path=apk.file_path
                )
                raise HTTPException(status_code=404, detail=f"APK file not found at {apk.file_path}")

            with open(apk.file_path, 'rb') as f:
                file_data = f.read()
            file_size = len(file_data)

            structured_logger.log_event(
                "apk.download.local_success",
                build_id=build_id,
                file_size=file_size
            )
        except HTTPException:
            raise
        except Exception as e:
            structured_logger.log_event(
                "apk.download.error",
                build_id=build_id,
                error="local_file_read_failed",
                error_message=str(e),
                file_path=apk.file_path
            )
            raise HTTPException(status_code=500, detail=f"Failed to read local APK file: {str(e)}")
    else:
        # Handle object storage (new)
        structured_logger.log_event(
            "apk.download.object_storage",
            build_id=build_id,
            file_path=apk.file_path
        )
        try:
            storage = get_storage_service()
            file_data, content_type, file_size = storage.download_file(apk.file_path)

            structured_logger.log_event(
                "apk.download.object_storage_success",
                build_id=build_id,
                file_size=file_size
            )
        except ObjectNotFoundError:
            structured_logger.log_event(
                "apk.download.error",
                build_id=build_id,
                error="object_not_found_in_storage",
                file_path=apk.file_path
            )
            raise HTTPException(status_code=404, detail="APK file not found in storage")
        except Exception as e:
            structured_logger.log_event(
                "apk.download.error",
                build_id=build_id,
                error="object_storage_download_failed",
                error_message=str(e),
                file_path=apk.file_path
            )
            raise HTTPException(status_code=500, detail=f"Failed to download APK: {str(e)}")

    structured_logger.log_event(
        "apk.download.success",
        build_id=apk.id,
        version_code=apk.version_code,
        version_name=apk.version_name,
        build_type=apk.build_type or "unknown",
        source="admin",
        file_size=file_size
    )

    download_event = ApkDownloadEvent(
        build_id=apk.id,
        source="admin",
        token_id=None,
        admin_user="admin",
        ip=request.client.host if request.client else None
    )
    db.add(download_event)
    db.commit()

    metrics.inc_counter("apk_download_total", {
        "build_type": apk.build_type or "unknown",
        "source": "admin"
    })

    return Response(
        content=file_data,
        media_type="application/vnd.android.package-archive",
        headers={
            "Content-Disposition": f'attachment; filename="{apk.package_name}_{apk.version_code}.apk"',
            "Content-Length": str(file_size)
        }
    )

@app.delete("/admin/apk/builds/{build_id}")
async def delete_apk_build(
    build_id: int,
    x_admin: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Delete an APK build by ID.
    Removes the database record and optionally the file.
    Requires admin authentication.
    """
    if not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=403, detail="Admin key required")

    apk = db.query(ApkVersion).filter(ApkVersion.id == build_id).first()
    if not apk:
        raise HTTPException(status_code=404, detail="APK build not found")

    file_path = apk.file_path

    # Delete from App Storage
    file_deleted = False
    if file_path:
        try:
            storage = get_storage_service()
            file_deleted = storage.delete_file(file_path)
        except Exception as e:
            print(f"[APK DELETE] Failed to delete file from storage {file_path}: {e}")

    # Mark as inactive in database
    apk.is_active = False
    db.commit()

    structured_logger.log_event(
        "apk.delete",
        build_id=build_id,
        version_code=apk.version_code,
        version_name=apk.version_name,
        build_type=apk.build_type or "unknown",
        file_deleted=file_deleted
    )

    metrics.inc_counter("apk_delete_total", {
        "build_type": apk.build_type or "unknown"
    })

    return {
        "success": True,
        "build_id": build_id,
        "file_deleted": file_deleted
    }

# ==================== Battery Whitelist Management ====================

@app.get("/v1/battery-whitelist")
async def get_battery_whitelist(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all battery optimization whitelist entries"""
    whitelist = db.query(BatteryWhitelist).order_by(BatteryWhitelist.added_at.desc()).all()

    return [{
        "id": entry.id,
        "package_name": entry.package_name,
        "app_name": entry.app_name,
        "added_at": entry.added_at.isoformat(),
        "enabled": entry.enabled,
        "added_by": entry.added_by
    } for entry in whitelist]

class AddWhitelistRequest(BaseModel):
    package_name: str
    app_name: str

@app.post("/v1/battery-whitelist")
async def add_battery_whitelist(
    payload: AddWhitelistRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add app to battery optimization whitelist"""
    existing = db.query(BatteryWhitelist).filter(
        BatteryWhitelist.package_name == payload.package_name
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Package already in whitelist")

    new_entry = BatteryWhitelist(
        package_name=payload.package_name,
        app_name=payload.app_name,
        enabled=True,
        added_by=current_user.username
    )

    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)

    return {
        "id": new_entry.id,
        "package_name": new_entry.package_name,
        "app_name": new_entry.app_name,
        "added_at": new_entry.added_at.isoformat(),
        "enabled": new_entry.enabled,
        "added_by": new_entry.added_by
    }

@app.delete("/v1/battery-whitelist/{whitelist_id}")
async def delete_battery_whitelist(
    whitelist_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove app from battery optimization whitelist"""
    entry = db.query(BatteryWhitelist).filter(BatteryWhitelist.id == whitelist_id).first()

    if not entry:
        raise HTTPException(status_code=404, detail="Whitelist entry not found")

    db.delete(entry)
    db.commit()

    return {"ok": True, "message": f"Removed {entry.app_name} from whitelist"}

@app.post("/v1/devices/apply-battery-whitelist")
async def apply_battery_whitelist_to_fleet(
    device_ids: Optional[List[str]] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Apply battery whitelist to all devices or specific devices via FCM"""
    print(f"[BATTERY-WHITELIST] Endpoint called by user: {current_user.username}")
    print(f"[BATTERY-WHITELIST] Device IDs filter: {device_ids}")

    whitelist = db.query(BatteryWhitelist).filter(BatteryWhitelist.enabled == True).all()

    if not whitelist:
        print("[BATTERY-WHITELIST] ERROR: No enabled whitelist entries found")
        raise HTTPException(status_code=400, detail="No enabled whitelist entries found")

    package_names = [entry.package_name for entry in whitelist]
    print(f"[BATTERY-WHITELIST] Packages to apply: {package_names}")

    if device_ids:
        devices = db.query(Device).filter(Device.id.in_(device_ids)).all()
        print(f"[BATTERY-WHITELIST] Filtered to {len(devices)} specific devices")
    else:
        devices = db.query(Device).all()
        print(f"[BATTERY-WHITELIST] Applying to all {len(devices)} devices")

    devices_with_fcm = [d for d in devices if d.fcm_token]
    print(f"[BATTERY-WHITELIST] Found {len(devices_with_fcm)} devices with FCM tokens")

    if not devices_with_fcm:
        print("[BATTERY-WHITELIST] ERROR: No devices with FCM tokens found")
        raise HTTPException(status_code=400, detail="No devices with FCM tokens found")

    success_count = 0
    failed_count = 0

    for device in devices_with_fcm:
        try:
            print(f"[BATTERY-WHITELIST] Sending FCM to device: {device.alias} ({device.id})")
            access_token = get_access_token()
            project_id = get_firebase_project_id()
            fcm_url = build_fcm_v1_url(project_id)

            message = {
                "message": {
                    "token": device.fcm_token,
                    "data": {
                        "action": "apply_battery_whitelist",
                        "packages": json.dumps(package_names)
                    },
                    "android": {
                        "priority": "high"
                    }
                }
            }

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(fcm_url, json=message, headers=headers)
                print(f"[BATTERY-WHITELIST] FCM response for {device.alias}: {response.status_code}")

                if response.status_code == 200:
                    success_count += 1
                    print(f"[BATTERY-WHITELIST] SUCCESS: Applied to {device.alias}")
                    log_device_event(db, device.id, "battery_whitelist_applied", {
                        "packages": package_names,
                        "count": len(package_names)
                    })
                else:
                    failed_count += 1
                    print(f"[BATTERY-WHITELIST] FAILED: {device.alias} - {response.text}")
        except Exception as e:
            print(f"[BATTERY-WHITELIST] EXCEPTION for {device.id}: {e}")
            failed_count += 1

    db.commit()

    return {
        "ok": True,
        "total_devices": len(devices_with_fcm),
        "success_count": success_count,
        "failed_count": failed_count,
        "packages_applied": package_names
    }

@app.post("/v1/devices/{device_id}/apply-battery-whitelist")
async def apply_battery_whitelist_to_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Apply battery whitelist to a specific device via FCM"""
    device = db.query(Device).filter(Device.id == device_id).first()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if not device.fcm_token:
        raise HTTPException(status_code=400, detail="Device has no FCM token")

    whitelist = db.query(BatteryWhitelist).filter(BatteryWhitelist.enabled == True).all()

    if not whitelist:
        raise HTTPException(status_code=400, detail="No enabled whitelist entries found")

    package_names = [entry.package_name for entry in whitelist]

    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
        fcm_url = build_fcm_v1_url(project_id)

        message = {
            "message": {
                "token": device.fcm_token,
                "data": {
                    "action": "apply_battery_whitelist",
                    "packages": json.dumps(package_names)
                },
                "android": {
                    "priority": "high"
                }
            }
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(fcm_url, json=message, headers=headers)
            if response.status_code != 200:
                raise HTTPException(status_code=500, detail=f"FCM failed: {response.text}")

        log_device_event(db, device.id, "battery_whitelist_applied", {
            "packages": package_names,
            "count": len(package_names)
        })
        db.commit()

        return {
            "ok": True,
            "device_id": device_id,
            "packages_applied": package_names
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send FCM: {str(e)}")