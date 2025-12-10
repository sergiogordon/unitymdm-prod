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
The frontend, built with Next.js and shadcn/ui, offers a modern, responsive interface for administrative tasks such as token management, script generation, and device status tracking. It includes a global settings drawer and APK deployment page with version filtering.

### Technical Implementations
- **Backend**: FastAPI, asynchronous programming, SQLAlchemy.
- **Frontend**: Next.js.
- **Real-time Communication**: WebSockets for live device updates and command execution.
- **Authentication**: JWT for users, bcrypt for device tokens, HMAC SHA-256 for command dispatch, X-Admin-Key for enrollment.
- **User Management**: Self-service registration, profile management, and password reset.
- **Android Agent**: Dedicated Android application with automated CI/CD and Device Owner Mode.
- **Zero-Tap Enrollment v2**: Production-hardened provisioning with simplified authentication and one-liner enrollment commands, including bloatware removal and system tweaks.
- **Device Management**: Real-time heartbeat monitoring, battery/memory tracking, remote command execution, auto-relaunch, offline detection, and bulk device deletion.
- **APK Management**: Admin dashboard for managing CI-built APKs, including chunked uploads, version tracking, and filtering for targeted deployments.
- **Remote Execution**: Comprehensive system with FCM and restricted Shell command execution, supporting multiple targeting modes, dry-run previews, and real-time result tracking. Includes presets for OS updates and other device actions.
- **WiFi Auto-Connect**: Centralized WiFi configuration management with FCM-based credential distribution to devices.
- **Remote OS Updates**: Fleet-wide Android system update management via shell command presets.

### System Design Choices
- **Database**: PostgreSQL with partitioned time-series tables, dual-write fast-read architecture, and 10s heartbeat deduplication.
- **Performance**: O(1) device status lookups, optimized heartbeat processing, and connection pooling.
- **Observability**: Structured JSON logging, Prometheus-compatible metrics, and connection pool monitoring.
- **Security**: bcrypt hashing, HMAC SHA-256, JWT, IP-based rate limiting, and audit tracking.
- **Operational Tooling**: Load testing infrastructure, acceptance test suite, automated maintenance jobs, and bulk delete architecture with background purge workers.
- **Scalability**: Registration queue with semaphore-based limiting, and optimized setup checks for high load.
- **Reliability**: Android agent hardening with persistent Room database-backed queue, network resilience, power management awareness, and dual-key HMAC SHA-256 validation for FCM commands.

## External Dependencies
- **PostgreSQL**: Primary database.
- **FastAPI**: Backend Python web framework.
- **Next.js**: Frontend React framework.
- **shadcn/ui**: Frontend UI component library.
- **Alembic**: Database migration tool.
- **Firebase Cloud Messaging (FCM)**: For command dispatch.
- **GitHub Actions**: For Android Agent CI/CD.
- **Replit Mail**: Email service for notifications.
- **Replit Object Storage**: For persistent APK file storage.
- **Room Database**: SQLite-based persistent storage for Android agent queue.