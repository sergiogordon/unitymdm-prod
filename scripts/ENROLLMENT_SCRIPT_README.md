# NexMDM Windows CMD Enrollment Scripts

## Overview

Zero-touch enrollment scripts for deploying NexMDM to Android devices via ADB. These scripts handle APK installation, Device Owner provisioning, permission grants, system optimizations, and auto-enrollment into your MDM backend.

## Prerequisites

### Required Software
- **ADB (Android Debug Bridge)**: Installed and in your system PATH
  - Download from: [Android Platform Tools](https://developer.android.com/studio/releases/platform-tools)
- **curl**: For downloading APK (included in Windows 10+ by default)

### Device Requirements
- **Android 13+** device
- **USB debugging enabled** in Developer Options
- **For Device Owner mode**: Device must be in **factory-fresh state**
  - No user accounts added
  - Setup wizard not completed
  - `device_provisioned=0` and `user_setup_complete=0`

### Network Requirements
- Device connected via USB with ADB enabled
- Internet connection for downloading latest APK from backend

## Files

| File | Purpose |
|------|---------|
| `enroll_nexmdm.cmd` | Full multi-line script with detailed logging and error handling |
| `enroll_nexmdm_oneliner.cmd` | Compact single-line version for quick deployment |

## Usage

### Method 1: Full Script (Recommended)

1. Connect Android device via USB
2. Enable USB debugging on device
3. Run the script:
   ```cmd
   cd scripts
   enroll_nexmdm.cmd
   ```

### Method 2: One-Liner (Quick Deployment)

1. Connect Android device via USB
2. Open Command Prompt as Administrator
3. Copy and paste the entire contents of `enroll_nexmdm_oneliner.cmd`
4. Press Enter

### Customization

Edit the configuration variables at the top of the script:

```bat
set PKG=com.nexmdm
set ALIAS=test                    REM Change to identify this device (e.g., "warehouse-01")
set SPEEDTEST_PKG=com.unitynetwork.unityapp
set BASE_URL=https://83b071bb-c5cb-4eda-b79c-d276873904c2-00-2ha4ytvejclnm.worf.replit.dev
set BEARER=_sDKZuilFJVWi3NkpQdEjmM07v2-HuGa3teb7bGKMro
```

## What the Script Does

### Step-by-Step Process

1. **Wait for Device** - Waits for ADB connection
2. **Download APK** - Fetches latest NexMDM APK from backend using enrollment token
3. **Install APK** - Attempts update (`-r`), falls back to clean install if needed
4. **Device Owner Setup** - Checks and sets Device Owner mode (requires factory-reset device)
5. **Permissions** - Grants runtime permissions and sets app operations
6. **Optimizations** - Applies system settings for performance and reliability:
   - Reduces animations (0.5x speed)
   - Disables battery optimization for NexMDM
   - Disables sleep on power
   - Enables stay-awake while charging
   - Disables package verification
   - Configures WiFi to never sleep
7. **Configuration** - Sends enrollment broadcast with server URL, token, and alias
8. **Verification** - Confirms service is running

### Device Owner Benefits

When Device Owner mode is enabled, NexMDM gains:
- **Silent app installation** - Install/update apps without user interaction
- **Remote wipe capabilities** - Factory reset devices remotely
- **Policy enforcement** - Lock down device settings
- **Persistent management** - Cannot be uninstalled by user

## Exit Codes

| Code | Meaning | Troubleshooting |
|------|---------|----------------|
| 0 | Success | Device enrolled successfully |
| 2 | No device found | Check USB connection and ADB drivers |
| 3 | APK download failed | Verify network connection and backend URL |
| 4 | APK installation failed | Check device storage space and permissions |
| 5 | Device already provisioned | Factory reset required for Device Owner mode |
| 6 | Device Owner set failed | Device incompatible or not in factory state |
| 7 | Device Owner verification failed | Re-run script or check `dumpsys device_policy` |
| 8 | Configuration broadcast failed | Check app installed correctly and receiver exists |
| 9 | Service not running | Check logcat for app errors: `adb logcat | findstr NexMDM` |

## Troubleshooting

### "Device already provisioned" Error (Exit 5)

**Problem**: Device Owner can only be set on factory-fresh devices.

**Solutions**:
1. **Factory Reset** (recommended for Device Owner):
   - Settings → System → Reset options → Factory data reset
   - Run script immediately after reset (before adding accounts)

2. **Use QR Code Enrollment** (alternative):
   - Skip Device Owner setup
   - Use QR provisioning from the web dashboard
   - Limited management capabilities without Device Owner

### "No device found" Error (Exit 2)

**Checks**:
- Run `adb devices` to verify device is connected
- Install/update ADB drivers for your device
- Enable USB debugging in Developer Options
- Try different USB cable or port

### APK Installation Fails (Exit 4)

**Common Causes**:
- Insufficient storage space on device
- Signature mismatch (uninstall existing app first)
- Device security settings blocking unknown sources

**Fix**:
```cmd
adb shell pm uninstall com.nexmdm
adb install -t -d "%APK_PATH%"
```

### Service Not Running (Exit 9)

**Diagnosis**:
```cmd
REM Check if app is installed
adb shell pm list packages | findstr nexmdm

REM View app logs
adb logcat -s NexMDM:V

REM Check crash logs
adb logcat -b crash
```

### Device Owner Already Set to Different App

**Symptom**: `dumpsys device_policy` shows another app as Device Owner

**Fix**:
```cmd
REM Remove existing Device Owner
adb shell dpm remove-active-admin com.other.app/.DeviceAdminReceiver

REM Then re-run enrollment script
```

## Advanced Usage

### Bulk Enrollment

Create a batch file to loop through multiple devices:

```bat
@echo off
set /p ALIAS_PREFIX="Enter device alias prefix: "
set COUNTER=1

:LOOP
echo.
echo ====================================
echo Enrolling device %COUNTER%...
echo ====================================
set ALIAS=%ALIAS_PREFIX%-%COUNTER%
call enroll_nexmdm.cmd
if errorlevel 1 (
  echo Device %COUNTER% failed. Fix issue and press any key to retry...
  pause >nul
  goto LOOP
)
set /a COUNTER+=1
echo.
echo Device enrolled! Disconnect and connect next device.
pause
goto LOOP
```

### CI/CD Integration

For automated testing:

```yaml
# GitHub Actions example
- name: Enroll Test Device
  run: |
    adb wait-for-device
    scripts/enroll_nexmdm.cmd
  env:
    ALIAS: ci-device-${{ github.run_id }}
```

### Verify Enrollment

After script completes, verify in dashboard:

```cmd
REM On device - check heartbeat is being sent
adb logcat -s NexMDM:V | findstr heartbeat

REM Check Device Owner status
adb shell dumpsys device_policy | findstr "Device Owner"

REM Verify auto-start on boot
adb shell dumpsys package com.nexmdm | findstr "enabled=1"
```

## Security Notes

- **Enrollment Token**: The `BEARER` token is a single-use enrollment credential
- **Device Owner**: Grants full device control - only use on company-owned devices
- **Network**: APK download is over HTTPS with bearer authentication
- **Credentials**: Never commit tokens to version control in production

## Support

For issues:
1. Check exit codes and troubleshooting section above
2. Review device logs: `adb logcat -s NexMDM:V`
3. Verify backend is accessible: `curl -I %BASE_URL%`
4. Check dashboard for device enrollment status

## References

- [Android Device Owner Mode](https://developer.android.com/work/dpc/dedicated-devices/device-owner)
- [ADB Documentation](https://developer.android.com/studio/command-line/adb)
- [Device Policy Manager](https://developer.android.com/reference/android/app/admin/DevicePolicyManager)
