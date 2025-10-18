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
- **Monitoring**: Structured logging for all operations, including database interactions, performance metrics, and error tracking.

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