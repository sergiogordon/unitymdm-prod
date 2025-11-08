# MDM System - Compressed Overview

## Overview
This project is a production-ready, cloud-based Mobile Device Management (MDM) system for Android devices, designed to manage 500-2,000 concurrent devices. It provides robust backend control, real-time updates, and secure provisioning, complemented by a modern web frontend. Key capabilities include zero-touch enrollment, remote command execution, bulk app launching, real-time device telemetry, secure device registration, heartbeat monitoring, FCM-based command dispatch, automated partition management, and comprehensive operational tooling. The system prioritizes scalability, performance, security, and operational excellence, aiming for predictable performance (p95 <150ms, p99 <300ms).

## User Preferences
- Focus on scalability and performance
- Clean, maintainable code structure
- Comprehensive error handling
- Real-time updates via WebSockets
- Email notifications for critical events
- Signal-rich, low-noise alerts with auto-remediation

## System Architecture
The system features a clear separation between its frontend and backend, optimized for scalability and real-time communication.

### UI/UX Decisions
The frontend, built with Next.js and shadcn/ui, offers a modern, responsive interface for administrative tasks such as token management, script generation, and device status tracking. Global Settings drawer is accessible from all pages via sidebar button (bottom of nav) and Dashboard header gear icon, managed through React Context for state consistency.

### Technical Implementations
- **Backend**: FastAPI, asynchronous programming, SQLAlchemy, PostgreSQL.
- **Frontend**: Next.js.
- **Database**: PostgreSQL with partitioned time-series tables.
- **Performance**: Dual-write fast-read architecture with O(1) device status lookups and 10s deduplication.
- **Real-time Communication**: WebSockets for live device updates and command execution.
- **Authentication**: JWT for users, bcrypt for device tokens, HMAC SHA-256 for command dispatch, X-Admin-Key for enrollment.
- **User Management**: Self-service user registration (public `/api/auth/signup`), profile management with email updates, password reset via email (ReplitMail integration), dual authentication paths (admin and public signup coexist).
- **Environment Detection**: Automatic dev/prod environment detection via `server/config.py`. Detects production via `REPLIT_DEPLOYMENT=1`, uses `REPLIT_DOMAINS` for production URL and `REPLIT_DEV_DOMAIN` for development. Manual override available via `SERVER_URL` secret. All URLs normalized without trailing slashes to prevent double-slash issues in enrollment scripts and API endpoints.
- **Android Agent**: Dedicated Android application with automated CI/CD.
- **Zero-Tap Enrollment v2**: Production-hardened provisioning with simplified authentication (admin-key directly), JWT-authenticated script generation. One-liner enrollment commands (Windows CMD and Bash) with 9-step flow including centrally-managed bloatware removal (downloads current list from server), system tweaks (app standby, ambient wake, battery optimizations), progress tracking, and diagnostic logging. Full enrollment scripts (.cmd/.sh) deprecated in favor of one-liners. Bloatware list manageable via admin UI Optimization page.
- **Persistence**: Partitioned heartbeat storage (2-day retention), device_last_status for O(1) reads, automated archival.
- **Observability**: Structured JSON logging, Prometheus-compatible metrics, connection pool monitoring.
- **Core Control Loop**: Secure device registration, heartbeat processing, FCM command dispatch, action result tracking, HMAC signature validation.
- **Device Management**: Real-time heartbeat monitoring, battery/memory tracking, remote command execution, auto-relaunch, offline detection.
- **Bulk Device Deletion**: Comprehensive hard delete system with UI, token revocation, async data purging, rate limiting, and safety modals.
- **Alert System**: Automated alerting for offline devices, low battery, app down, and configurable service monitoring with Discord integration and optional auto-remediation.
- **Service Monitoring**: Per-device configurable foreground monitoring for Android packages, triggering Discord alerts on service downtime.
- **Security**: bcrypt hashing, HMAC SHA-256, JWT, IP-based rate limiting, audit tracking.
- **Operational Tooling**: Load testing infrastructure, acceptance test suite, automated maintenance jobs.
- **Android Agent CI/CD**: Automated build, sign, verify, and upload of APKs.
- **Android Agent Runtime**: Device Owner Mode, HMAC-validated FCM execution, 5-minute heartbeats, structured logging, reliability features.
- **OTA Updates (Milestone 4)**: Secure fleet-wide agent updates with staged rollouts, rollback capability, and adoption telemetry.
- **APK Management (CI Integration)**: Admin dashboard for managing CI-built debug APKs, including registration, upload to Replit Object Storage, download, and deletion, all secured by admin key authentication.
- **Reliability Features (Milestone 5)**: Android agent hardening with persistent Room database-backed queue, network resilience (NetworkCallback, exponential backoff), power management awareness, queue management (size limits, pruning), dual-key HMAC SHA-256 validation for FCM commands, and enhanced observability.
- **Bulk Launch App**: Enterprise-grade bulk app launching with three targeting modes (entire fleet, filtered set, device IDs list), dry-run preview, rate-limited FCM dispatch (20 msg/sec), real-time result tracking, and comprehensive status reporting with device-level acknowledgments. Android agent sends LAUNCH_APP_ACK after app launch attempts with status codes (OK/ERROR) and descriptive messages. Recent launches limited to 3 most recent commands for clean UI.
- **Remote Execution**: Comprehensive remote command execution system with two modes: FCM (JSON payload dispatching ping, ring, reboot, launch_app commands) and Shell (restricted shell commands with server-side and agent-side allow-list validation). Supports three targeting modes (entire fleet, filtered set, device aliases with multi-select picker), dry-run preview, CSV export of results, and real-time ACK tracking. Android agent validates commands using regex patterns (am start, am force-stop, pm list, settings get/put, input keyevent/tap/swipe, svc wifi/data, cmd package), executes via Runtime.exec() with 8-second timeout, captures stdout/stderr (2KB limit), and sends ACK responses to /v1/remote-exec/ack with status (OK/FAILED/TIMEOUT/DENIED), exit_code, and output. Frontend displays real-time stats (sent/acked/errors), per-device results table, preset commands dropdown (FCM and Shell presets including WEA suppression and OS update triggers), multi-select device picker with checkboxes and selection badges, and recent runs sidebar. Shell presets include "Suppress WEA & Enable DND" (zen_mode 2, disable emergency alerts), "Restore Normal Mode", and OS update commands. Backend includes database models (RemoteExec, RemoteExecResult), four API endpoints, audit logging with user_id/IP/payload_hash, and correlation_id tracking for each device execution. Command validation uses token-based parsing with shlex.split() for security, blocking dangerous metacharacters (|, ;, >, <, `, $) while allowing safe && chaining. Special token-based validation for cmd jobscheduler (SystemUpdateService only) and getprop (OS version and security patch only).
- **Device ID Management**: Comprehensive debug logging throughout device_id lifecycle (SecurePreferences, QueueManager, FcmMessagingService) to track read/write operations. SecurePreferences uses commit() instead of apply() for immediate persistence of device_id. Includes clearAllCredentials() for clean re-enrollment scenarios.
- **WiFi Auto-Connect**: Centralized WiFi configuration management with FCM-based credential distribution. Admin-configurable SSID, password, and security type (open/WEP/WPA/WPA2/WPA3) stored in global settings. One-click push to fleet via FCM delivers credentials to devices running Android 10+, executing `cmd wifi connect-network` command. Supports all security types with automatic command formatting. WiFi settings UI integrated in global settings drawer with save/discard, password visibility toggle, and enable/disable control. Backend provides three API endpoints (GET/POST settings, POST push-to-devices) with structured logging, device targeting, and FCM status tracking. Android agent implements handleWiFiConnect() in FcmMessagingService with HMAC-validated FCM message handling, Runtime.exec() command execution, and sendWiFiConnectionAck() for status reporting (OK/FAILED/ERROR). See WIFI_ANDROID_IMPLEMENTATION.md for Android integration guide.
- **Remote OS Updates**: Fleet-wide Android system update management via shell command presets in Remote Execution. Admins can trigger OS update checks, verify security patch levels, and monitor update status across devices. Includes four preset commands: Set Auto-Update Policy (settings put global auto_system_update_policy 1), Trigger System Update Check (cmd jobscheduler run -f android/com.android.server.update.SystemUpdateService 1), Check OS Version (getprop ro.build.version.release), and Check Security Patch Level (getprop ro.build.version.security_patch). Commands execute on devices via Runtime.exec() with 8-second timeout, capturing stdout/stderr for verification. Backend validation uses secure token-based parsing to prevent command injection, restricting jobscheduler to SystemUpdateService only and getprop to OS version properties only. Supports AOSP-based devices with Device Owner privileges. Non-interactive execution with real-time result tracking and CSV export.

### System Design Choices
- **Async SQLAlchemy**: For non-blocking I/O.
- **Connection Pooling**: Production-validated configuration with health monitoring (75 base + 75 overflow = 150 total connections).
- **Partition Management**: Daily partitions with automated lifecycle.
- **Dual-Write Pattern**: Transactional writes for fast reads.
- **Deduplication**: 10-second bucketing for heartbeats.
- **WebSocket Architecture**: Centralized management.
- **Event Retention Policies**: 90-day heartbeat retention.
- **Performance Metrics**: Comprehensive latency tracking, pool utilization gauges, queue metrics.
- **Rate Limiting**: Configurable IP-based rate limiting.
- **Registration Queue**: Semaphore-based queue limiting concurrent device registrations to 15 maximum to prevent connection pool saturation during bulk deployments. Tracks queue depth, wait time, and active registration count via Prometheus metrics.
- **OTA Cohorting**: Deterministic SHA-256-based device cohorting for staged rollouts.
- **OTA Safety**: Wi-Fi-only downloads, battery thresholds, call-state checking.
- **Bulk Delete Architecture**: Device selection snapshots, background purge workers with PostgreSQL advisory locks.
- **APK Build Registry**: Admin-scoped API endpoints for CI integration with Replit Object Storage, handling metadata registration, file uploads, downloads, and deletions.

## External Dependencies
- **PostgreSQL**: Primary database.
- **FastAPI**: Backend Python web framework.
- **Next.js**: Frontend React framework.
- **shadcn/ui**: Frontend UI component library.
- **Alembic**: Database migration tool.
- **Firebase Cloud Messaging (FCM)**: For command dispatch.
- **GitHub Actions**: For Android Agent CI/CD.
- **Replit Mail**: Email service for notifications.
- **Replit Object Storage**: Native Python SDK for persistent APK file storage.
- **Room Database**: SQLite-based persistent storage for Android agent queue.