# UNITYmdm Deployment Guide

This guide will help you deploy UNITYmdm on Replit in under 15 minutes. No Docker, VPS, or command-line experience required!

## 📋 Prerequisites

- A Replit account (free or paid)
- A Google/Firebase account (free)
- (Optional) A Discord server for alerts

## 🚀 Quick Start Overview

1. **Fork this Repl** → Get your own copy
2. **Set up Firebase** → Enable push notifications
3. **Configure secrets** → Add your credentials
4. **Enable PostgreSQL** → Turn on the database
5. **Run the app** → Everything starts automatically!
6. **Enroll devices** → Add your Android phones

---

## Step 1: Fork/Remix This Repl

1. Click the **"Fork"** or **"Remix"** button at the top of this Repl
2. Give your Repl a name (e.g., `my-UNITYmdm`)
3. Your own copy will open in a new workspace

---

## Step 2: Set Up Firebase (Required)

Firebase is needed for push notifications to wake up your devices remotely.

### 2.1 Create a Firebase Project

1. Go to the [Firebase Console](https://console.firebase.google.com)
2. Click **"Add project"** (or select an existing project)
3. Enter a project name (e.g., `UNITYmdm`)
4. Disable Google Analytics (not needed for this project)
5. Click **"Create project"**

### 2.2 Enable Cloud Messaging

1. In your Firebase project, click the **gear icon** → **"Project settings"**
2. Go to the **"Cloud Messaging"** tab
3. You should see your **Server Key** and **Sender ID** - these will be used by the Android app

### 2.3 Download and Prepare Service Account Key

1. Still in Project Settings, go to the **"Service accounts"** tab
2. Click **"Generate new private key"**
3. A JSON file will download (e.g., `UNITYmdm-firebase-adminsdk-xxxxx.json`)
4. **Open the file** in a text editor (Notepad, VS Code, etc.)
5. **Copy ALL the contents** - from the opening `{` to the closing `}`
6. Keep this copied - you'll paste it into Replit Secrets next

**🔒 Security Note**: We'll paste this as a Replit Secret instead of uploading the file. This keeps your Firebase credentials private even if you make your Repl public!

---

## Step 3: Enable PostgreSQL Database

1. In your Replit workspace, look for the **"Database"** icon in the left toolbar
2. Click **"PostgreSQL"** and enable it
3. Replit will automatically create a `DATABASE_URL` secret for you
4. No additional configuration needed!

---

## Step 4: Configure Replit Secrets

Secrets are like environment variables but kept private and secure.

### 4.1 Open the Secrets Panel

1. Click the **lock icon (🔒)** in the left sidebar
2. This opens the **Secrets** pane

### 4.2 Add Required Secrets

Add each of these secrets by clicking **"New secret"**:

#### **ADMIN_KEY** (Required)
- **Purpose**: Administrative password for device management
- **How to generate**: Run this command in the Replit Shell:
  ```bash
  openssl rand -base64 32
  ```
- **Example value**: `Xk7mP9qR2sT5vW8xZ1aC4dF6gH9jK0lN3oP5rS7tU9w=`

#### **FIREBASE_SERVICE_ACCOUNT_JSON** (Required)
- **Purpose**: Firebase service account credentials
- **Value**: Paste the **entire JSON contents** you copied in Step 2.3
  - Make sure you copy everything from `{` to `}`
  - It will look like: `{"type":"service_account","project_id":"your-project",...}`
  - Paste it all as one value (newlines are okay, Replit handles multi-line secrets)
- **Why as a secret?** This keeps your Firebase credentials private even if you share your Repl or make it public!

#### **SERVER_URL** (Required)
- **Purpose**: Your public Replit app URL (for device enrollment)
- **How to find it**: 
  - After you run your Repl, look at the **Webview** window
  - The URL will be something like: `https://my-UNITYmdm.your-username.repl.co`
  - You can also find it in the **Deployments** tab after publishing
- **Example value**: `https://UNITYmdm-johndoe.repl.co`
- **Note**: You can add this secret *after* your first run, then restart

#### **DISCORD_WEBHOOK_URL** (Optional)
- **Purpose**: Send alerts to Discord when devices go offline or have low battery
- **How to create**:
  1. Open your Discord server
  2. Go to **Server Settings → Integrations → Webhooks**
  3. Click **"New Webhook"**
  4. Choose a channel (e.g., `#alerts`)
  5. Copy the **Webhook URL**
- **Example value**: `https://discord.com/api/webhooks/123456789/abcdefghijklmnop`
- **Skip this if**: You don't want Discord notifications (alerts will just print to console)

### 4.3 Optional Tuning Secrets

These have sensible defaults, but you can customize them:

| Secret | Default | Description |
|--------|---------|-------------|
| `OFFLINE_THRESHOLD_SECONDS` | `900` (15 min) | How long before a device is marked offline |
| `HEARTBEAT_INTERVAL_SECONDS` | `300` (5 min) | Expected time between device check-ins |
| `EVENT_RETENTION_DAYS` | `30` | How long to keep device event history |

---

## Step 5: Run Your UNITYmdm Server

1. Click the big green **"Run"** button at the top
2. Wait for both servers to start (Backend + Frontend)
3. You should see:
   ```
   INFO:     Uvicorn running on http://0.0.0.0:8000
   ▲ Next.js 15.2.4
   - Local:        http://localhost:5000
   ```
4. The **Webview** will open showing your UNITYmdm dashboard
5. If you see errors about missing secrets, go back to Step 4 and add them

### 5.1 Update SERVER_URL (If Not Set Yet)

1. Copy the URL from your Webview (e.g., `https://UNITYmdm-johndoe.repl.co`)
2. Go to **Secrets** (🔒) and add/update `SERVER_URL` with this value
3. Click **"Run"** again to restart with the new URL

---

## Step 6: Create Your Admin Account

1. In the dashboard, you should see a **registration** or **login** page
2. Create an admin account with your email and password
3. This account will let you manage devices, view stats, and deploy APKs

---

## 📱 Important: Device Owner Mode Prerequisites

**Before enrolling devices, you MUST understand Device Owner requirements:**

### Why Factory Reset is Required

Android's **Device Owner mode** is a security feature designed for enterprise device management. To prevent unauthorized takeover of personal devices, Google enforces strict requirements:

#### ✅ Device Owner Can ONLY Be Set When:
1. **No user accounts exist** - Device must be in factory-fresh state
2. **No work profiles configured** - No existing MDM or work profile setup
3. **No personal data present** - Clean slate to ensure user privacy

#### ❌ The `dpm set-device-owner` Command FAILS If:
- Any Google account is signed in
- Any user profile exists on the device
- Another MDM solution is already managing the device
- The device has completed initial setup with a user account

### What Device Owner Mode Enables

Once successfully provisioned, Device Owner mode provides:
- **Silent APK Installation** - Deploy apps without user interaction
- **Advanced Permission Control** - Auto-grant permissions programmatically
- **System-Level Management** - Disable apps, modify settings remotely
- **Enhanced Security** - Prevent uninstallation of management app

### Factory Reset Steps

**Option 1: Settings Menu**
1. Go to **Settings** → **System** → **Reset options**
2. Select **Erase all data (factory reset)**
3. Confirm and wait for device to restart
4. **DO NOT** sign into any accounts during setup
5. Skip all account setup screens
6. Proceed directly to ADB enrollment

**Option 2: Recovery Mode** (if device is locked)
1. Power off the device completely
2. Hold **Power + Volume Down** simultaneously
3. Navigate to **Wipe data/factory reset** using volume buttons
4. Confirm with Power button
5. Skip account setup after reboot

### ⚠️ Critical Warnings

- **Backup important data first** - Factory reset erases everything
- **Skip account setup** - Do not sign into Google or any accounts after reset
- **USB debugging required** - Enable immediately after reset (before adding accounts)
- **One chance only** - If you add an account, you must factory reset again

---

## Step 7: Enroll Your First Android Device

### 7.1 Build Your Own Android APK (Recommended)

**Why build your own?** Your APK will use YOUR Firebase project for push notifications, keeping everything isolated and secure.

**Good news**: You don't need Android Studio! We'll use GitHub Actions to build the APK automatically.

#### Step 1: Connect Your Repl to GitHub

1. In your Replit workspace, click the **Version Control** icon (🔀) in the left sidebar
2. Click **"Create a Git repository"** if you haven't already
3. Click **"Connect to GitHub"**
4. Authorize Replit to access your GitHub account
5. Choose **"Create a new repository"** and give it a name (e.g., `my-UNITYmdm`)
6. Click **"Create Repository"**

Your Repl is now synced to GitHub! Any changes you make will be pushed automatically.

#### Step 2: Replace Firebase Configuration

1. In the **Files** panel, navigate to `android/app/google-services.json`
2. **Delete this file** (it contains the demo Firebase config)
3. Download YOUR Firebase `google-services.json` file from:
   - Firebase Console → Project Settings → General
   - Scroll down to "Your apps"
   - Click **"google-services.json"** download button
4. **Upload your file** to replace the deleted one:
   - Right-click `android/app/` folder → Upload file
   - Select your downloaded `google-services.json`

#### Step 3: Generate APK Signing Keys

APK signing ensures your app can be updated consistently. Run this script to generate keys:

1. In the Replit **Shell**, run:
   ```bash
   bash scripts/generate-apk-signing-keys.sh
   ```

2. You'll be prompted to enter:
   - **Keystore password** (choose a strong password, save it!)
   - **Key alias** (default: `UNITYmdm` is fine)
   - **Key password** (can be same as keystore password)
   - Your name/organization (optional, can press Enter to skip)

3. The script will output your signing keys in **base64** format:
   ```
   ✅ Keystore generated successfully!
   
   Copy these values to GitHub Secrets:
   
   KEYSTORE_BASE64=MIIKEAIBAzCCCc... (long string)
   KEYSTORE_PASSWORD=your-password-here
   KEY_ALIAS=UNITYmdm
   KEY_PASSWORD=your-key-password-here
   ```

4. **Copy these values** - you'll need them in the next step!

#### Step 4: Add GitHub Secrets

1. Go to your GitHub repository (the one Replit created)
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **"New repository secret"** for each of these:

   | Secret Name | Value |
   |------------|--------|
   | `KEYSTORE_BASE64` | Paste the long base64 string from Step 3 |
   | `KEYSTORE_PASSWORD` | Your keystore password |
   | `KEY_ALIAS` | Your key alias (default: `UNITYmdm`) |
   | `KEY_PASSWORD` | Your key password |
   | `UNITYmdm_API_URL` | Your Replit URL (e.g., `https://UNITYmdm-you.repl.co`) |
   | `ADMIN_KEY` | Same as your backend `ADMIN_KEY` secret |

4. Click **"Add secret"** after entering each one

#### Step 5: Trigger the Build

1. In your Replit workspace, make a small change to trigger GitHub Actions:
   - Edit `android/README.md` and add a line: `Build triggered on [today's date]`
   - The change will auto-push to GitHub

2. Go to your GitHub repo → **Actions** tab
3. You should see **"Build Android APK"** workflow running
4. Wait 3-5 minutes for the build to complete

#### Step 6: Download Your APK

Once the build completes:

**Option A: From GitHub Actions (Immediate)**
1. Go to the completed workflow run
2. Scroll down to **"Artifacts"**
3. Download **`UNITYmdm-debug-apk`**
4. Extract the ZIP to get your APK

**Option B: From UNITYmdm Dashboard (Automatic Upload)**
1. The APK was automatically uploaded to your UNITYmdm backend!
2. Go to **APK Management** in your dashboard
3. You'll see the latest build listed
4. Click **"Download"** to get your APK
5. Or use **"Deploy"** to push it to all your devices at once!

#### Step 7: Install on Your Device

**Via USB (ADB)**:
```bash
adb install path/to/app-debug.apk
```

**Via Dashboard (Recommended)**:
1. In APK Management, click **"Deploy"** next to your APK
2. Select target devices
3. APK installs automatically via Device Owner mode!

**Manually**:
1. Transfer APK to your device (email, cloud storage, etc.)
2. Open the APK file on your device
3. Allow installation from unknown sources if prompted
4. Install

### 7.2 Enroll Using QR Code (Recommended)

1. In the UNITYmdm dashboard, click **"Device Enrollment"** or the QR code icon
2. You'll see a QR code displayed
3. On your Android device:
   - Open the UNITYmdm app
   - Tap **"Scan QR Code"**
   - Point camera at the QR code on your dashboard
   - Grant permissions when prompted
   - Device will auto-enroll!

### 7.3 Enroll Using ADB (Advanced)

For bulk enrollment or Device Owner mode:

1. In the dashboard, go to **"ADB Setup"**
2. Copy the generated script
3. Connect your Android device via USB with ADB enabled
4. Run the script in your terminal:
   ```bash
   bash -c "$(copied-script)"
   ```

#### What the ADB Script Does (Complete Transparency)

The automated setup script performs the following modifications to your device:

**📝 Device Settings Modified:**
- **Animation Scales**: Set to `0.5` for faster UI performance
- **Wake Features**: Enable ambient tilt-to-wake and touch-to-wake
- **App Standby**: Disabled to prevent app backgrounding
- **Battery Optimization**: Disabled for reliability
- **Unknown Sources**: Enabled to allow APK installation from UNITYmdm

**🗑️ Applications Disabled/Removed:**

*Carrier Bloatware (if applicable - Verizon carrier):*
- MyVerizon app, VCast Media Manager, Verizon APNLib
- Verizon MIPS Services, Visual Voicemail client
- Verizon Games Hub, Discounts app
- **Note:** If you're using a different carrier, see customization instructions below

*Google Apps (20+ apps):*
- YouTube, YouTube Music, Google Maps, Google Photos
- Gmail, Google Drive, Google Calendar, Google Keep
- Google Docs, Google Assistant, Google Duo
- Google Pay, Google Wallet, Google Chromecast
- Calculator, Clock, Android Auto, Files

*Pre-installed Games (15+ games):*
- Candy Crush Saga, Candy Crush Soda Saga
- Solitaire, Mahjong, Sudoku, Art Puzzle
- Toon Blast, Dice Dreams, Woodoku
- Bubble Shooter, Spades, Bingo, Hidden Spots

*Miscellaneous Apps:*
- Facebook, Facebook App Manager
- Logia Deck, Folder Launcher, Viper apps
- Easter Egg, Live Wallpapers, Music FX
- Sound Recorder, Weather widgets

**✅ Applications ENABLED (if applicable - Verizon carrier):**
- `com.verizon.dmclientupdate` - Verizon device management client
- `com.verizon.obdm` - Verizon diagnostic services
- `com.verizon.obdm_permissions` - Required permissions for above

**🔐 Permissions Granted to UNITYmdm:**
- `POST_NOTIFICATIONS` - For FCM push notifications
- `CAMERA` - For QR code scanning (enrollment)
- `ACCESS_FINE_LOCATION` - For device location tracking
- `GET_USAGE_STATS` - For app activity monitoring
- Battery optimization whitelist - Prevent Android from killing the service
- Device idle whitelist - Allow background operation

**🔧 Device Owner Setup:**
- Executes: `adb shell dpm set-device-owner com.UNITYmdm/.NexDeviceAdminReceiver`
- This grants silent APK installation and advanced management capabilities
- **Requires factory-fresh device** (see prerequisites section above)

**📋 Device Enrollment:**
- Configures server URL, device token, and monitored app package
- Starts UNITYmdm service automatically
- Verifies Device Owner status

#### Customizing the Script for Your Carrier

The default script is optimized for Verizon devices (Orbic Joy 2). If you're using a different carrier, **just ask Replit Agent** to adapt it:

**Example Prompts:**
- 💬 *"Adapt the ADB script for AT&T phones instead of Verizon"*
- 💬 *"My Samsung devices have different bloatware - update the ADB script to remove T-Mobile apps"*
- 💬 *"The enrollment script isn't disabling bloatware on my unlocked Motorola phones - fix it"*
- 💬 *"I'm using Sprint devices - replace all Verizon bloatware with Sprint bloatware in the ADB script"*

**That's it!** Replit Agent will automatically update the ADB script with the right bloatware packages for your carrier. No need to know package names or edit files manually.

**Common carriers supported:**
- AT&T (typical packages: `com.att.*`, `com.asurion.*`)
- T-Mobile (typical packages: `com.tmobile.*`, `com.mobitv.*`)
- Sprint (typical packages: `com.sprint.*`, `com.coremobility.*`)
- Unlocked/International devices (minimal bloatware)

### 7.4 Bulk Enrollment (50+ Devices)

Enrolling multiple devices? UNITYmdm includes a CSV-based bulk enrollment system that automates the process.

#### Prerequisites
1. Complete steps 1-6 (server running, Firebase configured, secrets set)
2. ADB installed on your computer
3. USB cable(s) for device connections
4. (Optional) USB hub for simultaneous connections

#### Step 1: Create Your Device List

**Option 1: Use the Template (Recommended)**
```bash
cd scripts
cp devices.csv.example devices.csv
# Edit devices.csv with your device names
```

**Option 2: Create from Scratch**

Create a `devices.csv` file in the `scripts/` folder with your device names:

```csv
alias,unity_package
RackA-01,com.speedtest.androidspeedtest
RackA-02,com.speedtest.androidspeedtest
RackA-03,com.speedtest.androidspeedtest
PhoneFarm-D01,com.yourapp.package
PhoneFarm-D02,com.yourapp.package
```

**📄 Template**: See `scripts/devices.csv.example` for a ready-to-use template with examples and comments.

**Device Naming Best Practices:**

| Pattern | Example | Best For |
|---------|---------|----------|
| Sequential | `D01`, `D02`, `D03` | Simple numbering |
| Location-based | `NYC-K1`, `LA-Office-D05` | Geographic tracking |
| Rack/Position | `Rack1-Shelf2-D07` | Physical organization |
| MAC-based | `Phone-A4F2` (last 4 of MAC) | Guaranteed uniqueness |

**💡 Tip**: Start with simple names (D01, D02, D03). You can edit aliases anytime in the dashboard!

#### Step 2: Set Environment Variables

```bash
export SERVER_URL="https://your-replit-app.repl.co"
export ADMIN_KEY="your-admin-key-from-secrets"
```

**Where to find these:**
- `SERVER_URL`: Your Replit URL from the Webview window
- `ADMIN_KEY`: From Replit Secrets (🔒 icon in sidebar)

#### Step 3: Run the Bulk Enrollment Script

```bash
cd scripts
./bulk_enroll.sh
```

**What happens:**
1. Script reads `devices.csv` line by line
2. For each device:
   - Registers device with server
   - Waits for ADB connection
   - Prompts: "Press Enter to continue to next device..."
   - You connect the device via USB
   - Press Enter to enroll
   - Script configures device and moves to next

#### Step 4: Connect and Enroll Each Device

**Interactive workflow (default):**
1. Connect first device via USB
2. Press Enter
3. Device enrolls (takes 10-15 seconds)
4. Disconnect device
5. Connect next device
6. Press Enter
7. Repeat for all devices

**Parallel workflow (USB hub):**
1. Connect 5-10 devices to USB hub
2. The script cycles through each one
3. Press Enter to move between devices
4. No need to disconnect/reconnect

#### Example: Enrolling 50 Devices

**Generate CSV automatically:**
```bash
# Create sequential device names D01 through D50
cd scripts
echo "alias,unity_package" > devices.csv
for i in {1..50}; do
  printf "D%02d,com.speedtest.androidspeedtest\n" $i >> devices.csv
done
```

**Run bulk enrollment:**
```bash
export SERVER_URL="https://unitymdm.yourname.repl.co"
export ADMIN_KEY="your-admin-key"
./bulk_enroll.sh
```

**Estimated time:** 5-10 minutes for 50 devices (with USB hub)

#### Advanced: Fully Automated Enrollment

For 100+ devices, remove interactive prompts:

1. Edit `bulk_enroll.sh`
2. Comment out or remove the `read` line (line 42-43):
   ```bash
   # echo "Press Enter to continue to next device (or Ctrl+C to stop)..."
   # read
   ```
3. Connect all devices via USB hub
4. Run script - it enrolls all devices automatically

#### Post-Enrollment: Rename Devices

After bulk enrollment, you can rename devices in the dashboard:

1. Go to **Devices** page
2. Click the **edit icon** next to device alias
3. Update name inline: D01 → "MainEntrance-Kiosk"
4. Press Enter to save

**Example workflow:**
1. Bulk enroll as D01, D02, D03... (5 min for 50 devices)
2. Deploy devices to physical locations
3. Rename in dashboard based on actual placement (5 min)

#### Troubleshooting Bulk Enrollment

**Error: "No ADB device connected"**
- Enable USB debugging on device
- Accept "Allow USB debugging" prompt on device
- Try: `adb devices` to verify connection

**Error: "Failed to register device"**
- Check `SERVER_URL` is correct (no trailing slash)
- Verify `ADMIN_KEY` matches Replit Secrets
- Ensure server is running (check Replit console)

**Script skips devices**
- Devices may already be enrolled
- Check dashboard for duplicate names
- Delete duplicates and re-run script

**Want to re-enroll a device?**
1. Delete device from dashboard
2. Add it back to `devices.csv`
3. Re-run bulk script for that device only

---

## Step 8: Verify Everything Works

### Check Dashboard
- You should see your device appear in the device list
- Status should show as "Online" (green)
- Battery level and other telemetry should be visible

### Check Heartbeats
- Device should send heartbeat every 5 minutes (by default)
- Last Seen timestamp should update regularly

### Test Remote Ping
- Click the **"Ping"** button next to your device
- Device should respond within a few seconds
- You'll see latency displayed

### Test Discord Alerts (If Configured)
- Temporarily stop the Android app on your device
- Wait 15 minutes (or your configured `OFFLINE_THRESHOLD_SECONDS`)
- You should receive a Discord notification that the device went offline

---

## 🎉 You're All Set!

Your UNITYmdm system is now running! Here's what you can do next:

- **Enroll more devices** using the same QR code or ADB script
- **Deploy APKs** remotely to all your devices from the APK Management page
- **Remote control** your devices with screen streaming and commands
- **Monitor status** in real-time via the dashboard
- **Publish your Repl** for production use (see below)

---

## 📦 Publishing for Production (Optional)

To make your UNITYmdm deployment always-on and accessible via a custom domain:

### Using Replit Deployments

1. Click the **"Deploy"** button in the top-right corner
2. Choose **"Autoscale"** deployment (recommended for web apps)
3. Configure your deployment:
   - All secrets will carry over automatically
   - Set a deployment name
4. Click **"Deploy"**
5. Your app will be live at `https://your-app-name.repl.app`

### Custom Domain (Replit Pro/Teams)

1. After deploying, go to the **Deployments** tab
2. Click **"Custom domains"**
3. Follow instructions to connect your domain (e.g., `mdm.yourcompany.com`)
4. Replit handles SSL certificates automatically

**Important**: After publishing with a custom domain, update your `SERVER_URL` secret to the new domain!

---

## 🔧 Troubleshooting

### "Firebase service account not found"
- Verify the JSON file is uploaded to your Repl
- Check that `FIREBASE_SERVICE_ACCOUNT_PATH` matches the exact filename
- Make sure there are no typos or extra spaces

### "Admin key required" errors
- Ensure `ADMIN_KEY` secret is set
- Restart your Repl after adding the secret
- Try generating a new key with `openssl rand -base64 32`

### Database connection errors
- Verify PostgreSQL is enabled in the Database panel
- Check that `DATABASE_URL` secret exists (Replit creates this automatically)
- Try disabling and re-enabling PostgreSQL

### Devices not showing up
- Check that `SERVER_URL` is set correctly
- Verify the Android app can reach your Repl URL (test in a browser)
- Make sure the device has internet connectivity
- Check the Android app logs for enrollment errors

### Discord notifications not working
- Verify your webhook URL is correct (test it in a browser)
- Check the Discord channel permissions
- Look for error messages in the Replit console logs

### App won't start / crashes
- Check the **Console** tab for error messages
- Verify all required secrets are set
- Try stopping and restarting the Repl
- Clear cache: Click ⋮ menu → "Clear output and restart"

---

## 🆘 Getting Help

- **GitHub Issues**: [Open an issue](https://github.com/your-repo/issues) for bugs or questions
- **Discord Community**: [Join our Discord](https://discord.gg/your-invite) for real-time help
- **Documentation**: Check the main [README.md](README.md) for feature details

---

## 🔒 Security Best Practices

1. **Keep secrets private**: Never commit secrets to Git or share them publicly
2. **Use strong admin keys**: Generate random 32+ character keys
3. **Rotate credentials**: Periodically regenerate your `ADMIN_KEY`
4. **Limit access**: Only share your Repl with trusted collaborators
5. **Monitor logs**: Check for suspicious activity in device enrollments

---

## 📝 Next Steps

- Explore the **APK Management** page to deploy apps remotely
- Try the **Remote Control** feature to view and interact with device screens
- Set up **Device Groups** for managing multiple devices at once
- Customize **alert thresholds** for your use case

Happy monitoring! 🎊
