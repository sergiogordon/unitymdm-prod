package com.nexmdm

import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.os.BatteryManager
import android.os.Build
import android.os.PowerManager
import android.util.Log

class PowerManagementMonitor(private val context: Context) {
    
    companion object {
        private const val TAG = "PowerMonitor"
    }
    
    private val powerManager = context.getSystemService(Context.POWER_SERVICE) as PowerManager
    private val devicePolicyManager = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
    private val batteryManager = context.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
    
    fun isDeviceOwner(): Boolean {
        return try {
            val adminComponent = ComponentName(context, NexDeviceAdminReceiver::class.java)
            devicePolicyManager.isDeviceOwnerApp(context.packageName)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to check device owner status", e)
            false
        }
    }
    
    fun isDozeWhitelisted(): Boolean {
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                powerManager.isIgnoringBatteryOptimizations(context.packageName)
            } else {
                true
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to check doze whitelist", e)
            false
        }
    }
    
    fun isPowerOk(): Boolean {
        val batteryPct = getBatteryPercent()
        val isCharging = isCharging()
        
        if (isCharging) {
            return true
        }
        
        return batteryPct >= 10
    }
    
    fun getBatteryPercent(): Int {
        return try {
            batteryManager.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to get battery level", e)
            100
        }
    }
    
    fun isCharging(): Boolean {
        return try {
            val status = batteryManager.getIntProperty(BatteryManager.BATTERY_PROPERTY_STATUS)
            status == BatteryManager.BATTERY_STATUS_CHARGING || 
            status == BatteryManager.BATTERY_STATUS_FULL
        } catch (e: Exception) {
            Log.e(TAG, "Failed to check charging status", e)
            false
        }
    }
    
    fun getPowerStatus(): PowerStatus {
        val isDeviceOwner = isDeviceOwner()
        val isDozeWhitelisted = isDozeWhitelisted()
        val isPowerOk = isPowerOk()
        val batteryPct = getBatteryPercent()
        val isCharging = isCharging()
        
        Log.d(TAG, "Power status: device_owner=$isDeviceOwner, doze_whitelisted=$isDozeWhitelisted, " +
                   "power_ok=$isPowerOk, battery=$batteryPct%, charging=$isCharging")
        
        return PowerStatus(
            isDeviceOwner = isDeviceOwner,
            isDozeWhitelisted = isDozeWhitelisted,
            isPowerOk = isPowerOk,
            batteryPercent = batteryPct,
            isCharging = isCharging
        )
    }
    
    data class PowerStatus(
        val isDeviceOwner: Boolean,
        val isDozeWhitelisted: Boolean,
        val isPowerOk: Boolean,
        val batteryPercent: Int,
        val isCharging: Boolean
    )
}
