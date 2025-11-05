# NexMDM - Enterprise Mobile Device Management Platform

<p align="center">
  <strong>Production-ready MDM solution for managing 500-2,000 Android devices with real-time monitoring, remote control, and zero-touch deployment</strong>
</p>

<p align="center">
  <a href="#-deploy-on-replit">Deploy on Replit</a> •
  <a href="#-features">Features</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-documentation">Documentation</a>
</p>

---

## 🚀 Deploy on Replit

Get your own NexMDM instance running in minutes! This project is optimized for deployment on Replit with automatic configuration.

### **Step 1: Remix This Project**

1. **Click the "Remix" button** at the top of this Repl
2. This creates your own copy of NexMDM that you can customize and deploy

### **Step 2: Set Up Integrations**

NexMDM requires three Replit integrations. Click the **Tools** panel (🔧) in the sidebar, then add:

#### **PostgreSQL Database** (Required)
- Click **Add Integration** → Search "PostgreSQL"
- Click **Set up** to create your database
- No additional configuration needed - connection details are auto-configured

#### **Object Storage** (Required)
- Click **Add Integration** → Search "Object Storage"
- Click **Set up** to enable APK storage
- Used for storing Android agent APK files

#### **ReplitMail** (Optional but recommended)
- Click **Add Integration** → Search "ReplitMail"
- Click **Set up** to enable email notifications
- Used for password reset and alert emails

### **Step 3: Configure Secrets**

Click the **Secrets** tab (🔒) in the sidebar and add these environment variables:

| Secret Name | Description | Example | Required |
|------------|-------------|---------|----------|
| `ADMIN_KEY` | Admin API key (min 16 chars) | `your-secure-admin-key-here` | ✅ Yes |
| `SESSION_SECRET` | JWT session secret | `your-random-secret-string` | ✅ Yes |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Firebase service account JSON for FCM | `{"type": "service_account"...}` | ✅ Yes (for push notifications) |
| `DISCORD_WEBHOOK_URL` | Discord webhook for alerts | `https://discord.com/api/webhooks/...` | ⚠️ Optional |

**How to get Firebase credentials:**
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Create a new project or select existing
3. Navigate to **Project Settings** → **Service Accounts**
4. Click **Generate New Private Key**
5. Copy the entire JSON content into `FIREBASE_SERVICE_ACCOUNT_JSON`

### **Step 4: Run the Application**

1. Click the **Run** button at the top
2. Wait for both backend and frontend to start (30-60 seconds)
3. The app will open in the Webview pane
4. **Default login:** Check the backend console for auto-generated admin credentials

### **Step 5: Deploy to Production**

1. Click the **Deploy** button in the top right
2. Choose **Autoscale Deployment** (recommended for most use cases)
3. Click **Deploy** and wait for deployment to complete
4. Your MDM will be live at `https://your-repl-name.replit.app`

**Important:** After deployment, update your Firebase project with the production URL for FCM to work correctly.

---

## ✨ Features

### **Device Management**
- 📱 **Zero-Touch Enrollment** - One-liner scripts for Windows/Linux/Mac via ADB
- 🔍 **Real-Time Monitoring** - Live device status, battery levels, memory usage
- 📊 **Fleet Dashboard** - KPI tiles, device filtering, pagination
- 🔄 **WebSocket Updates** - Instant notifications without page refresh

### **Remote Control**
- 🎯 **Remote Execution** - Send FCM commands (ping, ring, reboot, launch app)
- 💻 **Shell Commands** - Execute allowed shell commands across fleet
- 📲 **Bulk App Launch** - Deploy apps to entire fleet or filtered groups
- 🌐 **WiFi Auto-Connect** - Push WiFi credentials to devices remotely

### **APK Management**
- 📦 **APK Upload & Deploy** - Web-based APK management with version tracking
- 🤖 **CI/CD Integration** - Automated Android builds via GitHub Actions
- 🔐 **Secure Storage** - APKs stored in Replit Object Storage
- 📈 **Installation Tracking** - Monitor deployment status per device

### **Security & Alerts**
- 🔒 **Multi-Layer Authentication** - JWT for users, bcrypt for devices, HMAC for commands
- 🚨 **Discord Alerts** - Automated notifications for offline devices, low battery
- 📧 **Email Notifications** - Password reset, critical events via ReplitMail
- 🛡️ **Rate Limiting** - IP-based protection against abuse

### **Performance & Scalability**
- ⚡ **Dual-Write Architecture** - O(1) device lookups with fast-read pattern
- 🗄️ **Partitioned Tables** - Time-series data with 2-day retention
- 📉 **Connection Pooling** - 150 concurrent connections support
- 🎯 **Predictable Latency** - p95 <150ms, p99 <300ms response times

---

## 🏗️ Architecture

### **Backend (FastAPI + Python)**
- RESTful API with async SQLAlchemy
- PostgreSQL with partitioned time-series tables
- WebSocket manager for real-time updates
- FCM v1 integration for push notifications
- HMAC-validated command dispatch
- Structured JSON logging with Prometheus metrics

### **Frontend (Next.js + React)**
- Modern admin dashboard with shadcn/ui components
- Real-time device monitoring with WebSocket integration
- Global settings management via React Context
- Responsive design with dark mode support
- Device drawer with detailed metrics and actions

### **Android Agent (Kotlin)**
- Device Owner Mode for enterprise management
- Room database-backed command queue
- HMAC signature validation for security
- Network resilience with exponential backoff
- 5-minute heartbeat reporting
- FCM message handling for remote control

---

## 📖 Quick Start

### **Access the Dashboard**

1. Open your Repl's webview
2. Click **"Create Account"** on the login page
3. Register with your email and password
4. Login and access the dashboard

### **Enroll Your First Device**

1. Navigate to **ADB Setup** in the sidebar
2. Enter a device alias (e.g., "Test-Device-01")
3. Choose your platform (Windows or Linux/Mac)
4. Copy the one-liner enrollment script
5. Connect Android device via USB with ADB enabled
6. Paste and run the script in your terminal
7. Device appears in dashboard within 30 seconds

### **Deploy an APK**

1. Navigate to **APK Management** page
2. Click **Upload APK** button
3. Select your APK file and fill in version details
4. Click **Upload** and wait for processing
5. Click **Deploy** next to the uploaded APK
6. Select target devices and confirm
7. Devices auto-download and install within minutes

### **Execute Remote Commands**

1. Navigate to **Remote Execution** page
2. Choose **FCM** or **Shell** mode
3. Select preset command or enter custom
4. Choose targeting mode (entire fleet, filtered, or specific devices)
5. Preview targets with **Dry Run**
6. Click **Execute** and monitor real-time results

---

## 🔧 Technology Stack

### **Backend**
- **FastAPI** - High-performance async Python framework
- **SQLAlchemy** - ORM with async support
- **PostgreSQL** - Production database with partitioning
- **Uvicorn** - ASGI server
- **Pydantic** - Data validation
- **PyJWT** - JWT authentication
- **bcrypt** - Password hashing

### **Frontend**
- **Next.js 14** - React framework with App Router
- **TypeScript** - Type-safe JavaScript
- **shadcn/ui** - Modern component library
- **Tailwind CSS** - Utility-first styling
- **date-fns** - Date manipulation
- **WebSocket** - Real-time updates

### **Android**
- **Kotlin** - Modern Android development
- **Room** - SQLite database with persistence
- **Firebase Cloud Messaging** - Push notifications
- **OkHttp** - HTTP client
- **Gson** - JSON parsing

### **Infrastructure**
- **Replit** - Hosting and deployment
- **PostgreSQL (Neon)** - Managed database
- **Object Storage** - APK file storage
- **ReplitMail** - Transactional emails
- **GitHub Actions** - CI/CD for Android builds

---

## 📱 Android Agent CI/CD

NexMDM includes automated Android agent builds via GitHub Actions.

### **Features**
- ✅ Automatic builds on every commit to `main`
- ✅ Version-tagged releases (`v*` tags)
- ✅ Secure APK signing with release keystore
- ✅ Debug APKs auto-uploaded to backend
- ✅ Release APKs stored as GitHub artifacts
- ✅ APK signature verification
- ✅ SHA256 checksums for integrity
- ✅ Reproducible builds with Gradle caching

### **Required GitHub Secrets**

Configure in `Settings > Secrets and variables > Actions`:

| Secret | Description | Example |
|--------|-------------|---------|
| `ANDROID_KEYSTORE_BASE64` | Base64-encoded release keystore | `MIIKe...` |
| `KEYSTORE_PASSWORD` | Keystore password | `your_store_pass` |
| `ANDROID_KEY_ALIAS` | Key alias name | `nexmdm` |
| `ANDROID_KEY_ALIAS_PASSWORD` | Key password | `your_key_pass` |
| `BACKEND_URL` | Backend API URL | `https://your-repl.replit.app` |
| `ADMIN_KEY` | Backend admin API key | `your_admin_key` |

### **Setup Steps**

1. **Generate keystore:**
   ```bash
   keytool -genkey -v -keystore release.keystore -alias nexmdm \
     -keyalg RSA -keysize 2048 -validity 10000
   ```

2. **Encode to base64:**
   ```bash
   base64 -w 0 release.keystore > release.keystore.b64
   ```

3. **Add all 6 secrets to GitHub repository**

4. **Trigger build:**
   ```bash
   git push origin main
   # Or tag a release:
   git tag v1.0.0
   git push origin v1.0.0
   ```

**Full documentation:** [ANDROID_CI_SETUP.md](./ANDROID_CI_SETUP.md)

---

## 📚 Documentation

- **[Android CI/CD Setup Guide](./ANDROID_CI_SETUP.md)** - Complete CI pipeline documentation
- **[QR Enrollment Guide](./UNITYmdm/android/QR_ENROLLMENT_GUIDE.md)** - Device enrollment process
- **[Build Instructions](./UNITYmdm/android/BUILD_INSTRUCTIONS.md)** - Manual build steps
- **[WiFi Implementation Guide](./WIFI_ANDROID_IMPLEMENTATION.md)** - Android WiFi integration

---

## 🚨 Troubleshooting

### **Database Connection Issues**
- Verify PostgreSQL integration is set up in Replit
- Check `DATABASE_URL` secret is auto-populated
- Restart the backend workflow

### **Frontend Not Loading**
- Ensure both Frontend and Backend workflows are running
- Check browser console for errors (F12)
- Verify `REPLIT_DEV_DOMAIN` or `REPLIT_DOMAINS` is set

### **FCM Commands Not Working**
- Verify `FIREBASE_SERVICE_ACCOUNT_JSON` is valid JSON
- Check Firebase project has FCM API enabled
- Ensure Android agent has correct `google-services.json`

### **Device Enrollment Fails**
- Verify device has ADB debugging enabled
- Check `ADMIN_KEY` matches between script and backend
- Ensure device has internet connectivity
- Review backend logs for enrollment errors

### **APK Upload Fails**
- Verify Object Storage integration is set up
- Check APK file is valid (not corrupted)
- Ensure file size is under storage limits
- Review backend logs for upload errors

### **Email Notifications Not Sending**
- Verify ReplitMail integration is set up
- Check recipient email is valid
- Review backend logs for email service errors

---

## 🔄 Typical Workflow

1. **Deploy NexMDM** on Replit using Remix button
2. **Configure integrations** (PostgreSQL, Object Storage, ReplitMail)
3. **Add secrets** (ADMIN_KEY, SESSION_SECRET, Firebase credentials)
4. **Create admin account** via signup page
5. **Enroll devices** using ADB one-liner scripts
6. **Monitor fleet** via real-time dashboard
7. **Deploy APKs** through web interface or CI/CD
8. **Execute commands** remotely via FCM or shell
9. **Receive alerts** via Discord/email for issues
10. **Scale up** as needed with Replit deployment options

---

## 🌟 Use Cases

- **Enterprise Device Management** - Manage company-owned Android devices
- **Kiosk Mode Deployments** - Control devices in retail, hospitality, events
- **Field Service Management** - Monitor technician devices remotely
- **Education** - Manage student/classroom tablets
- **Digital Signage** - Control display devices across locations
- **Testing Farms** - Automate app testing across device fleet

---

## 🤝 Contributing

Contributions are welcome! Here's how:

1. **Fork the repository** on GitHub
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Make your changes** and test thoroughly
4. **Commit your changes** (`git commit -m 'Add amazing feature'`)
5. **Push to the branch** (`git push origin feature/amazing-feature`)
6. **Open a Pull Request** with detailed description

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

### **What this means:**
- ✅ Free to use for personal or commercial projects
- ✅ Modify and distribute as needed
- ✅ Private use allowed
- ⚠️ Provided "as-is" without warranty
- ℹ️ License and copyright notice must be included

---

## 🆘 Support

### **Getting Help**

- **Documentation**: Check the [docs folder](./docs) for detailed guides
- **Issues**: Open a GitHub issue for bugs or feature requests
- **Discussions**: Use GitHub Discussions for questions

### **Common Issues**

**"ADMIN_KEY is not set!"**
- Add `ADMIN_KEY` secret in Replit Secrets tab
- Minimum 16 characters recommended
- Restart backend after adding

**"Database connection failed"**
- Set up PostgreSQL integration in Replit
- Verify `DATABASE_URL` is populated
- Check database is running

**"CI build fails"**
- Verify all 6 GitHub secrets are configured
- Check keystore base64 has no line breaks
- Review GitHub Actions logs for details

**"Device not appearing in dashboard"**
- Check device internet connectivity
- Verify enrollment script used correct ADMIN_KEY
- Review backend logs for registration errors
- Ensure device completed all enrollment steps

---

## 📊 Performance Benchmarks

- **Concurrent Devices**: 500-2,000 (tested)
- **API Response Time**: p95 <150ms, p99 <300ms
- **WebSocket Connections**: 500+ simultaneous
- **Database Queries**: Optimized with partitioning and indexing
- **Heartbeat Processing**: <10ms per device (deduplicated)
- **APK Upload**: Supports files up to 100MB
- **FCM Dispatch**: 20 messages/second (rate limited)

---

## 🗺️ Roadmap

### **Completed**
- ✅ Core device management
- ✅ Real-time monitoring
- ✅ Zero-touch enrollment
- ✅ APK management
- ✅ Remote execution
- ✅ Bulk operations
- ✅ WiFi auto-connect
- ✅ Discord/email alerts
- ✅ CI/CD for Android agent

### **Planned**
- 🔲 Geofencing and location tracking
- 🔲 Custom command templates
- 🔲 Advanced reporting and analytics
- 🔲 Multi-tenant support
- 🔲 Role-based access control (RBAC)
- 🔲 Device grouping and tags
- 🔲 Scheduled command execution
- 🔲 Mobile app for admins

---

<p align="center">
  Made with ❤️ for the Android MDM community
</p>

<p align="center">
  <strong>Deploy your own instance today!</strong><br>
  Click the <strong>Remix</strong> button to get started
</p>
