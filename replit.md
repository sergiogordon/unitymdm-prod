# MDM System - Compressed Overview

## Overview
This project is a production-ready, cloud-based Mobile Device Management (MDM) system for Android devices. It offers robust backend control, real-time updates, and secure provisioning, complemented by a modern web frontend for administration. The system scales to **500-2,000 concurrent devices** with predictable performance (p95 <150ms, p99 <300ms), providing zero-touch enrollment, remote command execution, and real-time device telemetry. Key features include secure device registration, heartbeat monitoring, FCM-based command dispatch, automated partition management, and comprehensive operational tooling. The system prioritizes scalability, performance, security, and operational excellence.

## User Preferences
- Focus on scalability and performance
- Clean, maintainable code structure
- Comprehensive error handling
- Real-time updates via WebSockets
- Email notifications for critical events
- Signal-rich, low-noise alerts with auto-remediation

## System Architecture
The system employs a clear separation between its frontend and backend, built for scalability and real-time communication.

### UI/UX Decisions
The frontend, developed with Next.js and shadcn/ui, provides a modern, responsive interface optimized for administrative tasks such including token management, script generation, and device status tracking.

### Technical Implementations
- **Backend**: FastAPI, asynchronous programming, SQLAlchemy, PostgreSQL.
- **Frontend**: Next.js for a rich user experience.
- **Database**: PostgreSQL with partitioned time-series tables, optimized for 500-2,000 devices.
- **Performance**: Dual-write fast-read architecture with O(1) device status lookups, 10s deduplication bucketing.
- **Real-time Communication**: WebSockets for live device updates and command execution.
- **Authentication**: JWT for users, bcrypt for device tokens, HMAC SHA-256 for secure command dispatch, X-Admin-Key for enrollment flow.
- **Android Agent**: Dedicated Android application with an automated CI/CD pipeline (GitHub Actions) for secure deployment.
- **Zero-Tap Enrollment v2 (Metrics-Ready + Hardening - Oct 2025)**: Production-hardened device provisioning with bloatware removal, system optimization, and comprehensive diagnostics. The system provides **true 1-liner commands** (Windows CMD and Bash) that handle the complete enrollment workflow from factory-reset Android devices with fail-fast behavior and actionable error messages. **Enrollment tokens have been removed** - authentication now uses admin-key directly, eliminating the token creation step. Key features:
  - **Simplified Authentication**: Scripts use admin-key directly; no enrollment token creation required
  - **JWT-Authenticated Script Generation**: Frontend generates scripts after JWT login with just an alias input
  - **Android ConfigReceiver**: Accepts 'admin_key' in broadcast intents for device registration
  - **Backend /v1/register**: Authenticates via X-Admin-Key header for streamlined registration
  - **Enhanced Scripts**: All enrollment scripts (full .cmd/.sh and one-liners) feature 9-step progress tracking with ✅/❌ indicators, inline debug hints for failures, and specific exit codes (2-9) for each failure point
  - **Frontend Integration**: Simplified ADB setup page with one-click script generation and copy buttons for Windows and Bash one-liners
  - **Enrollment Flow v2** (9 steps): (1) Wait for device → (2) Download APK → (3) Install APK → (4) Set Device Owner → (5) Grant permissions → (6) Disable bloatware → (7) Apply system tweaks → (8) Launch app & send broadcast → (9) Verify service & registration
  - **Bloatware Removal**: Best-effort disabling of ~60 carrier/OEM/Google apps (Verizon bloat, YouTube, Maps, Calendar, Facebook, etc.) using `pm disable-user --user 0`. Non-blocking - continues enrollment if packages are missing
  - **System Tweaks**: Disables app standby, battery restrictions, sets ambient wake (tilt/touch), and optimizes screen brightness for reliable 24/7 operation
  - **Manual Step Guidance**: Clear post-enrollment instructions for Usage Access and Full-Screen Intents permissions with exact Settings paths for Android 13/14+
  - **Diagnostic Logging**: On failure, automatically captures ADB logcat output filtered for NexMDM, usage stats, doze, and standby to `%TEMP%\mdm_enroll_diag.txt` (Windows) or `/tmp/mdm_enroll_diag.txt` (Bash) for troubleshooting
  - **Error Guidance**: Each failure point includes specific fix instructions (e.g., "Fix: Factory reset device" for Device Owner failures)
  - Supports four script types: Windows .cmd (full batch file), Bash .sh (Unix/Linux/macOS), Windows one-liner (CMD paste), and Bash one-liner (Terminal paste)
  - **Persistent Console Windows**: Windows scripts keep console open to display enrollment progress and errors
  - **Metrics Verification**: Android agent automatically collects and sends battery %, network SSID, RAM usage, and uptime in heartbeats within 60 seconds of enrollment completion
- **Persistence**: Partitioned heartbeat storage (90-day retention), device_last_status for O(1) reads, automated archival with SHA-256 checksums.
- **Observability**: Structured JSON logging, Prometheus-compatible metrics with latency histograms, connection pool monitoring.

### Feature Specifications
- **Core Control Loop**: Secure device registration, heartbeat processing, FCM command dispatch, action result tracking, and HMAC signature validation.
- **Device Management**: Real-time heartbeat monitoring, battery/memory tracking, remote command execution, auto-relaunch, and offline detection.
- **Bulk Device Deletion**: Comprehensive hard delete system with multi-select UI, device selection snapshots (15-min TTL), token revocation (410 Gone on heartbeat), async historical data purging with advisory locks, rate limiting (10 ops/min), type-to-confirm safety modal, and optional purge history checkbox. Background workers execute purge jobs every 30 seconds with automatic partition support.
- **Alert System**: Automated alerting for offline devices (>12m), low battery (<15%), Unity app down, and **configurable service monitoring** with Discord webhook integration, deduplication, rate limiting, and optional auto-remediation via FCM.
- **Service Monitoring (NEW)**: Per-device configurable foreground monitoring for any Android package. Admin sets monitored package (e.g., Speedtest, Unity), display name, and threshold (1-120 min, default 10). Backend evaluates service up/down based on foreground recency from Android UsageStatsManager. Discord alerts fire on service_down transitions with service name, last foreground time, and threshold. Recovery alerts on service restoration. API endpoints: `GET/PATCH /admin/devices/{id}/monitoring`. Backward compatible with legacy Speedtest-specific detection. See `MONITORING_IMPLEMENTATION_STATUS.md` for full details.
- **Security**: bcrypt hashing, HMAC SHA-256, JWT, IP-based rate limiting, and audit tracking.
- **Performance Optimization**: Database partitioning, dual-write fast reads, connection pool monitoring, deduplication bucketing. Target SLIs: p95 <150ms, p99 <300ms for 2,000 devices.
- **Operational Tooling**: Load testing infrastructure (2,000 devices with realistic jitter), acceptance test suite, pool health monitoring, automated maintenance jobs with advisory locks.
- **Android Agent CI/CD**: Automated build, sign, verify, and upload of APKs.
- **Android Agent Runtime**: Device Owner Mode support, HMAC-validated FCM command execution, action result posting with exponential backoff, 5-minute heartbeat intervals, structured logging, and reliability features (persistent queue, network monitoring, power-aware retries).
- **OTA Updates (Milestone 4)**: Secure fleet-wide Android agent updates with one-click promotion, staged rollouts (1%-100%), deterministic device cohorting, rollback capability, and comprehensive adoption telemetry. Devices poll `/v1/agent/update` on startup, every 6 hours, or immediately via FCM nudge. Includes SHA-256 verification, signer fingerprint validation, Wi-Fi-only constraints, and safety controls (battery, network conditions).
- **APK Management (CI Integration)**: Admin dashboard for managing CI-built debug APKs. GitHub Actions workflow automatically registers builds with metadata (version, SHA256, signer fingerprint, Git SHA) via admin-authenticated API, then uploads the 18MB APK binary to `/admin/apk/upload`. Frontend displays builds with download/delete capabilities. **Uses Replit Object Storage SDK** (native Python SDK with automatic sidecar authentication) for persistent, scalable file storage that survives deployments and server restarts. Files stored with `storage://apk/debug/{uuid}_{filename}` paths (max 60MB per file). Comprehensive observability with structured logging (`storage.upload.start/success/error`, `storage.download.start/success/error`, `apk.register`, `apk.download`, `apk.delete`) and Prometheus metrics. Includes retry logic (3× with backoff) and file validation. See `.github/workflows/android-build-and-deploy.yml` for CI implementation.

### System Design Choices
- **Async SQLAlchemy**: For non-blocking I/O and improved concurrency.
- **Connection Pooling**: Production-validated configuration (100 max connections vs 450 Postgres limit) with health monitoring.
- **Partition Management**: Daily partitions with automated lifecycle (create → archive → drop), metadata tracking, VACUUM optimization.
- **Dual-Write Pattern**: Transactional writes to both partitioned heartbeats and device_last_status for fast reads, with hourly reconciliation.
- **Deduplication**: 10-second bucketing prevents duplicate writes, reduces storage by 20-30%.
- **WebSocket Architecture**: Centralized management for real-time communication.
- **Event Retention Policies**: 90-day heartbeat retention, automated archival with SHA-256 integrity checks.
- **Performance Metrics**: Comprehensive latency tracking (p95/p99), pool utilization gauges, Prometheus-compatible exposition.
- **Rate Limiting**: Configurable IP-based rate limiting (10 bulk delete ops/min, sliding window).
- **OTA Cohorting**: Deterministic SHA-256-based device cohorting ensures stable, reproducible rollout percentages without per-device state.
- **OTA Safety**: Wi-Fi-only downloads, battery thresholds, and call-state checking prevent disruptive updates during critical device usage.
- **Bulk Delete Architecture**: Device selection snapshots prevent race conditions, background purge workers use PostgreSQL advisory locks for safe concurrent execution, hard deletes cascade to device_last_status and device_events tables.
- **APK Build Registry**: Admin-scoped API endpoints for CI integration with Replit Object Storage:
  - `POST /admin/apk/register`: Register APK metadata (version, SHA256, CI info)
  - `POST /admin/apk/upload`: Upload actual APK binary file to Object Storage (multipart/form-data, max 60MB)
  - `GET /admin/apk/builds`: List registered builds with filtering
  - `GET /admin/apk/download/{build_id}`: Download APK file from Object Storage
  - `DELETE /admin/apk/builds/{build_id}`: Delete build and file from Object Storage
  All endpoints require admin key authentication. Download events tracked in `apk_download_events` table with source attribution. CI workflow performs two-step registration: metadata → file upload. Files stored with keys `apk/debug/{uuid}_{filename}.apk`, database paths use `storage://` prefix. Native `replit.object_storage.Client` handles authentication automatically via sidecar (127.0.0.1:1106).

### Reliability Features (Milestone 5) ✅ COMPLETED
The Android agent includes comprehensive reliability hardening to ensure field operation under poor network conditions and aggressive power management:

- **Persistent Queue**: Room database-backed queue (`QueueDatabase.kt`, `QueueItem.kt`, `QueueDao.kt`) for unsent heartbeats and action-results that survives crashes and reboots. Queued items are retained until successfully delivered or expired (24h TTL for action-results).
- **Network Resilience**: NetworkCallback (`NetworkMonitor.kt`) monitors connectivity state changes (wifi/cellular/offline) and triggers immediate queue drain when network becomes validated. Exponential backoff with full jitter (2s base, 5min cap) in `QueueManager.kt` prevents overwhelming the server during network instability.
- **Power Management**: PowerManagementMonitor (`PowerManagementMonitor.kt`) verifies Device Owner status, Doze whitelist, and battery optimization status. Confirms Doze exemption and unrestricted battery access. Pauses non-essential retries when battery drops below 10% and not charging.
- **Queue Management**: `QueueManager.kt` implements size limits (500 items, 10MB), prunes old heartbeats first (never prunes action-results), and coalesces duplicate heartbeats within the same 10s dedupe bucket. Uses CTE-based DELETE queries in `QueueDao.kt` for SQLite compatibility (WITH clause materializes IDs before deletion).
- **HMAC Validation**: Dual-key HMAC SHA-256 signature validation (`HmacValidator.kt`) for all incoming FCM commands with 5-minute timestamp window and constant-time comparison. HMAC keys stored in `SecurePreferences.kt` during enrollment via `ConfigReceiver.kt`.
- **Enhanced Observability**: Heartbeat payloads include `power_ok`, `doze_whitelisted`, `net_validated`, and `queue_depth` fields via updated `TelemetryCollector.kt`. Structured logs track queue operations (`queue.enqueue`, `queue.drain`, `queue.prune`), network changes (`net.change`, `net.regain`), retry scheduling (`retry.schedule`), and delivery outcomes (`deliver.ok`, `deliver.fail`).
- **Startup Recovery**: On service start or boot, `MonitorService.kt` automatically drains pending queue items within 5 seconds, ensuring no data loss from crashes or restarts.
- **FCM Security**: All FCM messages validated via HMAC before execution in `FcmMessagingService.kt`, rejecting tampered or expired commands.

## External Dependencies
- **PostgreSQL**: Primary database.
- **FastAPI**: Backend Python web framework.
- **Next.js**: Frontend React framework.
- **shadcn/ui**: Frontend UI component library.
- **Alembic**: Database migration tool.
- **Firebase Cloud Messaging (FCM)**: For command dispatch to devices.
- **GitHub Actions**: For Android Agent CI/CD.
- **Replit Mail**: Email service for notifications.
- **Replit Object Storage**: Native Python SDK (`replit.object_storage`) for persistent APK file storage with automatic sidecar authentication.
- **Room Database**: SQLite-based persistent storage for Android agent queue.