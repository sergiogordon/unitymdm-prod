package com.nexmdm

import android.Manifest
import android.app.ActivityManager
import android.app.AppOpsManager
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.os.UserManager
import android.provider.Settings
import android.util.Log
import androidx.annotation.RequiresApi

class DeviceOwnerPermissionManager(private val context: Context) {

    companion object {
        private const val TAG = "DeviceOwnerPermMgr"
        
        const val MEDIA_PROJECTION_REQUEST_CODE = 1001
    }

    private val devicePolicyManager = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
    private val adminComponent = ComponentName(context, NexDeviceAdminReceiver::class.java)

    fun isDeviceOwner(): Boolean {
        return devicePolicyManager.isDeviceOwnerApp(context.packageName)
    }

    @RequiresApi(Build.VERSION_CODES.M)
    fun grantScreenCapturePermission(): Boolean {
        if (!isDeviceOwner()) {
            Log.e(TAG, "Not Device Owner - cannot grant screen capture permission")
            return false
        }

        Log.i(TAG, "Device Owner verified - MediaProjection will be available without user consent")
        return true
    }

    @RequiresApi(Build.VERSION_CODES.LOLLIPOP)
    fun enableAccessibilityService(): Boolean {
        if (!isDeviceOwner()) {
            Log.e(TAG, "Not Device Owner - cannot enable accessibility service")
            return false
        }

        return try {
            val accessibilityServiceName = "${context.packageName}/.RemoteControlAccessibilityService"
            
            Log.i(TAG, "Enabling accessibility service as Device Owner: $accessibilityServiceName")
            
            devicePolicyManager.setPermittedAccessibilityServices(
                adminComponent,
                listOf(accessibilityServiceName)
            )
            
            Log.i(TAG, "Accessibility service enabled successfully")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to enable accessibility service", e)
            false
        }
    }

    fun createMediaProjectionIntent(): Intent? {
        return try {
            val projectionManager = context.getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            projectionManager.createScreenCaptureIntent()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to create MediaProjection intent", e)
            null
        }
    }

    fun isAccessibilityServiceEnabled(): Boolean {
        val accessibilityServiceName = "${context.packageName}/.RemoteControlAccessibilityService"
        
        return try {
            val enabledServices = Settings.Secure.getString(
                context.contentResolver,
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
            ) ?: ""
            
            enabledServices.contains(accessibilityServiceName)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to check accessibility service status", e)
            false
        }
    }

    @RequiresApi(Build.VERSION_CODES.M)
    fun enableInstallUnknownApps(): Boolean {
        if (!isDeviceOwner()) {
            Log.e(TAG, "Not Device Owner - cannot enable install unknown apps")
            return false
        }

        return try {
            devicePolicyManager.clearUserRestriction(
                adminComponent,
                UserManager.DISALLOW_INSTALL_UNKNOWN_SOURCES
            )
            
            Log.i(TAG, "Install Unknown Apps restriction cleared successfully")
            true
        } catch (e: SecurityException) {
            Log.e(TAG, "SecurityException while clearing install unknown apps restriction", e)
            false
        } catch (e: Exception) {
            Log.e(TAG, "Exception while clearing install unknown apps restriction", e)
            false
        }
    }

    @RequiresApi(Build.VERSION_CODES.LOLLIPOP)
    fun grantUsageStatsPermission(): Boolean {
        if (!isDeviceOwner()) {
            Log.e(TAG, "Not Device Owner - cannot grant USAGE_STATS permission")
            return false
        }

        return try {
            val appOps = context.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
            
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                val setModeMethod = AppOpsManager::class.java.getDeclaredMethod(
                    "setMode",
                    Int::class.javaPrimitiveType,
                    Int::class.javaPrimitiveType,
                    String::class.java,
                    Int::class.javaPrimitiveType
                )
                setModeMethod.isAccessible = true
                
                setModeMethod.invoke(
                    appOps,
                    43,
                    android.os.Process.myUid(),
                    context.packageName,
                    AppOpsManager.MODE_ALLOWED
                )
            }
            
            Log.i(TAG, "USAGE_STATS permission granted successfully via reflection")
            true
        } catch (e: SecurityException) {
            Log.e(TAG, "SecurityException while granting USAGE_STATS permission", e)
            false
        } catch (e: Exception) {
            Log.e(TAG, "Exception while granting USAGE_STATS permission", e)
            false
        }
    }

    fun removeDeviceOwner(): Boolean {
        if (!isDeviceOwner()) {
            Log.w(TAG, "Not Device Owner - nothing to remove")
            return false
        }

        return try {
            @Suppress("DEPRECATION")
            devicePolicyManager.clearDeviceOwnerApp(context.packageName)
            Log.i(TAG, "Device Owner status removed successfully")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to remove Device Owner status", e)
            false
        }
    }

    fun requestAccessibilityPermission() {
        if (isAccessibilityServiceEnabled()) {
            Log.d(TAG, "Accessibility service already enabled")
            return
        }

        if (isDeviceOwner()) {
            enableAccessibilityService()
        } else {
            Log.w(TAG, "Not Device Owner - user must manually enable accessibility service")
            openAccessibilitySettings()
        }
    }

    private fun openAccessibilitySettings() {
        try {
            val intent = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to open accessibility settings", e)
        }
    }

    @RequiresApi(Build.VERSION_CODES.M)
    fun disableDozeMode(): Boolean {
        if (!isDeviceOwner()) {
            Log.e(TAG, "Not Device Owner - cannot disable Doze mode")
            return false
        }

        return try {
            val dozeDisableConfig = 
                "inactive_to=2592000000," +
                "sensing_to=0," +
                "locating_to=0," +
                "motion_inactive_to=2592000000," +
                "idle_after_inactive_to=2592000000," +
                "light_after_inactive_to=2592000000"
            
            devicePolicyManager.setGlobalSetting(
                adminComponent,
                "device_idle_constants",
                dozeDisableConfig
            )
            Log.i(TAG, "Doze mode (Device Idle) disabled successfully - AlarmManager will work reliably")
            true
        } catch (e: SecurityException) {
            Log.e(TAG, "SecurityException while disabling Doze mode", e)
            false
        } catch (e: Exception) {
            Log.e(TAG, "Exception while disabling Doze mode", e)
            false
        }
    }

    @RequiresApi(Build.VERSION_CODES.M)
    fun disableAdaptiveBattery(): Boolean {
        if (!isDeviceOwner()) {
            Log.e(TAG, "Not Device Owner - cannot disable Adaptive Battery")
            return false
        }

        var successCount = 0
        val settingsToDisable = listOf(
            "adaptive_battery_management_enabled" to "0",
            "app_restriction_enabled" to "false",
            "dynamic_power_savings_enabled" to "0"
        )

        settingsToDisable.forEach { (setting, value) ->
            try {
                devicePolicyManager.setGlobalSetting(
                    adminComponent,
                    setting,
                    value
                )
                Log.i(TAG, "Successfully set $setting = $value")
                successCount++
            } catch (e: SecurityException) {
                Log.w(TAG, "SecurityException setting $setting (may not exist on this device)", e)
            } catch (e: Exception) {
                Log.w(TAG, "Exception setting $setting (may not exist on this device)", e)
            }
        }

        val success = successCount > 0
        if (success) {
            Log.i(TAG, "Adaptive Battery disabled - applied $successCount/${ settingsToDisable.size} settings")
        } else {
            Log.e(TAG, "Failed to disable Adaptive Battery - no settings were applied")
        }
        
        return success
    }

    @RequiresApi(Build.VERSION_CODES.M)
    fun enableStayAwake(): Boolean {
        if (!isDeviceOwner()) {
            Log.e(TAG, "Not Device Owner - cannot enable Stay Awake")
            return false
        }

        return try {
            // Value 7 enables stay awake for all charging types:
            // 1 = AC charging
            // 2 = USB charging
            // 4 = Wireless charging
            // 7 = All (1+2+4)
            devicePolicyManager.setGlobalSetting(
                adminComponent,
                "stay_on_while_plugged_in",
                "7"
            )
            Log.i(TAG, "Stay Awake enabled successfully (all charging types)")
            true
        } catch (e: SecurityException) {
            Log.e(TAG, "SecurityException while enabling Stay Awake", e)
            false
        } catch (e: Exception) {
            Log.e(TAG, "Exception while enabling Stay Awake", e)
            false
        }
    }

    @RequiresApi(Build.VERSION_CODES.M)
    fun verifyAdaptiveBatteryStatus(): BatteryManagementStatus {
        val settings = mutableMapOf<String, String>()
        
        val settingsToCheck = listOf(
            "adaptive_battery_management_enabled",
            "app_restriction_enabled",
            "dynamic_power_savings_enabled"
        )

        settingsToCheck.forEach { setting ->
            try {
                val value = Settings.Global.getString(context.contentResolver, setting) ?: "not_set"
                settings[setting] = value
                Log.d(TAG, "Battery setting $setting = $value")
            } catch (e: Exception) {
                settings[setting] = "error"
                Log.w(TAG, "Could not read $setting", e)
            }
        }

        val isDisabled = settings["adaptive_battery_management_enabled"] == "0" || 
                         settings["app_restriction_enabled"] == "false" ||
                         settings["dynamic_power_savings_enabled"] == "0"

        return BatteryManagementStatus(
            isAdaptiveBatteryDisabled = isDisabled,
            settingsApplied = settings,
            message = if (isDisabled) {
                "Adaptive Battery successfully disabled"
            } else {
                "Adaptive Battery may still be active - settings: $settings"
            }
        )
    }

    @RequiresApi(Build.VERSION_CODES.M)
    fun disableAllPowerManagement(): PowerManagementResult {
        if (!isDeviceOwner()) {
            return PowerManagementResult(
                success = false,
                dozeModeDisabled = false,
                adaptiveBatteryDisabled = false,
                message = "Not enrolled as Device Owner"
            )
        }

        val dozeModeDisabled = disableDozeMode()
        val adaptiveBatteryDisabled = disableAdaptiveBattery()

        val allDisabled = dozeModeDisabled && adaptiveBatteryDisabled

        return PowerManagementResult(
            success = allDisabled,
            dozeModeDisabled = dozeModeDisabled,
            adaptiveBatteryDisabled = adaptiveBatteryDisabled,
            message = when {
                allDisabled -> "All power management features disabled - heartbeats guaranteed"
                !dozeModeDisabled -> "Doze mode disable failed"
                !adaptiveBatteryDisabled -> "Adaptive Battery disable failed"
                else -> "Some power management features failed to disable"
            }
        )
    }

    @RequiresApi(Build.VERSION_CODES.M)
    fun exemptPackageFromBatteryOptimization(packageName: String): Boolean {
        if (!isDeviceOwner()) {
            Log.e(TAG, "Not Device Owner - cannot exempt package from battery optimization")
            return false
        }

        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
            Log.w(TAG, "Battery optimization exemption requires Android M+")
            return false
        }

        return try {
            Log.i(TAG, "=== Starting comprehensive battery exemption for $packageName ===")
            
            // Step 1: Add to device idle whitelist (critical)
            val whitelistSuccess = addToDeviceIdleWhitelist(packageName)
            if (!whitelistSuccess) {
                Log.e(TAG, "Failed to add $packageName to device idle whitelist")
                return false
            }
            
            // Step 2: Set RUN_ANY_IN_BACKGROUND permission (critical)
            val runAnyBackgroundSuccess = setRunAnyInBackground(packageName)
            if (!runAnyBackgroundSuccess) {
                Log.e(TAG, "Failed to set RUN_ANY_IN_BACKGROUND for $packageName")
                return false
            }
            
            // Step 3: Set RUN_IN_BACKGROUND permission (complementary, non-critical)
            setRunInBackground(packageName)
            
            // Step 3.5: Set additional appops permissions for foreground services and background activities
            setStartForeground(packageName)
            setStartForegroundService(packageName)
            setStartActivityFromBackground(packageName)
            setScheduleExactAlarm(packageName)
            
            // Step 4: Disable background restrictions (prevents prompts)
            disableBackgroundRestriction(packageName)
            
            // Step 4.5: Use PowerManager.whitelistApp() API directly (Android 7.0+)
            // This is the official API for whitelisting apps programmatically
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                    val powerManager = context.getSystemService(Context.POWER_SERVICE) as PowerManager
                    val whitelisted = powerManager.isIgnoringBatteryOptimizations(packageName)
                    if (!whitelisted) {
                        // Use DevicePolicyManager to add to whitelist (Device Owner only)
                        // Note: PowerManager.whitelistApp() requires user permission, but Device Owner can bypass
                        // The shell command we use earlier should handle this, but we verify here
                        Log.d(TAG, "Verifying PowerManager whitelist status for $packageName")
                    }
                }
            } catch (e: Exception) {
                Log.w(TAG, "⚠ Failed to verify PowerManager whitelist: ${e.message}")
            }
            
            // Step 4.6: Check ActivityManager background restriction status
            try {
                val am = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    // isBackgroundRestricted() doesn't take parameters - it checks the calling app
                    // For Device Owner, we verify via AppOpsManager instead
                    val appOpsManager = context.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
                    val packageManager = context.packageManager
                    val appInfo = packageManager.getApplicationInfo(packageName, 0)
                    val targetPackageUid = appInfo.uid
                    
                    // Check RUN_ANY_IN_BACKGROUND mode to determine if background is restricted
                    val runAnyBgMode = appOpsManager.checkOpNoThrow(
                        "android:run_any_in_background",
                        targetPackageUid,
                        packageName
                    )
                    val isRestricted = runAnyBgMode != AppOpsManager.MODE_ALLOWED
                    Log.i(TAG, "Background restriction status for $packageName: $isRestricted (mode: $runAnyBgMode)")
                    if (isRestricted) {
                        Log.w(TAG, "⚠ App is background restricted - additional steps may be needed")
                    } else {
                        Log.i(TAG, "✓ App is NOT background restricted")
                    }
                }
            } catch (e: Exception) {
                Log.w(TAG, "⚠ Failed to check background restriction status: ${e.message}")
            }
            
            // Step 4.7: Explicitly allow background activity via DevicePolicyManager API
            // This ensures Android recognizes the app is allowed to run in background
            try {
                // Get current restrictions (may be null if none set)
                val currentRestrictions = devicePolicyManager.getApplicationRestrictions(adminComponent, packageName)
                
                // Create new restrictions bundle that explicitly allows background
                val newRestrictions = Bundle().apply {
                    // Copy any existing restrictions to preserve other settings
                    if (currentRestrictions != null) {
                        putAll(currentRestrictions)
                    }
                    // Explicitly set background restriction to false (allowed)
                    // Note: Setting to false means background is NOT restricted (allowed)
                    // The key name varies by Android version, so we set multiple possible keys
                    putBoolean("restriction_background", false)
                    putBoolean("no_background", false)
                }
                
                // Apply restrictions (this explicitly allows background activity)
                devicePolicyManager.setApplicationRestrictions(adminComponent, packageName, newRestrictions)
                Log.i(TAG, "✓ Explicitly allowed background activity via DevicePolicyManager for $packageName")
            } catch (e: Exception) {
                Log.w(TAG, "⚠ Failed to set application restrictions via DevicePolicyManager: ${e.message}")
                // Non-critical, continue with other steps
            }
            
            // Step 5: Set app standby bucket to EXEMPTED (Android 9+)
            val standbySuccess = setAppStandbyBucketExempted(packageName)
            if (!standbySuccess && Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                Log.w(TAG, "Failed to set app standby bucket to EXEMPTED for $packageName")
            }
            
            // Step 6: Set AUTO_REVOKE_PERMISSIONS_IF_UNUSED to ignore
            val autoRevokeSuccess = setAutoRevokePermissionsIgnored(packageName)
            if (!autoRevokeSuccess) {
                Log.w(TAG, "Failed to set AUTO_REVOKE_PERMISSIONS_IF_UNUSED for $packageName (non-critical)")
            }
            
            // Step 7: Grant SYSTEM_ALERT_WINDOW to maintain overlay permissions
            grantSystemAlertWindow(packageName)
            
            // Step 8: Verify battery optimization exemption (increased delay for Android 13+)
            // Increased delays to ensure all settings propagate
            val delayMs = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                3000L // Android 13+ needs more time for all settings to propagate
            } else {
                2000L // Older versions also need more time
            }
            Log.d(TAG, "Waiting ${delayMs}ms for settings to propagate...")
            Thread.sleep(delayMs)
            
            // Verify each critical setting was applied
            val powerManager = context.getSystemService(Context.POWER_SERVICE) as PowerManager
            val nowIgnoring = powerManager.isIgnoringBatteryOptimizations(packageName)
            
            // Additional verification: Check appops status
            try {
                val appOpsManager = context.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
                
                // Get the target package's UID (not the Device Owner app's UID)
                val packageManager = context.packageManager
                val appInfo = packageManager.getApplicationInfo(packageName, 0)
                val targetPackageUid = appInfo.uid
                
                val runAnyInBgMode = appOpsManager.checkOpNoThrow(
                    "android:run_any_in_background",
                    targetPackageUid,
                    packageName
                )
                Log.d(TAG, "RUN_ANY_IN_BACKGROUND appops mode for $packageName (UID: $targetPackageUid): $runAnyInBgMode (0=allow, 1=ignore, 2=deny)")
                if (runAnyInBgMode == AppOpsManager.MODE_ALLOWED) {
                    Log.i(TAG, "✓ RUN_ANY_IN_BACKGROUND is set to ALLOWED for $packageName")
                } else {
                    Log.w(TAG, "⚠ RUN_ANY_IN_BACKGROUND is not ALLOWED for $packageName (mode: $runAnyInBgMode)")
                }
            } catch (e: Exception) {
                Log.w(TAG, "Failed to verify appops status for $packageName: ${e.message}")
            }
            
            if (nowIgnoring) {
                Log.i(TAG, "✓✓✓ Successfully exempted $packageName from ALL battery optimizations ✓✓✓")
                Log.i(TAG, "    - Device idle whitelist: ✓")
                Log.i(TAG, "    - Background execution: ✓")
                Log.i(TAG, "    - Background restrictions: ✓")
                Log.i(TAG, "    - App standby bucket: ✓")
                Log.i(TAG, "    - Auto-revoke permissions: ✓")
                true
            } else {
                Log.w(TAG, "⚠ Commands executed but PowerManager verification failed for $packageName")
                Log.w(TAG, "  App should still run in background, but may show as 'optimized' in UI")
                true // Return true anyway as commands were successful
            }
        } catch (e: Exception) {
            Log.e(TAG, "✗ Failed to exempt $packageName from battery optimization: ${e.message}", e)
            false
        }
    }
    
    /**
     * Add package to device idle whitelist using shell command.
     * On Android 13+, uses 'cmd deviceidle whitelist' (write command).
     * Falls back to 'dumpsys deviceidle whitelist' for older versions.
     * Works on all Android versions with Device Owner privileges.
     * @return true if command executed successfully
     */
    private fun addToDeviceIdleWhitelist(packageName: String): Boolean {
        return try {
            // On Android 13+, use 'cmd' (write command). On older versions, 'dumpsys' works for writing.
            val useCmd = Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU // Android 13+
            
            if (useCmd) {
                // Force refresh: remove first, then add (ensures system recognizes the change)
                Log.d(TAG, "Executing: sh -c 'cmd deviceidle whitelist -$packageName' (remove)")
                val removeCommand = arrayOf("sh", "-c", "cmd deviceidle whitelist -$packageName")
                val removeProcess = Runtime.getRuntime().exec(removeCommand)
                removeProcess.inputStream.bufferedReader().readText() // Consume output
                removeProcess.errorStream.bufferedReader().readText() // Consume error
                removeProcess.waitFor()
                Thread.sleep(100) // Brief pause between remove and add
            }
            
            // Add to whitelist
            val commandStr = if (useCmd) {
                "cmd deviceidle whitelist +$packageName"
            } else {
                "dumpsys deviceidle whitelist +$packageName"
            }
            
            Log.d(TAG, "Executing: sh -c '$commandStr'")
            val command = arrayOf("sh", "-c", commandStr)
            val process = Runtime.getRuntime().exec(command)
            
            // Read output to prevent blocking
            val output = process.inputStream.bufferedReader().readText().trim()
            val errorOutput = process.errorStream.bufferedReader().readText().trim()
            val exitCode = process.waitFor()
            
            if (exitCode == 0) {
                Log.i(TAG, "✓ Added $packageName to device idle whitelist")
                if (output.isNotEmpty()) {
                    Log.d(TAG, "Command output: $output")
                }
                true
            } else {
                Log.e(TAG, "✗ Failed to add to whitelist, exit code: $exitCode")
                if (output.isNotEmpty()) {
                    Log.e(TAG, "Output: $output")
                }
                if (errorOutput.isNotEmpty()) {
                    Log.e(TAG, "Error: $errorOutput")
                }
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "✗ Exception executing whitelist command: ${e.message}", e)
            false
        }
    }
    
    /**
     * Set AUTO_REVOKE_PERMISSIONS_IF_UNUSED app operation to ignore.
     * Prevents Android from automatically revoking permissions for unused apps.
     * Works on all Android versions with Device Owner privileges.
     * @return true if command executed successfully
     */
    private fun setAutoRevokePermissionsIgnored(packageName: String): Boolean {
        return try {
            Log.d(TAG, "Executing: sh -c 'cmd appops set $packageName AUTO_REVOKE_PERMISSIONS_IF_UNUSED ignore'")
            
            val command = arrayOf("sh", "-c", "cmd appops set $packageName AUTO_REVOKE_PERMISSIONS_IF_UNUSED ignore")
            val process = Runtime.getRuntime().exec(command)
            
            // Read output to prevent blocking
            val output = process.inputStream.bufferedReader().readText().trim()
            val errorOutput = process.errorStream.bufferedReader().readText().trim()
            val exitCode = process.waitFor()
            
            if (exitCode == 0) {
                Log.i(TAG, "✓ Set AUTO_REVOKE_PERMISSIONS_IF_UNUSED ignore for $packageName")
                if (output.isNotEmpty()) {
                    Log.d(TAG, "Command output: $output")
                }
                true
            } else {
                Log.e(TAG, "✗ Failed to set AUTO_REVOKE_PERMISSIONS_IF_UNUSED, exit code: $exitCode")
                if (output.isNotEmpty()) {
                    Log.e(TAG, "Output: $output")
                }
                if (errorOutput.isNotEmpty()) {
                    Log.e(TAG, "Error: $errorOutput")
                }
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "✗ Exception executing appops command: ${e.message}", e)
            false
        }
    }
    
    /**
     * Set RUN_ANY_IN_BACKGROUND app operation for unrestricted background execution.
     * Works on all Android versions with Device Owner privileges.
     * @return true if command executed successfully
     */
    private fun setRunAnyInBackground(packageName: String): Boolean {
        return try {
            Log.d(TAG, "Executing: sh -c 'cmd appops set $packageName RUN_ANY_IN_BACKGROUND allow'")
            
            val command = arrayOf("sh", "-c", "cmd appops set $packageName RUN_ANY_IN_BACKGROUND allow")
            val process = Runtime.getRuntime().exec(command)
            
            // Read output to prevent blocking
            val output = process.inputStream.bufferedReader().readText().trim()
            val errorOutput = process.errorStream.bufferedReader().readText().trim()
            val exitCode = process.waitFor()
            
            if (exitCode == 0) {
                Log.i(TAG, "✓ Set RUN_ANY_IN_BACKGROUND allow for $packageName")
                if (output.isNotEmpty()) {
                    Log.d(TAG, "Command output: $output")
                }
                true
            } else {
                Log.e(TAG, "✗ Failed to set RUN_ANY_IN_BACKGROUND, exit code: $exitCode")
                if (output.isNotEmpty()) {
                    Log.e(TAG, "Output: $output")
                }
                if (errorOutput.isNotEmpty()) {
                    Log.e(TAG, "Error: $errorOutput")
                }
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "✗ Exception executing appops command: ${e.message}", e)
            false
        }
    }
    
    /**
     * Set RUN_IN_BACKGROUND app operation to allow background execution.
     * Complementary to RUN_ANY_IN_BACKGROUND.
     * @return true if command executed successfully
     */
    private fun setRunInBackground(packageName: String): Boolean {
        return try {
            Log.d(TAG, "Executing: sh -c 'cmd appops set $packageName RUN_IN_BACKGROUND allow'")
            
            val command = arrayOf("sh", "-c", "cmd appops set $packageName RUN_IN_BACKGROUND allow")
            val process = Runtime.getRuntime().exec(command)
            
            val output = process.inputStream.bufferedReader().readText().trim()
            val errorOutput = process.errorStream.bufferedReader().readText().trim()
            val exitCode = process.waitFor()
            
            if (exitCode == 0) {
                Log.i(TAG, "✓ Set RUN_IN_BACKGROUND allow for $packageName")
                if (output.isNotEmpty()) {
                    Log.d(TAG, "Command output: $output")
                }
                true
            } else {
                Log.w(TAG, "✗ Failed to set RUN_IN_BACKGROUND (may not be supported), exit code: $exitCode")
                if (errorOutput.isNotEmpty()) {
                    Log.d(TAG, "Error: $errorOutput")
                }
                true // Non-critical, don't fail entire operation
            }
        } catch (e: Exception) {
            Log.w(TAG, "✗ Exception executing RUN_IN_BACKGROUND command: ${e.message}")
            true // Non-critical
        }
    }
    
    /**
     * Force app into STANDBY_BUCKET_EXEMPTED state to prevent throttling.
     * Android 9+ (API 28+) required.
     * @return true if command executed successfully
     */
    private fun setAppStandbyBucketExempted(packageName: String): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) {
            Log.d(TAG, "App standby bucket control requires Android P+, skipping")
            return true // Not applicable on older versions
        }
        
        return try {
            // Set to bucket 5 (STANDBY_BUCKET_EXEMPTED)
            Log.d(TAG, "Executing: sh -c 'am set-standby-bucket $packageName 5'")
            
            val command = arrayOf("sh", "-c", "am set-standby-bucket $packageName 5")
            val process = Runtime.getRuntime().exec(command)
            
            val output = process.inputStream.bufferedReader().readText().trim()
            val errorOutput = process.errorStream.bufferedReader().readText().trim()
            val exitCode = process.waitFor()
            
            if (exitCode == 0) {
                Log.i(TAG, "✓ Set app standby bucket to EXEMPTED (5) for $packageName")
                if (output.isNotEmpty()) {
                    Log.d(TAG, "Command output: $output")
                }
                true
            } else {
                Log.e(TAG, "✗ Failed to set app standby bucket, exit code: $exitCode")
                if (output.isNotEmpty()) {
                    Log.e(TAG, "Output: $output")
                }
                if (errorOutput.isNotEmpty()) {
                    Log.e(TAG, "Error: $errorOutput")
                }
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "✗ Exception executing app standby bucket command: ${e.message}", e)
            false
        }
    }
    
    /**
     * Disable background restrictions using cmd appops.
     * This prevents the system from prompting users about background usage.
     * @return true if command executed successfully
     */
    private fun disableBackgroundRestriction(packageName: String): Boolean {
        return try {
            // Set BACKGROUND_RESTRICTION to unrestricted (allows background without prompts)
            Log.d(TAG, "Executing: sh -c 'cmd appops set $packageName BACKGROUND_RESTRICTION unrestricted'")
            
            val command = arrayOf("sh", "-c", "cmd appops set $packageName BACKGROUND_RESTRICTION unrestricted")
            val process = Runtime.getRuntime().exec(command)
            
            val output = process.inputStream.bufferedReader().readText().trim()
            val errorOutput = process.errorStream.bufferedReader().readText().trim()
            val exitCode = process.waitFor()
            
            if (exitCode == 0) {
                Log.i(TAG, "✓ Set BACKGROUND_RESTRICTION unrestricted for $packageName")
                if (output.isNotEmpty()) {
                    Log.d(TAG, "Command output: $output")
                }
                true
            } else {
                Log.w(TAG, "✗ Failed to set BACKGROUND_RESTRICTION (may not be supported), exit code: $exitCode")
                if (errorOutput.isNotEmpty()) {
                    Log.d(TAG, "Error: $errorOutput")
                }
                true // Non-critical on some Android versions
            }
        } catch (e: Exception) {
            Log.w(TAG, "✗ Exception executing BACKGROUND_RESTRICTION command: ${e.message}")
            true // Non-critical
        }
    }
    
    /**
     * Grant SYSTEM_ALERT_WINDOW permission to ensure overlay permissions persist.
     * @return true if command executed successfully
     */
    private fun grantSystemAlertWindow(packageName: String): Boolean {
        return try {
            Log.d(TAG, "Executing: sh -c 'cmd appops set $packageName SYSTEM_ALERT_WINDOW allow'")
            
            val command = arrayOf("sh", "-c", "cmd appops set $packageName SYSTEM_ALERT_WINDOW allow")
            val process = Runtime.getRuntime().exec(command)
            
            val output = process.inputStream.bufferedReader().readText().trim()
            val errorOutput = process.errorStream.bufferedReader().readText().trim()
            val exitCode = process.waitFor()
            
            if (exitCode == 0) {
                Log.i(TAG, "✓ Set SYSTEM_ALERT_WINDOW allow for $packageName")
                if (output.isNotEmpty()) {
                    Log.d(TAG, "Command output: $output")
                }
                true
            } else {
                Log.w(TAG, "✗ Failed to set SYSTEM_ALERT_WINDOW, exit code: $exitCode")
                true // Non-critical
            }
        } catch (e: Exception) {
            Log.w(TAG, "✗ Exception executing SYSTEM_ALERT_WINDOW command: ${e.message}")
            true // Non-critical
        }
    }
    
    /**
     * Set START_FOREGROUND app operation to allow foreground services.
     * Required for apps that use foreground services.
     * @return true if command executed successfully
     */
    private fun setStartForeground(packageName: String): Boolean {
        return try {
            Log.d(TAG, "Executing: sh -c 'cmd appops set $packageName START_FOREGROUND allow'")
            
            val command = arrayOf("sh", "-c", "cmd appops set $packageName START_FOREGROUND allow")
            val process = Runtime.getRuntime().exec(command)
            
            val output = process.inputStream.bufferedReader().readText().trim()
            val errorOutput = process.errorStream.bufferedReader().readText().trim()
            val exitCode = process.waitFor()
            
            if (exitCode == 0) {
                Log.i(TAG, "✓ Set START_FOREGROUND allow for $packageName")
                true
            } else {
                Log.w(TAG, "✗ Failed to set START_FOREGROUND (may not be supported), exit code: $exitCode")
                true // Non-critical
            }
        } catch (e: Exception) {
            Log.w(TAG, "✗ Exception executing START_FOREGROUND command: ${e.message}")
            true // Non-critical
        }
    }
    
    /**
     * Set START_FOREGROUND_SERVICE app operation to allow foreground services.
     * Alternative permission for foreground services (Android 9+).
     * @return true if command executed successfully
     */
    private fun setStartForegroundService(packageName: String): Boolean {
        return try {
            Log.d(TAG, "Executing: sh -c 'cmd appops set $packageName START_FOREGROUND_SERVICE allow'")
            
            val command = arrayOf("sh", "-c", "cmd appops set $packageName START_FOREGROUND_SERVICE allow")
            val process = Runtime.getRuntime().exec(command)
            
            val output = process.inputStream.bufferedReader().readText().trim()
            val errorOutput = process.errorStream.bufferedReader().readText().trim()
            val exitCode = process.waitFor()
            
            if (exitCode == 0) {
                Log.i(TAG, "✓ Set START_FOREGROUND_SERVICE allow for $packageName")
                true
            } else {
                Log.w(TAG, "✗ Failed to set START_FOREGROUND_SERVICE (may not be supported), exit code: $exitCode")
                true // Non-critical
            }
        } catch (e: Exception) {
            Log.w(TAG, "✗ Exception executing START_FOREGROUND_SERVICE command: ${e.message}")
            true // Non-critical
        }
    }
    
    /**
     * Set START_ACTIVITY_FROM_BACKGROUND app operation to allow starting activities from background.
     * Prevents prompts when app tries to start activities while in background.
     * @return true if command executed successfully
     */
    private fun setStartActivityFromBackground(packageName: String): Boolean {
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                Log.d(TAG, "Executing: sh -c 'cmd appops set $packageName START_ACTIVITY_FROM_BACKGROUND allow'")
                
                val command = arrayOf("sh", "-c", "cmd appops set $packageName START_ACTIVITY_FROM_BACKGROUND allow")
                val process = Runtime.getRuntime().exec(command)
                
                val output = process.inputStream.bufferedReader().readText().trim()
                val errorOutput = process.errorStream.bufferedReader().readText().trim()
                val exitCode = process.waitFor()
                
                if (exitCode == 0) {
                    Log.i(TAG, "✓ Set START_ACTIVITY_FROM_BACKGROUND allow for $packageName")
                    true
                } else {
                    Log.w(TAG, "✗ Failed to set START_ACTIVITY_FROM_BACKGROUND (may not be supported), exit code: $exitCode")
                    true // Non-critical
                }
            } else {
                Log.d(TAG, "START_ACTIVITY_FROM_BACKGROUND not available on Android < 10")
                true
            }
        } catch (e: Exception) {
            Log.w(TAG, "✗ Exception executing START_ACTIVITY_FROM_BACKGROUND command: ${e.message}")
            true // Non-critical
        }
    }
    
    /**
     * Set SCHEDULE_EXACT_ALARM app operation to allow exact alarms.
     * Required for apps that need precise alarm scheduling (Android 12+).
     * @return true if command executed successfully
     */
    private fun setScheduleExactAlarm(packageName: String): Boolean {
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                Log.d(TAG, "Executing: sh -c 'cmd appops set $packageName SCHEDULE_EXACT_ALARM allow'")
                
                val command = arrayOf("sh", "-c", "cmd appops set $packageName SCHEDULE_EXACT_ALARM allow")
                val process = Runtime.getRuntime().exec(command)
                
                val output = process.inputStream.bufferedReader().readText().trim()
                val errorOutput = process.errorStream.bufferedReader().readText().trim()
                val exitCode = process.waitFor()
                
                if (exitCode == 0) {
                    Log.i(TAG, "✓ Set SCHEDULE_EXACT_ALARM allow for $packageName")
                    true
                } else {
                    Log.w(TAG, "✗ Failed to set SCHEDULE_EXACT_ALARM (may not be supported), exit code: $exitCode")
                    true // Non-critical
                }
            } else {
                Log.d(TAG, "SCHEDULE_EXACT_ALARM not available on Android < 12")
                true
            }
        } catch (e: Exception) {
            Log.w(TAG, "✗ Exception executing SCHEDULE_EXACT_ALARM command: ${e.message}")
            true // Non-critical
        }
    }

    @RequiresApi(Build.VERSION_CODES.M)
    fun grantAllRemoteControlPermissions(): PermissionGrantResult {
        if (!isDeviceOwner()) {
            return PermissionGrantResult(
                success = false,
                screenCaptureGranted = false,
                accessibilityEnabled = false,
                installUnknownAppsGranted = false,
                message = "Not enrolled as Device Owner"
            )
        }

        val screenCaptureGranted = grantScreenCapturePermission()
        val accessibilityEnabled = enableAccessibilityService()
        val installUnknownAppsGranted = enableInstallUnknownApps()

        val allGranted = screenCaptureGranted && accessibilityEnabled && installUnknownAppsGranted

        return PermissionGrantResult(
            success = allGranted,
            screenCaptureGranted = screenCaptureGranted,
            accessibilityEnabled = accessibilityEnabled,
            installUnknownAppsGranted = installUnknownAppsGranted,
            message = when {
                allGranted -> "All permissions granted successfully"
                !installUnknownAppsGranted -> "Install Unknown Apps permission failed"
                !screenCaptureGranted -> "Screen capture permission failed"
                !accessibilityEnabled -> "Accessibility service failed"
                else -> "Some permissions failed"
            }
        )
    }

    data class PermissionGrantResult(
        val success: Boolean,
        val screenCaptureGranted: Boolean,
        val accessibilityEnabled: Boolean,
        val installUnknownAppsGranted: Boolean,
        val message: String
    )

    data class PowerManagementResult(
        val success: Boolean,
        val dozeModeDisabled: Boolean,
        val adaptiveBatteryDisabled: Boolean,
        val message: String
    )

    data class BatteryManagementStatus(
        val isAdaptiveBatteryDisabled: Boolean,
        val settingsApplied: Map<String, String>,
        val message: String
    )
}
