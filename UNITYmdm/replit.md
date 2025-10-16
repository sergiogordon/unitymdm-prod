# UNITYmdm System

## Overview
UNITYmdm is a lightweight Mobile Device Management (MDM) system for monitoring Android 13+ devices. Its core function is to provide real-time device status visibility and dispatch immediate Discord alerts for critical events like devices going offline or low battery. The system offers configurable monitoring of any Android app's activity (default: Speedtest). Enrollment is flexible, supporting both ADB automated scripts and QR code scanning. The project delivers a robust, user-friendly solution for managing Android device fleets with real-time actionable insights and remote control capabilities, designed for easy community deployment with a Replit-first approach. Released under the MIT License to encourage open-source collaboration and commercial use.

## User Preferences
- I prefer simple language and clear, concise explanations.
- I appreciate detailed explanations when introducing new concepts or complex changes.
- I want an iterative development approach, with frequent communication and opportunities for feedback.
- Please ask for my approval before implementing any major architectural changes or significant feature additions.
- Ensure that any changes made to the codebase are well-documented and easy to understand.
- Do not make changes to the `/dashboard-backup/` folder.
- I expect the agent to maintain a high standard of code quality, including type safety and adherence to best practices.
- Do not reference specific use cases (like mining) in public-facing documentation - keep language generic for broader appeal.

## System Architecture

### UI/UX Decisions
The dashboard features an Apple-esque minimal design using `shadcn/ui` (new-york style, neutral theme) with light/dark mode, a sticky blur header, and real-time WebSocket updates. It includes KPI stat cards with semantic colors, a paginated device table (25 per page) with status indicators, and a responsive design. Accessibility, including ARIA support and keyboard navigation, is prioritized. All timestamps are localized to the user's browser time.

### Technical Implementations
- **Backend**: Python FastAPI, SQLAlchemy 2.0 (ORM), and Pydantic for data validation. Uses SQLite for development and PostgreSQL for production. It handles device registration, heartbeats, Discord alerts, FCM push notifications, and WebSocket connections for real-time updates.
- **Frontend**: Next.js 15.2.4 (App Router), TypeScript 5, and Tailwind CSS 4.1. Next.js API routes proxy requests to the FastAPI backend. WebSocket is used for real-time device updates.
- **Android Agent**: A Kotlin foreground service with a 5-minute heartbeat. It uses `UsageStatsManager` for app detection, encrypted credential storage, and boot persistence. Enrollment via QR code and ADB is supported. FCM is used for remote wake/ping. It includes a self-watchdog, crash recovery, `PARTIAL_WAKE_LOCK`, and `AlarmManager` for reliable heartbeats. Collects hardware telemetry. Remote control leverages `ScreenCaptureService`, `RemoteControlAccessibilityService`, `WebSocketClient`, and `DeviceOwnerPermissionManager` for permission auto-grants.
- **FCM Push Notifications**: Utilized for remote device ping/wake functionality and delivering high-priority messages.
- **Real-time Updates**: WebSocket connections broadcast device updates instantly upon heartbeat reception.
- **Performance Optimizations**: Database indexing, pagination, and a dedicated metrics endpoint.
- **Deployment**: Designed for easy community deployment with a Replit-first approach, offering one-click fork/remix, built-in PostgreSQL, automatic HTTPS, and secret management. Supports Docker for advanced self-hosting.

### Feature Specifications
- **Real-time Monitoring**: Dashboard with instant updates and manual refresh.
- **App Monitoring**: Tracks a configurable app's foreground activity (default: Speedtest).
- **Flexible App Display**: Two-field monitored app system separates visual display name (`monitored_app_name`) from actual package tracking (`monitored_package`). Allows showing "Unity" as the app name while monitoring `org.zwanoo.android.speedtest` for testing, with seamless transition to Unity package when available. Dashboard utilities dynamically use configured package for all lookups, filters, and stats.
- **Enrollment**: Supports QR code and ADB automated script, including Device Owner provisioning.
- **Device Owner Mode**: Comprehensive documentation explaining Android security requirements (factory reset prerequisite, no user accounts, technical rationale).
- **ADB Script Transparency**: Complete documentation of all device modifications (settings changes, disabled apps, permissions granted, Device Owner setup).
- **Carrier Customization**: Instructions for adapting Verizon-optimized script to other carriers using Replit Agent or ChatGPT.
- **Device Management**: Allows device deletion/unenrollment, including bulk operations.
- **Alerting**: Discord alerts for offline devices (>15 minutes) and low battery (<15%).
- **Device Telemetry**: Collects battery, RAM, network info, hardware details, APK version, and monitored app status.
- **Security**: Admin key for QR generation; delete operations require authentication; APK downloads require device token.
- **Remote Ping/Wake**: Sends high-priority FCM notifications for device wake-up and diagnostics.
- **Ring Device**: Triggers visual/audible alerts via FCM.
- **ADB Setup Page**: Generates automated bash scripts for installation, permissions, and enrollment. Scripts auto-download the latest APK from the backend using admin key authentication, eliminating manual APK downloads.
- **Device Alias Editing**: Inline editing in the dashboard.
- **Activity Timeline**: Device drawer displays chronological event history.
- **Event Retention**: 24-hour retention with hourly cleanup.
- **Remote APK Deployment**: APK version management, upload, secure downloads with integrity validation, and fleet-wide updates with real-time progress.
- **GitHub Actions APK Building**: Automated APK build pipeline without Android Studio. Users connect Replit to GitHub, configure Firebase credentials, generate signing keys, and push changes. GitHub Actions automatically builds, signs, and uploads APKs to the dashboard for deployment.
- **APK Download from Dashboard**: Web-based APK download feature allowing authenticated users to download any APK version directly from the APK Management page for local ADB installations.
- **Remote Control & Screen Streaming**: Live screen viewing (720p JPEG @ ~10 FPS). Interactive canvas for tap, swipe, text input, navigation keys. Includes real-time FPS/latency and fullscreen.
- **Clipboard Sync**: Bidirectional synchronization between desktop dashboard and Android devices via screen viewer.
- **Remote App Launcher**: Launch any installed app remotely on selected devices via FCM push notifications. Dashboard UI allows multi-device selection and package name input (e.g., com.speedtest.androidspeedtest). Uses Android's PackageManager to launch apps to their main activity.
- **Device Restart Capabilities**: Remote restart functionality for troubleshooting and maintenance. Features include:
  - **Hard Restart (Reboot)**: Full device reboot via DevicePolicyManager (requires Device Owner mode). 3-second delay before reboot with confirmation dialog warning about interruption to all device functions
  - **Soft Restart (App Restart)**: App-only restart using AlarmManager scheduling and process kill. Clean service shutdown with automatic MonitorService relaunch in ~10 seconds
  - **Dashboard UI**: Color-coded buttons (red for reboot, yellow for app restart) with detailed confirmation dialogs explaining each restart type
  - **Multi-device Support**: Apply restart commands to multiple selected devices simultaneously via FCM push notifications
  - **Auto-resume Monitoring**: BootReceiver handles RESTART_APP intent alongside BOOT_COMPLETED to automatically restart MonitorService after both restart types
- **Battery Optimization Management**: Centralized battery whitelist manager in dashboard to prevent Android from killing critical apps. Features include:
  - **Dynamic Whitelist**: Add/remove apps (package names) that should be exempt from battery optimization and Doze mode
  - **ADB Integration**: Generated enrollment scripts automatically include all whitelisted apps with battery exemption commands
  - **Fleet Management**: Apply whitelist to all online devices via FCM push notifications
  - **Device Optimization Page**: Displays ADB script modifications, manages battery whitelist, and provides fleet-wide controls
  - **Android Self-Healing**: Android app fetches server whitelist on startup and auto-applies exemptions for persistent protection
- **Demo Mode**: Interactive demo environment for GitHub visitors and potential users. Features include:
  - **One-Click Access**: "Access Demo" button on login page instantly loads dashboard with mock data
  - **Realistic Mock Data**: 12 varied demo devices with authentic states, metrics, APK versions, and activity timelines
  - **Full Feature Exploration**: All dashboard pages work with simulated API responses (200-500ms delays for realism)
  - **Visual Demo Banner**: Prominent gradient banner shows demo status with "Exit Demo" button
  - **Zero Backend Dependency**: Completely client-side demo mode for easy community exploration
  - **Clean Separation**: Demo token detection in API routes ensures production code remains untouched
- **MIT License**: Open-source license enabling unrestricted use, modification, and commercial deployment.

### System Design Choices
- **Two-Workflow Architecture**: Separates backend (FastAPI) and frontend (Next.js) processes.
- **API Integration**: Next.js API routes proxy requests to the FastAPI backend.
- **Modularity**: UI components are designed for modularity.
- **Security Model**: Designed for self-hosted/private deployments; admin key used in enrollment.

## External Dependencies

- **FastAPI**: Python web framework.
- **SQLAlchemy 2.0**: Python ORM.
- **Pydantic**: Python data validation.
- **Next.js 15.2.4**: React framework.
- **TypeScript 5**: Type-safe JavaScript.
- **Tailwind CSS 4.1**: CSS framework.
- **shadcn/ui**: UI component library.
- **date-fns**: JavaScript date utility.
- **Sonner**: Toast notification library.
- **ZXing**: QR code scanning library (Android).
- **Discord Webhooks**: For alerts.
- **Firebase Cloud Messaging (FCM)**: For push notifications.