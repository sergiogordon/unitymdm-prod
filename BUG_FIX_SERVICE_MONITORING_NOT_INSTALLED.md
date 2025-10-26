# Bug Fix: Service Showing "Up" When App Not Installed

## Problem Summary
Device D4 showed the Speedtest service status as **"Up"** even though the app was **not installed** on the device.

## Root Cause Analysis

### Database Investigation
```
D4 Status (before fix):
- service_up: TRUE ✗
- monitored_foreground_recent_s: -1
- monitored_package: org.zwanoo.android.speedtest
```

### The Bug
The service monitoring logic had a critical flaw:

1. **Android Agent Behavior**: When an app is not installed (or not found in UsageStats), the Android agent sends `-1` as a sentinel value for `foreground_recent_seconds`:
   ```kotlin
   // MonitorService.kt line 231
   foreground_recent_seconds = speedtestInfo.lastForegroundSeconds ?: -1
   ```

2. **Backend Flaw**: The backend checked if the value was `not None`:
   ```python
   # Old code (BUGGY)
   if monitored_foreground_recent_s is not None:
       threshold_seconds = monitoring_settings["threshold_min"] * 60
       service_up = monitored_foreground_recent_s <= threshold_seconds  # -1 <= 600 = TRUE!
   ```

3. **Result**: Since `-1 <= 600` evaluates to `TRUE`, the service incorrectly showed as "Up" when the app wasn't even installed!

## The Fix

### Changes Made
Updated `server/main.py` heartbeat endpoint with three defensive checks:

1. **Check if app is installed**:
   ```python
   app_info = payload.app_versions.get(monitoring_settings["package"])
   is_app_installed = app_info and app_info.installed if app_info else False
   ```

2. **Normalize -1 to None**:
   ```python
   # Treat -1 as sentinel value for "not available"
   if monitored_foreground_recent_s is not None and monitored_foreground_recent_s < 0:
       monitored_foreground_recent_s = None
   ```

3. **Evaluate only if installed**:
   ```python
   if not is_app_installed:
       # App not installed - service status is unknown
       service_up = None
       log("monitoring.evaluate.not_installed", reason="app_not_installed")
   elif monitored_foreground_recent_s is not None:
       # App installed and we have foreground data - evaluate status
       threshold_seconds = monitoring_settings["threshold_min"] * 60
       service_up = monitored_foreground_recent_s <= threshold_seconds
   else:
       # App installed but foreground data not available
       service_up = None
       log("monitoring.evaluate.unknown", reason="usage_access_missing")
   ```

## Expected Behavior After Fix

### When App NOT Installed
- **service_up**: `None` (Unknown)
- **Frontend Display**: Gray "Unknown" badge
- **Log**: `monitoring.evaluate.not_installed` with `reason="app_not_installed"`

### When App IS Installed
- **With foreground data**: Evaluates normally (Up/Down based on threshold)
- **Without foreground data**: Shows "Unknown" (e.g., usage access permission missing)

## Verification Steps

1. **Wait for next heartbeat** from D4 (devices send every 5 minutes)
2. **Check database**:
   ```sql
   SELECT alias, service_up, monitored_foreground_recent_s 
   FROM device_last_status dls
   JOIN devices d ON d.id = dls.device_id
   WHERE d.alias = 'D4';
   ```
   Expected: `service_up` should now be `NULL` instead of `TRUE`

3. **Check frontend**: D4's service status should show "Unknown" in gray badge

4. **Check logs**:
   ```bash
   grep "monitoring.evaluate.not_installed" /tmp/logs/Backend_*.log
   ```
   Should see log entry for D4 with `reason="app_not_installed"`

## Files Modified
- `server/main.py` (lines 1654-1714): Service monitoring evaluation logic

## Status
✅ **FIXED** - Backend restarted at 18:08:24 UTC
⏳ **Waiting** for next heartbeat from D4 to verify fix in production
