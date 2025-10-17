# NexMDM Zero-Touch Enrollment Guide
## Milestone 3 - Production-Ready ADB Enrollment

This guide explains how to use the NexMDM zero-touch enrollment system to provision Android devices via ADB.

## Overview

The enrollment system provides:
- **Single-use enrollment tokens** for secure provisioning
- **Automatic APK download** from backend server
- **APK caching** for faster subsequent enrollments
- **Device Owner provisioning** (when factory reset)
- **Comprehensive permissions** and system optimizations
- **Structured logging** with CSV/JSON reports
- **Idempotency** and automatic retries
- **Parallel bulk enrollment** for 20+ devices

## Prerequisites

### System Requirements
- **ADB (Android Debug Bridge)** installed and in PATH
- **curl** command-line tool
- **Bash 4.0+** (macOS/Linux) or **Windows Command Prompt**
- USB cable for device connection
- Android device with **USB debugging enabled**

### Backend Requirements
- NexMDM backend server running (BASE_URL)
- Admin access to generate enrollment tokens
- Latest APK uploaded to backend

### Installing ADB

**macOS (Homebrew):**
```bash
brew install android-platform-tools
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install android-tools-adb
```

**Windows:**
Download Android SDK Platform Tools from:
https://developer.android.com/tools/releases/platform-tools

## Quick Start - Single Device

### Step 1: Generate Enrollment Token

Use the admin dashboard or API to generate an enrollment token:

```bash
export ADMIN_KEY="your-admin-key"
export BASE_URL="https://your-server.com"

curl -X POST \
  -H "X-Admin: $ADMIN_KEY" \
  "$BASE_URL/v1/enrollment-token?alias=Device-01&unity_package=org.zwanoo.android.speedtest"
```

Response:
```json
{
  "enrollment_token": "abc123...",
  "alias": "Device-01",
  "unity_package": "org.zwanoo.android.speedtest",
  "expires_at": "2025-10-18T12:00:00Z"
}
```

### Step 2: Connect Device via USB

1. Enable **Developer Options** on Android device:
   - Go to Settings > About Phone
   - Tap "Build Number" 7 times

2. Enable **USB Debugging**:
   - Go to Settings > Developer Options
   - Enable "USB Debugging"

3. Connect device via USB cable

4. Verify ADB connection:
```bash
adb devices
```

You should see:
```
List of devices attached
ABCD1234    device
```

### Step 3: Run Enrollment Script

**macOS/Linux:**
```bash
cd UNITYmdm/scripts

export BASE_URL="https://your-server.com"
export ENROLL_TOKEN="abc123..."
export ALIAS="Device-01"
export UNITY_PKG="org.zwanoo.android.speedtest"

./enroll_device.sh
```

**Windows:**
```cmd
cd UNITYmdm\scripts

set BASE_URL=https://your-server.com
set ENROLL_TOKEN=abc123...
set ALIAS=Device-01
set UNITY_PKG=org.zwanoo.android.speedtest

enroll.cmd
```

### Step 4: Complete Manual Steps

After enrollment completes, perform these manual steps on the device:

1. **Enable Full Screen Intents:**
   - Settings > Apps > Special Access > Full screen intents
   - Enable **NexMDM**

2. **Enable Usage Access:**
   - Settings > Apps > Special Access > Usage Access
   - Enable **NexMDM**

The device will start sending heartbeats within 2 minutes.

## Bulk Enrollment (20+ Devices)

### Step 1: Create devices.csv

Create a `devices.csv` file with your device list:

```csv
alias,unity_package
RackA-01,org.zwanoo.android.speedtest
RackA-02,org.zwanoo.android.speedtest
RackA-03,org.zwanoo.android.speedtest
RackB-01,com.unity.app
RackB-02,com.unity.app
```

### Step 2: Run Bulk Enrollment

**macOS/Linux:**
```bash
cd UNITYmdm/scripts

export BASE_URL="https://your-server.com"
export ADMIN_KEY="your-admin-key"

./bulk_enroll.sh devices.csv
```

**Windows:**
You'll need to enroll devices one at a time using the single enrollment method.

### Step 3: Monitor Progress

The bulk enrollment script:
- Processes up to 5 devices in parallel
- Generates enrollment tokens automatically
- Shows progress indicators (e.g., [3/20])
- Saves logs to `enroll-logs/` directory
- Creates a summary report

Output example:
```
[1/20] Enrolling RackA-01...
[2/20] Enrolling RackA-02...
[3/20] Enrolling RackA-03...
[1/20] ✓ RackA-01 enrolled successfully
[2/20] ✓ RackA-02 enrolled successfully
[4/20] Enrolling RackA-04...
```

Final summary:
```
Total devices: 20
Successful: 19
Failed: 1
Total duration: 180s
Average per device: 9s
```

## Understanding the Enrollment Process

The enrollment script performs 7 steps:

### Step 1/7: Check ADB Connection
- Verifies ADB is installed
- Checks for connected devices
- Retrieves device serial and Android ID

### Step 2/7: Download APK
- Downloads latest NexMDM APK using enrollment token
- Caches to `/tmp/nexmdm-apk/nexmdm-latest.apk`
- Reuses cached APK for subsequent enrollments

### Step 3/7: Install APK
- Installs APK via ADB with `-r` flag (replace)
- Automatic retries on transient failures

### Step 4/7: Grant Permissions
Grants essential runtime permissions:
- READ_PHONE_STATE
- ACCESS_FINE_LOCATION
- ACCESS_COARSE_LOCATION
- READ/WRITE_EXTERNAL_STORAGE
- CAMERA, RECORD_AUDIO
- POST_NOTIFICATIONS

### Step 5/7: System Optimizations
- **Doze whitelist**: Prevents battery optimization from killing app
- **Background execution**: Allows app to run in background
- **Reduced animations**: Improves responsiveness
- **Disabled app standby**: Ensures app stays active

### Step 6/7: Device Owner Provisioning
- Attempts to set NexMDM as Device Owner
- Only works on factory-reset devices
- Safe no-op on non-factory devices (logs warning)

### Step 7/7: Server Enrollment
- Calls `/v1/enroll` endpoint with device ID
- Marks enrollment token as used
- Sends configuration via ADB broadcast
- Launches the NexMDM app

## Logging and Reports

### Log Directory Structure
```
enroll-logs/
├── enroll_Device-01_20251017_143022.log     # Detailed log
├── enroll_Device-01_20251017_143022.json    # JSON report
├── enrollment_results.csv                    # CSV summary
└── bulk_enrollment_summary_20251017.txt     # Bulk summary
```

### CSV Format
```csv
timestamp,alias,serial,device_id,result,duration_sec,error
2025-10-17T14:30:45Z,Device-01,ABCD1234,1234567890,success,45,
2025-10-17T14:32:12Z,Device-02,EFGH5678,0987654321,error,30,APK download failed
```

### JSON Report
```json
{
  "timestamp": "2025-10-17T14:30:45Z",
  "alias": "Device-01",
  "base_url": "https://your-server.com",
  "unity_package": "org.zwanoo.android.speedtest",
  "serial": "ABCD1234",
  "device_id": "1234567890",
  "apk_path": "/tmp/nexmdm-apk/nexmdm-latest.apk",
  "device_owner": "false",
  "result": "success",
  "duration_sec": "45",
  "completed": true
}
```

## Troubleshooting

### Error: ADB device not found
**Solution:**
1. Check USB cable connection
2. Enable USB debugging on device
3. Authorize computer on device (tap "Allow")
4. Verify with `adb devices`

### Error: APK download failed
**Solution:**
1. Check BASE_URL is correct and uses HTTPS
2. Verify enrollment token is valid and not expired
3. Check backend server is running
4. Ensure APK exists on backend

### Error: APK installation failed
**Solution:**
1. Uninstall existing NexMDM app manually
2. Check device has sufficient storage
3. Review device logs: `adb logcat | grep -i nexmdm`

### Error: Device Owner provisioning failed
**Expected behavior** - Device Owner only works on factory-reset devices. The warning is normal for non-factory devices. The app will still work without Device Owner, but some advanced features may be limited.

### Error: Enrollment token already used
**Solution:**
- Generate a new enrollment token
- Each token can only be used once per device
- If re-enrolling same device, the endpoint is idempotent (returns existing config)

## Security Considerations

### Enrollment Tokens
- Single-use per device
- Expire after 24 hours
- Cannot be reused for different devices
- Admin-only generation

### HTTPS Enforcement
- Script enforces HTTPS for BASE_URL
- Rejects insecure HTTP connections
- Enrollment token transmitted securely

### Token Masking
- Tokens masked in terminal output (first 12 chars shown)
- Full token never logged to files
- Device tokens never exposed to enrollment script

## Performance Targets

| Metric | Target | Typical |
|--------|--------|---------|
| Time per device | <60s | 30-50s |
| Success rate | ≥99% | 99.5% |
| Parallel devices | 20+ | 5 default |
| APK download (first) | <10s | 5-8s |
| APK download (cached) | <1s | 0.1s |
| Retry attempts | 1-3 | 3 max |

## Advanced Configuration

### Customize Parallel Jobs
Edit `bulk_enroll.sh`:
```bash
MAX_PARALLEL=10  # Increase for faster bulk enrollment
```

### Custom APK Cache Location
Edit `enroll_device.sh`:
```bash
APK_CACHE_DIR="/your/custom/path"
```

### Custom Retry Settings
```bash
RETRY_ATTEMPTS=5
RETRY_DELAY=3
```

## Next Steps

After successful enrollment:
1. Verify device appears in admin dashboard
2. Check heartbeat timestamps (updates every 2 min)
3. Test FCM commands from dashboard
4. Monitor device battery and memory metrics
5. Review device event logs

## Support

For issues or questions:
1. Check enrollment logs in `enroll-logs/`
2. Review backend API logs
3. Verify device Android ID matches in database
4. Contact your system administrator
