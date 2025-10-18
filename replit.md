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
- **Authentication**: JWT for users, bcrypt for device tokens, HMAC SHA-256 for secure command dispatch.
- **Android Agent**: Dedicated Android application with an automated CI/CD pipeline (GitHub Actions) for secure deployment.
- **Zero-Touch Enrollment**: Secure provisioning via single-use tokens and server-generated ADB scripts.
- **Persistence**: Partitioned heartbeat storage (90-day retention), device_last_status for O(1) reads, automated archival with SHA-256 checksums.
- **Observability**: Structured JSON logging, Prometheus-compatible metrics with latency histograms, connection pool monitoring.

### Feature Specifications
- **Core Control Loop**: Secure device registration, heartbeat processing, FCM command dispatch, action result tracking, and HMAC signature validation.
- **Device Management**: Real-time heartbeat monitoring, battery/memory tracking, remote command execution, auto-relaunch, and offline detection.
- **Alert System**: Automated alerting for offline devices (>12m), low battery (<15%), and Unity app down with Discord webhook integration, deduplication, rate limiting, and optional auto-remediation via FCM.
- **Security**: bcrypt hashing, HMAC SHA-256, JWT, IP-based rate limiting, and audit tracking.
- **Performance Optimization**: Database partitioning, dual-write fast reads, connection pool monitoring, deduplication bucketing. Target SLIs: p95 <150ms, p99 <300ms for 2,000 devices.
- **Operational Tooling**: Load testing infrastructure (2,000 devices with realistic jitter), acceptance test suite, pool health monitoring, automated maintenance jobs with advisory locks.
- **Android Agent CI/CD**: Automated build, sign, verify, and upload of APKs.
- **Android Agent Runtime**: Device Owner Mode support, HMAC-validated FCM command execution, action result posting with exponential backoff, 5-minute heartbeat intervals, structured logging, and reliability features (persistent queue, network monitoring, power-aware retries).
- **OTA Updates (Milestone 4)**: Secure fleet-wide Android agent updates with one-click promotion, staged rollouts (1%-100%), deterministic device cohorting, rollback capability, and comprehensive adoption telemetry. Devices poll `/v1/agent/update` on startup, every 6 hours, or immediately via FCM nudge. Includes SHA-256 verification, signer fingerprint validation, Wi-Fi-only constraints, and safety controls (battery, network conditions).

### System Design Choices
- **Async SQLAlchemy**: For non-blocking I/O and improved concurrency.
- **Connection Pooling**: Production-validated configuration (100 max connections vs 450 Postgres limit) with health monitoring.
- **Partition Management**: Daily partitions with automated lifecycle (create → archive → drop), metadata tracking, VACUUM optimization.
- **Dual-Write Pattern**: Transactional writes to both partitioned heartbeats and device_last_status for fast reads, with hourly reconciliation.
- **Deduplication**: 10-second bucketing prevents duplicate writes, reduces storage by 20-30%.
- **WebSocket Architecture**: Centralized management for real-time communication.
- **Event Retention Policies**: 90-day heartbeat retention, automated archival with SHA-256 integrity checks.
- **Performance Metrics**: Comprehensive latency tracking (p95/p99), pool utilization gauges, Prometheus-compatible exposition.
- **Rate Limiting**: Configurable IP-based rate limiting.
- **OTA Cohorting**: Deterministic SHA-256-based device cohorting ensures stable, reproducible rollout percentages without per-device state.
- **OTA Safety**: Wi-Fi-only downloads, battery thresholds, and call-state checking prevent disruptive updates during critical device usage.

### Reliability Features (Milestone 5)
The Android agent includes comprehensive reliability hardening to ensure field operation under poor network conditions and aggressive power management:

- **Persistent Queue**: Room database-backed queue for unsent heartbeats and action-results that survives crashes and reboots. Queued items are retained until successfully delivered or expired (24h TTL for action-results).
- **Network Resilience**: NetworkCallback monitors connectivity state changes (wifi/cellular/offline) and triggers immediate queue drain when network becomes validated. Exponential backoff with full jitter (2s base, 5min cap) prevents overwhelming the server during network instability.
- **Power Management**: On startup, verifies Device Owner status and battery whitelist. In Device Owner mode, confirms Doze exemption and unrestricted battery access. Pauses non-essential retries when battery drops below 10% and not charging.
- **Queue Management**: Implements size limits (500 items, 10MB), prunes old heartbeats first (never prunes action-results), and coalesces duplicate heartbeats within the same 10s dedupe bucket.
- **Enhanced Observability**: Heartbeat payloads include `power_ok`, `doze_whitelisted`, and `net_validated` flags. Structured logs track queue operations (`queue.enqueue`, `queue.drain`, `queue.prune`), network changes (`net.change`, `net.regain`), retry scheduling (`retry.schedule`), and delivery outcomes (`deliver.ok`, `deliver.fail`).
- **Startup Recovery**: On service start or boot, automatically drains pending queue items within 5 seconds, ensuring no data loss from crashes or restarts.

## External Dependencies
- **PostgreSQL**: Primary database.
- **FastAPI**: Backend Python web framework.
- **Next.js**: Frontend React framework.
- **shadcn/ui**: Frontend UI component library.
- **Alembic**: Database migration tool.
- **Firebase Cloud Messaging (FCM)**: For command dispatch to devices.
- **GitHub Actions**: For Android Agent CI/CD.
- **Replit Mail**: Email service for notifications.
- **Room Database**: SQLite-based persistent storage for Android agent queue.