package com.nexmdm

import android.Manifest
import android.app.AppOpsManager
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Build
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
