# USAGE_STATS Permission Grant Guide

## Overview
The Android agent requires the **USAGE_STATS** permission to track foreground app usage for service monitoring. This permission allows the backend to determine if a monitored app (like Speedtest) is currently running.

## Why Devices Show "Unknown" Service Status

When a device shows service status as **"Unknown"**, it means one of the following:

1. **App NOT installed** → Backend correctly sets `service_up = None` → Shows "Unknown" ✅
2. **USAGE_STATS permission NOT granted** → Backend receives `monitored_foreground_recent_s = null` → Shows "Unknown" ⚠️

## Automatic Permission Grant (Device Owner Mode)

### How It Works
For devices enrolled in **Device Owner** mode, you can grant USAGE_STATS permission remotely via FCM:

```bash
curl -X POST "http://localhost:8000/v1/devices/{device_id}/grant-permissions" \
  -H "X-Admin: YOUR_ADMIN_KEY"
```

### What Happens
1. Backend sends `grant_permissions` FCM command
2. Android agent receives command in `FcmMessagingService`
3. `DeviceOwnerPermissionManager.grantUsageStatsPermission()` uses reflection to grant permission
4. Agent triggers immediate heartbeat with updated foreground data

### Known Limitations
**Automatic grant can fail on**:
- Some Android versions (manufacturer customizations)
- Devices with restricted AppOps access
- OEM-specific permission restrictions

**Symptoms of failure**:
- Device still shows "Unknown" service status after grant command
- Backend logs continue to show `monitoring.evaluate.unknown` with `reason="usage_access_missing"`
- No `monitored_foreground_recent_s` data in heartbeats

## Manual Permission Grant (Workaround)

If automatic grant fails, grant the permission manually on the device:

### Steps
1. On the Android device, go to:
   - **Settings** → **Apps** → **Special app access** → **Usage access**
   
   OR on some devices:
   - **Settings** → **Security & privacy** → **Privacy** → **Special app access** → **Usage access**

2. Find **NexMDM** in the app list

3. Toggle **ON** to grant permission

4. Return to home screen

### Verification
After granting manually:
1. Wait up to 5 minutes for next heartbeat (or send a Ping command for immediate heartbeat)
2. Check device status in admin dashboard
3. Service status should change from **"Unknown"** → **"Up"** (if app is running) or **"Down"** (if not running)

## Backend Logging

When monitoring is working correctly, you'll see:

```json
// App installed, USAGE_STATS granted, app IS running
{"event": "monitoring.evaluate", "service_up": true}

// App installed, USAGE_STATS granted, app NOT running
{"event": "monitoring.evaluate", "service_up": false}

// App installed, USAGE_STATS NOT granted
{"event": "monitoring.evaluate.unknown", "reason": "usage_access_missing", "service_up": null}

// App NOT installed
{"event": "monitoring.evaluate.not_installed", "reason": "app_not_installed", "service_up": null}
```

## Deployment Recommendation

For large-scale deployments:
1. **Try automatic grant first** via `/v1/devices/{device_id}/grant-permissions`
2. **Monitor device_events** for `permission_grant_sent` events
3. **Verify success** by checking next heartbeat for `monitored_foreground_recent_s` data
4. **Fall back to manual** grant if automatic fails

## Technical Details

### Android Agent Code
- **Permission check**: `TelemetryCollector.getMonitoredForegroundRecency()` (lines 118-158)
- **Permission grant**: `DeviceOwnerPermissionManager.grantUsageStatsPermission()` (lines 118-155)
- **FCM handler**: `FcmMessagingService.handleGrantPermissions()` (lines 471-505)

### Backend Logic
- **Service evaluation**: `server/main.py` heartbeat endpoint (lines 1654-1714)
- **Grant command**: `server/main.py` `/v1/devices/{device_id}/grant-permissions` endpoint (lines 3465-3542)

## Current Status (Oct 26, 2025)

### D4 (ad03b5f4-ed42-43eb-8332-89914ab12566)
- **Monitored package**: org.zwanoo.android.speedtest
- **App installed**: ✅ Yes
- **USAGE_STATS granted**: ❌ No (automatic grant failed)
- **Service status**: Unknown
- **Action needed**: Manual permission grant

### D23 (4d701dec-3cd9-4158-9f2e-2089cb2d0759)
- **Monitored package**: org.zwanoo.android.speedtest  
- **App installed**: ❌ No
- **Service status**: Unknown (correct - app not installed)
- **Action needed**: None (working as expected)
