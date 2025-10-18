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