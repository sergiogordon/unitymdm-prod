# Observability & Ops Implementation

## Overview
This MDM system includes production-ready observability features for monitoring, debugging, and performance analysis. The implementation provides structured logging, Prometheus metrics, and database audit tables for complete control-loop visibility.

## Features Implemented

### ✅ Structured JSON Logging
All critical endpoints emit structured JSON logs to stdout with consistent fields:
- `ts`: ISO8601 timestamp with timezone
- `level`: INFO, WARN, ERROR
- `event`: Standardized event name
- `request_id`: Correlation ID for end-to-end tracing

### ✅ Request ID Middleware
Automatic request correlation across the entire request lifecycle:
- Generates or extracts `X-Request-ID` from headers
- Propagates through all logs and async operations
- Enables tracing command dispatch → FCM → device response

### ✅ Instrumented Endpoints
All hot paths instrumented with structured logging:
- `/v1/register` - Device registration (register.request, register.success, register.fail)
- `/v1/heartbeat` - Device heartbeats (heartbeat.ingest with battery_pct, network_type, uptime_s)
- `/v1/devices/{id}/ping` - FCM command dispatch (dispatch.request, dispatch.sent, dispatch.fail)
- `/v1/apk/download-latest` - APK downloads (apk.download with build info and source)
- `/v1/apk/download/{apk_id}` - Specific APK downloads
- `/v1/enroll-tokens` - Token operations (sec.token.create, sec.token.expired)

### ✅ Prometheus Metrics
Lightweight in-memory metrics collection with `/metrics` endpoint:
- `http_requests_total{route,method,status_code}` - Total HTTP requests
- `http_request_latency_ms{route}` - Request latency histogram
- `fcm_dispatch_latency_ms{action}` - FCM dispatch timing
- `heartbeats_ingested_total` - Heartbeat counter
- `apk_download_total{build_type,source}` - APK download tracking

### ✅ Database Audit Tables
Critical operations tracked in PostgreSQL:
- `apk_download_events` - APK download audit trail
- `fcm_dispatches` - FCM command tracking
- `enrollment_events` - Token lifecycle events

## Quick Start

### View Structured Logs
```bash
# All register events
grep '{"ts"' server.log | grep "register\."

# Error-level events only
grep '{"ts"' server.log | grep '"level": "ERROR"'

# Trace a specific request
grep 'fd840c13-e205-430b-ade8-d9c9d2e8eee4' server.log
```

### Query Metrics
```bash
# Scrape all metrics
curl -H "X-Admin: $ADMIN_KEY" http://localhost:8000/metrics

# Check heartbeat count
curl -s -H "X-Admin: $ADMIN_KEY" http://localhost:8000/metrics | grep heartbeats_ingested_total

# View request latencies
curl -s -H "X-Admin: $ADMIN_KEY" http://localhost:8000/metrics | grep http_request_latency_ms
```

### Example Structured Logs
```json
{"ts": "2025-10-18T15:31:37.114496+00:00", "request_id": "fd840c13-e205-430b-ade8-d9c9d2e8eee4", "level": "INFO", "event": "register.request", "alias": "test-device", "route": "/v1/register"}
{"ts": "2025-10-18T15:30:57.806958+00:00", "request_id": "1a365bd8-88b0-413b-a310-70c31d090ae1", "level": "INFO", "event": "metrics.scrape"}
```

## Event Vocabulary

### Registration Events
- `register.request` - Device registration initiated
- `register.success` - Device registered successfully
- `register.fail` - Registration failed (includes reason)

### Heartbeat Events
- `heartbeat.ingest` - Heartbeat received (includes battery_pct, network_type, uptime_s)

### Command Dispatch Events
- `dispatch.request` - FCM command initiated
- `dispatch.sent` - FCM successfully sent (includes latency_ms, fcm_http_code)
- `dispatch.fail` - FCM dispatch failed (includes error details)

### APK Events
- `apk.download` - APK downloaded (includes build_id, version_code, source)

### Security Events
- `sec.token.create` - Enrollment token created
- `sec.token.expired` - Expired token rejected
- `sec.token.consume` - Token used (ready for implementation)
- `sec.token.ratelimit` - Rate limit hit (ready for implementation)

### Metrics Events
- `metrics.scrape` - Prometheus metrics endpoint accessed

## Performance Targets
- ✅ Heartbeat processing: <150ms p95 latency
- ✅ Logging overhead: ≤5ms p95 on hot routes
- ✅ Metrics scrape: <50ms under nominal load
- ✅ FCM dispatch: Tracked end-to-end with request_id

## Testing
Run the observability test suite:
```bash
cd server && python test_observability.py
```

This validates:
- Health check availability
- Metrics endpoint authentication
- Metrics collection functionality
- Structured logging output
- Request ID correlation

## Files Created/Modified
- `server/observability.py` - Core structured logging and metrics
- `server/main.py` - Instrumentation across all endpoints
- `server/test_observability.py` - Validation test suite
- `replit.md` - Updated documentation with observability section

## Architecture Notes
- **12-Factor App**: Logs to stdout for platform-agnostic log aggregation
- **Low Overhead**: Async logging, minimal serialization, coarse metric cardinality
- **Request Correlation**: Middleware-based request_id propagation
- **Prometheus Compatible**: Standard histogram buckets and text exposition format
- **Security**: Admin-only `/metrics` endpoint with X-Admin header validation

## Future Enhancements
- Token consumption logging when enrollment flow is enhanced
- Rate limiting event tracking
- Deduplication event tracking for heartbeats
- Action result ingestion events (when endpoint is implemented)
- Distributed tracing with OpenTelemetry (optional)
