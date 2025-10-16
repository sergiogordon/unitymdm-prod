# UNITYmdm - Lightweight Mobile Device Management

A modern, self-hosted Mobile Device Management (MDM) system for monitoring and remotely controlling Android 13+ devices. Built specifically for managing fleets of dedicated devices with real-time monitoring, remote control, and fleet-wide app deployment.

[![Deploy on Replit](https://replit.com/badge)](https://replit.com/@SergioGordon/UNITYmdm?v=1)

## ⚠️ Important Notice for Unity Users

### Current System Status
All core functionality is **fully operational** including real-time monitoring, Discord alerts, device management, remote screen streaming, APK deployment, and fleet controls. However, **remote battery whitelist application** is currently limited due to Android security restrictions.

### Android Version Compatibility
**✅ Tested and optimized for Android 13+ (API 33) devices.** The system works on other Android versions, but you may need to customize battery optimization for your specific devices.

**Have Different Android Versions?** Just ask Replit Agent to adapt it for you:

**Example Prompts:**
- 💬 *"Adapt this system for Android 12 devices"*
- 💬 *"My Samsung Galaxy phones are running Android 11 - update the battery optimization to work with them"*
- 💬 *"Change the minimum Android version to Android 8 so I can use older phones"*
- 💬 *"The ADB script isn't working on my Motorola phones - fix the battery whitelist commands for Android 14"*

**That's it!** Replit Agent will automatically update the Android app configuration, battery optimization code, and ADB enrollment script to match your devices. No need to understand file paths or technical details.

**Core features (monitoring, APK deployment) work across all Android versions unchanged.**

### Battery Whitelist Limitation
- ✅ **ADB (Android Debug Bridge) Enrollment Script**: Successfully applies battery whitelist during initial device setup
- ❌ **Remote Application via FCM (Firebase Cloud Messaging)**: Not possible without root access (Android security prevents Device Owner apps from executing privileged shell commands)
- 📱 **Current Testing**: Uses Speedtest app as example; works perfectly when enrolled via ADB

### Deployment Options for Unity Users

**Option 1: Deploy Now (Recommended for Testing)**
- Fork and deploy UNITYmdm today to test all features with Speedtest
- When Unity APK becomes available:
  - Upload the Unity APK to your dashboard
  - Replit Agent will auto-update your ADB script with Unity package
  - Enroll new devices with battery whitelist automatically configured
- **Best for**: Users who want to test the system immediately and enroll Unity devices later

**⚠️ Important for Option 1 Users:**
- **Start with a few test devices first** - Don't deploy to your entire fleet immediately
- **When Unity APK is released**, you'll need to use ADB to configure battery optimization for Unity:
  - Unity must be set to **"Restricted"** battery mode to prevent Android's Doze/Battery Manager from killing the Unity service
  - This cannot be done remotely via FCM due to Android security restrictions
  - You'll need physical USB access to run the updated ADB enrollment script for Unity-specific battery optimization
- **Test thoroughly** with Speedtest before committing to Unity deployment

**Option 2: Wait for Unity APK**
- Wait until Unity APK is publicly available
- **This repo will be updated the same day Unity APK is released** with:
  - Unity APK included and ready to deploy
  - Pre-configured ADB script with battery whitelist for Unity
- Fork and deploy with Unity support ready out-of-the-box
- **Best for**: Users who only need Unity monitoring and can wait

### Important: Fork Independence
**⚠️ Once you fork/deploy this Repl, you won't receive automatic updates from this repository.** Each fork is an independent copy. While manual updates are technically possible via Git, they risk:
- Merge conflicts with your customizations
- Database schema breaking changes
- Configuration incompatibilities

**To get updates:** You'll need to fork the latest version fresh and manually migrate your settings/data.

## ✨ Features

### 📊 Real-Time Monitoring
- **Live Dashboard** - WebSocket-powered real-time device status updates
- **Device Telemetry** - Battery, RAM, network, hardware details, APK version
- **Activity Timeline** - Chronological event history for each device (30-day retention)
- **Smart Alerting** - Discord notifications for offline devices and low battery
- **App Detection** - Monitor specific app usage (configurable package name)

### 📦 APK Management & Deployment
- **Fleet-Wide Updates** - Deploy APKs to multiple devices with one click as long as they have wifi OR cellular data / internet
- **Real-Time Progress** - See download and installation progress for each device
- **Automated CI/CD** - GitHub Actions integration for auto-build and upload
- **Version Management** - Track APK versions and deployment status
- **Secure Downloads** - Token-authenticated device downloads with integrity validation

### 🔐 Device Enrollment
- **QR Code Enrollment** - Instant wireless enrollment via built-in QR scanner (**Not** **recommended** - can't enabled DeviceOwnerMode)
- **ADB One-Liner** - Automated bash script for bulk enrollment
- **Device Owner Mode** - Silent app installation and advanced permissions
- **Bloatware Removal** - Automatic disable of 27+ pre-installed apps
- **Power Management** - Complete disable of battery optimization for 24/7 reliability

### 🛠️ Management Tools
- **Device Aliases** - Inline editing of friendly device names
- **Bulk Operations** - Delete or manage multiple devices at once
- **Search & Filter** - Quickly find devices by name, status, or hardware
- **Clipboard Sync** - Copy/paste text between desktop and devices
- **Diagnostic Commands** - Troubleshoot devices with FCM diagnostic tools

### 🔄 Auto-Relaunch & App Monitoring
- **Flexible App Display** - Two-field system: display name (e.g., "Unity") + actual package name for tracking
- **Configurable App Monitoring** - Track any Android app by package name (Speedtest, Unity, or custom apps)
- **Auto-Relaunch** - Automatically restart monitored apps when they go down (works for any app)
- **Speedtest Pre-Installed** - Speedtest APK included for immediate testing and monitoring
- **Easy Unity Transition** - Display "Unity" as app name while monitoring Speedtest for testing, then seamlessly switch to Unity package when available
- **Per-Device Configuration** - Each device can monitor different apps with independent auto-relaunch settings

**Note**: While auto-relaunch works for any app, detection accuracy depends on app-specific telemetry. Speedtest provides notification-based detection. For Unity and other apps, the dashboard may show simplified running status until telemetry is enhanced.

## 📸 Screenshots

### Main Dashboard
The real-time monitoring dashboard provides instant visibility into your device fleet with KPI cards, status indicators, and activity filtering.

<img width="1376" height="813" alt="image" src="https://github.com/user-attachments/assets/9c849033-48a2-4dce-a6c9-a7082e567bff" />

### Device Drawer

<img width="1376" height="813" alt="image" src="https://github.com/user-attachments/assets/3e2a8759-2102-41fe-9bce-d66909798ed6" />



### APK Management
Upload, manage, and deploy APK files to your entire fleet with real-time progress tracking and version management.

<img width="1376" height="813" alt="image" src="https://github.com/user-attachments/assets/3b23b2bb-df2b-40c6-940f-5c1997ffeffe" />

### ADB Setup & Enrollment
Generate automated enrollment scripts with a single click. Scripts auto-download the latest APK and configure devices with all required permissions.

<img width="1376" height="813" alt="image" src="https://github.com/user-attachments/assets/9adc195c-12a8-434a-bcef-4e310918ddcc" />

### Remote Control
Live screen streaming with interactive controls for real-time device management and troubleshooting.

<img width="1376" height="813" alt="image" src="https://github.com/user-attachments/assets/ba28ca81-cfe9-474f-bb72-5a8c6e37392b" />


## 📋 Prerequisites

Before you begin, gather these requirements to ensure a smooth deployment:

### Required Setup
- ✅ **Replit Account** - [Sign up free](https://replit.com/signup) (deployment platform)
- ✅ **Firebase Project** - [Create project](https://console.firebase.google.com) (push notifications)
  - Download service account JSON file (needed for secrets)
  - Enable Firebase Cloud Messaging (FCM)
- ✅ **Android Device(s)** - Android 13+ with USB debugging enabled
- ✅ **ADB (Android Debug Bridge)** - Required for device enrollment
  - Mac: `brew install android-platform-tools`
  - Windows: [Download Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools)
  - Linux: `sudo apt install adb`

### Optional (But Recommended)
- 🔔 **Discord Webhook** - For device offline/battery alerts ([setup guide](https://support.discord.com/hc/en-us/articles/228383668))
- 🛠️ **GitHub Account** - For automated APK builds ([sign up](https://github.com/signup))

### Time Investment (First-Time Setup)

**Total: ~25-30 minutes** (breakdown below)

| Step | Time | Details |
|------|------|---------|
| Fork & Initial Setup | 5 min | Fork Repl, enable PostgreSQL |
| Firebase Configuration | 5-10 min | Create project, download JSON, enable FCM |
| Configure Secrets | 5 min | Add ADMIN_KEY, Firebase JSON, SERVER_URL |
| **APK Building** | **5-10 min** | **See details below** |
| First Device Enrollment | 3-5 min | Connect via USB, run ADB script |

**Subsequent enrollments**: ~30 seconds per device (bulk script)

### What to Expect

**Most Complex Step: Building the Android APK**

The APK build is the only technical hurdle, but we've made it as easy as possible:

**🎯 Option 1 (Recommended): GitHub Actions - Fully Automated**
- ✅ Pre-configured workflow already included in this repo
- ✅ Zero Android Studio or local setup required
- ✅ Build happens in the cloud automatically

**Setup once (5-10 minutes):**
1. Connect your Repl to GitHub (Replit's built-in Git integration)
2. Add 3 GitHub Secrets (Firebase JSON, signing keys)
3. Push code → APK builds and uploads to your dashboard automatically!

**After setup:** Every code change auto-builds APK and deploys to your dashboard.

**📱 Option 2: Manual Build with Android Studio**
- Requires Android Studio installation (~5GB download)
- Manual signing key generation
- Local APK compilation and upload
- Only use if GitHub Actions isn't an option

**Everything else is straightforward**: The rest of the deployment is copying/pasting credentials and clicking buttons. No coding or terminal commands required.

### Cost Breakdown
- **Replit Core**: $20/month (includes $25 credits monthly) - Required for 24/7 public deployment
- **Firebase**: Free tier (sufficient for 100+ devices)
- **Discord**: Free
- **GitHub Actions**: Free (2,000 build minutes/month included)
- **Total**: **~$20/month** (or $0 if Replit credits cover usage)

**💡 Pro Tips:**
- Test on Replit's **free tier first** - Works great for local development/testing
- Upgrade to **Core only when ready** for public deployment with custom domain
- Replit's $25/month credit usually **covers the $20 Core subscription**, making it effectively free if you don't exceed limits

---

## 🎨 Customizing with Replit Agent

**No technical skills needed!** Instead of manually editing code files, just tell Replit Agent what you want to change. It will automatically update the right files for you. I suggest trying / testing with 1 device if you have older or newer devices first and see if the compatability works with the current deployment or not -- then make changes if needed. 

### Common Customization Examples

**Android Compatibility:**
- 💬 *"Adapt this for Android 12 devices instead of Android 13"*
- 💬 *"My phones are running Android 11 - update the battery optimization code"*

**Carrier/Device Specific:** (Not necessary - but nice to have)
- 💬 *"Update the ADB script to remove AT&T bloatware phones instead of Verizon"* 
- 💬 *"Disable Samsung bloatware instead of generic Android apps"*
- 💬 *"The script isn't working on my Motorola devices - fix the battery whitelist commands"*

**Feature Customization:**
- 💬 *"Change the heartbeat interval from 5 minutes to 10 minutes"*
- 💬 *"Lower the battery alert threshold from 15% to 10%"*
- 💬 *"Send email alerts instead of Discord notifications"*
- 💬 *"Monitor a different app package instead of Speedtest"*

**Dashboard Changes:**
- 💬 *"Add a widget showing average device temperature"*
- 💬 *"Change the offline threshold from 15 minutes to 30 minutes"*
- 💬 *"Add a dark mode toggle to the dashboard"*

**That's it!** Replit Agent handles all the technical details - finding the right files, making the changes, and testing them. No need to understand code or file structures.

---

## 🚀 Quick Start (Replit)

The easiest way to deploy UNITYmdm is on Replit - no Docker, VPS, or complex setup required!

### 1. Fork This Repl
Click the **"Fork"** or **"Remix"** button to get your own copy.

### 2. Set Up Firebase (5 minutes)
1. Create a project at [Firebase Console](https://console.firebase.google.com)
2. Download the service account JSON file
3. Open it and copy ALL the contents (the entire `{...}` block)

### 3. Configure Secrets (2 minutes)
Click the 🔒 Secrets icon and add:
- `ADMIN_KEY` - Generate with: `openssl rand -base64 32`
- `FIREBASE_SERVICE_ACCOUNT_JSON` - Paste the entire JSON you copied above
- `SERVER_URL` - Your Repl URL (e.g., `https://unitymdm-you.repl.co`)
- `DISCORD_WEBHOOK_URL` (optional) - For Discord alerts

### 4. Enable PostgreSQL
Click the Database icon → Enable PostgreSQL. Done!

### 5. Run & Deploy
Click **"Run"** and you're live! Visit the dashboard to create your admin account.

**📖 Full deployment guide: [DEPLOYMENT.md](DEPLOYMENT.md)**

## 📦 Bulk Device Enrollment

Enrolling multiple devices? UNITYmdm makes it easy to onboard 10, 50, or 100+ devices efficiently with CSV-based bulk enrollment.

### How Bulk Enrollment Works (If the below is confusing - just ask Replit agent to do it for you :)  )

1. **Create a Device List** - Make a `devices.csv` file with your device names:
   ```csv
   alias,unity_package
   RackA-01,com.speedtest.androidspeedtest
   RackA-02,com.speedtest.androidspeedtest
   PhoneFarm-D01,com.speedtest.androidspeedtest
   Warehouse-K1,com.yourapp.package
   ```
   
   **📄 Quick Start**: Copy the template: `cp scripts/devices.csv.example scripts/devices.csv`

2. **Run the Bulk Script** - Automates enrollment for each device:
   ```bash
   export SERVER_URL="https://your-app.repl.co"
   export ADMIN_KEY="your-admin-key"
   cd scripts
   ./bulk_enroll.sh
   ```

3. **Connect Each Device** - The script pauses between devices:
   - Connect device via USB
   - Press Enter to enroll
   - Disconnect and connect next device
   - Repeat

### Device Naming Best Practices

Choose a naming convention that scales:

| Pattern | Example | Best For |
|---------|---------|----------|
| **Sequential** | `D01`, `D02`, `D03` | Simple numbering, easy to track |
| **Location-Based** | `NYC-Office-K1`, `Chicago-Warehouse-D05` | Geographic distribution |
| **Rack/Position** | `Rack1-Shelf2-D07`, `Cabinet-A-Phone-12` | Physical organization |
| **MAC-Based** | `Phone-A4F2` (last 4 of MAC) | Guaranteed uniqueness |

**💡 Pro Tip**: Aliases can be edited anytime in the dashboard! Start with simple names like D01-D50, then rename later based on actual deployment.

### Automation Options

**Semi-Automated (Default)**
- Interactive prompts between devices
- Safe for manual cable swapping
- Good for 10-50 devices

**Fully Automated (Advanced)**
- Edit `bulk_enroll.sh` to remove `read` prompts
- Use USB hubs for simultaneous connections
- Ideal for 100+ device deployments

### Example Workflows

**Scenario 1: Phone Farm (50 devices)**
```bash
# Generate CSV with D01 through D50
for i in {1..50}; do
  printf "D%02d,com.speedtest.androidspeedtest\n" $i >> devices.csv
done

# Run bulk enrollment
./bulk_enroll.sh
# Connect devices via USB hub, press Enter for each
```
```
Deploy with location-aware names, monitor by region in dashboard.

**Scenario 2: Rename After Deployment**
1. Enroll quickly as D01, D02, D03...
2. Deploy to physical locations
3. Edit aliases in dashboard: D01 → "MainEntrance-Kiosk", D02 → "Lobby-Display"

📖 **Detailed walkthrough**: See [DEPLOYMENT.md - Bulk Enrollment](DEPLOYMENT.md) for step-by-step guide with screenshots.

## 🏗️ Architecture

### Backend
- **FastAPI** - Python async web framework
- **SQLAlchemy 2.0** - ORM with PostgreSQL/SQLite support
- **Pydantic** - Data validation and settings management
- **WebSockets** - Real-time device status updates
- **Firebase Cloud Messaging (FCM)** - Push notifications for remote wake/commands

### Frontend
- **Next.js 15** - React framework with App Router
- **TypeScript 5** - Type-safe JavaScript
- **Tailwind CSS 4** - Utility-first styling
- **shadcn/ui** - Beautiful, accessible components
- **date-fns-tz** - Timezone-aware date formatting (CST display)

### Android Agent
- **Kotlin** - Modern Android development
- **Foreground Service** - 5-minute heartbeat with wake locks
- **MediaProjection** - Screen capture for remote viewing
- **AccessibilityService** - Touch input injection
- **UsageStatsManager** - App activity detection
- **Device Owner API** - Silent app installation and advanced permissions

## 📱 Supported Devices

- **Android 13+** (API level 33+)
- Tested extensively on **Orbic Joy 2** devices
- Works on any Android phone/tablet meeting the minimum version
- Best suited for dedicated devices (always-plugged phones, kiosks, tablets, etc.)

## 🎯 Use Cases

### Dedicated Device Fleet Management
Monitor and control 100+ always-plugged devices running specialized applications. Ensure apps stay running with complete power optimization disable and real-time monitoring.

### Digital Signage
Ensure displays stay online, deploy content updates, and monitor playback.

## 📊 System Requirements

### For the Server (Replit Deployment)
- Replit Core subscription ($25/month includes $25 credits)
- PostgreSQL database (automatically provided)
- ~100MB storage for APKs

### For Android Devices
- Android 13+ (API 33+)
- Internet connectivity (Wi-Fi or cellular)
- Google Play Services (for FCM push notifications)
- 50-100MB storage for the UNITYmdm agent app

## 📈 Scalability & Performance

UNITYmdm is designed to scale from small deployments to enterprise fleets:

### Default Deployment (100+ Devices)
The standard Replit deployment handles **100+ devices** effortlessly with:
- **Replit Core** - $25/month includes compute and database
- **Built-in PostgreSQL** - Replit's default database tier
- **5-minute heartbeats** - Efficient polling with minimal overhead
- **WebSocket updates** - Real-time dashboard without constant polling

**Performance characteristics:**
- Sub-second dashboard updates via WebSocket
- ~5MB database for 100 devices with 30-day event history
- Concurrent remote control for 5-10 devices
- APK deployments to entire fleet simultaneously

### Scaling to 3000+ Devices

For large-scale deployments (500-3000+ devices), simply upgrade your infrastructure:

#### Database Upgrade (Required)
- **External PostgreSQL** - Migrate to [Neon](https://neon.tech), [Supabase](https://supabase.com), or [Railway](https://railway.app)
- **Change 1 environment variable** - Update `DATABASE_URL` to new database
- **Zero code changes** - Application remains identical

#### Compute Resources (Recommended)
- **Boost Repl** - Upgrade to higher CPU/RAM tiers in Replit
- **Horizontal Scaling** - Run multiple backend instances (requires load balancer)
- **CDN for APKs** - Offload APK downloads to object storage (Replit, AWS S3, Cloudflare R2)

#### Cost Estimate for 3000 Devices
| Component | Service | Cost |
|-----------|---------|------|
| Compute | Replit Core (2x boost) | ~$50-75/month |
| Database | Neon Pro / Supabase Pro | ~$25-50/month |
| Storage | Replit Object Storage | ~$5-10/month |
| **Total** | | **~$80-135/month** |

**No code changes needed** - Just infrastructure upgrades!

### Performance Optimization Tips

1. **Increase heartbeat interval** - Change from 5min to 10min for 3000+ devices
2. **Database indexing** - Already optimized for device lookups and event queries
3. **Batch operations** - Use bulk APK deployment instead of device-by-device
4. **Event cleanup** - Automated 30-day retention keeps database lean

📊 **Tested at scale**: The architecture supports thousands of devices with proper infrastructure. Start small, scale seamlessly.

## 🔒 Security & Privacy

- **Self-Hosted** - Your data stays on your infrastructure
- **Admin Key Authentication** - Protect administrative operations
- **Device Token Auth** - Secure device-to-server communication
- **User Sessions** - Password-hashed user accounts
- **Secret Management** - Replit Secrets keep credentials private
- **Firebase Service Account** - Securely stored JSON credentials

**Note**: UNITYmdm is designed for private, self-hosted deployments managing your own devices. It's not a multi-tenant SaaS platform.

## 🔄 Transitioning from Speedtest to Unity App

UNITYmdm is pre-configured with Speedtest for immediate testing, but you can easily transition to monitoring your Unity app (or any custom Android app) when ready.

### Initial Setup (Pre-Unity)

1. **Deploy UNITYmdm** - Follow the Quick Start guide above
2. **Enroll Devices** - Use ADB or QR code enrollment **(QR code not recommended - doesn't support DeviceOwnerMode)**
3. **Deploy Speedtest** - Speedtest APK is pre-loaded in APK Management
   - Go to **APK Management** → Select Speedtest → **Deploy** to all devices
4. **Enable Monitoring** - Devices automatically monitor `org.zwanoo.android.speedtest`
5. **Optional: Enable Auto-Relaunch**
   - Open Device Drawer (click any device)
   - Go to **Device Settings** section
   - Enable "Auto-Relaunch" toggle
   - Speedtest will automatically restart if it crashes or is closed

### Transition to Unity (When Ready)

Once your Unity APK is ready:

1. **Upload Unity APK**
   - Go to **APK Management** → **Upload APK**
   - Upload your Unity app APK file
   - Note the package name (e.g., `com.yourcompany.unity`)

2. **Deploy Unity to Devices**
   - Select your Unity APK version
   - Click **Deploy** → Select devices
   - Wait for installation to complete

3. **Update Monitored App Settings**
   - Click on a device to open Device Drawer
   - Scroll to **Device Settings** section
   - Click **Edit**
   - Change "Monitored App Package" from `org.zwanoo.android.speedtest` to your Unity package name
   - Keep "Auto-Relaunch" enabled for automatic restart
   - Click **Save**

4. **Repeat for All Devices**
   - Update each device's settings individually, OR
   - Use the same package name in bulk via Device Drawer for each device

### Package Name Examples

- **Speedtest**: `org.zwanoo.android.speedtest`
- **Unity Example**: `com.yourcompany.unity`
- **Custom App**: `com.example.myapp`

**💡 Pro Tip**: You can have different devices monitor different apps! For example, some devices monitor Speedtest while others monitor Unity - perfect for A/B testing or gradual rollouts.

## 🛠️ Development

### Local Development

```bash
# Backend
cd server
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd dashboard
npm install
npm run dev
```

### Environment Variables
See [`.env.example`](.env.example) for all configuration options.

### Building the Android App

**Option 1: GitHub Actions (Recommended - No Android Studio needed!)**
1. Connect your Repl to GitHub (Version Control icon → Connect to GitHub)
2. Replace `android/app/google-services.json` with your Firebase config
3. Run `bash scripts/generate-apk-signing-keys.sh` to generate signing keys
4. Add the keys to GitHub Secrets (Settings → Secrets and variables → Actions)
5. Push changes - GitHub Actions builds and uploads APK automatically!
6. Download from **APK Management** page in your dashboard

📖 See [DEPLOYMENT.md](DEPLOYMENT.md#71-build-your-own-android-apk-recommended) for detailed step-by-step guide

**Option 2: Local Build with Android Studio**
1. Open the `android/` folder in Android Studio
2. Build APK: **Build → Build Bundle(s) / APK(s) → Build APK(s)**
3. Find APK in `android/app/build/outputs/apk/release/`

## 📦 Deployment Options

### Replit (Recommended)
- ✅ One-click deployment
- ✅ Built-in PostgreSQL
- ✅ Automatic HTTPS
- ✅ Secret management
- See [DEPLOYMENT.md](DEPLOYMENT.md) for full guide


## ❓ Frequently Asked Questions (FAQ)

### General Questions

**Q: Is UNITYmdm right for my use case?**

UNITYmdm is specifically designed for managing **physical Android devices spread across different locations** that need remote management without requiring a PC or physical access.

**Perfect for:**
- 📱 Physical phones/tablets deployed in multiple locations (homes, warehouses, offices)
- 🌐 Remote fleet management without USB access
- 🔄 Internet-connected devices that need OTA (over-the-air) updates
- 💰 Cost-effective scaling (10 to 1000+ devices)

**How it works:**
UNITYmdm leverages **Firebase Cloud Messaging (FCM)** for remote control:
- ✅ **No physical access needed** - Deploy APKs, restart devices, change settings from anywhere
- ✅ **Internet-based control** - Works as long as devices have WiFi/cellular connectivity
- ✅ **Real-time** - Instant push notifications vs. waiting for devices to poll
- ✅ **Scalable** - Manage your entire fleet from a laptop

**Not the best fit for:**
- 🖥️ **SIM box farms or USB-connected setups** - If your devices are permanently connected to a PC, USB-based tools may be simpler
- 🔌 **Local-only management** - If you have physical access and prefer wired control
- 📶 **Offline devices** - UNITYmdm requires internet connectivity for remote features

**Bottom line:** If you have physical devices in different locations and need to manage them remotely without traveling or USB cables, UNITYmdm is built for your use case. For other setups (sim boxes, local farms, etc.), there may be better-suited solutions.

---

**Q: Do I need to be technical to deploy this?**

**No!** UNITYmdm is designed for non-technical users with clear step-by-step instructions:

- 📖 **Detailed guides** - Follow [DEPLOYMENT.md](DEPLOYMENT.md) for copy/paste setup
- 🤖 **Replit Agent support** - Stuck? Ask Replit Agent and it will walk you through any issue
- ⚡ **No coding required** - The hardest part is copying Firebase credentials and running one script
- 🎯 **Pre-configured** - GitHub Actions workflow builds APKs automatically (no Android Studio needed)

**Example workflow:**
1. Fork this Repl (1 click)
2. Copy/paste Firebase credentials into Secrets (2 minutes)
3. Connect to GitHub and push code → APK builds automatically (10 minutes)
4. Plug in device, run ADB script (2 minutes per device)

If you can copy/paste and follow instructions, you can deploy UNITYmdm!

---

**Q: Can I customize UNITYmdm for my specific needs?**

**Absolutely!** UNITYmdm is designed to be flexible:

- 🤖 **Replit Agent** - Ask Replit Agent to customize anything:
  - "Change heartbeat interval to 10 minutes instead of 5"
  - "Add a custom dashboard widget showing device temperature"
  - "Modify the ADB script for Samsung phones"
  - "Add email alerts instead of Discord"
  
- 📱 **Device farm friendly** - Adapt for your specific hardware:
  - Custom battery thresholds for your phone models
  - Carrier-specific ADB optimizations
  - Custom monitoring apps beyond Speedtest/Unity
  
- 🎨 **Open source** - Full access to all code (MIT License)
- 📝 **Well documented** - `replit.md` explains the entire architecture

**Pro Tip**: Describe your farm setup to Replit Agent and it will tailor UNITYmdm to your exact requirements!

---

### Deployment Questions

**Q: How do I make this Repl available for others to use as a template?**

You have two options:

1. **Make it Public** (Recommended for sharing)
   - Click the visibility settings
   - Set to "Public"
   - Anyone can view and **Remix** your Repl to create their own copy
   - Your secrets remain private (never exposed)
   - Users get a fresh copy with their own database

2. **Publish as Template** (Optional)
   - Makes your Repl appear in Replit's template gallery
   - Same as public but with more visibility
   - Good for promoting to wider community

**For UNITYmdm**: Simply making it **public** is enough. Users can remix, configure their own Firebase/secrets, and deploy independently.

---

**Q: What if I don't have GitHub Actions? Can I still build APKs?**

Yes! You have options:

- **Option 1**: Use GitHub Actions (recommended, free, automated)
- **Option 2**: Build locally with Android Studio (manual, requires ~5GB download)
- **Option 3**: Ask a technical friend to build the APK for you once, then use UNITYmdm's built-in APK deployment for future updates

Most users choose GitHub Actions since it's 100% automated after initial 10-minute setup.

---

**Q: Will this work with my specific Android phone model?**

UNITYmdm works with **any Android 13+ device**, but some carrier-specific phones (Verizon, AT&T, etc.) have extra bloatware that may need customization:

- ✅ **Tested extensively** on Orbic Joy 2 (Verizon)
- ✅ **Community tested** on various Samsung, Motorola, and generic devices
- 🤖 **Easy customization** - Ask Replit Agent: "Adapt the ADB script for AT&T phones"

The included ADB script disables 27+ common bloatware apps. If your phone has different bloatware, Replit Agent can adjust the script in seconds.

---

**Q: How much does it cost to run UNITYmdm long-term?**

**Monthly costs (100 devices)**:
- Replit Core: $20/month (includes $25 credits)
- Firebase: Free tier (sufficient for 100-500 devices)
- Total: **~$0-20/month** (credits often cover the cost)

**At scale (1000 devices)**:
- Replit Core: ~$50/month (boosted resources)
- External PostgreSQL: ~$25/month (Neon/Supabase)
- Firebase: Still free tier
- Total: **~$75/month**

Compare to commercial MDM: $3-10 **per device per month** = $3000-10,000/month for 1000 devices!

---

**Q: What happens if my Repl goes down or I lose data?**

Replit provides:
- ✅ **Automatic backups** - Your entire Repl is version controlled
- ✅ **PostgreSQL backups** - Replit backs up your database automatically
- ✅ **Rollback support** - Restore to any previous checkpoint
- ✅ **99.9% uptime** - Replit Core provides production-grade reliability

For additional safety:
- Export your device data periodically (CSV from dashboard)
- Keep your Firebase credentials backed up separately
- Fork your Repl occasionally as a snapshot

---

**Q: Can I migrate from UNITYmdm to another system later?**

Yes! UNITYmdm doesn't lock you in:

- 📤 **Export device data** - PostgreSQL database is accessible (standard SQL)
- 🔓 **Open source** - MIT License allows any use
- 📱 **Standard Android** - No proprietary device modifications
- 🔄 **Easy unenrollment** - Devices can be factory reset or enrolled elsewhere

You own all your data and devices.

---

### Technical Questions

**Q: How does the remote APK deployment work without USB?**

1. You upload an APK to the dashboard
2. Click "Deploy" and select target devices
3. UNITYmdm sends FCM push notification to devices
4. Devices download APK from your backend server
5. Android's Device Owner API installs silently (no user interaction)
6. Dashboard shows real-time progress

All over the internet - no cables required!

---

**Q: What's the difference between QR code and ADB enrollment?**

| Method | Best For | Setup Time | Requires |
|--------|----------|------------|----------|
| **QR Code** | Quick individual enrollments **(Not recommended - Can't enabled DeviceOwnerMode)** | 30 seconds | WiFi only |
| **ADB Script** | Bulk enrollment, Device Owner mode | ~15secs | USB cable + ADB |

**QR Code**: Fast for 1-5 devices, but can't enable Device Owner mode (needed for silent app installs).

**ADB Script**: Recommended enrollment method - enables full Device Owner privileges, disables bloatware, and configures battery optimization automatically. Required for production deployments.

---

**Q: How do I get support if something breaks?**

1. **Check logs** - Dashboard shows device errors and heartbeat status
2. **Ask Replit Agent** - It has full context of your deployment and can debug issues
3. **Review documentation** - [DEPLOYMENT.md](DEPLOYMENT.md) and [replit.md](replit.md) cover common issues
4. **Open an issue** - Describe your problem and we'll help troubleshoot (feel free to DM Serg on TG and I'll do my best to help, but AI is a **lot** smarter than I am :D 
5. **Community support** - Other UNITYmdm users may have solved similar problems

Most issues are solved in minutes with Replit Agent's help!

---

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/), [Next.js](https://nextjs.org/), and [shadcn/ui](https://ui.shadcn.com/)
- Firebase Cloud Messaging for reliable push notifications
- Replit for making deployment incredibly simple

## 📞 Support

- **Documentation**: [DEPLOYMENT.md](DEPLOYMENT.md) | [replit.md](replit.md)
- **Issues**: Open an issue in your Replit project for support
- **Community**: Share your experience with other UNITYmdm users

---

**Made with ❤️ for managing fleets of Android devices**
