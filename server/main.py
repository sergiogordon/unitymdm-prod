# =============================================================================
# ⚠️  IMPORTANT: CODE DUPLICATION WARNING ⚠️
# =============================================================================
# This file was cleaned up on 2025-11-29 to remove ~5,870 duplicate lines
# that were accidentally introduced in commit 6addb18.
# 
# Before editing this file, especially during refactoring:
# 1. Use `wc -l server/main.py` to check line count (should be ~7,100-7,200)
# 2. If line count exceeds 8,000, check for accidental code duplication
# 3. Run `grep -n "# --- APK Download Tracking ---" server/main.py`
#    - This marker should appear exactly ONCE (around line 6081)
#    - Multiple occurrences indicate duplicate code blocks
# =============================================================================

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
import httpx
import random

from models import Device, User, Session as SessionModel, DeviceEvent, ApkVersion, ApkInstallation, BatteryWhitelist, PasswordResetToken, DeviceLastStatus, DeviceSelection, ApkDownloadEvent, MonitoringDefaults, AutoRelaunchDefaults, DiscordSettings, BloatwarePackage, WiFiSettings, DeviceCommand, DeviceMetric, BulkCommand, CommandResult, RemoteExec, RemoteExecResult, get_db, init_db, SessionLocal
from schemas import (
    HeartbeatPayload, HeartbeatResponse, DeviceSummary, RegisterResponse,
    UserRegisterRequest, UserLoginRequest, UpdateDeviceAliasRequest, DeployApkRequest,
    UpdateDeviceSettingsRequest, ActionResultRequest, UpdateAutoRelaunchDefaultsRequest,
    UpdateDiscordSettingsRequest, BulkUpdatePackageRequest
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
from hmac_utils import compute_hmac_signature, compute_hmac_signature_with_payload
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
from ota_utils import is_device_eligible_for_rollout

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

# Concurrency limit for APK downloads to prevent overwhelming object storage
APK_DOWNLOAD_CONCURRENCY_LIMIT = 20 # Max concurrent downloads
apk_download_semaphore = asyncio.Semaphore(APK_DOWNLOAD_CONCURRENCY_LIMIT)

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

# Request size limit middleware (BUG FIX #4): Prevent DoS attacks with large payloads
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

async def dispatch_launch_app_to_device(
    device,
    package_name: str,
    correlation_id: str,
    semaphore: asyncio.Semaphore,
    client: httpx.AsyncClient,
    fcm_url: str,
    access_token: str,
    db_results: dict
) -> dict:
    """
    Dispatch a launch_app FCM command to a device with tracking support.
    Uses 'action: remote_exec_fcm' format for consistent ACK tracking via /v1/remote-exec/ack endpoint.
    """
    async with semaphore:
        try:
            if not device.fcm_token:
                db_results[device.id] = {
                    "correlation_id": correlation_id,
                    "alias": device.alias,
                    "status": "error",
                    "error": "No FCM token"
                }
                return db_results[device.id]
            
            timestamp = datetime.now(timezone.utc).isoformat()
            # Include critical payload fields in HMAC to prevent tampering
            payload_fields = {
                "type": "launch_app",
                "package_name": package_name
            }
            hmac_signature = compute_hmac_signature_with_payload(
                correlation_id, device.id, "remote_exec_fcm", timestamp, payload_fields
            )
            
            message = {
                "message": {
                    "token": device.fcm_token,
                    "data": {
                        "action": "remote_exec_fcm",
                        "exec_id": "",
                        "correlation_id": correlation_id,
                        "device_id": device.id,
                        "type": "launch_app",
                        "package_name": package_name,
                        "ts": timestamp,
                        "hmac": hmac_signature
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
            
            response = await client.post(fcm_url, json=message, headers=headers, timeout=10.0)
            
            if response.status_code == 200:
                db_results[device.id] = {
                    "correlation_id": correlation_id,
                    "alias": device.alias,
                    "status": "sent"
                }
            else:
                db_results[device.id] = {
                    "correlation_id": correlation_id,
                    "alias": device.alias,
                    "status": "error",
                    "error": f"FCM error: {response.status_code}"
                }
            
            return db_results[device.id]
            
        except Exception as e:
            db_results[device.id] = {
                "correlation_id": correlation_id,
                "alias": device.alias,
                "status": "error",
                "error": str(e)
            }
            return db_results[device.id]

async def dispatch_force_stop_to_device(
    device,
    package_name: str,
    correlation_id: str,
    semaphore: asyncio.Semaphore,
    client: httpx.AsyncClient,
    fcm_url: str,
    access_token: str,
    db_results: dict
) -> dict:
    """
    Dispatch a force-stop FCM command to a device with tracking support.
    Uses 'action: remote_exec_fcm' with 'type: force_stop_app' to leverage Device Owner APIs
    instead of shell commands (which require system-level permissions).
    """
    async with semaphore:
        try:
            if not device.fcm_token:
                db_results[device.id] = {
                    "correlation_id": correlation_id,
                    "alias": device.alias,
                    "status": "error",
                    "error": "No FCM token"
                }
                return db_results[device.id]
            
            timestamp = datetime.now(timezone.utc).isoformat()
            payload_fields = {
                "type": "force_stop_app",
                "package_name": package_name
            }
            hmac_signature = compute_hmac_signature_with_payload(
                correlation_id, device.id, "remote_exec_fcm", timestamp, payload_fields
            )
            
            message = {
                "message": {
                    "token": device.fcm_token,
                    "data": {
                        "action": "remote_exec_fcm",
                        "exec_id": "",
                        "correlation_id": correlation_id,
                        "device_id": device.id,
                        "type": "force_stop_app",
                        "package_name": package_name,
                        "ts": timestamp,
                        "hmac": hmac_signature
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
            
            response = await client.post(fcm_url, json=message, headers=headers, timeout=10.0)
            
            if response.status_code == 200:
                db_results[device.id] = {
                    "correlation_id": correlation_id,
                    "alias": device.alias,
                    "status": "sent"
                }
            else:
                db_results[device.id] = {
                    "correlation_id": correlation_id,
                    "alias": device.alias,
                    "status": "error",
                    "error": f"FCM error: {response.status_code}"
                }
            
            return db_results[device.id]
            
        except Exception as e:
            db_results[device.id] = {
                "correlation_id": correlation_id,
                "alias": device.alias,
                "status": "error",
                "error": str(e)
            }
            return db_results[device.id]

async def dispatch_exempt_unity_to_device(
    device,
    package_name: str,
    correlation_id: str,
    semaphore: asyncio.Semaphore,
    client: httpx.AsyncClient,
    fcm_url: str,
    access_token: str,
    db_results: dict
) -> dict:
    """
    Dispatch an exempt Unity app from battery optimization FCM command to a device.
    Uses 'action: exempt_unity_app' to apply battery whitelist settings.
    """
    async with semaphore:
        try:
            if not device.fcm_token:
                db_results[device.id] = {
                    "correlation_id": correlation_id,
                    "alias": device.alias,
                    "status": "error",
                    "error": "No FCM token"
                }
                return db_results[device.id]
            
            timestamp = datetime.now(timezone.utc).isoformat()
            hmac_signature = compute_hmac_signature(
                correlation_id, device.id, "exempt_unity_app", timestamp
            )
            
            message = {
                "message": {
                    "token": device.fcm_token,
                    "data": {
                        "action": "exempt_unity_app",
                        "request_id": correlation_id,
                        "device_id": device.id,
                        "ts": timestamp,
                        "hmac": hmac_signature
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
            
            response = await client.post(fcm_url, json=message, headers=headers, timeout=10.0)
            
            if response.status_code == 200:
                db_results[device.id] = {
                    "correlation_id": correlation_id,
                    "alias": device.alias,
                    "status": "sent"
                }
            else:
                db_results[device.id] = {
                    "correlation_id": correlation_id,
                    "alias": device.alias,
                    "status": "error",
                    "error": f"FCM error: {response.status_code}"
                }
            
            return db_results[device.id]
            
        except Exception as e:
            db_results[device.id] = {
                "correlation_id": correlation_id,
                "alias": device.alias,
                "status": "error",
                "error": str(e)
            }
            return db_results[device.id]

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
                f"   Please upload the JSON file or switch to FIREBASE_SERVICE_ACCOUNT_JSON secret."
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
        # Allow server to start with warnings
        print("⚠️  Server starting despite configuration warnings...")

    try:
        init_db()
        print("✅ Database initialized")
    except Exception as e:
        print(f"⚠️  Database initialization warning: {e}")
        # Try to continue - database might already be initialized
        print("⚠️  Attempting to continue with existing database...")

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
        db.close()  # Close DB session immediately after auth/verification

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
    # NOTE: Skip connection test to avoid blocking during high load
    # The database connection is tested separately during actual operations
    db_url = config.get_database_url()
    if db_url and db_url != "sqlite:///./data.db":
        status["required"]["database"]["configured"] = True
        status["required"]["database"]["valid"] = True  # Assume OK if configured
        status["required"]["database"]["connection_tested"] = False  # Skipped for performance

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
    from monitoring_helpers import get_effective_monitoring_settings
    
    # PERF: Get monitoring settings ONCE and reuse throughout (avoid duplicate DB queries)
    monitoring_settings = get_effective_monitoring_settings(db, device)

    # Extract Unity app info (ALWAYS from io.unitynodes.unityapp)
    unity_running = None
    unity_pkg_version = None
    unity_app_info = payload.app_versions.get("io.unitynodes.unityapp")
    if unity_app_info and unity_app_info.installed:
        unity_pkg_version = unity_app_info.version_name
        # Check both process existence and foreground status
        # Android agent sends unity_process_running for process detection
        process_running = getattr(payload, 'unity_process_running', None)
        
        # Get foreground recency - only use if it's actually for Unity
        # monitored_foreground_recent_s represents the configured monitored package (may not be Unity)
        # Check device monitoring settings to see if Unity is the monitored package
        is_unity_monitored = monitoring_settings.get("package") == "io.unitynodes.unityapp"
        
        fg_seconds = None
        if is_unity_monitored:
            # Only use foreground data if Unity is actually the monitored package
            fg_seconds_raw = payload.monitored_foreground_recent_s if hasattr(payload, 'monitored_foreground_recent_s') else None
            # Exclude -1 sentinel value (unavailable data) before comparison
            if fg_seconds_raw is not None and fg_seconds_raw >= 0:
                fg_seconds = fg_seconds_raw
        
        # Unity is running if:
        # 1. Process exists (running in foreground OR background), OR
        # 2. App was in foreground within last 10 minutes (only if Unity is the monitored package)
        if process_running is True:
            # Process check succeeded and found process - Unity is running
            unity_running = True
        elif process_running is False:
            # Process check succeeded and found no process - Unity is definitively not running
            # Don't override with foreground data since process check is definitive
            unity_running = False
        elif fg_seconds is not None:
            # Process check unavailable (null) or failed - use foreground data as fallback
            unity_running = fg_seconds < 600
        else:
            # No process or foreground data available - status unknown
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
    # NOTE: monitoring_settings already fetched above (PERF optimization - single call)

    service_up = None
    monitored_foreground_recent_s = None

    if monitoring_settings["enabled"] and monitoring_settings["package"]:
        # Check if the monitored app is actually installed
        app_info = payload.app_versions.get(monitoring_settings["package"]) if payload.app_versions else None
        is_app_installed = app_info and app_info.installed if app_info else None

        # Get foreground recency from unified field (monitored_foreground_recent_s)
        # This field now tracks Unity app activity
        monitored_foreground_recent_s = payload.monitored_foreground_recent_s

        # Treat -1 as sentinel value for "not available" (normalize to None)
        if monitored_foreground_recent_s is not None and monitored_foreground_recent_s < 0:
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
            # App installed but foreground data not available
            # If app is installed but we have no foreground data, assume it's down (not running)
            # This matches auto-relaunch logic which treats missing foreground data as "down"
            service_up = False
            structured_logger.log_event(
                "monitoring.evaluate.no_foreground_data",
                level="WARN",
                device_id=device.id,
                alias=device.alias,
                monitored_package=monitoring_settings["package"],
                reason="foreground_data_unavailable",
                service_up=False,
                source=monitoring_settings["source"]
            )

    # PERF: Update DeviceLastStatus with service monitoring data using UPDATE...RETURNING
    # This avoids a separate SELECT query by returning prev_service_up in the same statement
    from sqlalchemy import text as sql_text
    update_result = db.execute(sql_text("""
        UPDATE device_last_status
        SET service_up = :service_up,
            monitored_foreground_recent_s = :fg_recent_s,
            monitored_package = :monitored_package,
            monitored_threshold_min = :threshold_min
        WHERE device_id = :device_id
        RETURNING (SELECT service_up FROM device_last_status WHERE device_id = :device_id) as prev_service_up
    """), {
        'service_up': service_up,
        'fg_recent_s': monitored_foreground_recent_s,
        'monitored_package': monitoring_settings["package"] if monitoring_settings["enabled"] else None,
        'threshold_min': monitoring_settings["threshold_min"] if monitoring_settings["enabled"] else None,
        'device_id': device.id
    })
    
    row = update_result.fetchone()
    if row:
        prev_service_up = row[0] if row else None
        
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
    # Unity field ALWAYS reflects io.unitynodes.unityapp, NOT the monitored package
    # Defensive check: ensure app_versions exists before accessing it
    if not payload.app_versions:
        last_status_dict["unity"] = {
            "package": "io.unitynodes.unityapp",
            "status": "not_installed"
        }
    else:
        unity_app_info = payload.app_versions.get("io.unitynodes.unityapp")

        if not unity_app_info:
            last_status_dict["unity"] = {
                "package": "io.unitynodes.unityapp",
                "status": "not_installed"
            }
        elif unity_app_info.installed:
            # Unity app is installed - determine running status
            # Check process running status first (works for background processes)
            process_running = getattr(payload, 'unity_process_running', None)
            
            # Get foreground recency - only use if it's actually for Unity
            # monitored_foreground_recent_s represents the configured monitored package (may not be Unity)
            is_unity_monitored = monitoring_settings.get("package") == "io.unitynodes.unityapp"
            
            unity_fg_seconds = None
            if is_unity_monitored:
                # Only use foreground data if Unity is actually the monitored package
                fg_seconds_raw = payload.monitored_foreground_recent_s if hasattr(payload, 'monitored_foreground_recent_s') else None
                # Exclude -1 sentinel value (unavailable data) before comparison
                if fg_seconds_raw is not None and fg_seconds_raw >= 0:
                    unity_fg_seconds = fg_seconds_raw
            
            # Unity is running if:
            # 1. Process exists (running in foreground OR background), OR
            # 2. App was in foreground within last 10 minutes (only if Unity is the monitored package)
            if process_running is True:
                # Process check succeeded and found process - Unity is running
                unity_status = "running"
            elif process_running is False:
                # Process check succeeded and found no process - Unity is definitively not running
                unity_status = "down"
            elif unity_fg_seconds is not None:
                # Process check unavailable (null) - use foreground data as fallback
                unity_status = "running" if unity_fg_seconds < 600 else "down"
            else:
                # No process or foreground data available - assume down
                unity_status = "down"

            last_status_dict["unity"] = {
                "package": "io.unitynodes.unityapp",
                "version": unity_app_info.version_name or "unknown",
                "status": unity_status
            }
        else:
            last_status_dict["unity"] = {
                "package": "io.unitynodes.unityapp",
                "status": "not_installed"
            }

    # Agent field always reflects MDM agent version (always running if sending heartbeats)
    last_status_dict["agent"] = {
        "version": payload.app_version or "unknown"
    }

    device.last_status = json.dumps(last_status_dict)

    # Auto-relaunch logic: Check if monitored app is down and auto-relaunch is enabled
    # Use monitoring settings package if available, otherwise use device.monitored_package
    auto_relaunch_package = None
    if device.auto_relaunch_enabled:
        # Prefer monitoring_settings package if monitoring is enabled, otherwise use device.monitored_package
        if monitoring_settings.get("enabled") and monitoring_settings.get("package"):
            auto_relaunch_package = monitoring_settings["package"]
        elif device.monitored_package:
            auto_relaunch_package = device.monitored_package
        
        if auto_relaunch_package:
            # Try primary lookup first, then fallback to io.unitynodes.unityapp for consistency
            app_info = payload.app_versions.get(auto_relaunch_package) if payload.app_versions else None
            package_used = auto_relaunch_package
            used_fallback = False

            # If primary lookup failed, try fallback to io.unitynodes.unityapp
            if not app_info and auto_relaunch_package != "io.unitynodes.unityapp":
                fallback_package = "io.unitynodes.unityapp"
                app_info = payload.app_versions.get(fallback_package) if payload.app_versions else None
                if app_info:
                    package_used = fallback_package
                    used_fallback = True

            # Check if app is installed
            if app_info and app_info.installed:
                fg_seconds = payload.monitored_foreground_recent_s
                if fg_seconds is not None and fg_seconds < 0:
                    fg_seconds = None

                if fg_seconds is not None:
                    threshold_min = monitoring_settings.get("threshold_min") or device.monitored_threshold_min or 10
                    threshold_seconds = threshold_min * 60
                    is_app_running = fg_seconds <= threshold_seconds
                else:
                    is_app_running = False
            else:
                is_app_running = True  # Prevent relaunch loop for uninstalled apps

            # If app is not running, trigger FCM relaunch
            if not is_app_running and device.fcm_token:
                try:
                    asyncio.create_task(send_fcm_launch_app(device.fcm_token, package_used, device.id))
                    log_device_event(db, device.id, "auto_relaunch_triggered", {
                        "package": package_used,
                        "used_fallback": used_fallback,
                        "original_package": auto_relaunch_package
                    })
                except Exception as e:
                    structured_logger.log_event("auto_relaunch.failed", level="ERROR", 
                                               device_id=device.id, error=str(e))

    db.commit()

    # Invalidate cache on device update
    response_cache.invalidate("/v1/metrics")
    response_cache.invalidate("/v1/devices")

    await manager.broadcast({
        "type": "device_update",
        "device_id": device.id
    })

    return HeartbeatResponse(ok=True, next_heartbeat_seconds=alert_config.HEARTBEAT_INTERVAL_SECONDS)

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
    cache_key = None
    cache_ttl = 300
    if page == 1 and limit in (25, 100):
        cache_key = make_cache_key("/v1/devices", {"page": 1, "limit": limit})
        cached_result = response_cache.get(cache_key, ttl_seconds=cache_ttl)
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

    if cache_key:
        response_cache.set(cache_key, response, ttl_seconds=cache_ttl, path="/v1/devices")

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

class ApkDownloadEventRequest(BaseModel):
    apk_version_id: int
    status: str
    downloaded_at: Optional[datetime] = None
    installed_at: Optional[datetime] = None
    message: Optional[str] = None

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
            "package": "io.unitynodes.unityapp",
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

            installation = ApkInstallation(
                device_id=device.id,
                apk_version_id=None, # This is not an APK installation, so apk_version_id is None
                status="pending", # Set initial status to pending
                initiated_at=datetime.now(timezone.utc),
                initiated_by="admin" # Or current_user.username if available and relevant
            )
            db.add(installation)
            db.commit()
            db.refresh(installation)


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

# =============================================================================
# ⚠️  CRITICAL ENDPOINT - DO NOT DELETE ⚠️
# =============================================================================
# This endpoint generates the Windows one-liner enrollment script used to
# enroll new Android devices via ADB. It is referenced in:
#   - MILESTONE_DELIVERABLES.md
#   - ACCEPTANCE_TESTS.md  
#   - BUG_BASH_FINAL_REPORT.md
#   - Frontend enrollment UI components
# Deleting this endpoint will break device enrollment functionality.
# =============================================================================
@app.get("/v1/scripts/enroll.one-liner.cmd")
async def get_windows_one_liner_script(
    alias: str = Query(...),
    agent_pkg: str = Query("com.nexmdm"),
    unity_pkg: str = Query("io.unitynodes.unityapp"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate zero-tap Windows one-liner enrollment command with enhanced debugging.
    
    ⚠️  CRITICAL ENDPOINT - DO NOT DELETE ⚠️
    This is required for device enrollment functionality.
    """
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
    
    apk_path = "%TEMP%\\\\nexmdm.apk"
    bloat_file = "%TEMP%\\\\mdm_bloatware.txt"
    
    one_liner = f'''cmd.exe /K "echo ============================================ & echo NexMDM Zero-Tap Enrollment v7 - {alias} & echo ============================================ & echo. & echo [Step 1/11] Check prerequisites... & where adb & where curl & echo. & echo [Step 2/11] Wait for device... & adb wait-for-device & adb devices -l & echo. & echo [Step 3/11] Check Android version... & adb shell getprop ro.build.version.release & adb shell getprop ro.build.version.sdk & echo. & echo [Step 4/11] Download NexMDM APK... & echo Downloading NexMDM agent (approx 16MB)... & curl -L --progress-bar -H X-Admin-Key:{admin_key} {server_url}/v1/apk/download-latest -o {apk_path} & echo. & dir {apk_path} & echo. & echo [Step 5/11] Install NexMDM APK... & adb install -r -g {apk_path} & echo. & echo [Step 6/11] Verify NexMDM installed... & adb shell pm path {agent_pkg} & echo. & echo [Step 7/11] Set Device Owner... & adb shell dpm set-device-owner {agent_pkg}/.NexDeviceAdminReceiver & echo. & echo [Step 8/11] Grant permissions... & adb shell pm grant {agent_pkg} android.permission.POST_NOTIFICATIONS & adb shell pm grant {agent_pkg} android.permission.ACCESS_FINE_LOCATION & adb shell appops set {agent_pkg} RUN_ANY_IN_BACKGROUND allow & adb shell appops set {agent_pkg} GET_USAGE_STATS allow & adb shell dumpsys deviceidle whitelist +{agent_pkg} & echo. & echo [Step 9/11] Disable bloatware... & curl -s -H X-Admin-Key:{admin_key} {server_url}/admin/bloatware-list -o {bloat_file} & echo Disabling bloatware packages... & (for /f %p in ({bloat_file}) do @echo Disabling %p... ^& adb shell pm disable-user --user 0 %p) & echo Bloatware disabled. & echo. & echo [Step 10/11] Apply system tweaks... & adb shell settings put global app_standby_enabled 0 & adb shell settings put global ambient_display_always_on 0 & adb shell cmd power set-adaptive-power-saver-enabled false & echo System tweaks applied. & echo. & echo [Step 11/11] Auto-enroll and launch NexMDM... & adb shell am broadcast -a com.nexmdm.CONFIGURE -n {agent_pkg}/.ConfigReceiver --receiver-foreground --es server_url {server_url} --es admin_key {admin_key} --es alias {alias} & timeout /t 2 /nobreak >nul & adb shell monkey -p {agent_pkg} -c android.intent.category.LAUNCHER 1 & timeout /t 3 /nobreak >nul & adb shell pidof {agent_pkg} & echo. & echo ============================================ & echo Enrollment complete for {alias} & echo ============================================"'''
    
    return Response(
        content=one_liner,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'inline; filename="enroll-{alias}-oneliner.cmd"'
        }
    )
# =============================================================================
# ⚠️  END CRITICAL ENDPOINT ⚠️
# =============================================================================

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
        if not re.match(r'^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$', pkg.strip()):
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

@app.post("/admin/devices/monitoring/bulk-update-package")
async def bulk_update_package_name(
    request: BulkUpdatePackageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk update monitored_package for all devices"""
    # Validate package name format
    if not request.monitored_package.strip():
        raise HTTPException(status_code=400, detail="Monitored package cannot be empty")
    import re
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$', request.monitored_package.strip()):
        raise HTTPException(status_code=400, detail="Invalid package name format")
    
    new_package = request.monitored_package.strip()
    
    # Optimized: Use bulk update instead of individual updates
    # This is 10-50x faster for bulk operations
    # Update both monitored_package and monitoring_use_defaults
    updated_count = db.query(Device).update({
        Device.monitored_package: new_package,
        Device.monitoring_use_defaults: False
    })
    
    # Log events for each device (for audit trail)
    devices = db.query(Device).all()
    for device in devices:
        log_device_event(db, device.id, "monitoring_settings_updated", {
            "monitored_package": new_package,
            "monitoring_use_defaults": False,
            "bulk_update": True
        })
    
    db.commit()
    
    # Invalidate cache on bulk update
    response_cache.invalidate("/v1/metrics")
    response_cache.invalidate("/v1/devices")
    
    structured_logger.log_event(
        "monitoring.bulk_package_update",
        user=current_user.username,
        updated_count=updated_count,
        new_package=new_package
    )
    
    return {
        "ok": True,
        "message": f"Package name updated to '{new_package}' for {updated_count} devices",
        "updated_count": updated_count,
        "monitored_package": new_package
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

                raise HTTPException(status_code=500, detail=f"FCM request failed with status {response.status_code}")

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
    # For LAUNCH_APP_ACK, also allow RemoteExecResult (used by restart-app feature)
    if payload.type != "WIFI_CONNECT_ACK":
        if not correlation_id:
            print(f"[ACK] ERROR: Missing correlation_id for type={payload.type}")
            raise HTTPException(status_code=400, detail="correlation_id is required for this ACK type")

        command = db.query(DeviceCommand).filter(
            DeviceCommand.correlation_id == correlation_id
        ).first()

        # For LAUNCH_APP_ACK, allow RemoteExecResult as fallback (restart-app feature)
        if not command and payload.type != "LAUNCH_APP_ACK":
            print(f"[ACK] Command not found for correlation_id={correlation_id}, type={payload.type}")
            raise HTTPException(status_code=404, detail="Command not found with this correlation_id")
        
        # For LAUNCH_APP_ACK, check if RemoteExecResult exists before raising 404
        if not command and payload.type == "LAUNCH_APP_ACK":
            remote_exec_result_check = db.query(RemoteExecResult).filter(
                RemoteExecResult.correlation_id == correlation_id,
                RemoteExecResult.device_id == device_id
            ).first()
            if not remote_exec_result_check:
                print(f"[ACK] Command and RemoteExecResult not found for correlation_id={correlation_id}, type={payload.type}")
                raise HTTPException(status_code=404, detail="Command not found with this correlation_id")

        if command and command.device_id != device_id:
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
            # Check for RemoteExecResult (used by restart-app feature)
            remote_exec_result = db.query(RemoteExecResult).filter(
                RemoteExecResult.correlation_id == correlation_id,
                RemoteExecResult.device_id == device_id
            ).first()
            
            if remote_exec_result:
                print(f"[ACK] Found RemoteExecResult: id={remote_exec_result.id}, exec_id={remote_exec_result.exec_id}, current_status={remote_exec_result.status}")
                old_status = remote_exec_result.status
                
                # Map ACK status to RemoteExecResult status
                ack_status = payload.status or "OK"
                if ack_status.upper() == "OK":
                    remote_exec_result.status = "OK"
                else:
                    remote_exec_result.status = "ERROR"
                
                remote_exec_result.exit_code = 0 if remote_exec_result.status == "OK" else 1
                remote_exec_result.output_preview = payload.message[:2048] if payload.message else None
                remote_exec_result.error = None if remote_exec_result.status == "OK" else (payload.message[:1024] if payload.message else "Launch failed")
                remote_exec_result.updated_at = datetime.now(timezone.utc)
                
                print(f"[ACK] Updated RemoteExecResult: new_status={remote_exec_result.status}")
                
                # Update parent exec record counters if status changed from pending
                exec_record = db.query(RemoteExec).filter(RemoteExec.id == remote_exec_result.exec_id).first()
                if exec_record and old_status == "pending":
                    exec_record.acked_count += 1
                    if remote_exec_result.status != "OK":
                        exec_record.error_count += 1
                    
                    # Check if all results are now complete
                    pending_count = db.query(RemoteExecResult).filter(
                        RemoteExecResult.exec_id == exec_record.id,
                        RemoteExecResult.status == "pending"
                    ).count()
                    
                    if pending_count == 0:
                        exec_record.status = "completed"
                        exec_record.completed_at = datetime.now(timezone.utc)
                
                log_device_event(db, device_id, "launch_app_ack", {
                    "correlation_id": correlation_id,
                    "status": payload.status,
                    "message": payload.message,
                    "exec_id": remote_exec_result.exec_id
                })
            else:
                print(f"[ACK] CommandResult and RemoteExecResult not found for correlation_id={correlation_id}")
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

    # Special handling for am broadcast (token-based validation for security)
    if len(tokens) >= 2 and tokens[0] == "am" and tokens[1] == "broadcast":
        # Must have --receiver-foreground flag
        if "--receiver-foreground" not in tokens:
            return False, "am broadcast requires --receiver-foreground flag"
        
        # Must have -a com.nexmdm.CONFIGURE
        try:
            action_idx = tokens.index("-a")
            if action_idx + 1 >= len(tokens) or tokens[action_idx + 1] != "com.nexmdm.CONFIGURE":
                return False, "Only com.nexmdm.CONFIGURE action is allowed"
        except ValueError:
            return False, "am broadcast requires -a flag with action"
        
        # Must have -n com.nexmdm/.ConfigReceiver
        try:
            receiver_idx = tokens.index("-n")
            if receiver_idx + 1 >= len(tokens) or tokens[receiver_idx + 1] != "com.nexmdm/.ConfigReceiver":
                return False, "Only com.nexmdm/.ConfigReceiver receiver is allowed"
        except ValueError:
            return False, "am broadcast requires -n flag with receiver"
        
        # Validate required extras: server_url, admin_key or token, alias
        # Also validate that values aren't themselves extra type flags (prevents injection)
        extra_type_flags = ["--es", "--ez", "--ei", "--el", "--ef", "--eu", "--ecn", "-a", "-n", "--receiver-foreground"]
        extras = {}
        i = 0
        while i < len(tokens):
            if tokens[i] in ["--es", "--ez", "--ei", "--el", "--ef", "--eu", "--ecn"]:
                if i + 2 < len(tokens):
                    key = tokens[i + 1]
                    value = tokens[i + 2]
                    # Validate that the value isn't itself an extra type flag (prevents malformed commands)
                    if value in extra_type_flags:
                        return False, f"Invalid extra value: '{value}' cannot be an extra type flag"
                    # Validate that the key isn't an extra type flag either
                    if key in extra_type_flags:
                        return False, f"Invalid extra key: '{key}' cannot be an extra type flag"
                    extras[key] = value
                    i += 3
                    continue
            i += 1
        
        # Check required extras
        if "server_url" not in extras:
            return False, "am broadcast requires --es server_url"
        if "admin_key" not in extras and "token" not in extras:
            return False, "am broadcast requires --es admin_key or --es token"
        if "alias" not in extras:
            return False, "am broadcast requires --es alias"
        
        # Validate server_url format (basic URL validation)
        server_url = extras["server_url"]
        if not (server_url.startswith("http://") or server_url.startswith("https://")):
            return False, "server_url must start with http:// or https://"
        
        # Optional extras validation (only allow known safe extras)
        allowed_optional_extras = ["hmac_primary_key", "hmac_rotation_key"]
        for key in extras:
            if key not in ["server_url", "admin_key", "token", "alias"] + allowed_optional_extras:
                return False, f"Unknown extra parameter: {key}"
        
        return True, None

    # Regex-based validation for other commands
    allow_patterns = [
        r'^am\s+start\s+(-[nWDR]\s+[A-Za-z0-9._/:]+\s*)+$',  # More restrictive: specific flags only, no shell injection
        r'^am\s+force-stop\s+[A-Za-z0-9._]+$',
        r'^cmd\s+package\s+(list|resolve-activity)\s+[A-Za-z0-9._\s-]*$',  # More restrictive
        r'^settings\s+(get|put)\s+(secure|system|global)\s+[A-Za-z0-9._]+(\s+[A-Za-z0-9._]+)?$',  # More restrictive
        r'^input\s+(keyevent|tap|swipe)\s+[0-9\s]+$',  # Numbers only for input commands
        r'^svc\s+(wifi|data)\s+(enable|disable)$',
        r'^pm\s+list\s+packages(\s+-[a-z]+)*$',  # Allow flags like -s, -d, etc
        r'^monkey\s+-p\s+[A-Za-z0-9._]+\s+-c\s+android\.intent\.category\.(LAUNCHER|DEFAULT)\s+1$',  # App launch via monkey
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

async def dispatch_apk_fcm_to_device(
    device: Device,
    apk: ApkVersion,
    installation: ApkInstallation,
    semaphore: asyncio.Semaphore,
    client: "httpx.AsyncClient",
    fcm_url: str,
    access_token: str
) -> dict:
    """
    Dispatch APK installation FCM message to a single device with semaphore-based concurrency control.
    Returns result dict with device_id, status, installation_id, and optional error.
    """
    async with semaphore:
        try:
            if not device.fcm_token:
                return {
                    "device_id": device.id,
                    "alias": device.alias,
                    "installation_id": installation.id,
                    "status": "error",
                    "error": "No FCM token"
                }
            
            request_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc).isoformat()
            hmac_signature = compute_hmac_signature(request_id, device.id, "install_apk", timestamp)
            
            # Generate the download URL for the APK
            download_url = f"{config.server_url}/v1/apk/download/{apk.id}"
            
            fcm_message = {
                "message": {
                    "token": device.fcm_token,
                    "data": {
                        "action": "install_apk",
                        "request_id": request_id,
                        "device_id": device.id,
                        "ts": timestamp,
                        "hmac": hmac_signature,
                        "installation_id": str(installation.id),
                        "apk_id": str(apk.id),
                        "version_name": apk.version_name,
                        "version_code": str(apk.version_code),
                        "file_size": str(apk.file_size) if apk.file_size else "0",
                        "package_name": apk.package_name if hasattr(apk, 'package_name') and apk.package_name else "com.nexmdm",
                        "download_url": download_url
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
            
            response = await client.post(fcm_url, json=fcm_message, headers=headers, timeout=10.0)
            
            if response.status_code == 200:
                return {
                    "device_id": device.id,
                    "alias": device.alias,
                    "installation_id": installation.id,
                    "status": "sent"
                }
            else:
                error_msg = f"FCM failed: {response.status_code}"
                return {
                    "device_id": device.id,
                    "alias": device.alias,
                    "installation_id": installation.id,
                    "status": "error",
                    "error": error_msg
                }
        except asyncio.TimeoutError:
            return {
                "device_id": device.id,
                "alias": device.alias,
                "installation_id": installation.id,
                "status": "error",
                "error": "FCM timeout"
            }
        except Exception as e:
            return {
                "device_id": device.id,
                "alias": device.alias,
                "installation_id": installation.id,
                "status": "error",
                "error": f"FCM error: {str(e)}"
            }

@app.post("/v1/apk/deploy")
async def deploy_apk_v1(
    payload: DeployApkRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Deploy an APK to selected devices.
    This endpoint is intended for admin use and requires JWT authentication.
    It takes the apk_id and a list of device_ids.
    Supports batch processing with configurable batch_size and batch_delay_seconds.
    """
    from ota_utils import is_device_eligible_for_rollout
    
    apk_id = payload.apk_id
    device_ids = [d_id.strip() for d_id in (payload.device_ids or []) if d_id.strip()]

    # Check if APK exists
    apk = db.query(ApkVersion).filter(ApkVersion.id == apk_id).first()
    if not apk:
        raise HTTPException(status_code=404, detail="APK not found")

    # Get devices - use all devices if no specific devices provided
    if device_ids:
        devices = db.query(Device).filter(Device.id.in_(device_ids)).all()
    else:
        devices = db.query(Device).all()
    
    # Apply cohort-based rollout filtering if percentage < 100
    rollout_percent = getattr(payload, 'rollout_percent', 100) or 100
    if rollout_percent < 100:
        devices = [d for d in devices if is_device_eligible_for_rollout(d.id, rollout_percent)]
    
    found_devices = {d.id: d for d in devices}

    # Filter devices without FCM tokens first
    devices_with_fcm = []
    failed_devices = []
    
    for device in devices:
        if not device.fcm_token:
            failed_devices.append({
                "device_id": device.id,
                "alias": device.alias,
                "reason": "No FCM token"
            })
        else:
            devices_with_fcm.append(device)

    # Create all ApkInstallation records in bulk
    installations = []
    now = datetime.now(timezone.utc)
    
    for device in devices_with_fcm:
        installation = ApkInstallation(
            device_id=device.id,
            apk_version_id=apk.id,
            status="pending",
            initiated_at=now,
            initiated_by=user.username
        )
        db.add(installation)
        installations.append(installation)
    
    # Bulk commit all installations
    db.commit()
    
    # Refresh all installations to get their IDs
    for installation in installations:
        db.refresh(installation)
    
    # Create mapping of device_id to installation
    installation_map = {inst.device_id: inst for inst in installations}
    
    # Get FCM credentials (once, outside the loop)
    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
        fcm_url = build_fcm_v1_url(project_id)
    except Exception as e:
        # If FCM setup fails, installations are already created in DB
        # Mark FCM send failures but return the installations that were created
        fcm_failed_devices = [
            {
                "device_id": device.id,
                "alias": device.alias,
                "reason": f"FCM setup failed: {str(e)}"
            }
            for device in devices_with_fcm
        ]
        failed_devices.extend(fcm_failed_devices)
        
        structured_logger.log_event(
            "apk.deploy.complete",
            level="ERROR",
            apk_id=apk.id,
            success_count=len(installations),
            failed_count=len(failed_devices),
            total_devices=len(device_ids),
            fcm_setup_failed=True
        )
        return {
            "success_count": len(installations),
            "failed_count": len(failed_devices),
            "installations": [
                {
                    "id": inst.id,
                    "device": {
                        "id": inst.device_id,
                        "alias": found_devices[inst.device_id].alias if inst.device_id in found_devices else "Unknown"
                    }
                }
                for inst in installations
            ],
            "failed_devices": failed_devices
        }
    
    # Determine batch processing parameters
    batch_size = payload.batch_size
    batch_delay_seconds = payload.batch_delay_seconds
    
    # If batch_size is set but batch_delay_seconds is not, default to 30 seconds
    if batch_size is not None and batch_delay_seconds is None:
        batch_delay_seconds = 30
    
    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(FCM_DISPATCH_CONCURRENCY)
    
    # Process devices
    async with httpx.AsyncClient() as client:
        if batch_size is not None and batch_size > 0:
            # Process in batches with delays
            total_batches = (len(devices_with_fcm) + batch_size - 1) // batch_size
            
            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min(start_idx + batch_size, len(devices_with_fcm))
                batch_devices = devices_with_fcm[start_idx:end_idx]
                
                # Create tasks for this batch
                tasks = [
                    dispatch_apk_fcm_to_device(
                        device=device,
                        apk=apk,
                        installation=installation_map[device.id],
                        semaphore=semaphore,
                        client=client,
                        fcm_url=fcm_url,
                        access_token=access_token
                    )
                    for device in batch_devices
                ]
                
                # Process batch in parallel
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results (track FCM failures, but installations are already created)
                for i, result in enumerate(batch_results):
                    if isinstance(result, Exception):
                        # Handle exceptions - mark device as failed
                        device = batch_devices[i]
                        failed_devices.append({
                            "device_id": device.id,
                            "alias": device.alias,
                            "reason": f"FCM error: {str(result)}"
                        })
                        continue
                    
                    if result.get("status") != "sent":
                        failed_devices.append({
                            "device_id": result["device_id"],
                            "alias": result["alias"],
                            "reason": result.get("error", "Unknown error")
                        })
                
                # Wait before next batch (except for the last batch)
                if batch_num < total_batches - 1 and batch_delay_seconds > 0:
                    await asyncio.sleep(batch_delay_seconds)
        else:
            # Process all devices in parallel (backward compatible)
            tasks = [
                dispatch_apk_fcm_to_device(
                    device=device,
                    apk=apk,
                    installation=installation_map[device.id],
                    semaphore=semaphore,
                    client=client,
                    fcm_url=fcm_url,
                    access_token=access_token
                )
                for device in devices_with_fcm
            ]
            
            # Process all in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results (track FCM failures, but installations are already created)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    # Handle exceptions - mark device as failed
                    device = devices_with_fcm[i]
                    failed_devices.append({
                        "device_id": device.id,
                        "alias": device.alias,
                        "reason": f"FCM error: {str(result)}"
                    })
                    continue
                
                if result.get("status") != "sent":
                    failed_devices.append({
                        "device_id": result["device_id"],
                        "alias": result["alias"],
                        "reason": result.get("error", "Unknown error")
                    })

    # All installations are considered successful (backward compatible behavior)
    # failed_devices only contains FCM send failures
    structured_logger.log_event(
        "apk.deploy.complete",
        level="INFO",
        apk_id=apk.id,
        success_count=len(installations),
        failed_count=len(failed_devices),
        total_devices=len(device_ids),
        batch_size=batch_size,
        batch_delay_seconds=batch_delay_seconds
    )

    return {
        "success_count": len(installations),
        "failed_count": len(failed_devices),
        "installations": [
            {
                "id": inst.id,
                "device": {
                    "id": inst.device_id,
                    "alias": found_devices[inst.device_id].alias if inst.device_id in found_devices else "Unknown"
                }
            }
            for inst in installations
        ],
        "failed_devices": failed_devices
    }

@app.get("/v1/apk/download-latest")
async def download_latest_apk(
    request: Request,
    db: Session = Depends(get_db),
    x_device_token: Optional[str] = Header(None),
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
    installation_id: Optional[int] = Query(None),
):
    """
    Download the latest available APK for the device.
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

    # Find the latest APK version (use uploaded_at since created_at doesn't exist)
    latest_apk = db.query(ApkVersion).filter(ApkVersion.is_active == True).order_by(ApkVersion.uploaded_at.desc()).first()
    if not latest_apk:
        raise HTTPException(status_code=404, detail="No APK versions found")

    # Use optimized download service
    return await download_apk_optimized(
        apk_id=latest_apk.id,
        db=db,
        device_id=device_id,
        installation_id=installation_id,
        use_cache=True
    )

@app.get("/v1/apk/download/{apk_id}")
async def download_apk_by_id(
    apk_id: int,
    request: Request,
    x_device_token: Optional[str] = Header(None),
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
    installation_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Download a specific APK version by ID.
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

@app.post("/v1/apk/upload-chunk")
async def upload_apk_chunk(
    request: Request,
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    filename: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload a chunk of an APK file. Used for large APKs with chunked uploads."""
    try:
        if not (0 <= chunk_index < total_chunks):
            raise HTTPException(status_code=422, detail="Invalid chunk index or total chunks")
        
        chunk_data = await file.read()
        chunk_key = f"chunks/{upload_id}/chunk_{chunk_index:04d}"
        
        storage_service = get_storage_service()
        storage_service.client.upload_from_bytes(chunk_key, chunk_data)
        
        structured_logger.log_event(
            "apk.chunk.uploaded",
            upload_id=upload_id,
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            chunk_size=len(chunk_data),
            user=current_user.username
        )
        
        return {
            "ok": True,
            "upload_id": upload_id,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks
        }
    except Exception as e:
        structured_logger.log_event(
            "apk.chunk.upload.error",
            level="ERROR",
            upload_id=upload_id,
            chunk_index=chunk_index,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to upload chunk: {str(e)}")

@app.post("/v1/apk/complete")
async def complete_apk_upload(
    upload_id: str = Form(...),
    package_name: str = Form(...),
    version_name: str = Form(...),
    version_code: int = Form(...),
    filename: str = Form(...),
    total_chunks: int = Form(...),
    build_type: str = Form("release"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Combine uploaded chunks and create APK record."""
    try:
        storage_service = get_storage_service()
        
        # Download and assemble chunks first
        all_chunks = []
        for i in range(total_chunks):
            chunk_key = f"chunks/{upload_id}/chunk_{i:04d}"
            try:
                chunk_data = storage_service.client.download_as_bytes(chunk_key)
                all_chunks.append(chunk_data)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Missing chunk {i}: {str(e)}")
        
        complete_file = b"".join(all_chunks)
        file_size = len(complete_file)
        sha256_hash = hashlib.sha256(complete_file).hexdigest()
        
        # Handle duplicate version_code by auto-incrementing version_code
        # The unique constraint is on (package_name, version_code), so we must change version_code
        original_version_code = version_code
        modified_version_code = version_code
        max_attempts = 10
        
        for attempt in range(max_attempts):
            # Check for duplicate: same package_name AND version_code (matches database unique constraint)
            existing_version = db.query(ApkVersion).filter(
                (ApkVersion.package_name == package_name) & (ApkVersion.version_code == modified_version_code)
            ).first()
            
            if not existing_version:
                # No duplicate found, proceed with upload
                break
            
            # Duplicate found, increment version_code by a random amount (1-100)
            # This ensures we can always find a unique version_code
            increment = random.randint(1, 100)
            modified_version_code = modified_version_code + increment
            
            if attempt == max_attempts - 1:
                # Last attempt failed, raise error (shouldn't happen with random increment)
                for i in range(total_chunks):
                    chunk_key = f"chunks/{upload_id}/chunk_{i:04d}"
                    try:
                        storage_service.client.delete(chunk_key, ignore_not_found=True)
                    except:
                        pass
                raise HTTPException(
                    status_code=409,
                    detail=f"Unable to find unique version code after {max_attempts} attempts. Please try a different version code."
                )
        
        # Use modified version code for storage and database
        version_code_modified = modified_version_code != original_version_code
        object_name = f"apks/{version_name}_{modified_version_code}.apk"
        storage_service.client.upload_from_bytes(object_name, complete_file)
        
        for i in range(total_chunks):
            chunk_key = f"chunks/{upload_id}/chunk_{i:04d}"
            try:
                storage_service.client.delete(chunk_key, ignore_not_found=True)
            except:
                pass
        
        apk_version = ApkVersion(
            version_name=version_name,
            version_code=modified_version_code,
            package_name=package_name,
            build_type=build_type,
            file_size=file_size,
            sha256=sha256_hash,
            file_path=object_name,
            storage_url=object_name,
            is_active=True,
            uploaded_by=current_user.username
        )
        db.add(apk_version)
        db.commit()
        db.refresh(apk_version)
        
        # Log if version code was modified
        log_message = "APK uploaded successfully"
        if version_code_modified:
            log_message = f"APK uploaded successfully (version code auto-incremented from {original_version_code} to {modified_version_code} due to duplicate)"
        
        structured_logger.log_event(
            "apk.uploaded",
            apk_id=apk_version.id,
            version_name=version_name,
            version_code=modified_version_code,
            original_version_code=original_version_code if version_code_modified else None,
            file_size=file_size,
            user=current_user.username,
            version_code_modified=version_code_modified
        )
        
        return {
            "ok": True,
            "message": log_message,
            "apk_id": apk_version.id,
            "version_name": apk_version.version_name,
            "version_code": apk_version.version_code,
            "original_version_code": original_version_code if version_code_modified else None,
            "storage_url": apk_version.storage_url,
            "version_code_modified": version_code_modified
        }
    except HTTPException:
        raise
    except Exception as e:
        structured_logger.log_event(
            "apk.complete.error",
            level="ERROR",
            upload_id=upload_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to complete upload: {str(e)}")

@app.post("/admin/apk/upload")
async def upload_apk_admin(
    request: Request,
    apk_file: UploadFile = File(...),
    version_name: str = Form(...),
    version_code: int = Form(...),
    description: str = Form(""),
    build_type: str = Form("release"),
    enabled: bool = Form(True),
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
    db: Session = Depends(get_db)
):
    """Upload an APK file directly via admin interface (for smaller files).
    
    Idempotent: If APK with same version already exists, returns success with existing info.
    This allows CI/CD re-runs without failure.
    """
    verify_admin_key(x_admin_key)

    # Validate version code
    if version_code <= 0:
        raise HTTPException(status_code=422, detail="version_code must be a positive integer")

    # Check for existing version with same code or name
    existing_version = db.query(ApkVersion).filter(
        (ApkVersion.version_code == version_code) | (ApkVersion.version_name == version_name)
    ).first()
    
    if existing_version:
        # If version already exists, return success with existing info (idempotent)
        # This allows CI/CD re-runs without failure
        structured_logger.log_event(
            "apk.upload.skipped_existing",
            admin_user="admin",
            existing_apk_id=existing_version.id,
            version_name=existing_version.version_name,
            version_code=existing_version.version_code,
            reason="version_already_exists"
        )
        return {
            "ok": True,
            "message": "APK version already exists (skipped upload)",
            "apk_id": existing_version.id,
            "version_name": existing_version.version_name,
            "version_code": existing_version.version_code,
            "storage_url": existing_version.storage_url,
            "already_existed": True
        }

    # Save the APK file to object storage
    try:
        storage_service = get_storage_service()
        file_content = await apk_file.read()
        file_size = len(file_content)
        sha256_hash = hashlib.sha256(file_content).hexdigest()

        # Construct object name
        object_name = f"apks/{version_name}_{version_code}.apk"
        # upload_file is synchronous, do not await
        storage_service.upload_file(file_content, object_name)

        apk_version = ApkVersion(
            version_name=version_name,
            version_code=version_code,
            notes=description,
            build_type=build_type,
            file_size=file_size,
            sha256=sha256_hash,
            file_path=object_name,
            storage_url=object_name,
            is_active=enabled,
            uploaded_by="admin",
            package_name="com.nexmdm"
        )
        db.add(apk_version)
        db.commit()
        db.refresh(apk_version)

        structured_logger.log_event(
            "apk.uploaded",
            admin_user="admin",
            apk_id=apk_version.id,
            version_name=version_name,
            version_code=version_code,
            file_size=file_size,
            sha256_hash=sha256_hash
        )

        return {
            "ok": True,
            "message": "APK uploaded successfully",
            "apk_id": apk_version.id,
            "version_name": apk_version.version_name,
            "version_code": apk_version.version_code,
            "storage_url": apk_version.storage_url
        }

    except ObjectNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Object storage error: {str(e)}")
    except Exception as e:
        structured_logger.log_event(
            "apk.upload.fail",
            level="ERROR",
            admin_user="admin",
            version_name=version_name,
            version_code=version_code,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to upload APK: {str(e)}")

@app.get("/admin/apks")
async def get_admin_apks(
    enabled: Optional[bool] = Query(None),
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
    db: Session = Depends(get_db)
):
    """Get list of APK versions, optionally filtered by enabled status."""
    verify_admin_key(x_admin_key)

    query = db.query(ApkVersion)
    if enabled is not None:
        query = query.filter(ApkVersion.enabled == enabled)

    apks = query.order_by(ApkVersion.created_at.desc()).all()

    return [
        {
            "id": apk.id,
            "version_name": apk.version_name,
            "version_code": apk.version_code,
            "description": apk.description,
            "file_size": apk.file_size,
            "sha256_hash": apk.sha256_hash,
            "object_name": apk.object_name,
            "enabled": apk.enabled,
            "created_at": apk.created_at.isoformat() + "Z",
            "uploaded_by": apk.uploaded_by
        }
        for apk in apks
    ]

class UpdateApkVersionRequest(BaseModel):
    description: Optional[str] = None
    enabled: Optional[bool] = None

@app.patch("/admin/apks/{apk_id}")
async def update_apk_version(
    apk_id: int,
    request: UpdateApkVersionRequest,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
    db: Session = Depends(get_db)
):
    """Update an APK version's details (e.g., description, enabled status)."""
    verify_admin_key(x_admin_key)

    apk = db.query(ApkVersion).filter(ApkVersion.id == apk_id).first()
    if not apk:
        raise HTTPException(status_code=404, detail="APK version not found")

    if request.description is not None:
        apk.description = request.description
    if request.enabled is not None:
        apk.enabled = request.enabled

    db.commit()
    db.refresh(apk)

    structured_logger.log_event(
        "apk.update",
        admin_user="admin",
        apk_id=apk_id,
        enabled=apk.enabled,
        description=apk.description
    )

    return {
        "ok": True,
        "message": "APK version updated successfully",
        "apk": {
            "id": apk.id,
            "version_name": apk.version_name,
            "version_code": apk.version_code,
            "description": apk.description,
            "enabled": apk.enabled
        }
    }

@app.delete("/admin/apks/{apk_id}")
async def delete_apk_version(
    apk_id: int,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
    db: Session = Depends(get_db)
):
    """Delete an APK version and its associated files."""
    verify_admin_key(x_admin_key)

    apk = db.query(ApkVersion).filter(ApkVersion.id == apk_id).first()
    if not apk:
        raise HTTPException(status_code=404, detail="APK version not found")

    # Check if any devices are currently targeting this APK for deployment
    # This is a soft check - we don't prevent deletion but warn the admin
    active_deployments = db.query(ApkInstallation).filter(
        ApkInstallation.apk_version_id == apk_id,
        ApkInstallation.status.in_(["pending", "downloading", "installing"])
    ).count()

    if active_deployments > 0:
        structured_logger.log_event(
            "apk.delete.warning",
            level="WARN",
            admin_user="admin",
            apk_id=apk_id,
            active_deployments=active_deployments,
            message="Deleting an APK with active deployments. Consider disabling first."
        )
        # Proceed with deletion but log a warning

    # Delete from object storage first (if it exists)
    try:
        storage_service = get_storage_service()
        storage_service.delete_file(apk.object_name)
    except ObjectNotFoundError:
        # File not found in storage, but we can still delete the DB record
        structured_logger.log_event(
            "apk.delete.object_not_found",
            admin_user="admin",
            apk_id=apk_id,
            object_name=apk.object_name
        )
    except Exception as e:
        structured_logger.log_event(
            "apk.delete.object_error",
            level="ERROR",
            admin_user="admin",
            apk_id=apk_id,
            object_name=apk.object_name,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to delete APK file from storage: {str(e)}")

    # Delete associated ApkInstallation records
    db.query(ApkInstallation).filter(ApkInstallation.apk_version_id == apk_id).delete()

    # Delete the ApkVersion record
    db.delete(apk)
    db.commit()

    structured_logger.log_event(
        "apk.delete.success",
        admin_user="admin",
        apk_id=apk_id,
        version_name=apk.version_name
    )

    return {"ok": True, "message": f"APK version '{apk.version_name}' deleted successfully"}

# =============================================================================
# ⚠️  CRITICAL ENDPOINTS - DO NOT DELETE ⚠️
# =============================================================================
# These endpoints are required for the APK Management page and device
# installation tracking. They were accidentally deleted in commit 6addb18.
# Deleting these endpoints will break:
#   - APK Management page (can't list builds)
#   - Device installation status updates
#   - Admin APK build management
# =============================================================================

@app.get("/admin/apk/builds")
async def list_apk_builds(
    build_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    order: str = Query("desc"),
    x_admin: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    ⚠️  CRITICAL ENDPOINT - DO NOT DELETE ⚠️
    
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
            "uploaded_at": apk.uploaded_at.isoformat() if apk.uploaded_at else None,
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

@app.delete("/admin/apk/builds/{build_id}")
async def delete_apk_build(
    build_id: int,
    x_admin: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    ⚠️  CRITICAL ENDPOINT - DO NOT DELETE ⚠️
    
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

    file_deleted = False
    if file_path:
        try:
            storage = get_storage_service()
            file_deleted = storage.delete_file(file_path)
        except Exception as e:
            print(f"[APK DELETE] Failed to delete file from storage {file_path}: {e}")

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


@app.get("/v1/apk/installations")
async def list_apk_installations(
    apk_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List APK installation records with optional filtering.
    
    Returns recent installations with APK and device metadata.
    Used by the Recent Deployments panel on the APK deploy page.
    """
    query = db.query(ApkInstallation)
    
    if apk_id is not None:
        query = query.filter(ApkInstallation.apk_version_id == apk_id)
    
    if status:
        query = query.filter(ApkInstallation.status == status)
    
    query = query.order_by(ApkInstallation.initiated_at.desc()).limit(limit)
    
    installations = query.all()
    
    results = []
    for inst in installations:
        device = db.query(Device).filter(Device.id == inst.device_id).first()
        apk = db.query(ApkVersion).filter(ApkVersion.id == inst.apk_version_id).first() if inst.apk_version_id else None
        
        apk_data = None
        if apk:
            filename = apk.file_path.split('/')[-1] if apk.file_path else None
            apk_data = {
                "id": apk.id,
                "filename": filename,
                "package_name": apk.package_name,
                "version_name": apk.version_name,
                "version_code": apk.version_code,
            }
        
        results.append({
            "id": inst.id,
            "device_id": inst.device_id,
            "apk_id": inst.apk_version_id,
            "status": inst.status,
            "created_at": inst.initiated_at.isoformat() if inst.initiated_at else None,
            "completed_at": inst.completed_at.isoformat() if inst.completed_at else None,
            "download_progress": inst.download_progress,
            "error_message": inst.error_message,
            "device": {
                "id": device.id,
                "alias": device.alias,
            } if device else None,
            "apk": apk_data,
        })
    
    return results


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
    """
    ⚠️  CRITICAL ENDPOINT - DO NOT DELETE ⚠️
    
    Update installation status from device.
    Used by Android devices to report APK installation progress.
    """
    installation = db.query(ApkInstallation).filter(
        ApkInstallation.id == payload.installation_id
    ).first()

    if not installation:
        raise HTTPException(status_code=404, detail="Installation not found")

    device = db.query(Device).filter(Device.id == installation.device_id).first()

    if not device or not verify_token(x_device_token, device.token_hash):
        raise HTTPException(status_code=401, detail="Invalid device token")

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

    # Check if this installation is part of a reinstall-unity-and-launch operation
    # If so, trigger launch_app after a delay
    if payload.status == "completed":
        reinstall_exec = db.query(RemoteExec).filter(
            RemoteExec.mode == "reinstall_unity_and_launch",
            RemoteExec.targets.contains(f'"{device.id}"')
        ).order_by(RemoteExec.created_at.desc()).first()
        
        if reinstall_exec:
            raw_request = json.loads(reinstall_exec.raw_request) if reinstall_exec.raw_request else {}
            launch_correlations = raw_request.get("launch_correlations", {})
            package_name = raw_request.get("package_name", "io.unitynodes.unityapp")
            
            if device.id in launch_correlations:
                # Schedule launch_app dispatch after 2-3 second delay
                launch_correlation_id = launch_correlations[device.id]
                asyncio.create_task(
                    trigger_launch_after_install(
                        device_id=device.id,
                        package_name=package_name,
                        correlation_id=launch_correlation_id,
                        exec_id=reinstall_exec.id
                    )
                )

    await manager.broadcast({
        "type": "installation_update",
        "device_id": str(device.id),
        "installation_id": payload.installation_id,
        "status": payload.status,
        "progress": payload.download_progress
    })

    return {"success": True}

async def trigger_launch_after_install(
    device_id: str,
    package_name: str,
    correlation_id: str,
    exec_id: str
):
    """
    Helper function to trigger launch_app after installation completes.
    Waits 2-3 seconds, then dispatches launch_app FCM command.
    """
    import httpx
    
    # Wait 2-3 seconds for installation to fully complete
    await asyncio.sleep(2.5)
    
    # Create a new database session for this async task
    db_session = SessionLocal()
    try:
        # Refresh device to get latest FCM token
        device = db_session.query(Device).filter(Device.id == device_id).first()
        if not device or not device.fcm_token:
            # Update result record to show error
            result = db_session.query(RemoteExecResult).filter(
                RemoteExecResult.exec_id == exec_id,
                RemoteExecResult.device_id == device_id,
                RemoteExecResult.correlation_id == correlation_id
            ).first()
            if result:
                result.status = "error"
                result.error = "No FCM token available"
                db_session.commit()
            return
        
        # Get FCM credentials
        access_token = get_access_token()
        project_id = get_firebase_project_id()
        fcm_url = build_fcm_v1_url(project_id)
        
        # Dispatch launch_app FCM command
        semaphore = asyncio.Semaphore(FCM_DISPATCH_CONCURRENCY)
        db_results = {}
        
        async with httpx.AsyncClient() as client:
            await dispatch_launch_app_to_device(
                device=device,
                package_name=package_name,
                correlation_id=correlation_id,
                semaphore=semaphore,
                client=client,
                fcm_url=fcm_url,
                access_token=access_token,
                db_results=db_results
            )
        
        # Update result record with dispatch status
        result = db_session.query(RemoteExecResult).filter(
            RemoteExecResult.exec_id == exec_id,
            RemoteExecResult.device_id == device_id,
            RemoteExecResult.correlation_id == correlation_id
        ).first()
        
        if result:
            result_data = db_results.get(device_id, {})
            if result_data.get("status") == "sent":
                result.status = "pending"  # Will be updated by ACK
            else:
                result.status = "error"
                result.error = result_data.get("error", "FCM dispatch failed")
            db_session.commit()
    except Exception as e:
        # Update result record to show error
        try:
            result = db_session.query(RemoteExecResult).filter(
                RemoteExecResult.exec_id == exec_id,
                RemoteExecResult.device_id == device_id,
                RemoteExecResult.correlation_id == correlation_id
            ).first()
            if result:
                result.status = "error"
                result.error = f"Launch trigger failed: {str(e)}"
                db_session.commit()
        except:
            pass
    finally:
        db_session.close()

# =============================================================================
# ⚠️  END CRITICAL APK ENDPOINTS ⚠️
# =============================================================================


# --- APK Download Tracking ---

@app.post("/v1/apk/download")
async def track_apk_download(
    request: Request,
    payload: ApkDownloadEventRequest,
    device: Device = Depends(verify_device_token),
    db: Session = Depends(get_db)
):
    """
    Track APK download events from devices.

    Receives download status (started, completed, failed) and logs it.
    Used for monitoring deployment progress.
    """
    if not payload.apk_version_id or not payload.status:
        raise HTTPException(status_code=400, detail="apk_version_id and status are required")

    # Find the ApkInstallation record
    installation = db.query(ApkInstallation).filter(
        ApkInstallation.device_id == device.id,
        ApkInstallation.apk_version_id == payload.apk_version_id,
        ApkInstallation.status.in_(["pending", "downloading", "installing"]) # Only update if in progress
    ).order_by(ApkInstallation.initiated_at.desc()).first()

    if not installation:
        # This can happen if the device retries after a previous success or if it's an unexpected event
        # Log it as a warning, but don't fail the request
        structured_logger.log_event(
            "apk.download.unexpected_event",
            level="WARN",
            device_id=device.id,
            apk_version_id=payload.apk_version_id,
            status=payload.status,
            message=payload.message
        )
        # Return success to prevent device retries
        return {"ok": True, "message": "Installation not found or already completed"}

    installation.status = payload.status
    installation.downloaded_at = payload.downloaded_at
    installation.installed_at = payload.installed_at
    installation.download_error = payload.message
    installation.updated_at = datetime.now(timezone.utc)

    db.commit()

    structured_logger.log_event(
        "apk.download.track",
        device_id=device.id,
        apk_version_id=payload.apk_version_id,
        status=payload.status,
        downloaded_at=payload.downloaded_at.isoformat() if payload.downloaded_at else None,
        installed_at=payload.installed_at.isoformat() if payload.installed_at else None,
        message=payload.message
    )

    # Broadcast update to dashboard if installation status changed
    if payload.status in ["downloaded", "installed", "failed"]:
        await manager.broadcast({
            "type": "installation_update",
            "installation_id": installation.id,
            "device_id": device.id,
            "apk_version_id": payload.apk_version_id,
            "status": payload.status,
            "message": payload.message
        })

    return {"ok": True, "message": "Download status updated"}

@app.get("/v1/apk/versions")
async def get_apk_versions(
    enabled: Optional[bool] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a list of available APK versions."""
    query = db.query(ApkVersion)
    if enabled is not None:
        query = query.filter(ApkVersion.enabled == enabled)

    apks = query.order_by(ApkVersion.created_at.desc()).all()

    return [
        {
            "id": apk.id,
            "version_name": apk.version_name,
            "version_code": apk.version_code,
            "description": apk.description,
            "file_size": apk.file_size,
            "sha256_hash": apk.sha256_hash,
            "object_name": apk.object_name,
            "enabled": apk.enabled,
            "created_at": apk.created_at.isoformat() + "Z",
            "uploaded_by": apk.uploaded_by
        }
        for apk in apks
    ]

@app.get("/v1/apk/versions/{apk_id}")
async def get_apk_version(
    apk_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get details of a specific APK version."""
    apk = db.query(ApkVersion).filter(ApkVersion.id == apk_id).first()
    if not apk:
        raise HTTPException(status_code=404, detail="APK version not found")

    return {
        "id": apk.id,
        "version_name": apk.version_name,
        "version_code": apk.version_code,
        "description": apk.description,
        "file_size": apk.file_size,
        "sha256_hash": apk.sha256_hash,
        "object_name": apk.object_name,
        "enabled": apk.enabled,
        "created_at": apk.created_at.isoformat() + "Z",
        "uploaded_by": apk.uploaded_by
    }

@app.get("/v1/apk/versions/{apk_id}/download-url")
async def get_apk_download_url(
    apk_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a pre-signed URL to download a specific APK version."""
    apk = db.query(ApkVersion).filter(ApkVersion.id == apk_id).first()
    if not apk:
        raise HTTPException(status_code=404, detail="APK version not found")

    if not apk.object_name:
        raise HTTPException(status_code=500, detail="APK object name not found in database")

    try:
        download_url = await get_apk_download_url(apk.object_name)
        return {"download_url": download_url}
    except ObjectNotFoundError:
        raise HTTPException(status_code=404, detail="APK file not found in storage")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate download URL: {str(e)}")

# --- Device Command Execution ---

@app.post("/v1/devices/{device_id}/commands")
async def send_command(
    device_id: str,
    payload: dict,
    device: Device = Depends(verify_device_token),
    db: Session = Depends(get_db)
):
    """
    Send a command to a device via FCM.
    Command types: PING, RING, RING_STOP, INSTALL_APK, UNINSTALL_APK,
                   REMOTE_EXEC, SET_WIFI, SET_POLICY, REBOOT, FACTORY_RESET,
                   LOCK, FACTORY_ERASE, SET_ALARM_ADMIN, CLEAR_DEVICE_OWNER,
                   LAUNCH_APP, START_APP, FORCE_STOP_APP, SET_SETTINGS
    """
    command_type = payload.get("type")
    command_payload = payload.get("payload")

    if not command_type:
        raise HTTPException(status_code=422, detail="Command type is required")

    if not device.fcm_token:
        raise HTTPException(status_code=400, detail="Device does not have FCM token registered")

    # Rate limiting for commands (e.g., 10 commands per minute per device)
    rate_key = f"device_commands:{device_id}"
    if not rate_limiter.is_allowed(rate_key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    now = datetime.now(timezone.utc)
    correlation_id = str(uuid.uuid4())

    # Update device state based on command type
    if command_type == "PING":
        if device.last_ping_at and (now - ensure_utc(device.last_ping_at)).total_seconds() < 15:
            raise HTTPException(status_code=429, detail="Rate limit: Ping too frequent")
        device.last_ping_at = now
        device.ping_request_id = correlation_id
        device.last_ping_sent = now

    elif command_type == "RING":
        duration_sec = command_payload.get("duration_sec", 30)
        volume = command_payload.get("volume", 1.0)
        if not (5 <= duration_sec <= 120):
            raise HTTPException(status_code=422, detail="duration_sec must be between 5 and 120")
        if not (0.0 <= volume <= 1.0):
            raise HTTPException(status_code=422, detail="volume must be between 0.0 and 1.0")
        if device.ringing_until and ensure_utc(device.ringing_until) > now:
            raise HTTPException(status_code=400, detail="Device is already ringing")
        device.ringing_until = now + timedelta(seconds=duration_sec)

    elif command_type == "RING_STOP":
        if not device.ringing_until or ensure_utc(device.ringing_until) <= now:
            raise HTTPException(status_code=400, detail="Device is not currently ringing")
        device.ringing_until = None

    elif command_type == "REBOOT":
        pass # No state change needed on device object

    elif command_type == "FACTORY_RESET":
        pass

    elif command_type == "FACTORY_ERASE":
        pass

    elif command_type == "LOCK":
        pass

    elif command_type == "SET_ALARM_ADMIN":
        pass

    elif command_type == "CLEAR_DEVICE_OWNER":
        pass

    elif command_type in ["INSTALL_APK", "UNINSTALL_APK", "REMOTE_EXEC", "SET_WIFI", "SET_POLICY", "START_APP", "FORCE_STOP_APP", "SET_SETTINGS"]:
        # Commands that require validation will be handled by validate_shell_command
        if command_type == "REMOTE_EXEC":
            command_script = command_payload.get("script")
            if not command_script:
                raise HTTPException(status_code=422, detail="script is required for REMOTE_EXEC")
            is_valid, error_msg = validate_shell_command(command_script)
            if not is_valid:
                raise HTTPException(status_code=422, detail=f"Invalid command script: {error_msg}")

    command = DeviceCommand(
        device_id=device_id,
        type=command_type,
        status="queued",
        correlation_id=correlation_id,
        payload=json.dumps(command_payload) if command_payload else None,
        created_by=user.username if user else "admin"
    )
    db.add(command)
    db.flush()

    username = user.username if user else "admin"
    log_device_event(db, device.id, f"{command_type.lower()}_initiated", {
        "correlation_id": correlation_id,
        "username": username,
        "payload": command_payload
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
    hmac_signature = compute_hmac_signature(correlation_id, device.id, command_type.lower(), timestamp)

    fcm_data = {
        "action": command_type.lower(),
        "correlation_id": correlation_id,
        "device_id": device.id,
        "ts": timestamp,
        "hmac": hmac_signature,
    }
    if command_payload:
        fcm_data.update(command_payload)

    message = {
        "message": {
            "token": device.fcm_token,
            "data": fcm_data,
            "android": {
                "priority": "high"
            }
        }
    }

    fcm_start_time = time.time()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(fcm_url, json=message, headers=headers, timeout=10.0)

            if response.status_code != 200:
                command.status = "failed"
                command.error = f"FCM request failed with status {response.status_code}"
                db.commit()

                raise HTTPException(status_code=500, detail=f"FCM request failed with status {response.status_code}")

            db.commit()

            structured_logger.log_event(
                "dispatch.sent",
                request_id=correlation_id,
                device_id=device.id,
                action=command_type.lower(),
                fcm_http_code=response.status_code,
                fcm_status="success",
                latency_ms=int((time.time() - fcm_start_time) * 1000)
            )

            return {"command_id": str(command.id), "status": "queued", "correlation_id": correlation_id}

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

@app.post("/v1/devices/{device_id}/commands/remote-exec")
async def remote_exec(
    device_id: str,
    payload: dict,
    x_admin: str = Header(None),
    user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Execute arbitrary shell commands on a device."""
    if not user and not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=401, detail="Authentication required")

    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if not device.fcm_token:
        raise HTTPException(status_code=400, detail="Device does not have FCM token registered")

    command_script = payload.get("script")
    if not command_script:
        raise HTTPException(status_code=422, detail="script is required")

    is_valid, error_msg = validate_shell_command(command_script)
    if not is_valid:
        raise HTTPException(status_code=422, detail=f"Invalid command script: {error_msg}")

    # Check rate limiting
    rate_key = f"remote_exec:{device_id}"
    if not rate_limiter.is_allowed(rate_key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    correlation_id = str(uuid.uuid4())

    command = DeviceCommand(
        device_id=device_id,
        type="REMOTE_EXEC",
        status="queued",
        correlation_id=correlation_id,
        payload=json.dumps({"script": command_script}),
        created_by=user.username if user else "admin"
    )
    db.add(command)
    db.commit()
    db.refresh(command)

    username = user.username if user else "admin"
    log_device_event(db, device.id, "remote_exec_initiated", {
        "correlation_id": correlation_id,
        "script": command_script,
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
    hmac_signature = compute_hmac_signature(correlation_id, device.id, "remote_exec", timestamp)

    message = {
        "message": {
            "token": device.fcm_token,
            "data": {
                "action": "remote_exec",
                "script": command_script,
                "correlation_id": correlation_id,
                "device_id": device.id,
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

            db.commit()

            return {"command_id": str(command.id), "status": "queued", "correlation_id": correlation_id}

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

@app.get("/v1/devices/{device_id}/commands")
async def get_device_commands(
    device_id: str,
    limit: int = 25,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a list of commands sent to a specific device."""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    commands = db.query(DeviceCommand).filter(DeviceCommand.device_id == device_id).order_by(DeviceCommand.created_at.desc()).limit(limit).all()

    return [
        {
            "id": cmd.id,
            "type": cmd.type,
            "status": cmd.status,
            "correlation_id": cmd.correlation_id,
            "payload": json.loads(cmd.payload) if cmd.payload else None,
            "error": cmd.error,
            "created_by": cmd.created_by,
            "created_at": cmd.created_at.isoformat() + "Z",
            "updated_at": cmd.updated_at.isoformat() + "Z" if cmd.updated_at else None
        }
        for cmd in commands
    ]

@app.get("/v1/commands/results")
async def get_command_results(
    request_id: Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get results for dispatched commands."""
    query = db.query(CommandResult)

    if request_id:
        query = query.filter(CommandResult.correlation_id == request_id)
    if device_id:
        query = query.filter(CommandResult.device_id == device_id)
    if action:
        query = query.filter(CommandResult.action == action)

    results = query.order_by(CommandResult.finished_at.desc()).all()

    return [
        {
            "id": res.id,
            "correlation_id": res.correlation_id,
            "device_id": res.device_id,
            "action": res.action,
            "status": res.status,
            "message": res.message,
            "created_at": res.created_at.isoformat() + "Z",
            "finished_at": res.finished_at.isoformat() + "Z" if res.finished_at else None
        }
        for res in results
    ]

@app.get("/admin/commands")
async def get_admin_commands(
    device_id: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a list of admin-initiated commands."""
    query = db.query(DeviceCommand)

    if device_id:
        query = query.filter(DeviceCommand.device_id == device_id)
    if type:
        query = query.filter(DeviceCommand.type == type)
    if status:
        query = query.filter(DeviceCommand.status == status)

    commands = query.order_by(DeviceCommand.created_at.desc()).limit(limit).all()

    return [
        {
            "id": cmd.id,
            "device_id": cmd.device_id,
            "type": cmd.type,
            "status": cmd.status,
            "correlation_id": cmd.correlation_id,
            "payload": json.loads(cmd.payload) if cmd.payload else None,
            "error": cmd.error,
            "created_by": cmd.created_by,
            "created_at": cmd.created_at.isoformat() + "Z",
            "updated_at": cmd.updated_at.isoformat() + "Z" if cmd.updated_at else None
        }
        for cmd in commands
    ]

# --- Batch Remote Execution Endpoints ---
# Rate limiting: 10 batch remote executions per minute per user
remote_exec_batch_limiter = RateLimiter(max_requests=10, window_seconds=60)

# Concurrency control for FCM dispatch (prevent overwhelming Firebase)
FCM_DISPATCH_CONCURRENCY = 20  # Max concurrent FCM requests

class RemoteExecRequest(BaseModel):
    mode: str  # "fcm" or "shell"
    payload: Optional[dict] = None  # FCM payload or {"script": "..."} for shell
    command: Optional[str] = None  # Alternative: direct command string for shell mode
    scope_type: str = "all"  # "all", "filter", "aliases", "device_ids"
    targets: Optional[dict] = None  # Alternative: {"aliases": [...]} or {"device_ids": [...]}
    device_ids: Optional[List[str]] = None
    aliases: Optional[List[str]] = None
    online_only: bool = False
    dry_run: bool = False

class RemoteExecAckRequest(BaseModel):
    exec_id: str
    correlation_id: str
    device_id: str
    status: str  # "OK", "FAILED", "TIMEOUT", "DENIED"
    exit_code: Optional[int] = None
    output: Optional[str] = None
    error: Optional[str] = None

async def dispatch_fcm_to_device(
    device: Device,
    exec_id: str,
    mode: str,
    payload: dict,
    semaphore: asyncio.Semaphore,
    client: "httpx.AsyncClient",
    fcm_url: str,
    access_token: str,
    db_results: dict,
    correlation_id: str  # Pre-generated correlation_id to match DB record
) -> dict:
    """
    Dispatch FCM message to a single device with semaphore-based concurrency control.
    Uses pre-generated correlation_id that matches the RemoteExecResult record in DB.
    Returns result dict with device_id, status, and optional error.
    """
    
    async with semaphore:
        try:
            if not device.fcm_token:
                # Update db_results so error is tracked properly
                db_results[device.id] = {
                    "correlation_id": correlation_id,
                    "alias": device.alias,
                    "status": "error",
                    "error": "No FCM token"
                }
                return {
                    "device_id": device.id,
                    "alias": device.alias,
                    "correlation_id": correlation_id,
                    "status": "error",
                    "error": "No FCM token"
                }
            
            timestamp = datetime.now(timezone.utc).isoformat()
            action = f"remote_exec_{mode}"
            
            if mode == "shell":
                command_template = payload.get("script", "")
                # Substitute template variables with device-specific values
                # Supported variables: {alias}, {device_id}
                # Note: {device_token} is not available as tokens are hashed for security
                command = command_template.replace("{alias}", device.alias or "")
                command = command.replace("{device_id}", device.id or "")
                
                # CRITICAL: Re-validate the command after substitution to ensure it's still valid
                # This prevents templates that pass validation from producing invalid commands after substitution
                # Run validation in thread pool to avoid blocking async event loop (validation may do DB queries)
                try:
                    is_valid, error_msg = await asyncio.to_thread(validate_shell_command, command)
                    if not is_valid:
                        error_detail = f"Command invalid after template substitution: {error_msg}"
                        # Update db_results so error is tracked properly
                        db_results[device.id] = {
                            "correlation_id": correlation_id,
                            "alias": device.alias,
                            "status": "error",
                            "error": error_detail
                        }
                        return {
                            "device_id": device.id,
                            "alias": device.alias,
                            "correlation_id": correlation_id,
                            "status": "error",
                            "error": error_detail
                        }
                except Exception as e:
                    # If validation itself fails, log and allow command (fail-safe)
                    print(f"[REMOTE-EXEC] Validation error for device {device.id}: {e}")
                    # Continue with command execution rather than blocking
                
                # Include critical payload field (command) in HMAC to prevent tampering
                # Use substituted command for HMAC to ensure integrity
                payload_fields = {"command": command}
                hmac_signature = compute_hmac_signature_with_payload(
                    correlation_id, device.id, action, timestamp, payload_fields
                )
                fcm_data = {
                    "action": "remote_exec_shell",
                    "exec_id": exec_id,
                    "correlation_id": correlation_id,
                    "device_id": device.id,
                    "command": command,
                    "ts": timestamp,
                    "hmac": hmac_signature
                }
            else:  # FCM mode
                # Include critical payload fields in HMAC to prevent tampering
                # Extract type and other critical fields from payload
                payload_fields = {}
                if "type" in payload:
                    payload_fields["type"] = str(payload["type"])
                if "package_name" in payload:
                    payload_fields["package_name"] = str(payload["package_name"])
                if "enable" in payload:  # For set_dnd
                    payload_fields["enable"] = str(payload["enable"])
                if "duration" in payload:  # For ring
                    payload_fields["duration"] = str(payload["duration"])
                
                hmac_signature = compute_hmac_signature_with_payload(
                    correlation_id, device.id, action, timestamp, payload_fields
                )
                fcm_data = {
                    "action": "remote_exec_fcm",
                    "exec_id": exec_id,
                    "correlation_id": correlation_id,
                    "device_id": device.id,
                    "ts": timestamp,
                    "hmac": hmac_signature,
                    **{k: str(v) for k, v in payload.items()}  # Flatten payload into FCM data
                }
            
            fcm_message = {
                "message": {
                    "token": device.fcm_token,
                    "data": fcm_data,
                    "android": {
                        "priority": "high"
                    }
                }
            }
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            response = await client.post(fcm_url, json=fcm_message, headers=headers, timeout=10.0)
            
            if response.status_code == 200:
                db_results[device.id] = {
                    "correlation_id": correlation_id,
                    "alias": device.alias,
                    "status": "sent"
                }
                return {
                    "device_id": device.id,
                    "alias": device.alias,
                    "correlation_id": correlation_id,
                    "status": "sent"
                }
            else:
                error_msg = f"FCM error: {response.status_code}"
                db_results[device.id] = {
                    "correlation_id": correlation_id,
                    "alias": device.alias,
                    "status": "error",
                    "error": error_msg
                }
                return {
                    "device_id": device.id,
                    "alias": device.alias,
                    "correlation_id": correlation_id,
                    "status": "error",
                    "error": error_msg
                }
        except asyncio.TimeoutError:
            db_results[device.id] = {
                "correlation_id": correlation_id,
                "alias": device.alias,
                "status": "error",
                "error": "FCM timeout"
            }
            return {
                "device_id": device.id,
                "alias": device.alias,
                "correlation_id": correlation_id,
                "status": "error",
                "error": "FCM timeout"
            }
        except Exception as e:
            db_results[device.id] = {
                "correlation_id": correlation_id,
                "alias": device.alias,
                "status": "error",
                "error": str(e)
            }
            return {
                "device_id": device.id,
                "alias": device.alias,
                "correlation_id": correlation_id,
                "status": "error",
                "error": str(e)
            }

@app.get("/v1/remote-exec")
async def list_remote_executions(
    limit: int = Query(10, ge=1, le=100),
    status: Optional[str] = Query(None),
    mode: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List recent remote execution runs.
    Returns summary info with stats for each execution.
    """
    query = db.query(RemoteExec)
    
    if status:
        query = query.filter(RemoteExec.status == status)
    if mode:
        query = query.filter(RemoteExec.mode == mode)
    
    executions = query.order_by(RemoteExec.created_at.desc()).limit(limit).all()
    
    return [
        {
            "exec_id": exec.id,
            "mode": exec.mode,
            "status": exec.status,
            "created_at": exec.created_at.isoformat() + "Z",
            "created_by": exec.created_by,
            "stats": {
                "total_targets": exec.total_targets,
                "sent_count": exec.sent_count,
                "acked_count": exec.acked_count,
                "error_count": exec.error_count
            }
        }
        for exec in executions
    ]

@app.post("/v1/remote-exec")
async def create_remote_execution(
    request: RemoteExecRequest,
    req: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create and dispatch a batch remote execution to multiple devices.
    Supports FCM commands (ping, ring, reboot, etc.) and shell commands.
    Scales to 100+ devices using async parallel FCM dispatch with bounded concurrency.
    """
    import httpx
    
    # Rate limit check
    rate_key = f"remote_exec_batch:{user.id}"
    if not remote_exec_batch_limiter.is_allowed(rate_key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")
    
    # Validate mode
    if request.mode not in ["fcm", "shell"]:
        raise HTTPException(status_code=422, detail="Mode must be 'fcm' or 'shell'")
    
    # Normalize payload - handle both payload.script and direct command field
    effective_payload = request.payload or {}
    if request.mode == "shell":
        # Support both payload.script and direct command field
        script = effective_payload.get("script") or request.command
        if not script:
            raise HTTPException(status_code=422, detail="Shell mode requires 'script' in payload or 'command' field")
        is_valid, error_msg = validate_shell_command(script)
        if not is_valid:
            raise HTTPException(status_code=422, detail=f"Invalid shell command: {error_msg}")
        # Normalize: put script in payload for consistency
        effective_payload = {"script": script}
    
    # Build target device query
    query = db.query(Device)
    
    # Handle both old format (scope_type + device_ids/aliases) and new format (targets dict)
    target_device_ids = request.device_ids
    target_aliases = request.aliases
    
    # If targets dict is provided, extract from there
    if request.targets:
        if "device_ids" in request.targets:
            target_device_ids = request.targets["device_ids"]
        if "aliases" in request.targets:
            target_aliases = request.targets["aliases"]
    
    # Determine scope type from data if not explicitly set
    scope_type = request.scope_type
    if request.targets:
        if "device_ids" in request.targets:
            scope_type = "device_ids"
        elif "aliases" in request.targets:
            scope_type = "aliases"
    
    if scope_type == "device_ids" and target_device_ids:
        query = query.filter(Device.id.in_(target_device_ids))
    elif scope_type == "aliases" and target_aliases:
        query = query.filter(Device.alias.in_(target_aliases))
    # "all" and "filter" scope_types use all devices
    
    # Filter to online only if requested
    if request.online_only:
        heartbeat_interval = alert_config.HEARTBEAT_INTERVAL_SECONDS
        offline_threshold = datetime.now(timezone.utc) - timedelta(seconds=heartbeat_interval * 3)
        query = query.filter(Device.last_seen >= offline_threshold)
    
    # Get target devices
    devices = query.all()
    
    if not devices:
        raise HTTPException(status_code=404, detail="No devices match the specified criteria")
    
    # Dry run mode - just return preview
    if request.dry_run:
        return {
            "dry_run": True,
            "target_count": len(devices),
            "sample_devices": [
                {"id": d.id, "alias": d.alias}
                for d in devices[:10]
            ]
        }
    
    # Create RemoteExec record
    client_ip = req.client.host if req.client else "unknown"
    payload_hash = hashlib.sha256(json.dumps(effective_payload, sort_keys=True).encode()).hexdigest()
    
    exec_record = RemoteExec(
        mode=request.mode,
        raw_request=json.dumps({
            "mode": request.mode,
            "payload": effective_payload,
            "scope_type": scope_type,
            "online_only": request.online_only
        }),
        targets=json.dumps([d.id for d in devices]),
        created_by=user.username,
        created_by_ip=client_ip,
        payload_hash=payload_hash,
        total_targets=len(devices),
        sent_count=0,
        acked_count=0,
        error_count=0,
        status="dispatching"
    )
    db.add(exec_record)
    db.commit()
    db.refresh(exec_record)
    exec_id = exec_record.id
    
    # Get FCM credentials
    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
        fcm_url = build_fcm_v1_url(project_id)
    except Exception as e:
        exec_record.status = "failed"
        exec_record.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=500, detail=f"FCM authentication failed: {str(e)}")
    
    # CRITICAL: Create RemoteExecResult records FIRST with pre-generated correlation_ids
    # This ensures records exist in DB before ACKs arrive from devices
    device_correlation_ids = {}  # Map device_id -> correlation_id
    
    for device in devices:
        correlation_id = str(uuid.uuid4())
        device_correlation_ids[device.id] = correlation_id
        
        result_record = RemoteExecResult(
            exec_id=exec_id,
            device_id=device.id,
            alias=device.alias,
            correlation_id=correlation_id,
            status="pending",  # Will be updated after FCM dispatch
            error=None
        )
        db.add(result_record)
    
    # Commit all result records BEFORE dispatching FCM
    # This prevents race condition where ACKs arrive before records exist
    db.commit()
    
    # Dispatch FCM messages in parallel with bounded concurrency
    semaphore = asyncio.Semaphore(FCM_DISPATCH_CONCURRENCY)
    dispatch_results = {}  # Track dispatch success/failure per device
    
    async with httpx.AsyncClient() as client:
        tasks = [
            dispatch_fcm_to_device(
                device=device,
                exec_id=exec_id,
                mode=request.mode,
                payload=effective_payload,
                semaphore=semaphore,
                client=client,
                fcm_url=fcm_url,
                access_token=access_token,
                db_results=dispatch_results,
                correlation_id=device_correlation_ids[device.id]  # Pass pre-generated correlation_id
            )
            for device in devices
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Update RemoteExecResult records with dispatch status
    sent_count = 0
    error_count = 0
    
    for device in devices:
        result_data = dispatch_results.get(device.id, {})
        dispatch_status = result_data.get("status", "error")
        error = result_data.get("error")
        
        if dispatch_status == "sent":
            sent_count += 1
        else:
            error_count += 1
            # Update the result record to show dispatch error
            result = db.query(RemoteExecResult).filter(
                RemoteExecResult.exec_id == exec_id,
                RemoteExecResult.device_id == device.id
            ).first()
            if result:
                result.status = "error"
                result.error = error
    
    # Update exec record with counts
    exec_record.sent_count = sent_count
    exec_record.error_count = error_count
    exec_record.status = "pending" if sent_count > 0 else "failed"
    if sent_count == 0:
        exec_record.completed_at = datetime.now(timezone.utc)
    db.commit()
    
    # Log the execution
    structured_logger.log_event(
        "remote_exec.batch.dispatched",
        exec_id=exec_id,
        mode=request.mode,
        user=user.username,
        total_targets=len(devices),
        sent_count=sent_count,
        error_count=error_count,
        client_ip=client_ip
    )
    
    return {
        "exec_id": exec_id,
        "status": exec_record.status,
        "stats": {
            "total_targets": len(devices),
            "sent_count": sent_count,
            "error_count": error_count
        }
    }

@app.get("/v1/remote-exec/{exec_id}")
async def get_remote_execution(
    exec_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get details of a specific remote execution including per-device results.
    """
    exec_record = db.query(RemoteExec).filter(RemoteExec.id == exec_id).first()
    if not exec_record:
        raise HTTPException(status_code=404, detail="Remote execution not found")
    
    # Get all results for this execution
    results = db.query(RemoteExecResult).filter(RemoteExecResult.exec_id == exec_id).all()
    
    return {
        "exec_id": exec_record.id,
        "mode": exec_record.mode,
        "status": exec_record.status,
        "created_at": exec_record.created_at.isoformat() + "Z",
        "created_by": exec_record.created_by,
        "completed_at": exec_record.completed_at.isoformat() + "Z" if exec_record.completed_at else None,
        "stats": {
            "total_targets": exec_record.total_targets,
            "sent_count": exec_record.sent_count,
            "acked_count": exec_record.acked_count,
            "error_count": exec_record.error_count
        },
        "results": [
            {
                "device_id": r.device_id,
                "alias": r.alias,
                "correlation_id": r.correlation_id,
                "status": r.status,
                "exit_code": r.exit_code,
                "output": r.output_preview,
                "error": r.error,
                "updated_at": r.updated_at.isoformat() + "Z"
            }
            for r in results
        ]
    }

@app.post("/v1/remote-exec/ack")
async def remote_exec_ack(
    request: RemoteExecAckRequest,
    req: Request,
    db: Session = Depends(get_db)
):
    """
    Receive ACK from device for remote execution command.
    Called by Android agent after executing the command.
    Updates RemoteExecResult status and parent RemoteExec counters.
    """
    # Find the result record by correlation_id
    result = db.query(RemoteExecResult).filter(
        RemoteExecResult.correlation_id == request.correlation_id,
        RemoteExecResult.device_id == request.device_id
    ).first()
    
    if not result:
        # Try to find by exec_id and device_id as fallback
        result = db.query(RemoteExecResult).filter(
            RemoteExecResult.exec_id == request.exec_id,
            RemoteExecResult.device_id == request.device_id
        ).first()
    
    if not result:
        structured_logger.log_event(
            "remote_exec.ack.not_found",
            level="WARN",
            exec_id=request.exec_id,
            correlation_id=request.correlation_id,
            device_id=request.device_id
        )
        raise HTTPException(status_code=404, detail="Result record not found")
    
    # Update result record
    old_status = result.status
    result.status = request.status
    result.exit_code = request.exit_code
    result.output_preview = request.output[:2048] if request.output else None  # Limit output size
    result.error = request.error[:1024] if request.error else None  # Limit error size
    result.updated_at = datetime.now(timezone.utc)
    
    # Update parent exec record counters if status changed from pending
    exec_record = db.query(RemoteExec).filter(RemoteExec.id == result.exec_id).first()
    if exec_record and old_status == "pending":
        exec_record.acked_count += 1
        if request.status != "OK":
            exec_record.error_count += 1
        
        # Check if all results are now complete
        pending_count = db.query(RemoteExecResult).filter(
            RemoteExecResult.exec_id == exec_record.id,
            RemoteExecResult.status == "pending"
        ).count()
        
        if pending_count == 0:
            exec_record.status = "completed"
            exec_record.completed_at = datetime.now(timezone.utc)
    
    db.commit()
    
    structured_logger.log_event(
        "remote_exec.ack.received",
        exec_id=request.exec_id,
        correlation_id=request.correlation_id,
        device_id=request.device_id,
        status=request.status,
        exit_code=request.exit_code
    )
    
    return {"ok": True, "status": "received"}

# --- Restart App Endpoint (Three-Step: Force Stop + Battery Exemption + Launch) ---

class RestartAppRequest(BaseModel):
    package_name: str = "io.unitynodes.unityapp"
    scope_type: str = "all"  # "all", "aliases", "device_ids"
    targets: Optional[dict] = None  # {"aliases": [...]} or {"device_ids": [...]}
    device_ids: Optional[List[str]] = None
    aliases: Optional[List[str]] = None
    online_only: bool = False
    dry_run: bool = False

@app.post("/v1/remote-exec/restart-app")
async def restart_app(
    request: RestartAppRequest,
    req: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Restart an app on target devices using a three-step process:
    1. Force-stop the app
    2. Re-apply battery optimization exemption (prevents Android from resetting background permission)
    3. Launch the app
    
    Each step has a 2-second delay to ensure proper execution.
    Returns combined status tracking for all three steps.
    """
    import httpx
    
    # Rate limit check
    rate_key = f"remote_exec_batch:{user.id}"
    if not remote_exec_batch_limiter.is_allowed(rate_key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")
    
    # Build target device query
    query = db.query(Device)
    
    target_device_ids = request.device_ids
    target_aliases = request.aliases
    
    if request.targets:
        if "device_ids" in request.targets:
            target_device_ids = request.targets["device_ids"]
        if "aliases" in request.targets:
            target_aliases = request.targets["aliases"]
    
    scope_type = request.scope_type
    if request.targets:
        if "device_ids" in request.targets:
            scope_type = "device_ids"
        elif "aliases" in request.targets:
            scope_type = "aliases"
    
    if scope_type == "device_ids" and target_device_ids:
        query = query.filter(Device.id.in_(target_device_ids))
    elif scope_type == "aliases" and target_aliases:
        query = query.filter(Device.alias.in_(target_aliases))
    
    if request.online_only:
        heartbeat_interval = alert_config.HEARTBEAT_INTERVAL_SECONDS
        offline_threshold = datetime.now(timezone.utc) - timedelta(seconds=heartbeat_interval * 3)
        query = query.filter(Device.last_seen >= offline_threshold)
    
    devices = query.all()
    
    if not devices:
        raise HTTPException(status_code=404, detail="No devices match the specified criteria")
    
    # Dry run mode
    if request.dry_run:
        return {
            "dry_run": True,
            "target_count": len(devices),
            "package_name": request.package_name,
            "sample_devices": [{"id": d.id, "alias": d.alias} for d in devices[:10]]
        }
    
    client_ip = req.client.host if req.client else "unknown"
    
    # Create exec records for all three steps
    force_stop_exec = RemoteExec(
        mode="restart_app_stop",
        raw_request=json.dumps({
            "package_name": request.package_name,
            "step": "force_stop",
            "command": f"am force-stop {request.package_name}"
        }),
        targets=json.dumps([d.id for d in devices]),
        created_by=user.username,
        created_by_ip=client_ip,
        total_targets=len(devices),
        status="dispatching"
    )
    db.add(force_stop_exec)
    db.commit()
    db.refresh(force_stop_exec)
    
    exempt_exec = RemoteExec(
        mode="restart_app_exempt",
        raw_request=json.dumps({
            "package_name": request.package_name,
            "step": "battery_exemption",
            "linked_exec_id": force_stop_exec.id
        }),
        targets=json.dumps([d.id for d in devices]),
        created_by=user.username,
        created_by_ip=client_ip,
        total_targets=len(devices),
        status="dispatching"
    )
    db.add(exempt_exec)
    db.commit()
    db.refresh(exempt_exec)
    
    launch_exec = RemoteExec(
        mode="restart_app_launch",
        raw_request=json.dumps({
            "package_name": request.package_name,
            "step": "launch",
            "linked_exec_id": exempt_exec.id
        }),
        targets=json.dumps([d.id for d in devices]),
        created_by=user.username,
        created_by_ip=client_ip,
        total_targets=len(devices),
        status="dispatching"
    )
    db.add(launch_exec)
    db.commit()
    db.refresh(launch_exec)
    
    ui_clicks_exec = RemoteExec(
        mode="restart_app_ui_clicks",
        raw_request=json.dumps({
            "package_name": request.package_name,
            "step": "ui_clicks",
            "linked_exec_id": launch_exec.id
        }),
        targets=json.dumps([d.id for d in devices]),
        created_by=user.username,
        created_by_ip=client_ip,
        total_targets=len(devices),
        status="pending"
    )
    db.add(ui_clicks_exec)
    db.commit()
    db.refresh(ui_clicks_exec)
    
    # Get FCM credentials
    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
        fcm_url = build_fcm_v1_url(project_id)
    except Exception as e:
        force_stop_exec.status = "failed"
        exempt_exec.status = "failed"
        launch_exec.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"FCM authentication failed: {str(e)}")
    
    # Create result records for all four steps
    force_stop_correlations = {}
    exempt_correlations = {}
    launch_correlations = {}
    ui_clicks_correlations = {}
    
    for device in devices:
        # Force stop result
        fs_correlation = str(uuid.uuid4())
        force_stop_correlations[device.id] = fs_correlation
        db.add(RemoteExecResult(
            exec_id=force_stop_exec.id,
            device_id=device.id,
            alias=device.alias,
            correlation_id=fs_correlation,
            status="pending"
        ))
        
        # Battery exemption result
        exempt_correlation = str(uuid.uuid4())
        exempt_correlations[device.id] = exempt_correlation
        db.add(RemoteExecResult(
            exec_id=exempt_exec.id,
            device_id=device.id,
            alias=device.alias,
            correlation_id=exempt_correlation,
            status="pending"
        ))
        
        # Launch result
        launch_correlation = str(uuid.uuid4())
        launch_correlations[device.id] = launch_correlation
        db.add(RemoteExecResult(
            exec_id=launch_exec.id,
            device_id=device.id,
            alias=device.alias,
            correlation_id=launch_correlation,
            status="pending"
        ))
        
        # UI clicks result
        ui_clicks_correlation = str(uuid.uuid4())
        ui_clicks_correlations[device.id] = ui_clicks_correlation
        db.add(RemoteExecResult(
            exec_id=ui_clicks_exec.id,
            device_id=device.id,
            alias=device.alias,
            correlation_id=ui_clicks_correlation,
            status="pending"
        ))
    
    db.commit()
    
    # Step 1: Dispatch force-stop commands
    semaphore = asyncio.Semaphore(FCM_DISPATCH_CONCURRENCY)
    force_stop_results = {}
    
    async with httpx.AsyncClient() as client:
        tasks = [
            dispatch_force_stop_to_device(
                device=device,
                package_name=request.package_name,
                correlation_id=force_stop_correlations[device.id],
                semaphore=semaphore,
                client=client,
                fcm_url=fcm_url,
                access_token=access_token,
                db_results=force_stop_results
            )
            for device in devices
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    # Update force-stop exec counts
    fs_sent = sum(1 for r in force_stop_results.values() if r.get("status") == "sent")
    fs_errors = len(devices) - fs_sent
    force_stop_exec.sent_count = fs_sent
    force_stop_exec.error_count = fs_errors
    force_stop_exec.status = "pending" if fs_sent > 0 else "failed"
    
    # Update failed result records
    for device in devices:
        result_data = force_stop_results.get(device.id, {})
        if result_data.get("status") != "sent":
            result = db.query(RemoteExecResult).filter(
                RemoteExecResult.exec_id == force_stop_exec.id,
                RemoteExecResult.device_id == device.id
            ).first()
            if result:
                result.status = "error"
                result.error = result_data.get("error", "FCM dispatch failed")
    
    db.commit()
    
    # 2-second delay to allow force-stop to complete
    await asyncio.sleep(2.0)
    
    # Step 2: Dispatch battery exemption commands
    exempt_results = {}
    
    async with httpx.AsyncClient() as client:
        tasks = [
            dispatch_exempt_unity_to_device(
                device=device,
                package_name=request.package_name,
                correlation_id=exempt_correlations[device.id],
                semaphore=semaphore,
                client=client,
                fcm_url=fcm_url,
                access_token=access_token,
                db_results=exempt_results
            )
            for device in devices
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    # Update exemption exec counts
    exempt_sent = sum(1 for r in exempt_results.values() if r.get("status") == "sent")
    exempt_errors = len(devices) - exempt_sent
    exempt_exec.sent_count = exempt_sent
    exempt_exec.error_count = exempt_errors
    exempt_exec.status = "pending" if exempt_sent > 0 else "failed"
    
    # Update failed result records
    for device in devices:
        result_data = exempt_results.get(device.id, {})
        if result_data.get("status") != "sent":
            result = db.query(RemoteExecResult).filter(
                RemoteExecResult.exec_id == exempt_exec.id,
                RemoteExecResult.device_id == device.id
            ).first()
            if result:
                result.status = "error"
                result.error = result_data.get("error", "FCM dispatch failed")
    
    db.commit()
    
    # 2-second delay to allow battery exemption to complete
    await asyncio.sleep(2.0)
    
    # Step 3: Dispatch launch commands
    launch_results = {}
    
    async with httpx.AsyncClient() as client:
        tasks = [
            dispatch_launch_app_to_device(
                device=device,
                package_name=request.package_name,
                correlation_id=launch_correlations[device.id],
                semaphore=semaphore,
                client=client,
                fcm_url=fcm_url,
                access_token=access_token,
                db_results=launch_results
            )
            for device in devices
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    # Update launch exec counts
    launch_sent = sum(1 for r in launch_results.values() if r.get("status") == "sent")
    launch_errors = len(devices) - launch_sent
    launch_exec.sent_count = launch_sent
    launch_exec.error_count = launch_errors
    launch_exec.status = "pending" if launch_sent > 0 else "failed"
    
    # Update failed result records
    for device in devices:
        result_data = launch_results.get(device.id, {})
        if result_data.get("status") != "sent":
            result = db.query(RemoteExecResult).filter(
                RemoteExecResult.exec_id == launch_exec.id,
                RemoteExecResult.device_id == device.id
            ).first()
            if result:
                result.status = "error"
                result.error = result_data.get("error", "FCM dispatch failed")
    
    db.commit()
    
    # 15-second delay to allow app to load and show permission prompt
    await asyncio.sleep(15.0)
    
    # Step 4: Dispatch UI clicks commands (with retry logic)
    ui_clicks_exec.status = "dispatching"
    db.commit()
    
    # First tap: input tap 500 885 (with retry logic - 3 attempts)
    # Use base correlation ID for all retry attempts (updates same result record)
    first_tap_results = {}
    first_tap_success = set()
    
    for attempt in range(3):
        attempt_results = {}
        async with httpx.AsyncClient() as client:
            tasks = [
                dispatch_fcm_to_device(
                    device=device,
                    exec_id=ui_clicks_exec.id,
                    mode="shell",
                    payload={"script": "input tap 500 885"},
                    semaphore=semaphore,
                    client=client,
                    fcm_url=fcm_url,
                    access_token=access_token,
                    db_results=attempt_results,
                    correlation_id=ui_clicks_correlations[device.id]  # Use base correlation ID
                )
                for device in devices if device.id not in first_tap_success
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        
        # Track successful dispatches
        for device_id, result in attempt_results.items():
            if result.get("status") == "sent":
                first_tap_success.add(device_id)
                if device_id not in first_tap_results:
                    first_tap_results[device_id] = result
        
        # If all devices succeeded or this is the last attempt, break
        if len(first_tap_success) == len(devices) or attempt == 2:
            break
        
        # Wait 1 second between retries
        if attempt < 2:
            await asyncio.sleep(1.0)
    
    # Check if first tap failed for any devices - abort for those devices
    failed_devices = set(device.id for device in devices) - first_tap_success
    if failed_devices:
        for device_id in failed_devices:
            result = db.query(RemoteExecResult).filter(
                RemoteExecResult.exec_id == ui_clicks_exec.id,
                RemoteExecResult.device_id == device_id
            ).first()
            if result:
                result.status = "error"
                result.error = "First tap failed after 3 retry attempts - aborted"
    
    # Wait 2 seconds before second tap
    await asyncio.sleep(2.0)
    
    # Second tap: input tap 590 980 (with retry logic - 3 attempts, only for devices that succeeded first tap)
    # Use same correlation ID (updates same result record with second tap result)
    second_tap_results = {}
    second_tap_success = set()
    
    for attempt in range(3):
        attempt_results = {}
        async with httpx.AsyncClient() as client:
            tasks = [
                dispatch_fcm_to_device(
                    device=device,
                    exec_id=ui_clicks_exec.id,
                    mode="shell",
                    payload={"script": "input tap 590 980"},
                    semaphore=semaphore,
                    client=client,
                    fcm_url=fcm_url,
                    access_token=access_token,
                    db_results=attempt_results,
                    correlation_id=ui_clicks_correlations[device.id]  # Use same correlation ID
                )
                for device in devices if device.id in first_tap_success and device.id not in second_tap_success
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        
        # Track successful dispatches
        for device_id, result in attempt_results.items():
            if result.get("status") == "sent":
                second_tap_success.add(device_id)
                if device_id not in second_tap_results:
                    second_tap_results[device_id] = result
        
        # If all eligible devices succeeded or this is the last attempt, break
        if len(second_tap_success) == len(first_tap_success) or attempt == 2:
            break
        
        # Wait 1 second between retries
        if attempt < 2:
            await asyncio.sleep(1.0)
    
    # Update UI clicks exec counts and status
    ui_clicks_sent = len(first_tap_success)
    ui_clicks_errors = len(devices) - ui_clicks_sent
    ui_clicks_exec.sent_count = ui_clicks_sent
    ui_clicks_exec.error_count = ui_clicks_errors
    ui_clicks_exec.status = "pending" if ui_clicks_sent > 0 else "failed"
    
    # Update result records for devices where second tap failed
    for device_id in first_tap_success:
        if device_id not in second_tap_success:
            result = db.query(RemoteExecResult).filter(
                RemoteExecResult.exec_id == ui_clicks_exec.id,
                RemoteExecResult.device_id == device_id
            ).first()
            if result:
                # Partial success - first tap worked but second failed
                result.status = "error"
                result.error = "First tap succeeded but second tap failed after 3 retry attempts"
    
    db.commit()
    
    structured_logger.log_event(
        "remote_exec.restart_app.dispatched",
        force_stop_exec_id=force_stop_exec.id,
        exempt_exec_id=exempt_exec.id,
        launch_exec_id=launch_exec.id,
        ui_clicks_exec_id=ui_clicks_exec.id,
        package_name=request.package_name,
        user=user.username,
        total_targets=len(devices),
        force_stop_sent=fs_sent,
        exempt_sent=exempt_sent,
        launch_sent=launch_sent,
        ui_clicks_sent=ui_clicks_sent,
        client_ip=client_ip
    )
    
    return {
        "restart_id": force_stop_exec.id,
        "force_stop_exec_id": force_stop_exec.id,
        "exempt_exec_id": exempt_exec.id,
        "launch_exec_id": launch_exec.id,
        "ui_clicks_exec_id": ui_clicks_exec.id,
        "package_name": request.package_name,
        "stats": {
            "total_targets": len(devices),
            "force_stop": {"sent": fs_sent, "errors": fs_errors},
            "battery_exemption": {"sent": exempt_sent, "errors": exempt_errors},
            "launch": {"sent": launch_sent, "errors": launch_errors},
            "ui_clicks": {"sent": ui_clicks_sent, "errors": ui_clicks_errors}
        }
    }

@app.get("/v1/remote-exec/restart-app/{restart_id}")
async def get_restart_app_status(
    restart_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get combined status for a restart-app operation.
    Returns status of all four steps: force-stop, battery exemption, launch, and UI clicks.
    """
    # Get force-stop exec (primary)
    force_stop_exec = db.query(RemoteExec).filter(
        RemoteExec.id == restart_id,
        RemoteExec.mode == "restart_app_stop"
    ).first()
    
    if not force_stop_exec:
        raise HTTPException(status_code=404, detail="Restart operation not found")
    
    # Get linked exemption, launch, and UI clicks execs
    raw_request = json.loads(force_stop_exec.raw_request) if force_stop_exec.raw_request else {}
    package_name = raw_request.get("package_name", "unknown")
    
    exempt_exec = db.query(RemoteExec).filter(
        RemoteExec.mode == "restart_app_exempt",
        RemoteExec.created_by == force_stop_exec.created_by,
        RemoteExec.created_at >= force_stop_exec.created_at,
        RemoteExec.created_at <= force_stop_exec.created_at + timedelta(seconds=15)
    ).first()
    
    launch_exec = db.query(RemoteExec).filter(
        RemoteExec.mode == "restart_app_launch",
        RemoteExec.created_by == force_stop_exec.created_by,
        RemoteExec.created_at >= force_stop_exec.created_at,
        RemoteExec.created_at <= force_stop_exec.created_at + timedelta(seconds=15)
    ).first()
    
    ui_clicks_exec = db.query(RemoteExec).filter(
        RemoteExec.mode == "restart_app_ui_clicks",
        RemoteExec.created_by == force_stop_exec.created_by,
        RemoteExec.created_at >= force_stop_exec.created_at,
        RemoteExec.created_at <= force_stop_exec.created_at + timedelta(seconds=30)
    ).first()
    
    # Get results for all four steps
    force_stop_results = db.query(RemoteExecResult).filter(
        RemoteExecResult.exec_id == force_stop_exec.id
    ).all()
    
    exempt_results = []
    if exempt_exec:
        exempt_results = db.query(RemoteExecResult).filter(
            RemoteExecResult.exec_id == exempt_exec.id
        ).all()
    
    launch_results = []
    if launch_exec:
        launch_results = db.query(RemoteExecResult).filter(
            RemoteExecResult.exec_id == launch_exec.id
        ).all()
    
    ui_clicks_results = []
    if ui_clicks_exec:
        ui_clicks_results = db.query(RemoteExecResult).filter(
            RemoteExecResult.exec_id == ui_clicks_exec.id
        ).all()
    
    # Timeout logic: Mark pending results older than 5 minutes as timed_out
    timeout_threshold = datetime.now(timezone.utc) - timedelta(minutes=5)
    timeout_updated = False
    
    # Check force-stop results
    for result in force_stop_results:
        if result.status == "pending" and result.sent_at and result.sent_at < timeout_threshold:
            result.status = "timed_out"
            result.error = "Operation timed out after 5 minutes"
            result.updated_at = datetime.now(timezone.utc)
            timeout_updated = True
    
    # Check exemption results
    for result in exempt_results:
        if result.status == "pending" and result.sent_at and result.sent_at < timeout_threshold:
            result.status = "timed_out"
            result.error = "Operation timed out after 5 minutes"
            result.updated_at = datetime.now(timezone.utc)
            timeout_updated = True
    
    # Check launch results
    for result in launch_results:
        if result.status == "pending" and result.sent_at and result.sent_at < timeout_threshold:
            result.status = "timed_out"
            result.error = "Operation timed out after 5 minutes"
            result.updated_at = datetime.now(timezone.utc)
            timeout_updated = True
    
    # Check UI clicks results
    for result in ui_clicks_results:
        if result.status == "pending" and result.sent_at and result.sent_at < timeout_threshold:
            result.status = "timed_out"
            result.error = "Operation timed out after 5 minutes"
            result.updated_at = datetime.now(timezone.utc)
            timeout_updated = True
    
    # Commit timeout updates if any
    if timeout_updated:
        db.commit()
        # Refresh results after update
        force_stop_results = db.query(RemoteExecResult).filter(
            RemoteExecResult.exec_id == force_stop_exec.id
        ).all()
        if exempt_exec:
            exempt_results = db.query(RemoteExecResult).filter(
                RemoteExecResult.exec_id == exempt_exec.id
            ).all()
        if launch_exec:
            launch_results = db.query(RemoteExecResult).filter(
                RemoteExecResult.exec_id == launch_exec.id
            ).all()
        if ui_clicks_exec:
            ui_clicks_results = db.query(RemoteExecResult).filter(
                RemoteExecResult.exec_id == ui_clicks_exec.id
            ).all()
    
    # Build per-device combined status
    device_statuses = {}
    for r in force_stop_results:
        device_statuses[r.device_id] = {
            "device_id": r.device_id,
            "alias": r.alias,
            "force_stop": {
                "status": r.status,
                "exit_code": r.exit_code,
                "output": r.output_preview,
                "error": r.error
            },
            "battery_exemption": {"status": "pending"},
            "launch": {"status": "pending"},
            "ui_clicks": {"status": "pending"}
        }
    
    for r in exempt_results:
        if r.device_id in device_statuses:
            device_statuses[r.device_id]["battery_exemption"] = {
                "status": r.status,
                "exit_code": r.exit_code,
                "output": r.output_preview,
                "error": r.error
            }
    
    for r in launch_results:
        if r.device_id in device_statuses:
            device_statuses[r.device_id]["launch"] = {
                "status": r.status,
                "exit_code": r.exit_code,
                "output": r.output_preview,
                "error": r.error
            }
    
    for r in ui_clicks_results:
        if r.device_id in device_statuses:
            device_statuses[r.device_id]["ui_clicks"] = {
                "status": r.status,
                "exit_code": r.exit_code,
                "output": r.output_preview,
                "error": r.error
            }
    
    # Compute overall status per device
    for d in device_statuses.values():
        fs_status = d["force_stop"]["status"]
        exempt_status = d["battery_exemption"]["status"]
        launch_status = d["launch"]["status"]
        ui_clicks_status = d["ui_clicks"]["status"]
        fs_ok = fs_status == "OK"
        exempt_ok = exempt_status == "OK"
        launch_ok = launch_status == "OK"
        ui_clicks_ok = ui_clicks_status == "OK"
        
        # Check for timed_out (terminal state)
        fs_timed_out = fs_status == "timed_out"
        exempt_timed_out = exempt_status == "timed_out"
        launch_timed_out = launch_status == "timed_out"
        ui_clicks_timed_out = ui_clicks_status == "timed_out"
        
        if fs_ok and exempt_ok and launch_ok and ui_clicks_ok:
            d["overall_status"] = "ok"
        elif fs_timed_out or exempt_timed_out or launch_timed_out or ui_clicks_timed_out:
            d["overall_status"] = "timed_out"
        elif fs_status == "pending" or exempt_status == "pending" or launch_status == "pending" or ui_clicks_status == "pending":
            d["overall_status"] = "pending"
        else:
            d["overall_status"] = "failed"
    
    # Aggregate stats
    total = len(device_statuses)
    ok_count = sum(1 for d in device_statuses.values() if d["overall_status"] == "ok")
    failed_count = sum(1 for d in device_statuses.values() if d["overall_status"] == "failed")
    timed_out_count = sum(1 for d in device_statuses.values() if d["overall_status"] == "timed_out")
    pending_count = total - ok_count - failed_count - timed_out_count
    
    # Compute overall status with proper terminal states
    if pending_count == 0:
        if timed_out_count > 0 and ok_count == 0 and failed_count == 0:
            overall_status = "timed_out"
            failure_reason = f"All {timed_out_count} device(s) timed out"
        elif failed_count == 0 and timed_out_count == 0:
            overall_status = "completed"
            failure_reason = None
        elif ok_count == 0 and timed_out_count == 0:
            overall_status = "failed"
            failure_reason = f"All {failed_count} device(s) failed to restart"
        else:
            overall_status = "partial"
            parts = []
            if ok_count > 0:
                parts.append(f"{ok_count} OK")
            if failed_count > 0:
                parts.append(f"{failed_count} failed")
            if timed_out_count > 0:
                parts.append(f"{timed_out_count} timed out")
            failure_reason = ", ".join(parts)
    else:
        overall_status = "pending"
        failure_reason = None
    
    result = {
        "restart_id": restart_id,
        "package_name": package_name,
        "status": overall_status,
        "failure_reason": failure_reason,
        "created_at": force_stop_exec.created_at.isoformat() + "Z",
        "created_by": force_stop_exec.created_by,
        "force_stop_exec_id": force_stop_exec.id,
        "stats": {
            "total": total,
            "ok": ok_count,
            "failed": failed_count,
            "timed_out": timed_out_count,
            "pending": pending_count
        },
        "devices": list(device_statuses.values())
    }
    
    if exempt_exec:
        result["exempt_exec_id"] = exempt_exec.id
    if launch_exec:
        result["launch_exec_id"] = launch_exec.id
    if ui_clicks_exec:
        result["ui_clicks_exec_id"] = ui_clicks_exec.id
    
    return result

# --- Unity Soft Update Refresh Endpoint ---

def find_latest_unity_apk(db: Session) -> Optional[ApkVersion]:
    """
    Find the latest Unity APK where version_name starts with 'Unity'.
    Returns the most recently uploaded Unity APK, or None if not found.
    """
    unity_apk = db.query(ApkVersion).filter(
        ApkVersion.version_name.like('Unity%'),
        ApkVersion.is_active == True
    ).order_by(ApkVersion.uploaded_at.desc()).first()
    return unity_apk

class ReinstallUnityAndLaunchRequest(BaseModel):
    device_ids: List[str]
    dry_run: bool = False


async def _run_reinstall_unity_fcm_dispatch(
    exec_id: int,
    apk_id: int,
    apk_version_name: str,
    apk_version_code: int,
    apk_package_name: str,
    device_data: List[dict],
    installation_data: List[dict],
    install_correlations: dict,
    launch_correlations: dict,
    username: str,
    client_ip: str
):
    """
    Background task to dispatch FCM messages for reinstall-unity-and-launch.
    Runs asynchronously after the endpoint returns.
    """
    import httpx
    
    db = SessionLocal()
    try:
        reinstall_exec = db.query(RemoteExec).filter(RemoteExec.id == exec_id).first()
        if not reinstall_exec:
            structured_logger.log_event(
                "apk.reinstall_unity_and_launch.background_error",
                exec_id=exec_id,
                error="RemoteExec not found"
            )
            return
        
        apk = db.query(ApkVersion).filter(ApkVersion.id == apk_id).first()
        if not apk:
            reinstall_exec.status = "failed"
            reinstall_exec.error_count = len(device_data)
            db.commit()
            return
        
        try:
            access_token = get_access_token()
            project_id = get_firebase_project_id()
            fcm_url = build_fcm_v1_url(project_id)
        except Exception as e:
            reinstall_exec.status = "failed"
            reinstall_exec.error_count = len(device_data)
            
            for device_info in device_data:
                install_results = db.query(RemoteExecResult).filter(
                    RemoteExecResult.exec_id == exec_id,
                    RemoteExecResult.device_id == device_info["id"]
                ).all()
                for result in install_results:
                    result.status = "error"
                    result.error = f"FCM authentication failed: {str(e)}"
            
            db.commit()
            structured_logger.log_event(
                "apk.reinstall_unity_and_launch.fcm_auth_failed",
                exec_id=exec_id,
                error=str(e)
            )
            return
        
        devices = db.query(Device).filter(Device.id.in_([d["id"] for d in device_data])).all()
        device_map = {d.id: d for d in devices}
        
        installations = db.query(ApkInstallation).filter(
            ApkInstallation.id.in_([i["id"] for i in installation_data])
        ).all()
        installation_map = {inst.device_id: inst for inst in installations}
        
        batch_size = 5
        semaphore = asyncio.Semaphore(FCM_DISPATCH_CONCURRENCY)
        
        total_batches = (len(device_data) + batch_size - 1) // batch_size
        sent_count = 0
        error_count = 0
        
        async with httpx.AsyncClient() as client:
            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min(start_idx + batch_size, len(device_data))
                batch_device_ids = [d["id"] for d in device_data[start_idx:end_idx]]
                batch_devices = [device_map[did] for did in batch_device_ids if did in device_map]
                
                tasks = [
                    dispatch_apk_fcm_to_device(
                        device=device,
                        apk=apk,
                        installation=installation_map.get(device.id),
                        semaphore=semaphore,
                        client=client,
                        fcm_url=fcm_url,
                        access_token=access_token
                    )
                    for device in batch_devices
                    if device.id in installation_map
                ]
                
                if tasks:
                    batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for i, result in enumerate(batch_results):
                        device = batch_devices[i]
                        if isinstance(result, Exception):
                            error_count += 1
                            if device.id in install_correlations:
                                result_record = db.query(RemoteExecResult).filter(
                                    RemoteExecResult.exec_id == exec_id,
                                    RemoteExecResult.device_id == device.id,
                                    RemoteExecResult.correlation_id == install_correlations[device.id]["correlation_id"]
                                ).first()
                                if result_record:
                                    result_record.status = "error"
                                    result_record.error = f"FCM dispatch failed: {str(result)}"
                        elif result.get("status") == "sent":
                            sent_count += 1
                        else:
                            error_count += 1
                            device_id = result.get("device_id")
                            if device_id and device_id in install_correlations:
                                result_record = db.query(RemoteExecResult).filter(
                                    RemoteExecResult.exec_id == exec_id,
                                    RemoteExecResult.device_id == device_id,
                                    RemoteExecResult.correlation_id == install_correlations[device_id]["correlation_id"]
                                ).first()
                                if result_record:
                                    result_record.status = "error"
                                    result_record.error = result.get("error", "Unknown error")
                    
                    db.commit()
                
                if batch_num < total_batches - 1:
                    await asyncio.sleep(2.0)
        
        reinstall_exec.sent_count = sent_count
        reinstall_exec.error_count = error_count
        reinstall_exec.status = "pending" if sent_count > 0 else "failed"
        db.commit()
        
        structured_logger.log_event(
            "apk.reinstall_unity_and_launch.dispatched",
            exec_id=exec_id,
            apk_id=apk_id,
            version_name=apk_version_name,
            user=username,
            total_targets=len(device_data),
            sent_count=sent_count,
            error_count=error_count,
            client_ip=client_ip
        )
        
    except Exception as e:
        structured_logger.log_event(
            "apk.reinstall_unity_and_launch.background_error",
            exec_id=exec_id,
            error=str(e)
        )
        try:
            reinstall_exec = db.query(RemoteExec).filter(RemoteExec.id == exec_id).first()
            if reinstall_exec:
                reinstall_exec.status = "failed"
                db.commit()
        except:
            pass
    finally:
        db.close()


@app.post("/v1/apk/reinstall-unity-and-launch")
async def reinstall_unity_and_launch(
    request: ReinstallUnityAndLaunchRequest,
    req: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reinstall the latest Unity APK and launch the app.
    Returns immediately with exec_id, dispatches FCM in background.
    Poll the status endpoint for progress updates.
    """
    rate_key = f"remote_exec_batch:{user.id}"
    if not remote_exec_batch_limiter.is_allowed(rate_key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")
    
    unity_apk = find_latest_unity_apk(db)
    if not unity_apk:
        raise HTTPException(status_code=404, detail="No Unity APK found. Upload an APK with version_name starting with 'Unity'.")
    
    devices = db.query(Device).filter(Device.id.in_(request.device_ids)).all()
    if not devices:
        raise HTTPException(status_code=404, detail="No devices found")
    
    devices_with_fcm = [d for d in devices if d.fcm_token]
    if not devices_with_fcm:
        raise HTTPException(status_code=400, detail="No devices with FCM tokens found")
    
    if request.dry_run:
        return {
            "dry_run": True,
            "target_count": len(devices_with_fcm),
            "unity_apk": {
                "id": unity_apk.id,
                "version_name": unity_apk.version_name,
                "version_code": unity_apk.version_code
            },
            "sample_devices": [{"id": d.id, "alias": d.alias} for d in devices_with_fcm[:10]]
        }
    
    client_ip = req.client.host if req.client else "unknown"
    
    reinstall_exec = RemoteExec(
        mode="reinstall_unity_and_launch",
        raw_request=json.dumps({
            "apk_id": unity_apk.id,
            "version_name": unity_apk.version_name,
            "version_code": unity_apk.version_code,
            "package_name": unity_apk.package_name if hasattr(unity_apk, 'package_name') else "io.unitynodes.unityapp"
        }),
        targets=json.dumps([d.id for d in devices_with_fcm]),
        created_by=user.username,
        created_by_ip=client_ip,
        total_targets=len(devices_with_fcm),
        status="dispatching"
    )
    db.add(reinstall_exec)
    db.commit()
    db.refresh(reinstall_exec)
    
    installations = []
    now = datetime.now(timezone.utc)
    
    for device in devices_with_fcm:
        installation = ApkInstallation(
            device_id=device.id,
            apk_version_id=unity_apk.id,
            status="pending",
            initiated_at=now,
            initiated_by=user.username
        )
        db.add(installation)
        installations.append(installation)
    
    db.commit()
    
    for installation in installations:
        db.refresh(installation)
    
    install_correlations = {}
    launch_correlations = {}
    
    for device in devices_with_fcm:
        installation = next((inst for inst in installations if inst.device_id == device.id), None)
        if installation:
            install_correlation = str(uuid.uuid4())
            install_correlations[device.id] = {
                "correlation_id": install_correlation,
                "installation_id": installation.id
            }
            db.add(RemoteExecResult(
                exec_id=reinstall_exec.id,
                device_id=device.id,
                alias=device.alias,
                correlation_id=install_correlation,
                status="pending"
            ))
            
            launch_correlation = str(uuid.uuid4())
            launch_correlations[device.id] = launch_correlation
            db.add(RemoteExecResult(
                exec_id=reinstall_exec.id,
                device_id=device.id,
                alias=device.alias,
                correlation_id=launch_correlation,
                status="pending"
            ))
    
    db.commit()
    
    raw_request_data = json.loads(reinstall_exec.raw_request)
    raw_request_data["install_correlations"] = install_correlations
    raw_request_data["launch_correlations"] = launch_correlations
    reinstall_exec.raw_request = json.dumps(raw_request_data)
    db.commit()
    
    device_data = [{"id": d.id, "alias": d.alias, "fcm_token": d.fcm_token} for d in devices_with_fcm]
    installation_data = [{"id": inst.id, "device_id": inst.device_id} for inst in installations]
    
    asyncio.create_task(_run_reinstall_unity_fcm_dispatch(
        exec_id=reinstall_exec.id,
        apk_id=unity_apk.id,
        apk_version_name=unity_apk.version_name,
        apk_version_code=unity_apk.version_code,
        apk_package_name=unity_apk.package_name if hasattr(unity_apk, 'package_name') else "io.unitynodes.unityapp",
        device_data=device_data,
        installation_data=installation_data,
        install_correlations=install_correlations,
        launch_correlations=launch_correlations,
        username=user.username,
        client_ip=client_ip
    ))
    
    structured_logger.log_event(
        "apk.reinstall_unity_and_launch.started",
        exec_id=reinstall_exec.id,
        apk_id=unity_apk.id,
        version_name=unity_apk.version_name,
        user=user.username,
        total_targets=len(devices_with_fcm),
        client_ip=client_ip
    )
    
    return {
        "exec_id": reinstall_exec.id,
        "apk_id": unity_apk.id,
        "version_name": unity_apk.version_name,
        "version_code": unity_apk.version_code,
        "status": "dispatching",
        "stats": {
            "total_targets": len(devices_with_fcm),
            "sent": 0,
            "errors": 0
        }
    }

@app.get("/v1/apk/reinstall-unity-and-launch/{exec_id}/status")
async def get_reinstall_unity_and_launch_status(
    exec_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get combined status for a reinstall-unity-and-launch operation.
    Returns status of both installation and launch steps per device.
    """
    reinstall_exec = db.query(RemoteExec).filter(
        RemoteExec.id == exec_id,
        RemoteExec.mode == "reinstall_unity_and_launch"
    ).first()
    
    if not reinstall_exec:
        raise HTTPException(status_code=404, detail="Reinstall operation not found")
    
    raw_request = json.loads(reinstall_exec.raw_request) if reinstall_exec.raw_request else {}
    apk_id = raw_request.get("apk_id")
    package_name = raw_request.get("package_name", "io.unitynodes.unityapp")
    
    # Get all RemoteExecResult records for this exec
    results = db.query(RemoteExecResult).filter(
        RemoteExecResult.exec_id == reinstall_exec.id
    ).all()
    
    # Get ApkInstallation records
    installations = []
    if apk_id:
        installations = db.query(ApkInstallation).filter(
            ApkInstallation.apk_version_id == apk_id,
            ApkInstallation.device_id.in_([r.device_id for r in results])
        ).all()
    
    # Build per-device status
    device_statuses = {}
    install_correlations = raw_request.get("install_correlations", {})
    launch_correlations = raw_request.get("launch_correlations", {})
    
    # Initialize device statuses
    device_ids = set(r.device_id for r in results)
    for device_id in device_ids:
        device_statuses[device_id] = {
            "device_id": device_id,
            "installation": {"status": "pending"},
            "launch": {"status": "pending"},
            "overall_status": "pending"
        }
    
    # Update installation status from ApkInstallation records
    for installation in installations:
        if installation.device_id in device_statuses:
            install_status = "pending"
            if installation.status == "completed":
                install_status = "ok"
            elif installation.status == "failed":
                install_status = "failed"
            
            device_statuses[installation.device_id]["installation"] = {
                "status": install_status,
                "installation_id": installation.id,
                "error": installation.error_message
            }
    
    # Update launch status from RemoteExecResult records
    for result in results:
        device_id = result.device_id
        if device_id in device_statuses:
            # Check if this is a launch result (correlation_id matches launch_correlations)
            if device_id in launch_correlations and result.correlation_id == launch_correlations[device_id]:
                launch_status = "pending"
                if result.status == "OK":
                    launch_status = "ok"
                elif result.status in ["error", "FAILED"]:
                    launch_status = "failed"
                elif result.status == "timed_out":
                    launch_status = "timed_out"
                
                device_statuses[device_id]["launch"] = {
                    "status": launch_status,
                    "exit_code": result.exit_code,
                    "output": result.output_preview,
                    "error": result.error
                }
    
    # Compute overall status per device
    for device_id, status in device_statuses.items():
        install_status = status["installation"]["status"]
        launch_status = status["launch"]["status"]
        
        install_ok = install_status == "ok"
        launch_ok = launch_status == "ok"
        
        if install_ok and launch_ok:
            status["overall_status"] = "ok"
        elif install_status == "failed" or launch_status == "failed":
            status["overall_status"] = "failed"
        elif install_status == "pending" or launch_status == "pending":
            status["overall_status"] = "pending"
        else:
            status["overall_status"] = "failed"
    
    # Compute overall stats
    total = len(device_statuses)
    ok_count = sum(1 for s in device_statuses.values() if s["overall_status"] == "ok")
    failed_count = sum(1 for s in device_statuses.values() if s["overall_status"] == "failed")
    pending_count = total - ok_count - failed_count
    
    overall_status = "ok" if ok_count == total else ("failed" if failed_count > 0 else "pending")
    
    return {
        "exec_id": exec_id,
        "apk_id": apk_id,
        "package_name": package_name,
        "status": overall_status,
        "created_at": reinstall_exec.created_at.isoformat() + "Z",
        "created_by": reinstall_exec.created_by,
        "stats": {
            "total": total,
            "ok": ok_count,
            "failed": failed_count,
            "pending": pending_count
        },
        "devices": list(device_statuses.values())
    }

@app.get("/admin/apks")
async def get_admin_apks(
    enabled: Optional[bool] = Query(None),
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
    db: Session = Depends(get_db)
):
    """Get list of APK versions, optionally filtered by enabled status."""
    verify_admin_key(x_admin_key)

    query = db.query(ApkVersion)
    if enabled is not None:
        query = query.filter(ApkVersion.enabled == enabled)

    apks = query.order_by(ApkVersion.created_at.desc()).all()

    return [
        {
            "id": apk.id,
            "version_name": apk.version_name,
            "version_code": apk.version_code,
            "description": apk.description,
            "file_size": apk.file_size,
            "sha256_hash": apk.sha256_hash,
            "object_name": apk.object_name,
            "enabled": apk.enabled,
            "created_at": apk.created_at.isoformat() + "Z",
            "uploaded_by": apk.uploaded_by
        }
        for apk in apks
    ]

class UpdateApkVersionRequest(BaseModel):
    description: Optional[str] = None
    enabled: Optional[bool] = None

@app.patch("/admin/apks/{apk_id}")
async def update_apk_version(
    apk_id: int,
    request: UpdateApkVersionRequest,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
    db: Session = Depends(get_db)
):
    """Update an APK version's details (e.g., description, enabled status)."""
    verify_admin_key(x_admin_key)

    apk = db.query(ApkVersion).filter(ApkVersion.id == apk_id).first()
    if not apk:
        raise HTTPException(status_code=404, detail="APK version not found")

    if request.description is not None:
        apk.description = request.description
    if request.enabled is not None:
        apk.enabled = request.enabled

    db.commit()
    db.refresh(apk)

    structured_logger.log_event(
        "apk.update",
        admin_user="admin",
        apk_id=apk_id,
        enabled=apk.enabled,
        description=apk.description
    )

    return {
        "ok": True,
        "message": "APK version updated successfully",
        "apk": {
            "id": apk.id,
            "version_name": apk.version_name,
            "version_code": apk.version_code,
            "description": apk.description,
            "enabled": apk.enabled
        }
    }

@app.delete("/admin/apks/{apk_id}")
async def delete_apk_version(
    apk_id: int,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
    db: Session = Depends(get_db)
):
    """Delete an APK version and its associated files."""
    verify_admin_key(x_admin_key)

    apk = db.query(ApkVersion).filter(ApkVersion.id == apk_id).first()
    if not apk:
        raise HTTPException(status_code=404, detail="APK version not found")

    # Check if any devices are currently targeting this APK for deployment
    # This is a soft check - we don't prevent deletion but warn the admin
    active_deployments = db.query(ApkInstallation).filter(
        ApkInstallation.apk_version_id == apk_id,
        ApkInstallation.status.in_(["pending", "downloading", "installing"])
    ).count()

    if active_deployments > 0:
        structured_logger.log_event(
            "apk.delete.warning",
            level="WARN",
            admin_user="admin",
            apk_id=apk_id,
            active_deployments=active_deployments,
            message="Deleting an APK with active deployments. Consider disabling first."
        )
        # Proceed with deletion but log a warning

    # Delete from object storage first (if it exists)
    try:
        storage_service = get_storage_service()
        storage_service.delete_file(apk.object_name)
    except ObjectNotFoundError:
        # File not found in storage, but we can still delete the DB record
        structured_logger.log_event(
            "apk.delete.object_not_found",
            admin_user="admin",
            apk_id=apk_id,
            object_name=apk.object_name
        )
    except Exception as e:
        structured_logger.log_event(
            "apk.delete.object_error",
            level="ERROR",
            admin_user="admin",
            apk_id=apk_id,
            object_name=apk.object_name,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to delete APK file from storage: {str(e)}")

    # Delete associated ApkInstallation records
    db.query(ApkInstallation).filter(ApkInstallation.apk_version_id == apk_id).delete()

    # Delete the ApkVersion record
    db.delete(apk)
    db.commit()

    structured_logger.log_event(
        "apk.delete.success",
        admin_user="admin",
        apk_id=apk_id,
        version_name=apk.version_name
    )

    return {"ok": True, "message": f"APK version '{apk.version_name}' deleted successfully"}