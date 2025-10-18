# MDM System - Compressed Overview

## Overview
This project is a production-ready, cloud-based Mobile Device Management (MDM) system for Android devices. It offers robust backend control, real-time updates, and secure provisioning, complemented by a modern web frontend for administration. The system supports 100+ concurrent devices, providing zero-touch enrollment, remote command execution, and real-time device telemetry. Key features include secure device registration, heartbeat monitoring, FCM-based command dispatch, and an automated CI/CD pipeline for the Android agent. The system prioritizes scalability, security, and comprehensive device management capabilities.

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
- **Database**: PostgreSQL for primary data storage, optimized for time-series data with Alembic for migrations.
- **Real-time Communication**: WebSockets for live device updates and command execution.
- **Authentication**: JWT for users, bcrypt for device tokens, HMAC SHA-256 for secure command dispatch.
- **Android Agent**: Dedicated Android application with an automated CI/CD pipeline (GitHub Actions) for secure deployment.
- **Zero-Touch Enrollment**: Secure provisioning via single-use tokens and server-generated ADB scripts.
- **Persistence**: Optimized data models for FCM dispatches, APK downloads, device heartbeats, and enrollment tokens with retention policies.
- **Observability**: Structured JSON logging and Prometheus-compatible metrics for end-to-end visibility.

### Feature Specifications
- **Core Control Loop**: Secure device registration, heartbeat processing, FCM command dispatch, action result tracking, and HMAC signature validation.
- **Device Management**: Real-time heartbeat monitoring, battery/memory tracking, remote command execution, auto-relaunch, and offline detection.
- **Alert System**: Automated alerting for offline devices (>12m), low battery (<15%), and Unity app down with Discord webhook integration, deduplication, rate limiting, and optional auto-remediation via FCM.
- **Security**: bcrypt hashing, HMAC SHA-256, JWT, IP-based rate limiting, and audit tracking.
- **Performance**: Connection pooling, async database operations, and indexed queries for sub-100ms heartbeat processing.
- **Android Agent CI/CD**: Automated build, sign, verify, and upload of APKs.
- **Android Agent Runtime**: Device Owner Mode support, HMAC-validated FCM command execution, action result posting with exponential backoff, 5-minute heartbeat intervals, and structured logging.

### System Design Choices
- **Async SQLAlchemy**: For non-blocking I/O and improved concurrency.
- **Connection Pooling**: Efficient database connection management.
- **WebSocket Architecture**: Centralized management for real-time communication.
- **Event Retention Policies**: Automated data cleanup for performance.
- **Rate Limiting**: Configurable IP-based rate limiting.

## External Dependencies
- **PostgreSQL**: Primary database.
- **FastAPI**: Backend Python web framework.
- **Next.js**: Frontend React framework.
- **shadcn/ui**: Frontend UI component library.
- **Alembic**: Database migration tool.
- **Firebase Cloud Messaging (FCM)**: For command dispatch to devices.
- **GitHub Actions**: For Android Agent CI/CD.
- **Replit Mail**: Email service for notifications.