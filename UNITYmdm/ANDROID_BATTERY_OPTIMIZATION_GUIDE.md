# Android App Battery Optimization Implementation Guide

## Overview
This guide explains the changes needed in the NexMDM Android app to support battery optimization exemptions and automated whitelist management.

## Required Features

### 1. Battery Optimization Exemption (Self)
The app must request battery optimization exemption for itself on first run.

#### Implementation:
```kotlin
// File: MainActivity.kt or HeartbeatService.kt

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings

fun requestBatteryOptimizationExemption(context: Context) {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
        val powerManager = context.getSystemService(Context.POWER_SERVICE) as PowerManager
        val packageName = context.packageName
        
        if (!powerManager.isIgnoringBatteryOptimizations(packageName)) {
            val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                data = Uri.parse("package:$packageName")
            }
            
            try {
                context.startActivity(intent)
                Log.d("BatteryOptimization", "Requesting battery exemption for NexMDM")
            } catch (e: Exception) {
                Log.e("BatteryOptimization", "Failed to request battery exemption", e)
            }
        } else {
            Log.d("BatteryOptimization", "NexMDM already whitelisted")
        }
    }
}

// Call this in onCreate() or service initialization
override fun onCreate() {
    super.onCreate()
    requestBatteryOptimizationExemption(this)
}
```

### 2. FCM Handler for Battery Whitelist
Handle the `apply_battery_whitelist` FCM action to apply exemptions for multiple apps.

#### Implementation:
```kotlin
// File: NexMDMFirebaseMessagingService.kt

override fun onMessageReceived(remoteMessage: RemoteMessage) {
    val action = remoteMessage.data["action"]
    
    when (action) {
        "apply_battery_whitelist" -> {
            val packagesJson = remoteMessage.data["packages"]
            if (packagesJson != null) {
                applyBatteryWhitelist(packagesJson)
            }
        }
        // ... existing actions (ping, ring, etc.)
    }
}

private fun applyBatteryWhitelist(packagesJson: String) {
    try {
        val packages = JSONArray(packagesJson)
        val successCount = AtomicInteger(0)
        val failedCount = AtomicInteger(0)
        
        for (i in 0 until packages.length()) {
            val packageName = packages.getString(i)
            
            if (whitelistPackageFromBatteryOptimization(packageName)) {
                successCount.incrementAndGet()
                Log.d("BatteryWhitelist", "Whitelisted: $packageName")
            } else {
                failedCount.incrementAndGet()
                Log.e("BatteryWhitelist", "Failed to whitelist: $packageName")
            }
        }
        
        // Send acknowledgment to server
        val result = JSONObject().apply {
            put("success_count", successCount.get())
            put("failed_count", failedCount.get())
            put("total", packages.length())
        }
        
        sendHeartbeatAck("battery_whitelist_applied", result.toString())
        
        Toast.makeText(
            this,
            "Battery whitelist applied: ${successCount.get()}/${packages.length()} apps",
            Toast.LENGTH_LONG
        ).show()
        
    } catch (e: Exception) {
        Log.e("BatteryWhitelist", "Error applying battery whitelist", e)
        sendHeartbeatAck("battery_whitelist_failed", e.message ?: "Unknown error")
    }
}

private fun whitelistPackageFromBatteryOptimization(packageName: String): Boolean {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
        return true // No optimization on older versions
    }
    
    try {
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        
        if (powerManager.isIgnoringBatteryOptimizations(packageName)) {
            Log.d("BatteryWhitelist", "$packageName already whitelisted")
            return true
        }
        
        // For Device Owner apps, we can use Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS
        // This will show a system dialog for each app
        val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
            data = Uri.parse("package:$packageName")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        
        startActivity(intent)
        
        return true
    } catch (e: Exception) {
        Log.e("BatteryWhitelist", "Failed to whitelist $packageName", e)
        return false
    }
}
```

### 3. Device Owner Mode Enhancements
For Device Owner apps, use `DevicePolicyManager` to manage battery optimization more programmatically.

#### Implementation:
```kotlin
// File: DeviceAdminReceiver.kt or MainActivity.kt

import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context

fun applyBatteryWhitelistAsDeviceOwner(context: Context, packages: List<String>) {
    val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
    val adminComponent = ComponentName(context, NexDeviceAdminReceiver::class.java)
    
    if (!dpm.isDeviceOwnerApp(context.packageName)) {
        Log.e("BatteryWhitelist", "App is not Device Owner")
        return
    }
    
    // For each package, disable battery optimization using ADB-like commands
    packages.forEach { packageName ->
        try {
            // Use shell command execution if available (requires Device Owner)
            val command = "dumpsys deviceidle whitelist +$packageName"
            Runtime.getRuntime().exec(command)
            
            Log.d("BatteryWhitelist", "Device Owner whitelisted: $packageName")
        } catch (e: Exception) {
            Log.e("BatteryWhitelist", "Failed to whitelist via Device Owner: $packageName", e)
        }
    }
}
```

### 4. Startup Battery Whitelist Fetch
Fetch the battery whitelist from the server on app startup and apply automatically.

#### Implementation:
```kotlin
// File: HeartbeatService.kt or MainActivity.kt

private suspend fun fetchAndApplyBatteryWhitelist() {
    try {
        val response = withContext(Dispatchers.IO) {
            // Note: This endpoint requires authentication, so include device token
            val url = "$serverUrl/v1/battery-whitelist"
            val connection = URL(url).openConnection() as HttpURLConnection
            connection.requestMethod = "GET"
            connection.setRequestProperty("Authorization", "Bearer $deviceToken")
            
            if (connection.responseCode == 200) {
                val reader = BufferedReader(InputStreamReader(connection.inputStream))
                val response = reader.readText()
                reader.close()
                response
            } else {
                Log.e("BatteryWhitelist", "Failed to fetch whitelist: ${connection.responseCode}")
                null
            }
        }
        
        if (response != null) {
            val whitelist = JSONArray(response)
            val packages = mutableListOf<String>()
            
            for (i in 0 until whitelist.length()) {
                val entry = whitelist.getJSONObject(i)
                if (entry.getBoolean("enabled")) {
                    packages.add(entry.getString("package_name"))
                }
            }
            
            // Apply whitelist
            packages.forEach { packageName ->
                whitelistPackageFromBatteryOptimization(packageName)
            }
            
            Log.d("BatteryWhitelist", "Applied ${packages.size} packages from server whitelist")
        }
    } catch (e: Exception) {
        Log.e("BatteryWhitelist", "Error fetching battery whitelist", e)
    }
}

// Call this during service initialization
override fun onCreate() {
    super.onCreate()
    
    // Request exemption for self first
    requestBatteryOptimizationExemption(this)
    
    // Fetch and apply server whitelist
    GlobalScope.launch(Dispatchers.Main) {
        delay(2000) // Wait for service to stabilize
        fetchAndApplyBatteryWhitelist()
    }
}
```

### 5. Permissions Required
Add this permission to `AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS"/>
```

**Note**: This permission is restricted on Google Play Store but allowed for Device Owner/MDM apps distributed via enterprise channels.

## Integration Flow

### First-Time Device Setup (ADB)
1. ADB script disables Adaptive Battery globally
2. ADB script whitelists NexMDM and all configured apps from Doze
3. APK is installed and set as Device Owner
4. App requests battery exemption on first launch (backup)

### Existing Device (FCM Push)
1. User adds app to whitelist in dashboard
2. User clicks "Apply to Fleet"
3. Backend sends FCM to all devices with package list
4. Each device receives FCM and processes whitelist
5. Device shows system dialog for each app (requires user tap)
6. Device reports back success/failure count

### Android App Startup
1. App checks if it's whitelisted (self-check)
2. If not whitelisted, requests exemption
3. Fetches server whitelist via API
4. Applies exemptions for all listed apps
5. Persists check on every app restart

## Testing

### Test Battery Exemption Status:
```bash
# Check if app is whitelisted
adb shell dumpsys deviceidle whitelist | grep com.nexmdm

# Check Power Manager status
adb shell dumpsys power | grep -A 5 com.nexmdm

# Manually whitelist (for testing)
adb shell dumpsys deviceidle whitelist +com.nexmdm
```

### Test FCM Push:
```bash
# Send test FCM message from backend
curl -X POST http://localhost:3000/v1/devices/DEVICE_ID/apply-battery-whitelist \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Notes
- Device Owner apps can execute ADB-like commands programmatically
- Regular apps must show system dialogs for battery exemption
- Adaptive Battery settings persist across reboots but can be re-enabled by OTA updates
- OEM-specific battery managers (Samsung, Xiaomi, Huawei) may require additional handling

## Files to Modify
1. `app/src/main/java/com/nexmdm/HeartbeatService.kt` - Add startup whitelist fetch
2. `app/src/main/java/com/nexmdm/NexMDMFirebaseMessagingService.kt` - Add FCM handler
3. `app/src/main/java/com/nexmdm/MainActivity.kt` - Add self-exemption request
4. `app/src/main/AndroidManifest.xml` - Add REQUEST_IGNORE_BATTERY_OPTIMIZATIONS permission

## Expected Behavior After Implementation
- ✅ NexMDM app never killed by Android battery optimization
- ✅ Configured apps (e.g., Speedtest) never killed by Doze mode
- ✅ Dashboard can remotely manage battery whitelist
- ✅ ADB scripts automatically include current whitelist
- ✅ Devices self-heal on startup by fetching server whitelist
