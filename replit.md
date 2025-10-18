# MDM System - Compressed Overview

## Overview
This project is a production-ready, cloud-based Mobile Device Management (MDM) system designed to manage and monitor Android devices. It features a robust backend for device control, real-time updates, and secure provisioning, coupled with a modern web frontend for administrative tasks. The system aims for high scalability, supporting 100+ concurrent devices, and provides a comprehensive solution for zero-touch enrollment, remote command execution, and real-time device telemetry. Key capabilities include secure device registration, heartbeat monitoring, FCM-based command dispatch, and an automated CI/CD pipeline for the Android agent.

## User Preferences
- Focus on scalability and performance
- Clean, maintainable code structure
- Comprehensive error handling
- Real-time updates via WebSockets
- Email notifications for critical events

## System Architecture
The system is built with a clear separation between frontend and backend.

### UI/UX Decisions
The frontend is developed using Next.js with shadcn/ui components, ensuring a modern and responsive user interface ready for Vercel deployment. The design prioritizes ease of use for administrative tasks, including a dashboard for token management, script generation, and device status tracking.

### Technical Implementations
- **Backend**: FastAPI framework, leveraging asynchronous programming with SQLAlchemy and PostgreSQL for high concurrency and efficient data handling.
- **Frontend**: Next.js for server-side rendering and a rich user experience.
- **Database**: PostgreSQL is used as the primary data store, configured with connection pooling and optimized for time-series data retention (e.g., 2-day event retention for heartbeats). Alembic is used for database migrations.
- **Real-time Communication**: WebSocket support enables live updates for device status and command execution.
- **Authentication**: JWT tokens for user authentication, bcrypt for device token hashing, and HMAC SHA-256 for secure command dispatch and integrity validation.
- **Android Agent**: A dedicated Android application (NexMDM Agent) handles device-side logic, built with an automated CI/CD pipeline (GitHub Actions) for secure building, signing, and deployment.
- **Zero-Touch Enrollment**: Comprehensive system for secure device provisioning using single-use enrollment tokens and server-generated ADB scripts for both Windows and Bash environments.
- **Persistence**: Optimized data models for tracking FCM dispatches, APK download events, device heartbeats, and enrollment tokens with built-in idempotency and retention policies.
- **Observability**: Production-grade structured JSON logging and Prometheus-compatible metrics for complete control-loop visibility (register → heartbeat → command → result → APK fetch). See Observability section below for details.

### Feature Specifications
- **V1 Production Control Loop**: Secure device registration, heartbeat processing (<150ms p95 latency), FCM high-priority command dispatch, action result tracking, and HMAC signature validation.
- **Device Management**: Real-time heartbeat monitoring, battery/memory tracking, remote command execution, auto-relaunch, and offline detection.
- **Security**: bcrypt password hashing, HMAC SHA-256, X-Admin header validation, JWT authentication, IP-based rate limiting, and audit tracking.
- **Performance**: Connection pooling (60 total connections), async database operations, indexed queries, and background cleanup tasks for sub-100ms heartbeat processing.
- **Android Agent CI/CD**: Automated build, sign, verify, and upload of APKs to the backend, with secure keystore management and reproducible builds.
- **Milestone 4 - Android Agent Runtime**: Device Owner Mode support, HMAC-validated FCM command execution, action result posting with exponential backoff retry, 5-minute heartbeat intervals, structured logging, and 401 error handling with graceful backoff.

### System Design Choices
- **Async SQLAlchemy**: For non-blocking I/O and improved concurrency.
- **Connection Pooling**: To efficiently manage database connections for high loads.
- **WebSocket Architecture**: Centralized manager for robust real-time communication.
- **Event Retention Policies**: Automated cleanup for operational data to maintain database performance.
- **Rate Limiting**: IP-based and configurable to prevent abuse.

## External Dependencies
- **PostgreSQL**: Primary database for all system data.
- **FastAPI**: Python web framework for the backend.
- **Next.js**: React framework for the frontend.
- **shadcn/ui**: UI component library for the frontend.
- **Alembic**: Database migration tool.
- **Firebase Cloud Messaging (FCM)**: For high-priority command dispatch to devices.
- **GitHub Actions**: For Android Agent CI/CD pipeline automation.
- **Replit Mail**: Email service for password resets and critical notifications.

## Observability & Operations

### Structured Logging
The system emits JSON-formatted structured logs to stdout for all critical operations, enabling efficient log aggregation and analysis.

**Common Fields** (all events):
- `ts`: ISO8601 timestamp with timezone
- `level`: Log level (INFO, WARN, ERROR)
- `event`: Event identifier (e.g., "register.success", "heartbeat.ingest")
- `request_id`: Request correlation ID (generated or extracted from X-Request-ID header)

**Event Vocabulary**:
- **Registration**: `register.request`, `register.success`, `register.fail`
- **Heartbeats**: `heartbeat.ingest` (includes battery_pct, network_type, uptime_s)
- **Commands**: `dispatch.request`, `dispatch.sent`, `dispatch.fail` (includes fcm_http_code, fcm_status, latency_ms)
- **APK Downloads**: `apk.download` (includes build_id, version_code, version_name, build_type, source)
- **Security**: `sec.token.create`, `sec.token.consume`, `sec.token.expired`, `sec.token.ratelimit`
- **Metrics**: `metrics.scrape`

**Request Correlation**:
All logs within a single request share the same `request_id`, enabling end-to-end tracing (e.g., command dispatch → FCM send → device response).

### Prometheus Metrics
The system exposes Prometheus-compatible metrics at the `/metrics` endpoint (requires admin authentication via X-Admin header).

**Available Metrics**:
- `http_requests_total{route,method,status_code}`: Total HTTP requests by route
- `http_request_latency_ms{route}`: Request latency histogram with buckets (5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s, 2.5s, 5s, 10s)
- `fcm_dispatch_latency_ms{action}`: FCM dispatch latency histogram
- `heartbeats_ingested_total`: Total heartbeats processed
- `apk_download_total{build_type,source}`: Total APK downloads by type and source

**Scraping**:
```bash
curl -H "X-Admin: $ADMIN_KEY" https://your-app.repl.co/metrics
```

### Database Audit Tables
Critical operations are tracked in database tables for audit and analysis:
- `apk_download_events`: APK download audit trail (build_id, source, token_id, IP, timestamp)
- `fcm_dispatches`: FCM command dispatch tracking (request_id, device_id, action, latency_ms, http_code, fcm_status)
- `enrollment_events`: Enrollment token lifecycle events

### Operational Runbook

**Viewing Structured Logs**:
```bash
grep '^\{' /path/to/server.log | jq -r '. | select(.event | startswith("register"))'
grep '^\{' /path/to/server.log | jq -r '. | select(.level == "ERROR")'
```

**Tracing a Request**:
```bash
REQUEST_ID="abc-123"
grep "$REQUEST_ID" /path/to/server.log | jq .
```

**Finding Device Activity**:
```bash
DEVICE_ID="device-uuid"
grep '^\{' /path/to/server.log | jq -r ". | select(.device_id == \"$DEVICE_ID\")"
```

**Checking Metrics**:
```bash
curl -s -H "X-Admin: $ADMIN_KEY" http://localhost:8000/metrics | grep heartbeats_ingested_total
curl -s -H "X-Admin: $ADMIN_KEY" http://localhost:8000/metrics | grep http_request_latency
```

**Performance Targets**:
- Heartbeat processing: <150ms p95 latency
- Logging overhead: ≤5ms p95 on hot routes
- Metrics scrape: <50ms under nominal load
- FCM dispatch: tracked end-to-end with request_id correlation

**Log Rotation**:
Logs are emitted to stdout (12-factor app pattern). Rotation and retention should be handled by the container platform or log aggregation service (e.g., Replit logs, Docker logs driver, filebeat).

## Testing & Quality Assurance

### Acceptance Test Suite
Comprehensive pytest-based test suite validates all backend APIs, observability, and performance budgets. Located in `server/tests/`.

**Test Coverage**:
- **Contract Tests**: All public endpoints (device lifecycle, enrollment, APK, ops/metrics) with success and failure paths
- **20-Device Simulation**: Full enrollment control loop with parallel registration, heartbeat streaming, command dispatch, and latency tracking
- **Observability**: Structured logging, metrics collection, and request ID propagation verification
- **Idempotency**: FCM dispatch, heartbeat bucketing, and action result deduplication
- **Performance**: Validates p95/p99 latency budgets (heartbeats <150ms, dispatch <50ms, metrics scrape <50ms)

**Running Tests**:
```bash
cd server
./run_acceptance_tests.sh
```

**Test Structure**:
- `tests/conftest.py`: Shared fixtures (test DB, auth, observability capture)
- `tests/test_device_lifecycle.py`: /v1/register, /v1/heartbeat, /v1/action-result
- `tests/test_enrollment_apk.py`: Enrollment tokens, APK downloads, enrollment scripts
- `tests/test_ops_metrics.py`: /metrics, /healthz, request ID middleware
- `tests/test_20_device_simulation.py`: Complete 20-device enrollment simulation

See `server/ACCEPTANCE_TESTS.md` for detailed test documentation and results.

## Milestone 4 - Android Agent Runtime

### Overview
Milestone 4 delivers a production-ready, self-managing Android agent that runs as Device Owner, posts reliable 5-minute heartbeats, executes HMAC-signed FCM commands (ping, launch_app), and reports results back to the backend with retry/backoff.

### Key Features Implemented

#### 1. Device Owner Mode
- **Device Owner Verification**: Agent checks Device Owner status at startup
- **Logging**: 
  - `device_owner.confirmed` when Device Owner is set
  - `device_owner.warning` when not set
- **Benefits**: Persistent foreground service, bypasses Doze restrictions, auto-grants permissions

#### 2. HMAC Command Validation
- **Signature Algorithm**: HMAC-SHA256
- **Message Format**: `{request_id}|{device_id}|{action}|{timestamp}`
- **Validation**: All FCM commands validated before execution
- **Security**: Invalid signatures logged as `fcm.hmac_invalid` and rejected
- **Secret Management**: HMAC_SECRET stored in environment variable (backend) and EncryptedSharedPreferences (Android)

**Setup Instructions:**
```bash
# Generate HMAC secret
openssl rand -base64 32

# Add to Replit Secrets as HMAC_SECRET
# Android agent receives secret during enrollment (currently uses placeholder)
```

#### 3. Heartbeat Runtime
- **Interval**: 5 minutes (300s) via AlarmManager with `setExactAndAllowWhileIdle`
- **Payload**: Nested structure with battery, system, memory, network telemetry
- **Retry Logic**: Exponential backoff (max 3 retries, base 1s delay, max 30s)
- **401 Handling**: Graceful 60-second backoff on authentication failures
- **Structured Logging**:
  - `heartbeat.sent`: Before sending (includes device_id, battery_pct)
  - `heartbeat.ack`: After successful response
  - `heartbeat.failed`: On errors

#### 4. Action Result Posting
- **Endpoint**: POST `/v1/action-result`
- **Schema**:
  ```json
  {
    "request_id": "uuid",
    "device_id": "uuid",
    "action": "ping|launch_app",
    "outcome": "success|failure",
    "message": "descriptive message",
    "finished_at": "ISO8601 timestamp"
  }
  ```
- **Retry Logic**: Exponential backoff with RetryHelper (max 3 retries)
- **Idempotency**: Backend handles duplicate submissions gracefully
- **Structured Logging**:
  - `command.executed`: When command succeeds
  - `result.posted`: After successful result posting
  - `result.retry`: On retry attempts

#### 5. Supported Commands
- **ping**: Immediate response test
  - Validates HMAC
  - Triggers immediate heartbeat
  - Posts action result with latency
- **launch_app**: Launch specified package
  - Validates HMAC
  - Launches app via Intent
  - Verifies process is running
  - Posts action result with success/failure

#### 6. Observability & Structured Logging
All logs follow format: `[EVENT] key1=value1 key2=value2`

**Agent Events**:
- `agent.startup`: Agent initialization (includes agent_version, device_owner status)
- `device_owner.confirmed`: Device Owner mode verified
- `device_owner.warning`: Device Owner mode not set
- `heartbeat.sent`: Heartbeat transmission
- `heartbeat.ack`: Heartbeat acknowledged by server
- `heartbeat.failed`: Heartbeat error
- `fcm.hmac_invalid`: HMAC validation failed
- `command.executed`: FCM command completed
- `result.posted`: Action result posted to backend
- `result.retry`: Result posting retry attempt

#### 7. New Android Components
- **HmacValidator.kt**: HMAC signature computation and verification
- **RetryHelper.kt**: Exponential backoff retry logic with jitter
- **SecurePreferences.hmacSecret**: Encrypted storage for HMAC secret

#### 8. Performance Targets
- Heartbeat RTT: < 3s typical on Wi-Fi/cellular
- Heartbeat interval accuracy: ±30s
- Command success rate: ≥ 98% under normal conditions
- Foreground service uptime: ≥ 99%

#### 9. Database Schema Updates
**FcmDispatch Table** (new columns):
- `completed_at`: Timestamp when action completed
- `result`: Outcome (success/failure)
- `result_message`: Detailed result message

### Security Baseline
- HTTPS only (reject plaintext)
- HMAC-SHA256 validation on all FCM payloads
- Device tokens in EncryptedSharedPreferences
- Strict action allow-list (ping, launch_app only)
- Logs redact tokens and HMAC keys

### Testing
- Updated `/v1/action-result` endpoint tests
- HMAC signature generation validated
- Action result idempotency verified
- 401/404 error handling confirmed