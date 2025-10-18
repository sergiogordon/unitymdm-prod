package com.nexmdm

import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Build
import android.os.PowerManager
import android.util.Log

class PowerManagementMonitor(private val context: Context) {
    
    companion object {
        private const val TAG = "PowerManagementMonitor"
        private const val LOW_BATTERY_THRESHOLD_PCT = 10
        private const val SAFE_BATTERY_THRESHOLD_PCT = 20
    }
    
    private val devicePolicyManager = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
    private val powerManager = context.getSystemService(Context.POWER_SERVICE) as PowerManager
    private val adminComponent = ComponentName(context, NexDeviceAdminReceiver::class.java)
    
    fun checkAndLogPowerStatus(): PowerStatus {
        val isDeviceOwner = devicePolicyManager.isDeviceOwnerApp(context.packageName)
        
        val dozeWhitelisted = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            powerManager.isIgnoringBatteryOptimizations(context.packageName)
        } else {
            true
        }
        
        val batteryInfo = getBatteryInfo()
        val powerOk = isDeviceOwner && dozeWhitelisted
        
        if (isDeviceOwner) {
            if (dozeWhitelisted) {
                Log.i(TAG, "[reliability.power.owner_confirmed] battery_whitelisted=true power_ok=true")
            } else {
                Log.w(TAG, "[reliability.power.owner_confirmed] battery_whitelisted=false power_ok=false - Doze may still affect service")
            }
        } else {
            Log.w(TAG, "[reliability.power.suboptimal_power] device_owner=false - using foreground service fallback")
        }
        
        return PowerStatus(
            isDeviceOwner = isDeviceOwner,
            dozeWhitelisted = dozeWhitelisted,
            powerOk = powerOk,
            batteryPct = batteryInfo.pct,
            isCharging = batteryInfo.charging
        )
    }
    
    fun shouldPauseRetries(): Boolean {
        val batteryInfo = getBatteryInfo()
        
        if (batteryInfo.pct < LOW_BATTERY_THRESHOLD_PCT && !batteryInfo.charging) {
            Log.w(TAG, "[reliability.battery.low] pct=${batteryInfo.pct} charging=${batteryInfo.charging} - pausing non-essential retries")
            return true
        }
        
        return false
    }
    
    fun shouldResumeRetries(): Boolean {
        val batteryInfo = getBatteryInfo()
        
        if (batteryInfo.pct >= SAFE_BATTERY_THRESHOLD_PCT || batteryInfo.charging) {
            return true
        }
        
        return false
    }
    
    private fun getBatteryInfo(): BatteryInfo {
        val batteryStatus = context.registerReceiver(
            null,
            IntentFilter(Intent.ACTION_BATTERY_CHANGED)
        )
        
        val level = batteryStatus?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = batteryStatus?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        val pct = if (level >= 0 && scale > 0) (level * 100 / scale) else 0
        
        val status = batteryStatus?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        val charging = status == BatteryManager.BATTERY_STATUS_CHARGING ||
                status == BatteryManager.BATTERY_STATUS_FULL
        
        return BatteryInfo(pct = pct, charging = charging)
    }
    
    data class PowerStatus(
        val isDeviceOwner: Boolean,
        val dozeWhitelisted: Boolean,
        val powerOk: Boolean,
        val batteryPct: Int,
        val isCharging: Boolean
    )
    
    data class BatteryInfo(
        val pct: Int,
        val charging: Boolean
    )
}
