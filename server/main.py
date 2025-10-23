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

from models import Device, User, Session as SessionModel, DeviceEvent, ApkVersion, ApkInstallation, BatteryWhitelist, PasswordResetToken, DeviceLastStatus, DeviceSelection, ApkDownloadEvent, MonitoringDefaults, get_db, init_db, SessionLocal
from schemas import (
    HeartbeatPayload, HeartbeatResponse, DeviceSummary, RegisterResponse,
    UserRegisterRequest, UserLoginRequest, UpdateDeviceAliasRequest, DeployApkRequest,
    UpdateDeviceSettingsRequest, CreateEnrollmentTokensRequest, CreateEnrollmentTokensResponse,
    EnrollmentTokenResponse, ListEnrollmentTokensResponse, EnrollmentTokenListItem,
    BatchDeleteEnrollmentTokensRequest, BatchDeleteEnrollmentTokensResponse,
    ActionResultRequest
)
from auth import (
    verify_device_token, hash_token, verify_token, generate_device_token, verify_admin_key,
    hash_password, verify_password, create_session, get_current_user, get_current_user_optional,
    compute_token_id, verify_enrollment_token, verify_admin_key_header, security
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

# Feature flags for gradual rollout
READ_FROM_LAST_STATUS = os.getenv("READ_FROM_LAST_STATUS", "false").lower() == "true"

# Helper function to ensure datetime is timezone-aware (assume UTC for naive datetimes)
def ensure_utc(dt: Optional[datetime]) -> datetime:
    """Convert naive datetime to timezone-aware UTC datetime. Returns current time if None."""
    if dt is None:
        return datetime.now(timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

app = FastAPI(title="NexMDM API")

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
    # Exempt APK upload endpoint from size limit (needs to handle 18MB+ APK files)
    if request.url.path == "/admin/apk/upload":
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
    print(f"[VALIDATION ERROR] {request.url.path}")
    
    # Skip body logging for multipart requests to avoid stream consumption errors
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        print(f"[VALIDATION ERROR] Body: <multipart/form-data - skipped to prevent stream error>")
    else:
        try:
            body = await request.body()
            print(f"[VALIDATION ERROR] Body preview: {str(body[:200])}")
        except RuntimeError as e:
            print(f"[VALIDATION ERROR] Body: <stream consumed - {e}>")
        except Exception as e:
            print(f"[VALIDATION ERROR] Body: <unable to read - {e}>")
    
    print(f"[VALIDATION ERROR] Errors: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

def validate_configuration():
    """
    Validate required environment variables and configuration on startup.
    Provides helpful error messages with links to documentation.
    """
    errors = []
    warnings = []
    
    # Check required secrets
    admin_key = os.getenv("ADMIN_KEY")
    if not admin_key:
        errors.append(
            "❌ ADMIN_KEY is not set!\n"
            "   Generate one with: openssl rand -base64 32\n"
            "   See DEPLOYMENT.md for detailed instructions."
        )
    elif len(admin_key) < 16:
        warnings.append(
            "⚠️  ADMIN_KEY is too short (minimum 16 characters recommended for security)"
        )
    
    # Check Firebase service account (prefer JSON secret over file for security)
    firebase_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
    firebase_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "")
    
    if not firebase_json and not firebase_path:
        errors.append(
            "❌ Firebase credentials not configured!\n"
            "   RECOMMENDED (secure for public forks):\n"
            "   1. Download your Firebase service account JSON from:\n"
            "      https://console.firebase.google.com → Project Settings → Service Accounts\n"
            "   2. Copy the ENTIRE JSON file contents\n"
            "   3. Create a Replit Secret named: FIREBASE_SERVICE_ACCOUNT_JSON\n"
            "   4. Paste the JSON content as the secret value\n"
            "\n"
            "   ALTERNATIVE (less secure - exposes credentials on public forks):\n"
            "   - Upload JSON file and set FIREBASE_SERVICE_ACCOUNT_PATH\n"
            "\n"
            "   See DEPLOYMENT.md for detailed instructions."
        )
    elif firebase_path and not firebase_json:
        # Using file path - warn about security
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
    elif firebase_json:
        # Validate it's valid JSON
        try:
            json.loads(firebase_json)
        except json.JSONDecodeError:
            errors.append(
                "❌ FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON!\n"
                "   Please paste the complete contents of your Firebase service account file."
            )
    
    # Check SERVER_URL (helpful for enrollment)
    server_url = os.getenv("SERVER_URL")
    if not server_url:
        warnings.append(
            "⚠️  SERVER_URL is not set (device enrollment will not work)\n"
            "   Set this to your Replit app URL (e.g., https://your-app.repl.co)\n"
            "   You can find this in your Webview window after starting the app."
        )
    
    # Check optional Discord webhook
    discord_webhook = os.getenv("DISCORD_WEBHOOK_URL")
    if not discord_webhook:
        warnings.append(
            "ℹ️  DISCORD_WEBHOOK_URL not set - alerts will only print to console\n"
            "   To enable Discord notifications, create a webhook and add it to Secrets."
        )
    
    # Print validation results
    print("\n" + "="*80)
    print("🔍 NexMDM Configuration Validation")
    print("="*80)
    
    if errors:
        print("\n🚨 CONFIGURATION ERRORS - Server cannot start properly:\n")
        for error in errors:
            print(error)
        print("\n📖 For setup instructions, see: DEPLOYMENT.md")
        print("   Or visit: https://github.com/yourusername/nexmdm#quick-start")
        print("\n" + "="*80 + "\n")
        raise RuntimeError("Configuration validation failed. Please fix the errors above.")
    
    if warnings:
        print("\n⚠️  Configuration Warnings:\n")
        for warning in warnings:
            print(warning)
        print()
    
    # Print success status
    print("✅ Required configuration validated successfully")
    
    # Print configuration summary
    print("\n📊 Configuration Summary:")
    print(f"   • Admin Key: {'✓ Set' if admin_key else '✗ Missing'}")
    
    if firebase_json:
        print(f"   • Firebase: ✓ JSON Secret (secure)")
    elif firebase_path and os.path.exists(firebase_path):
        print(f"   • Firebase: ✓ File Path (⚠️  less secure) - {firebase_path}")
    else:
        print(f"   • Firebase: ✗ Missing")
    
    print(f"   • Server URL: {server_url if server_url else '⚠️  Not set'}")
    print(f"   • Discord Alerts: {'✓ Enabled' if discord_webhook else 'ℹ️  Disabled (console only)'}")
    print(f"   • Database: {os.getenv('DATABASE_URL', 'sqlite:///./data.db')[:50]}...")
    print("="*80 + "\n")

@app.on_event("startup")
async def startup_event():
    """
    Initialize application dependencies and background tasks.
    Wraps background task startup in defensive error handling to prevent
    silent crashes from unhandled exceptions in async loops.
    """
    validate_configuration()
    init_db()
    migrate_database()
    
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

@app.on_event("shutdown")
async def shutdown_event():
    await alert_scheduler.stop()
    await background_tasks.stop()

backend_start_time = datetime.now(timezone.utc)

def migrate_database():
    """Add missing columns to existing database tables"""
    from sqlalchemy import text
    from models import engine
    
    with engine.connect() as conn:
        try:
            columns_to_add = [
                ("app_version", "VARCHAR"),
                ("model", "VARCHAR"),
                ("manufacturer", "VARCHAR"),
                ("android_version", "VARCHAR"),
                ("sdk_int", "INTEGER"),
                ("build_id", "VARCHAR"),
                ("is_device_owner", "BOOLEAN"),
            ]
            
            for column_name, column_type in columns_to_add:
                try:
                    conn.execute(text(f"ALTER TABLE devices ADD COLUMN {column_name} {column_type}"))
                    conn.commit()
                    print(f"[MIGRATION] Added column: {column_name}")
                except Exception as e:
                    if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                        conn.rollback()
                    else:
                        raise
        except Exception as e:
            print(f"[MIGRATION] Error: {e}")

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
            base_url = os.getenv("BASE_URL", "http://localhost:3000")
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
    """Register a device using admin key authentication"""
    from models import EnrollmentToken, EnrollmentEvent
    
    alias = payload.get("alias")
    hardware_id = payload.get("hardware_id", "unknown")
    
    if not alias:
        raise HTTPException(status_code=422, detail="alias is required")
    
    structured_logger.log_event(
        "register.request",
        alias=alias,
        auth_method="admin_key",
        route="/v1/register"
    )
    
    try:
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
            result="success"
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
    
    # Check for status changes (online/offline)
    was_offline = False
    offline_seconds = 0
    if device.last_seen:
        offline_seconds = (datetime.now(timezone.utc) - ensure_utc(device.last_seen)).total_seconds()
        heartbeat_interval = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "120"))
        was_offline = offline_seconds > heartbeat_interval * 2
    
    if was_offline:
        log_device_event(db, device.id, "status_change", {
            "from": "offline",
            "to": "online",
            "offline_duration_seconds": int(offline_seconds)
        })
    
    # Check for battery level changes
    prev_battery = prev_status.get("battery", {}).get("pct")
    new_battery = payload.battery.pct if payload.battery else None
    if prev_battery is not None and new_battery is not None:
        if prev_battery >= 20 and new_battery < 20:
            log_device_event(db, device.id, "battery_low", {"level": new_battery})
        elif prev_battery >= 15 and new_battery < 15:
            log_device_event(db, device.id, "battery_critical", {"level": new_battery})
    
    # Check for network changes
    prev_network = prev_status.get("network", {}).get("transport")
    new_network = payload.network.transport if payload.network else None
    if prev_network and new_network and prev_network != new_network:
        log_device_event(db, device.id, "network_change", {
            "from": prev_network,
            "to": new_network,
            "ssid": payload.network.ssid if new_network == "wifi" else None,
            "carrier": payload.network.carrier if new_network == "cellular" else None
        })
    
    device.last_seen = datetime.now(timezone.utc)
    device.last_status = json.dumps(payload.dict())
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
    
    unity_running = None
    if device.monitored_package and device.monitored_package in payload.app_versions:
        app_info = payload.app_versions.get(device.monitored_package)
        if app_info and app_info.installed:
            if device.monitored_package == "org.zwanoo.android.speedtest":
                has_notif = payload.speedtest_running_signals.has_service_notification
                fg_seconds = payload.speedtest_running_signals.foreground_recent_seconds
                unity_running = (has_notif or (fg_seconds is not None and fg_seconds < 60))
    
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
        'unity_pkg_version': payload.app_version,
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
            log_device_event(db, device.id, "ping_response", {"latency_ms": latency_ms})
            # Clear ping state after successful response
            device.ping_request_id = None
    
    # Service monitoring evaluator: Determine if monitored service is up/down
    # Get effective monitoring settings (device or global defaults)
    from monitoring_helpers import get_effective_monitoring_settings
    monitoring_settings = get_effective_monitoring_settings(db, device)
    
    service_up = None
    monitored_foreground_recent_s = None
    
    if monitoring_settings["enabled"] and monitoring_settings["package"]:
        # Get foreground recency from new unified field (for any package)
        monitored_foreground_recent_s = payload.monitored_foreground_recent_s
        
        # Fallback to Speedtest-specific signals if monitored_foreground_recent_s not provided
        if monitored_foreground_recent_s is None and monitoring_settings["package"] == "org.zwanoo.android.speedtest":
            fg_seconds = payload.speedtest_running_signals.foreground_recent_seconds
            if fg_seconds is not None:
                monitored_foreground_recent_s = fg_seconds
        
        # Evaluate service status
        if monitored_foreground_recent_s is not None:
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
            # If foreground data not available, service status is unknown
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
    
    # Auto-relaunch logic: Check if monitored app is down and auto-relaunch is enabled
    print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: auto_relaunch_enabled={device.auto_relaunch_enabled}, monitored_package={device.monitored_package}")
    print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: app_versions keys in payload: {list(payload.app_versions.keys())}")
    
    if device.auto_relaunch_enabled and device.monitored_package:
        # Android app now sends full package names as keys (e.g., org.zwanoo.android.speedtest)
        # No mapping needed - direct 1:1 lookup
        app_info = payload.app_versions.get(device.monitored_package)
        is_app_running = True  # Default to running to prevent spam loops
        
        print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: app_info={app_info}, installed={app_info.installed if app_info else 'N/A'}")
        
        # Check if app is installed
        if app_info and app_info.installed:
            # For Speedtest specifically, check running signals
            if device.monitored_package == "org.zwanoo.android.speedtest":
                has_notif = payload.speedtest_running_signals.has_service_notification
                fg_seconds = payload.speedtest_running_signals.foreground_recent_seconds
                is_app_running = (
                    has_notif or
                    (fg_seconds is not None and fg_seconds < 60)
                )
                print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: Speedtest signals - has_service_notification={has_notif}, foreground_recent_seconds={fg_seconds}, is_app_running={is_app_running}")
            else:
                # For other apps (Unity, etc), assume running to prevent endless relaunch loops
                # The Android app currently only sends foreground detection for Speedtest
                # To enable auto-relaunch for other apps, the Android app needs to send
                # foreground_recent_seconds for the monitored package
                is_app_running = True  # Conservative: assume running unless proven otherwise
                print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: Non-Speedtest app, defaulting is_app_running=True")
        else:
            # App not installed - don't try to relaunch
            is_app_running = True  # Prevent relaunch loop for uninstalled apps
            print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: App not installed, defaulting is_app_running=True")
        
        # If app is not running, trigger FCM relaunch
        print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: Final check - is_app_running={is_app_running}, fcm_token={'present' if device.fcm_token else 'missing'}")
        
        if not is_app_running and device.fcm_token:
            try:
                print(f"[AUTO-RELAUNCH] {device.alias}: {device.monitored_package} is down, sending relaunch command")
                asyncio.create_task(send_fcm_launch_app(device.fcm_token, device.monitored_package, device.id))
                log_device_event(db, device.id, "auto_relaunch_triggered", {
                    "package": device.monitored_package
                })
            except Exception as e:
                print(f"[AUTO-RELAUNCH] Failed to send relaunch for {device.alias}: {e}")
    else:
        if not device.auto_relaunch_enabled:
            print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: Auto-relaunch is DISABLED")
        if not device.monitored_package:
            print(f"[AUTO-RELAUNCH-DEBUG] {device.alias}: No monitored package configured")
    
    db.commit()
    
    await manager.broadcast({
        "type": "device_update",
        "device_id": device.id
    })
    
    return HeartbeatResponse(ok=True)

@app.post("/v1/action-result")
async def action_result(
    payload: ActionResultRequest,
    device: Device = Depends(verify_device_token),
    db: Session = Depends(get_db)
):
    """
    Receive action result from device after executing FCM command.
    Validates device_id matches authenticated device and updates dispatch record.
    """
    if payload.device_id != device.id:
        raise HTTPException(status_code=403, detail="device_id mismatch")
    
    from models import FcmDispatch
    
    dispatch = db.query(FcmDispatch).filter(
        FcmDispatch.request_id == payload.request_id
    ).first()
    
    if not dispatch:
        structured_logger.log_event(
            "result.unknown",
            level="WARN",
            request_id=payload.request_id,
            device_id=payload.device_id,
            action=payload.action,
            outcome=payload.outcome
        )
        raise HTTPException(status_code=404, detail="request_id not found")
    
    if dispatch.completed_at:
        structured_logger.log_event(
            "result.duplicate",
            request_id=payload.request_id,
            device_id=payload.device_id,
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
        device_id=payload.device_id,
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
    total_devices = db.query(func.count(Device.id)).scalar()
    
    heartbeat_interval = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "300"))
    offline_threshold = datetime.now(timezone.utc) - timedelta(seconds=heartbeat_interval * 3)
    
    # Optimized: Count online devices with a single query
    online_count = db.query(func.count(Device.id)).filter(
        Device.last_seen >= offline_threshold
    ).scalar() or 0
    
    offline_count = total_devices - online_count
    
    # For low battery, we still need to parse JSON, but only fetch last_status field
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
    
    return {
        "total": total_devices,
        "online": online_count,
        "offline": offline_count,
        "low_battery": low_battery_count
    }

@app.get("/v1/devices")
async def list_devices(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    total_count = db.query(func.count(Device.id)).scalar()
    
    offset = (page - 1) * limit
    devices = db.query(Device).order_by(Device.last_seen.desc()).offset(offset).limit(limit).all()
    
    # Batch fetch device statuses if using fast reads
    device_statuses = {}
    if READ_FROM_LAST_STATUS:
        device_ids = [d.id for d in devices]
        device_statuses = fast_reads.get_all_device_statuses_fast(db, device_ids)
    
    result = []
    heartbeat_interval = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "300"))
    
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
    
    return {
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
    
    return {"ok": True, "message": f"Device {device_alias} deleted successfully"}

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
    
    return result

@app.post("/v1/devices/bulk-delete")
async def bulk_delete_devices_legacy(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Legacy bulk delete endpoint (deprecated - use /admin/devices/bulk-delete).
    """
    body = await request.json()
    device_ids = body.get("device_ids", [])
    
    if not device_ids:
        raise HTTPException(status_code=400, detail="No device IDs provided")
    
    result = bulk_delete.bulk_delete_devices(
        db=db,
        device_ids=device_ids,
        purge_history=False,  # Legacy endpoint doesn't purge history
        admin_user=user.username if user else None
    )
    
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
        if request.monitored_threshold_min < 1 or request.monitored_threshold_min > 120:
            raise HTTPException(status_code=400, detail="Threshold must be between 1 and 120 minutes")
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
        if request.monitored_threshold_min < 1 or request.monitored_threshold_min > 120:
            raise HTTPException(status_code=400, detail="Threshold must be between 1 and 120 minutes")
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

@app.post("/v1/devices/settings/bulk")
async def update_all_devices_settings(
    request: UpdateDeviceSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update auto-relaunch settings for all devices"""
    if request.auto_relaunch_enabled is None:
        raise HTTPException(status_code=400, detail="auto_relaunch_enabled is required")
    
    devices = db.query(Device).all()
    updated_count = 0
    
    for device in devices:
        device.auto_relaunch_enabled = request.auto_relaunch_enabled
        log_device_event(db, device.id, "settings_updated", {
            "auto_relaunch_enabled": device.auto_relaunch_enabled,
            "bulk_update": True
        })
        updated_count += 1
    
    db.commit()
    
    return {
        "ok": True,
        "message": f"Auto-relaunch {'enabled' if request.auto_relaunch_enabled else 'disabled'} for {updated_count} devices",
        "updated_count": updated_count
    }

@app.post("/v1/test-alert")
async def send_test_alert():
    from discord_webhook import discord_client
    from alert_config import alert_config
    
    if not alert_config.DISCORD_WEBHOOK_URL:
        raise HTTPException(status_code=400, detail="Discord webhook not configured")
    
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

@app.post("/v1/devices/{device_id}/ping")
async def ping_device(
    device_id: str,
    x_admin: str = Header(None),
    db: Session = Depends(get_db)
):
    if not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=401, detail="Admin key required")
    
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if not device.fcm_token:
        raise HTTPException(status_code=400, detail="Device does not have FCM token registered")
    
    if device.last_ping_sent:
        time_since_last_ping = (datetime.now(timezone.utc) - ensure_utc(device.last_ping_sent)).total_seconds()
        if time_since_last_ping < 120:
            raise HTTPException(
                status_code=429, 
                detail=f"Rate limit: Please wait {int(120 - time_since_last_ping)} seconds before pinging again"
            )
    
    import uuid
    request_id = str(uuid.uuid4())
    
    structured_logger.log_event(
        "dispatch.request",
        request_id=request_id,
        device_id=device_id,
        action="ping"
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
    hmac_signature = compute_hmac_signature(request_id, device_id, "ping", timestamp)
    
    message = {
        "message": {
            "token": device.fcm_token,
            "data": {
                "action": "ping",
                "request_id": request_id,
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
                    request_id=request_id,
                    device_id=device_id,
                    action="ping",
                    fcm_http_code=response.status_code,
                    fcm_status="failed",
                    latency_ms=int(latency_ms)
                )
                
                return {
                    "ok": False,
                    "error": f"FCM request failed with status {response.status_code}",
                    "fcm_response": fcm_result
                }
            
            fcm_result = response.json()
            
            structured_logger.log_event(
                "dispatch.sent",
                request_id=request_id,
                device_id=device_id,
                action="ping",
                fcm_http_code=response.status_code,
                fcm_status="success",
                latency_ms=int(latency_ms)
            )
            
            metrics.observe_histogram("fcm_dispatch_latency_ms", latency_ms, {
                "action": "ping"
            })
            
            device.last_ping_sent = datetime.now(timezone.utc)
            device.ping_request_id = request_id
            db.commit()
            
            log_device_event(db, device.id, "ping_sent", {"request_id": request_id})
            
            return {
                "ok": True,
                "request_id": request_id,
                "message": "Ping sent successfully",
                "fcm_response": fcm_result
            }
            
        except httpx.TimeoutException:
            latency_ms = (time.time() - fcm_start_time) * 1000
            structured_logger.log_event(
                "dispatch.fail",
                level="ERROR",
                request_id=request_id,
                device_id=device_id,
                action="ping",
                fcm_http_code=504,
                fcm_status="timeout",
                latency_ms=int(latency_ms)
            )
            raise HTTPException(status_code=504, detail="FCM request timed out")
        except Exception as e:
            latency_ms = (time.time() - fcm_start_time) * 1000
            structured_logger.log_event(
                "dispatch.fail",
                level="ERROR",
                request_id=request_id,
                device_id=device_id,
                action="ping",
                fcm_http_code=500,
                fcm_status="error",
                error=str(e),
                latency_ms=int(latency_ms)
            )
            raise HTTPException(status_code=500, detail=f"Failed to send FCM message: {str(e)}")

@app.post("/v1/devices/{device_id}/ring")
async def ring_device(
    device_id: str,
    duration_seconds: int = 30,
    x_admin: str = Header(None),
    db: Session = Depends(get_db)
):
    if not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=401, detail="Admin key required")
    
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if not device.fcm_token:
        raise HTTPException(status_code=400, detail="Device does not have FCM token registered")
    
    if duration_seconds < 5 or duration_seconds > 120:
        raise HTTPException(status_code=400, detail="Duration must be between 5 and 120 seconds")
    
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
                "action": "ring",
                "duration": str(duration_seconds)
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
            
            log_device_event(db, device.id, "ring_sent", {"duration": duration_seconds})
            
            return {
                "ok": True,
                "message": f"Ring command sent to {device.alias}",
                "duration": duration_seconds,
                "fcm_response": fcm_result
            }
            
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="FCM request timed out")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to send FCM message: {str(e)}")

@app.post("/v1/devices/{device_id}/grant-permissions")
async def grant_device_permissions(
    device_id: str,
    x_admin: str = Header(None),
    db: Session = Depends(get_db)
):
    if not verify_admin_key(x_admin or ""):
        raise HTTPException(status_code=401, detail="Admin key required")
    
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if not device.fcm_token:
        raise HTTPException(status_code=400, detail="Device does not have FCM token registered")
    
    if not device.is_device_owner:
        raise HTTPException(
            status_code=400, 
            detail="Device is not enrolled as Device Owner. Cannot grant permissions remotely."
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
    
    message = {
        "message": {
            "token": device.fcm_token,
            "data": {
                "action": "grant_permissions"
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
            
            log_device_event(db, device.id, "permission_grant_sent", {})
            
            return {
                "ok": True,
                "message": f"Permission grant command sent to {device.alias}",
                "fcm_response": fcm_result
            }
            
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="FCM request timed out")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to send FCM message: {str(e)}")

@app.post("/v1/devices/{device_id}/list-packages")
async def list_device_packages(
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
                results.append({"device_id": device_id, "ok": False, "error": "Device not found"})
                continue
            
            if not device.fcm_token:
                results.append({"device_id": device_id, "ok": False, "error": "No FCM token"})
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
                        "ok": False,
                        "error": f"FCM error: {response.status_code}"
                    })
            except Exception as e:
                results.append({
                    "device_id": device_id,
                    "ok": False,
                    "error": str(e)
                })
    
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
                        "message": "Launch command sent successfully"
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

@app.get("/v1/enrollment-qr-payload")
async def get_enrollment_qr_payload(alias: str):
    if not alias or not alias.strip():
        raise HTTPException(status_code=400, detail="Alias is required")
    
    server_url = os.getenv("SERVER_URL", "")
    if not server_url:
        server_url = "http://localhost:8000"
    
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key:
        raise HTTPException(status_code=500, detail="Admin key not configured")
    
    return {
        "server_url": server_url,
        "admin_key": admin_key,
        "alias": alias.strip()
    }

@app.post("/v1/enroll-tokens", response_model=CreateEnrollmentTokensResponse)
async def create_enrollment_tokens(
    request: CreateEnrollmentTokensRequest,
    req: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate enrollment tokens for batch device provisioning"""
    from models import EnrollmentToken, EnrollmentEvent
    import secrets
    import hashlib
    from datetime import timedelta
    
    if not request.aliases or len(request.aliases) == 0:
        raise HTTPException(status_code=400, detail="At least one alias is required")
    
    if len(request.aliases) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 tokens per request")
    
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=request.expires_in_sec)
    tokens_response = []
    
    for alias in request.aliases:
        alias = alias.strip()
        if not alias:
            continue
        
        raw_token = secrets.token_urlsafe(32)
        token_id = compute_token_id(raw_token)
        token_hash = hash_token(raw_token)
        
        enrollment_token = EnrollmentToken(
            token_id=token_id,
            alias=alias,
            token_hash=token_hash,
            issued_by=current_user.username,
            expires_at=expires_at,
            uses_allowed=request.uses_allowed,
            uses_consumed=0,
            note=request.note,
            status='active',
            scope='register'
        )
        
        db.add(enrollment_token)
        
        event = EnrollmentEvent(
            event_type='token.create',
            token_id=token_id,
            alias=alias,
            ip_address=req.client.host if req.client else None,
            details=json.dumps({
                "issued_by": current_user.username,
                "expires_in_sec": request.expires_in_sec,
                "uses_allowed": request.uses_allowed,
                "note": request.note
            })
        )
        db.add(event)
        
        structured_logger.log_event(
            "sec.token.create",
            token_id=token_id,
            alias=alias,
            issued_by=current_user.username,
            expires_in_sec=request.expires_in_sec,
            uses_allowed=request.uses_allowed
        )
        
        tokens_response.append(EnrollmentTokenResponse(
            token_id=token_id,
            alias=alias,
            token=raw_token,
            expires_at=expires_at
        ))
    
    db.commit()
    
    print(f"[ENROLL-TOKENS] Generated {len(tokens_response)} tokens for user {current_user.username}")
    
    return CreateEnrollmentTokensResponse(tokens=tokens_response)

@app.get("/v1/enroll-tokens", response_model=ListEnrollmentTokensResponse)
async def list_enrollment_tokens(
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List enrollment tokens with optional filtering"""
    from models import EnrollmentToken
    
    query = db.query(EnrollmentToken)
    
    if status:
        query = query.filter(EnrollmentToken.status == status)
    
    now = datetime.now(timezone.utc)
    
    tokens = query.order_by(EnrollmentToken.issued_at.desc()).limit(limit).all()
    
    token_items = []
    for token in tokens:
        current_status = token.status
        if token.status == 'active':
            token_expires_at = token.expires_at if token.expires_at.tzinfo else token.expires_at.replace(tzinfo=timezone.utc)
            if token_expires_at < now:
                token.status = 'expired'
                current_status = 'expired'
                structured_logger.log_event(
                    "sec.token.expired",
                    token_id=token.token_id,
                    alias=token.alias,
                    expired_at=token.expires_at.isoformat()
                )
            elif token.uses_consumed >= token.uses_allowed:
                token.status = 'exhausted'
                current_status = 'exhausted'
        
        token_items.append(EnrollmentTokenListItem(
            token_id=token.token_id,
            alias=token.alias,
            token_last4=token.token_hash[-4:],
            status=current_status,
            expires_at=token.expires_at,
            uses_allowed=token.uses_allowed,
            uses_consumed=token.uses_consumed,
            note=token.note,
            issued_at=token.issued_at,
            issued_by=token.issued_by
        ))
    
    db.commit()
    
    return ListEnrollmentTokensResponse(
        tokens=token_items,
        total=len(token_items)
    )

@app.delete("/v1/enroll-tokens/{token_id}")
async def revoke_enrollment_token(
    token_id: str,
    req: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Revoke an enrollment token"""
    from models import EnrollmentToken, EnrollmentEvent
    
    token = db.query(EnrollmentToken).filter(EnrollmentToken.token_id == token_id).first()
    
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    now = datetime.now(timezone.utc)
    
    if token.status == 'revoked':
        return {
            "ok": True,
            "message": "Token already revoked",
            "token_id": token_id,
            "status": "revoked"
        }
    
    if token.status == 'exhausted':
        raise HTTPException(
            status_code=409,
            detail="Cannot revoke exhausted token"
        )
    
    if token.status == 'expired' or token.expires_at < now:
        raise HTTPException(
            status_code=409,
            detail="Cannot revoke expired token"
        )
    
    token.status = 'revoked'
    db.commit()
    
    event = EnrollmentEvent(
        event_type='token.revoke',
        token_id=token_id,
        alias=token.alias,
        ip_address=req.client.host if req.client else None,
        details=json.dumps({
            "revoked_by": current_user.username
        })
    )
    db.add(event)
    db.commit()
    
    structured_logger.log_event(
        "sec.token.revoke",
        token_id=token_id,
        alias=token.alias,
        revoked_by=current_user.username
    )
    
    return {
        "ok": True,
        "message": "Token revoked successfully",
        "token_id": token_id,
        "status": "revoked"
    }

@app.post("/v1/enroll-tokens/batch-delete", response_model=BatchDeleteEnrollmentTokensResponse)
async def batch_delete_enrollment_tokens(
    request: BatchDeleteEnrollmentTokensRequest,
    req: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete multiple enrollment tokens in batch"""
    from models import EnrollmentToken, EnrollmentEvent
    
    if not request.token_ids or len(request.token_ids) == 0:
        raise HTTPException(status_code=400, detail="token_ids is required and must not be empty")
    
    if len(request.token_ids) > 500:
        raise HTTPException(status_code=400, detail="Cannot delete more than 500 tokens at once")
    
    deleted_count = 0
    failed_count = 0
    errors = []
    
    for token_id in request.token_ids:
        try:
            token = db.query(EnrollmentToken).filter(EnrollmentToken.token_id == token_id).first()
            
            if not token:
                failed_count += 1
                errors.append({
                    "token_id": token_id,
                    "error": "Token not found"
                })
                continue
            
            db.delete(token)
            
            event = EnrollmentEvent(
                event_type='token.delete',
                token_id=token_id,
                alias=token.alias,
                ip_address=req.client.host if req.client else None,
                details=json.dumps({
                    "deleted_by": current_user.username,
                    "status": token.status
                })
            )
            db.add(event)
            
            structured_logger.log_event(
                "sec.token.delete",
                token_id=token_id,
                alias=token.alias,
                deleted_by=current_user.username
            )
            
            deleted_count += 1
            
        except Exception as e:
            failed_count += 1
            errors.append({
                "token_id": token_id,
                "error": str(e)
            })
            continue
    
    db.commit()
    
    print(f"[BATCH-DELETE-TOKENS] Deleted {deleted_count} tokens, {failed_count} failed by user {current_user.username}")
    
    return BatchDeleteEnrollmentTokensResponse(
        deleted_count=deleted_count,
        failed_count=failed_count,
        errors=errors
    )

@app.get("/v1/scripts/enroll.cmd")
async def get_windows_enroll_script(
    alias: str = Query(...),
    token_id: str = Query(...),
    raw_token: Optional[str] = Query(None),
    agent_pkg: str = Query("com.nexmdm"),
    unity_pkg: str = Query("org.zwanoo.android.speedtest"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate zero-tap Windows enrollment script with enhanced debugging"""
    from models import EnrollmentToken, EnrollmentEvent
    
    # Validate enrollment token
    token = db.query(EnrollmentToken).filter(EnrollmentToken.token_id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    if token.status != 'active':
        raise HTTPException(status_code=400, detail=f"Token is {token.status}")
    
    # Get server configuration
    server_url = os.getenv("SERVER_URL", "")
    if not server_url:
        raise HTTPException(status_code=500, detail="SERVER_URL environment variable not set")
    
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY environment variable not set")
    
    # Log script generation event
    event = EnrollmentEvent(
        event_type='script.render',
        token_id=token_id,
        alias=alias,
        details=json.dumps({"platform": "windows", "agent_pkg": agent_pkg, "unity_pkg": unity_pkg})
    )
    db.add(event)
    db.commit()
    
    # Generate script with enhanced debugging and fail-fast behavior
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
set APK_PATH=%TEMP%\\unityndm-agent.apk
set DEVICE_ALIAS={alias}

echo ================================================
echo UnityMDM Zero-Tap Enrollment
echo Device: !ALIAS!
echo ================================================
echo.

echo [Step 1/7] Wait for device...
adb wait-for-device >nul 2>&1
if errorlevel 1 (
    echo ❌ No device found
    echo    Fix: Check USB cable, ensure USB debugging enabled
    echo    Run: adb devices -l
    set EXITCODE=2
    goto :end
)
echo ✅ Device connected
echo.

echo [Step 2/7] Download latest APK...
curl -L -H "X-Admin-Key: !ADMIN_KEY!" "!BASE_URL!/v1/apk/download/latest" -o "!APK_PATH!" >nul 2>&1
if errorlevel 1 (
    echo ❌ Download failed
    echo    Fix: Check network, verify SERVER_URL: !BASE_URL!
    echo    Debug: curl -v "!BASE_URL!/v1/apk/download/latest"
    set EXITCODE=3
    goto :end
)
if not exist "!APK_PATH!" (
    echo ❌ APK missing at !APK_PATH!
    echo    Fix: Check temp directory permissions
    set EXITCODE=3
    goto :end
)
echo ✅ APK downloaded
echo.

echo [Step 3/7] Install APK...
adb install -r -g "!APK_PATH!" >nul 2>&1
if errorlevel 1 (
    echo    Retry: Uninstalling existing version...
    adb uninstall !PKG! >nul 2>&1
    adb install -r -g -t "!APK_PATH!" >nul 2>&1
    if errorlevel 1 (
        echo ❌ Install failed
        echo    Fix: Check adb install errors
        echo    Debug: adb install -r -g "!APK_PATH!"
        set EXITCODE=4
        goto :end
    )
)
echo ✅ APK installed
echo.

echo [Step 4/7] Set Device Owner...
REM Check if device is provisioned
for /f "tokens=*" %%A in ('adb shell settings get secure user_setup_complete 2^>nul') do set SETUP=%%A
set SETUP=!SETUP:~0,1!

if "!SETUP!"=="1" (
    echo    WARN: Device appears provisioned (user_setup_complete=1)
)

adb shell dpm set-device-owner !PKG!/!RECEIVER! >nul 2>&1
if errorlevel 1 (
    echo ❌ Device Owner setup failed
    echo    Fix: Factory reset device or use QR provisioning
    echo    Debug: adb shell dpm get-device-owner
    echo    Note: Device must be unprovisioned (fresh or reset)
    set EXITCODE=5
    goto :end
)

REM Verify Device Owner
adb shell dumpsys device_policy | findstr /C:"!PKG!" >nul 2>&1
if errorlevel 1 (
    echo ❌ Device Owner verification failed
    echo    Debug: adb shell dumpsys device_policy
    set EXITCODE=6
    goto :end
)
echo ✅ Device Owner confirmed
echo.

echo [Step 5/7] Grant core permissions...
adb shell pm grant !PKG! android.permission.POST_NOTIFICATIONS >nul 2>&1
adb shell pm grant !PKG! android.permission.ACCESS_FINE_LOCATION >nul 2>&1
adb shell pm grant !PKG! android.permission.CAMERA >nul 2>&1
adb shell appops set !PKG! RUN_ANY_IN_BACKGROUND allow >nul 2>&1
adb shell appops set !PKG! GET_USAGE_STATS allow >nul 2>&1
adb shell dumpsys deviceidle whitelist +!PKG! >nul 2>&1
echo ✅ Permissions granted
echo.

echo [Step 6/7] Launch and auto-enroll...
REM Launch app
adb shell monkey -p !PKG! -c android.intent.category.LAUNCHER 1 >nul 2>&1
timeout /t 2 /nobreak >nul

REM Send configuration broadcast with admin_key instead of token
adb shell am broadcast -a com.nexmdm.CONFIGURE -n !PKG!/.ConfigReceiver --es server_url "!BASE_URL!" --es admin_key "!ADMIN_KEY!" --es alias "!DEVICE_ALIAS!" >nul 2>&1
if errorlevel 1 (
    echo ❌ Configuration broadcast failed
    echo    Debug: Check ConfigReceiver in manifest
    echo    Fix: Verify receiver is exported
    set EXITCODE=7
    goto :end
)
echo ✅ Auto-enrollment initiated
echo.

echo [Step 7/7] Verify enrollment...
timeout /t 3 /nobreak >nul
adb shell pidof !PKG! >nul 2>&1
if errorlevel 1 (
    echo ❌ Service not running
    echo    Debug: adb logcat -d ^| findstr !PKG!
    set EXITCODE=8
    goto :end
)
echo ✅ Service running
echo.

echo ================================================
echo ✅✅✅ ENROLLMENT COMPLETE ✅✅✅
echo ================================================
echo 📱 Device "!ALIAS!" enrolled successfully!
echo 🔍 Check dashboard within 60 seconds
echo ================================================
set EXITCODE=0

:end
echo.
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
    token_id: str = Query(...),
    raw_token: Optional[str] = Query(None),
    agent_pkg: str = Query("com.nexmdm"),
    unity_pkg: str = Query("org.zwanoo.android.speedtest"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate zero-tap Bash enrollment script with enhanced debugging"""
    from models import EnrollmentToken, EnrollmentEvent
    
    # Validate enrollment token
    token = db.query(EnrollmentToken).filter(EnrollmentToken.token_id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    if token.status != 'active':
        raise HTTPException(status_code=400, detail=f"Token is {token.status}")
    
    # Get server configuration
    server_url = os.getenv("SERVER_URL", "")
    if not server_url:
        raise HTTPException(status_code=500, detail="SERVER_URL environment variable not set")
    
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY environment variable not set")
    
    # Log script generation event
    event = EnrollmentEvent(
        event_type='script.render',
        token_id=token_id,
        alias=alias,
        details=json.dumps({"platform": "bash", "agent_pkg": agent_pkg, "unity_pkg": unity_pkg})
    )
    db.add(event)
    db.commit()
    
    # Generate script with enhanced debugging and fail-fast behavior
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
APK_PATH="/tmp/unitymdm-agent.apk"
DEVICE_ALIAS="{alias}"

echo "================================================"
echo "UnityMDM Zero-Tap Enrollment"
echo "Device: $ALIAS"
echo "================================================"
echo

echo "[Step 1/7] Wait for device..."
if ! adb wait-for-device 2>/dev/null; then
    echo "❌ No device found"
    echo "   Fix: Check USB cable, ensure USB debugging enabled"
    echo "   Run: adb devices -l"
    exit 2
fi
echo "✅ Device connected"
echo

echo "[Step 2/7] Download latest APK..."
if ! curl -L -H "X-Admin-Key: $ADMIN_KEY" "$BASE_URL/v1/apk/download/latest" -o "$APK_PATH" 2>/dev/null; then
    echo "❌ Download failed"
    echo "   Fix: Check network, verify SERVER_URL: $BASE_URL"
    echo "   Debug: curl -v '$BASE_URL/v1/apk/download/latest'"
    exit 3
fi
if [ ! -f "$APK_PATH" ]; then
    echo "❌ APK missing at $APK_PATH"
    echo "   Fix: Check temp directory permissions"
    exit 3
fi
echo "✅ APK downloaded"
echo

echo "[Step 3/7] Install APK..."
if ! adb install -r -g "$APK_PATH" 2>/dev/null; then
    echo "   Retry: Uninstalling existing version..."
    adb uninstall "$PKG" 2>/dev/null || true
    if ! adb install -r -g -t "$APK_PATH" 2>/dev/null; then
        echo "❌ Install failed"
        echo "   Fix: Check adb install errors"
        echo "   Debug: adb install -r -g '$APK_PATH'"
        exit 4
    fi
fi
echo "✅ APK installed"
echo

echo "[Step 4/7] Set Device Owner..."
# Check if device is provisioned
SETUP=$(adb shell settings get secure user_setup_complete 2>/dev/null | tr -d '\\r\\n')

if [ "$SETUP" = "1" ]; then
    echo "   WARN: Device appears provisioned (user_setup_complete=1)"
fi

if ! adb shell dpm set-device-owner "$PKG/$RECEIVER" 2>/dev/null; then
    echo "❌ Device Owner setup failed"
    echo "   Fix: Factory reset device or use QR provisioning"
    echo "   Debug: adb shell dpm get-device-owner"
    echo "   Note: Device must be unprovisioned (fresh or reset)"
    exit 5
fi

# Verify Device Owner
if ! adb shell dumpsys device_policy 2>/dev/null | grep -q "$PKG"; then
    echo "❌ Device Owner verification failed"
    echo "   Debug: adb shell dumpsys device_policy"
    exit 6
fi
echo "✅ Device Owner confirmed"
echo

echo "[Step 5/7] Grant core permissions..."
adb shell pm grant "$PKG" android.permission.POST_NOTIFICATIONS 2>/dev/null || true
adb shell pm grant "$PKG" android.permission.ACCESS_FINE_LOCATION 2>/dev/null || true
adb shell pm grant "$PKG" android.permission.CAMERA 2>/dev/null || true
adb shell appops set "$PKG" RUN_ANY_IN_BACKGROUND allow 2>/dev/null || true
adb shell appops set "$PKG" GET_USAGE_STATS allow 2>/dev/null || true
adb shell dumpsys deviceidle whitelist +"$PKG" 2>/dev/null || true
echo "✅ Permissions granted"
echo

echo "[Step 6/7] Launch and auto-enroll..."
# Launch app
adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
sleep 2

# Send configuration broadcast with admin_key instead of token
if ! adb shell am broadcast -a com.nexmdm.CONFIGURE -n "$PKG/.ConfigReceiver" --es server_url "$BASE_URL" --es admin_key "$ADMIN_KEY" --es alias "$DEVICE_ALIAS" 2>/dev/null; then
    echo "❌ Configuration broadcast failed"
    echo "   Debug: Check ConfigReceiver in manifest"
    echo "   Fix: Verify receiver is exported"
    exit 7
fi
echo "✅ Auto-enrollment initiated"
echo

echo "[Step 7/7] Verify enrollment..."
sleep 3
if ! adb shell pidof "$PKG" 2>/dev/null; then
    echo "❌ Service not running"
    echo "   Debug: adb logcat -d | grep $PKG"
    exit 8
fi
echo "✅ Service running"
echo

echo "================================================"
echo "✅✅✅ ENROLLMENT COMPLETE ✅✅✅"
echo "================================================"
echo "📱 Device \"$ALIAS\" enrolled successfully!"
echo "🔍 Check dashboard within 60 seconds"
echo "================================================"
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
    token_id: str = Query(...),
    raw_token: Optional[str] = Query(None),
    agent_pkg: str = Query("com.nexmdm"),
    unity_pkg: str = Query("org.zwanoo.android.speedtest"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate zero-tap Windows one-liner enrollment command with enhanced debugging"""
    from models import EnrollmentToken, EnrollmentEvent
    
    # Validate enrollment token
    token = db.query(EnrollmentToken).filter(EnrollmentToken.token_id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    if token.status != 'active':
        raise HTTPException(status_code=400, detail=f"Token is {token.status}")
    
    # Get server configuration
    server_url = os.getenv("SERVER_URL", "")
    if not server_url:
        raise HTTPException(status_code=500, detail="SERVER_URL environment variable not set")
    
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY environment variable not set")
    
    # Log script generation event
    event = EnrollmentEvent(
        event_type='script.render_one_liner',
        token_id=token_id,
        alias=alias,
        details=json.dumps({"platform": "windows_oneliner", "agent_pkg": agent_pkg, "unity_pkg": unity_pkg})
    )
    db.add(event)
    db.commit()
    
    structured_logger.log_event(
        "script.render_one_liner",
        token_id=token_id,
        alias=alias,
        platform="windows"
    )
    
    metrics.inc_counter("script_oneliner_copies_total", {"platform": "windows", "alias": alias})
    
    # Create simplified one-liner that doesn't exit early - /K keeps window open
    one_liner = f'''cmd.exe /V:ON /K "set PKG={agent_pkg} & set ALIAS={alias} & set BASE_URL={server_url} & set ADMINKEY={admin_key} & set APK_PATH=%TEMP%\\unitymdm.apk & echo ============================================ & echo UnityMDM Zero-Tap Enrollment - !ALIAS! & echo ============================================ & echo. & echo [Step 1/7] Wait for device... & adb wait-for-device >nul 2>&1 && (echo ✅ Device connected) || (echo ❌ No device - Check USB cable) & echo. & echo [Step 2/7] Download APK... & curl -L -H ^"X-Admin-Key: !ADMINKEY!^" ^"!BASE_URL!/v1/apk/download/latest^" -o ^"!APK_PATH!^" >nul 2>&1 && (echo ✅ APK downloaded) || (echo ❌ Download failed - Check network) & echo. & echo [Step 3/7] Install APK... & (adb install -r -g ^"!APK_PATH!^" >nul 2>&1 || (adb uninstall !PKG! >nul 2>&1 & adb install -r -g -t ^"!APK_PATH!^" >nul 2>&1)) && (echo ✅ APK installed) || (echo ❌ Install failed) & echo. & echo [Step 4/7] Set Device Owner... & adb shell dpm set-device-owner !PKG!/.NexDeviceAdminReceiver >nul 2>&1 && (echo ✅ Device Owner confirmed) || (echo ❌ Device Owner failed - Factory reset required) & echo. & echo [Step 5/7] Grant permissions... & adb shell pm grant !PKG! android.permission.POST_NOTIFICATIONS >nul 2>&1 & adb shell pm grant !PKG! android.permission.ACCESS_FINE_LOCATION >nul 2>&1 & adb shell pm grant !PKG! android.permission.CAMERA >nul 2>&1 & adb shell appops set !PKG! RUN_ANY_IN_BACKGROUND allow >nul 2>&1 & adb shell appops set !PKG! GET_USAGE_STATS allow >nul 2>&1 & adb shell dumpsys deviceidle whitelist +!PKG! >nul 2>&1 & echo ✅ Permissions granted & echo. & echo [Step 6/7] Launch and auto-enroll... & adb shell monkey -p !PKG! -c android.intent.category.LAUNCHER 1 >nul 2>&1 & timeout /t 2 /nobreak >nul & adb shell am broadcast -a com.nexmdm.CONFIGURE -n !PKG!/.ConfigReceiver --es server_url ^"!BASE_URL!^" --es admin_key ^"!ADMINKEY!^" --es alias ^"!ALIAS!^" >nul 2>&1 && (echo ✅ Auto-enrollment initiated) || (echo ❌ Broadcast failed) & echo. & echo [Step 7/7] Verify... & timeout /t 3 /nobreak >nul & adb shell pidof !PKG! >nul 2>&1 && (echo ✅ Service running) || (echo ❌ Service not running) & echo. & echo ============================================ & echo ✅ ENROLLMENT COMPLETE & echo ============================================ & echo Device: !ALIAS! & echo Check dashboard within 60 seconds & echo ============================================ & echo. & echo Window will stay open - Type 'exit' to close"'''
    
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
    token_id: str = Query(...),
    raw_token: Optional[str] = Query(None),
    agent_pkg: str = Query("com.nexmdm"),
    unity_pkg: str = Query("org.zwanoo.android.speedtest"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate zero-tap Bash one-liner enrollment command with enhanced debugging"""
    from models import EnrollmentToken, EnrollmentEvent
    
    # Validate enrollment token
    token = db.query(EnrollmentToken).filter(EnrollmentToken.token_id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    if token.status != 'active':
        raise HTTPException(status_code=400, detail=f"Token is {token.status}")
    
    # Get server configuration
    server_url = os.getenv("SERVER_URL", "")
    if not server_url:
        raise HTTPException(status_code=500, detail="SERVER_URL environment variable not set")
    
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY environment variable not set")
    
    # Log script generation event
    event = EnrollmentEvent(
        event_type='script.render_one_liner',
        token_id=token_id,
        alias=alias,
        details=json.dumps({"platform": "bash_oneliner", "agent_pkg": agent_pkg, "unity_pkg": unity_pkg})
    )
    db.add(event)
    db.commit()
    
    structured_logger.log_event(
        "script.render_one_liner",
        token_id=token_id,
        alias=alias,
        platform="bash"
    )
    
    metrics.inc_counter("script_oneliner_copies_total", {"platform": "bash", "alias": alias})
    
    # Create Bash one-liner with proper debugging
    one_liner = f'''PKG="{agent_pkg}" ALIAS="{alias}" BASE_URL="{server_url}" ADMIN_KEY="{admin_key}" APK="/tmp/unitymdm.apk" && echo "================================================" && echo "UnityMDM Zero-Tap Enrollment - $ALIAS" && echo "================================================" && echo && echo "[Step 1/7] Wait for device..." && (adb wait-for-device 2>/dev/null && echo "✅ Device connected") || (echo "❌ No device found. Fix: Check USB cable" && exit 2) && echo && echo "[Step 2/7] Download latest APK..." && (curl -L -H "X-Admin-Key: $ADMIN_KEY" "$BASE_URL/v1/apk/download/latest" -o "$APK" 2>/dev/null && echo "✅ APK downloaded") || (echo "❌ Download failed. Fix: Check network" && exit 3) && echo && echo "[Step 3/7] Install APK..." && (adb install -r -g "$APK" 2>/dev/null && echo "✅ APK installed") || (adb uninstall "$PKG" 2>/dev/null; (adb install -r -g -t "$APK" 2>/dev/null && echo "✅ APK installed") || (echo "❌ Install failed" && exit 4)) && echo && echo "[Step 4/7] Set Device Owner..." && (adb shell dpm set-device-owner "$PKG/.NexDeviceAdminReceiver" 2>/dev/null && echo "✅ Device Owner confirmed") || (echo "❌ Device Owner failed. Fix: Factory reset device" && exit 5) && echo && echo "[Step 5/7] Grant permissions..." && adb shell pm grant "$PKG" android.permission.POST_NOTIFICATIONS 2>/dev/null; adb shell pm grant "$PKG" android.permission.ACCESS_FINE_LOCATION 2>/dev/null; adb shell pm grant "$PKG" android.permission.CAMERA 2>/dev/null; adb shell appops set "$PKG" RUN_ANY_IN_BACKGROUND allow 2>/dev/null; adb shell appops set "$PKG" GET_USAGE_STATS allow 2>/dev/null; adb shell dumpsys deviceidle whitelist +"$PKG" 2>/dev/null && echo "✅ Permissions granted" && echo && echo "[Step 6/7] Launch and auto-enroll..." && adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1; sleep 2; (adb shell am broadcast -a com.nexmdm.CONFIGURE -n "$PKG/.ConfigReceiver" --es server_url "$BASE_URL" --es admin_key "$ADMIN_KEY" --es alias "$ALIAS" 2>/dev/null && echo "✅ Auto-enrollment initiated") || (echo "❌ Broadcast failed" && exit 7) && echo && echo "[Step 7/7] Verify enrollment..." && sleep 3 && (adb shell pidof "$PKG" 2>/dev/null && echo "✅ Service running") || (echo "❌ Service not running" && exit 8) && echo && echo "================================================" && echo "✅✅✅ ENROLLMENT COMPLETE ✅✅✅" && echo "================================================" && echo "📱 Device \\\"$ALIAS\\\" enrolled successfully!" && echo "🔍 Check dashboard within 60 seconds" && echo "================================================"'''
    
    return Response(
        content=one_liner,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'inline; filename="enroll-{alias}-oneliner.sh"'
        }
    )

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
    
    base_url = os.getenv("SERVER_URL", "")
    if not base_url:
        base_url = "http://localhost:8000"
    
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

@app.get("/v1/apk/list")
async def list_apks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all uploaded APK versions with OTA deployment info"""
    from models import ApkDeploymentStats
    
    apks = db.query(ApkVersion).filter(ApkVersion.is_active == True).order_by(ApkVersion.uploaded_at.desc()).all()
    
    base_url = os.getenv("SERVER_URL", "")
    if not base_url:
        base_url = "http://localhost:8000"
    
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
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Download a specific APK version (requires device token or enrollment token)"""
    from models import ApkDownloadEvent, EnrollmentToken
    
    device = None
    token_id_last4 = "anon"
    auth_source = "unknown"
    
    # Try device token authentication first
    if x_device_token:
        devices = db.query(Device).limit(100).all()
        for d in devices:
            if verify_token(x_device_token, d.token_hash):
                device = d
                token_id_last4 = device.token_id[-4:] if device.token_id else "none"
                auth_source = "device"
                break
    
    # Try enrollment token authentication if no device token
    if not device and authorization:
        try:
            if authorization.startswith("Bearer "):
                enroll_token_value = authorization[7:]
                # Check if it's a valid enrollment token
                enrollment_tokens = db.query(EnrollmentToken).filter(
                    EnrollmentToken.status == 'active'
                ).all()
                for et in enrollment_tokens:
                    if verify_token(enroll_token_value, et.token_hash):
                        token_id_last4 = et.token_id[-4:]
                        auth_source = "enrollment"
                        break
        except Exception as e:
            print(f"[APK DOWNLOAD] Enrollment token validation error: {e}")
    
    if not device and auth_source != "enrollment":
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    
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
    
    # Get the latest active APK
    apk = db.query(ApkVersion).filter(
        ApkVersion.is_active == True
    ).order_by(
        ApkVersion.uploaded_at.desc()
    ).first()
    
    if not apk:
        raise HTTPException(status_code=404, detail="No APK versions available")
    
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
        "file_size": str(apk.file_size)
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
    
    base_url = os.getenv("SERVER_URL", "")
    if not base_url:
        base_url = "http://localhost:8000"
    
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
    
    devices = db.query(Device).limit(100).all()
    device = None
    for d in devices:
        if verify_token(x_device_token, d.token_hash):
            device = d
            break
    
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
    
    base_url = os.getenv("SERVER_URL", "")
    if not base_url:
        base_url = "http://localhost:8000"
    
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
    
    log_ota_event("ota.rollout.update", build_id=apk.id, version_code=apk.version_code,
                 old_percent=old_percent, new_percent=payload.staged_rollout_percent,
                 updated_by=current_user.username)
    
    structured_logger.log_event(
        "ota.rollout.update",
        build_id=apk.id,
        version_code=apk.version_code,
        old_percent=old_percent,
        new_percent=payload.staged_rollout_percent,
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
    device_ids: Optional[list[str]] = None

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
        raise HTTPException(status_code=404, detail="No devices found with FCM tokens")
    
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
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    fcm_url,
                    json=message,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    timeout=10.0
                )
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
    - Maximum size: 60MB (enforced by object storage)
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
    - 413: File too large (>60MB)
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
        final_filename = f"{package_name}_{version_code}_{build_type}.apk"
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

@app.get("/download/nexmdm.apk")
async def download_apk():
    apk_path = os.path.join(os.path.dirname(__file__), "..", "downloads", "nexmdm.apk")
    
    if not os.path.exists(apk_path):
        raise HTTPException(
            status_code=404, 
            detail="APK not found. Please build and place the APK in the downloads directory."
        )
    
    return FileResponse(
        apk_path,
        media_type="application/vnd.android.package-archive",
        filename="nexmdm.apk"
    )

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")
    
    @app.get("/d/{device_id}")
    async def device_detail_page(device_id: str):
        index_file = os.path.join(static_dir, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"message": "Dashboard not built yet"}
    
    @app.get("/")
    async def dashboard():
        index_file = os.path.join(static_dir, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"message": "Dashboard not built yet"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
