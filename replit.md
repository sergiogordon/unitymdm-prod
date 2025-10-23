# MDM System - Compressed Overview

## Overview
This project is a production-ready, cloud-based Mobile Device Management (MDM) system for Android devices, designed to manage 500-2,000 concurrent devices. It provides robust backend control, real-time updates, and secure provisioning, complemented by a modern web frontend. Key capabilities include zero-touch enrollment, remote command execution, real-time device telemetry, secure device registration, heartbeat monitoring, FCM-based command dispatch, automated partition management, and comprehensive operational tooling. The system prioritizes scalability, performance, security, and operational excellence, aiming for predictable performance (p95 <150ms, p99 <300ms).

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
The frontend, built with Next.js and shadcn/ui, offers a modern, responsive interface for administrative tasks such as token management, script generation, and device status tracking.

### Technical Implementations
- **Backend**: FastAPI, asynchronous programming, SQLAlchemy, PostgreSQL.
- **Frontend**: Next.js.
- **Database**: PostgreSQL with partitioned time-series tables.
- **Performance**: Dual-write fast-read architecture with O(1) device status lookups and 10s deduplication.
- **Real-time Communication**: WebSockets for live device updates and command execution.
- **Authentication**: JWT for users, bcrypt for device tokens, HMAC SHA-256 for command dispatch, X-Admin-Key for enrollment.
- **Android Agent**: Dedicated Android application with automated CI/CD.
- **Zero-Tap Enrollment v2**: Production-hardened provisioning with simplified authentication (admin-key directly), JWT-authenticated script generation, comprehensive 9-step enrollment scripts with progress tracking and diagnostic logging, bloatware removal, and system optimization.
- **Persistence**: Partitioned heartbeat storage (90-day retention), device_last_status for O(1) reads, automated archival.
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

### System Design Choices
- **Async SQLAlchemy**: For non-blocking I/O.
- **Connection Pooling**: Production-validated configuration with health monitoring.
- **Partition Management**: Daily partitions with automated lifecycle.
- **Dual-Write Pattern**: Transactional writes for fast reads.
- **Deduplication**: 10-second bucketing for heartbeats.
- **WebSocket Architecture**: Centralized management.
- **Event Retention Policies**: 90-day heartbeat retention.
- **Performance Metrics**: Comprehensive latency tracking, pool utilization gauges.
- **Rate Limiting**: Configurable IP-based rate limiting.
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