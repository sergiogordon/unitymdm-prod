# NexMDM Acceptance Tests

Comprehensive contract tests and 20-device enrollment simulation for NexMDM backend.

## Overview

This test suite validates:
- **Contract tests**: All public endpoints (device lifecycle, enrollment, APK, ops/metrics)
- **20-device simulation**: Full enrollment and command dispatch flow
- **Observability**: Structured logging, metrics, and request ID propagation
- **Idempotency**: FCM dispatch, heartbeat bucketing, and action result handling
- **Latency budgets**: p95/p99 tracking for critical operations

## Running Tests

### Run all acceptance tests:
```bash
cd server
pytest tests/ -v
```

### Run specific test modules:
```bash
# Device lifecycle tests
pytest tests/test_device_lifecycle.py -v

# Enrollment and APK tests
pytest tests/test_enrollment_apk.py -v

# Ops and metrics tests
pytest tests/test_ops_metrics.py -v

# 20-device simulation
pytest tests/test_20_device_simulation.py -v
```

### Run with detailed output:
```bash
pytest tests/ -v -s
```

## Test Structure

```
tests/
├── __init__.py
├── conftest.py                    # Shared fixtures and test configuration
├── test_device_lifecycle.py       # /v1/register, /v1/heartbeat, /v1/action-result
├── test_enrollment_apk.py         # Enrollment tokens, APK downloads, scripts
├── test_ops_metrics.py            # /metrics, /healthz, observability
└── test_20_device_simulation.py   # Full 20-device enrollment simulation
```

## Test Coverage

### Device Lifecycle (test_device_lifecycle.py)
- ✅ POST /v1/register (200, 401 with invalid/expired/revoked tokens)
- ✅ POST /v1/heartbeat (200, 401, 422, idempotency within 10s bucket)
- ✅ POST /v1/action-result (200, 404, 401, idempotency)
- ✅ Structured logging verification for all endpoints

### Enrollment & APK (test_enrollment_apk.py)
- ✅ POST /v1/enroll-tokens (200, 400, 401, rate limits)
- ✅ GET /v1/enroll-tokens (200, filtering by status)
- ✅ DELETE /v1/enroll-tokens/{token_id} (200, 404, 409, idempotency)
- ✅ GET /v1/apk/download-latest (200, 401)
- ✅ GET /v1/scripts/enroll.sh (200, 401, 404)
- ✅ GET /v1/scripts/enroll.cmd (200, 401, 404)

### Ops & Metrics (test_ops_metrics.py)
- ✅ GET /metrics (200 with admin, 401 without, Prometheus format, <50ms latency)
- ✅ GET /healthz (200, DB check included, <100ms latency)
- ✅ Request ID middleware (generation, preservation, log correlation)
- ✅ HTTP metrics collection (counters, histograms)

### 20-Device Simulation (test_20_device_simulation.py)
- ✅ Create 20 enrollment tokens
- ✅ Parallel device registration
- ✅ Heartbeat streaming with dedupe validation
- ✅ Command dispatch to all devices
- ✅ Action result reporting
- ✅ Latency budget validation:
  - Heartbeat p95 < 150ms, p99 < 300ms
  - Dispatch write p95 < 50ms
  - Metrics scrape < 50ms

## Fixtures (conftest.py)

### Database Fixtures
- `test_db`: Clean in-memory SQLite database per test
- `client`: FastAPI TestClient with DB dependency override

### Authentication Fixtures
- `admin_user`: Test admin user
- `admin_auth`: Admin JWT bearer token headers
- `admin_key`: Admin API key headers
- `test_device`: Test device with bearer token
- `device_auth`: Device bearer token headers

### Observability Fixtures
- `capture_logs`: Capture structured logs emitted during tests
- `capture_metrics`: Capture metrics (counters, histograms) during tests

## Latency Budgets

The tests enforce the following latency budgets:

| Operation | Target | Measured By |
|-----------|--------|-------------|
| Heartbeat p95 | <150ms | test_20_device_simulation.py |
| Heartbeat p99 | <300ms | test_20_device_simulation.py |
| FCM dispatch write p95 | <50ms | test_20_device_simulation.py |
| Metrics scrape | <50ms | test_ops_metrics.py |
| Health check | <100ms | test_ops_metrics.py |

## CI Integration

To run in CI:
```bash
# From repo root
cd server
pytest tests/ -v --tb=short
```

Tests use in-memory SQLite for fast, isolated execution without external dependencies.

## Expected Output

Successful test run shows:
```
tests/test_device_lifecycle.py::TestRegisterEndpoint::test_register_success_with_enrollment_token PASSED
tests/test_device_lifecycle.py::TestHeartbeatEndpoint::test_heartbeat_success PASSED
tests/test_enrollment_apk.py::TestEnrollmentTokenCRUD::test_create_tokens_success PASSED
tests/test_ops_metrics.py::TestMetricsEndpoint::test_metrics_success_with_admin_auth PASSED
tests/test_20_device_simulation.py::TestTwentyDeviceSimulation::test_complete_20_device_simulation PASSED
```

The 20-device simulation outputs a detailed summary:
```
============================================================
20-Device Enrollment Simulation
============================================================

Step 1: Admin creates 20 enrollment tokens...
  ✓ Created 20 tokens in 45.23ms

Step 2: Devices register in parallel...
  ✓ Registered 20/20 devices in 234.56ms

...

============================================================
Simulation Summary
============================================================
✓ 20/20 devices registered successfully
✓ 160 heartbeats ingested
✓ 20 heartbeat rows (dedupe factor: 8.0x)
✓ 20/20 commands dispatched
✓ 20/20 action results received

Latency Budgets:
  Heartbeat p95: 42.31ms (budget: <150ms) ✓
  Heartbeat p99: 87.12ms (budget: <300ms) ✓
  Dispatch p95: 12.45ms (budget: <50ms) ✓
  Metrics scrape max: 23.67ms (budget: <50ms) ✓
============================================================
```

## Troubleshooting

### Test failures due to missing environment variables:
- Set `ADMIN_KEY` environment variable (defaults to "admin" if not set)
- Database URL automatically uses in-memory SQLite for tests

### Import errors:
- Ensure you're running from the `server/` directory
- Run `pip install -r requirements.txt` to install dependencies

### Database-related failures:
- Tests use isolated in-memory databases, no cleanup needed
- Each test gets a fresh database via `test_db` fixture
