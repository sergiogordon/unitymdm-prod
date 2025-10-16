package com.nexmdm

import android.app.KeyguardManager
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.PowerManager
import android.util.Log

class ScreenWakeHelper(private val context: Context) {
    
    companion object {
        private const val TAG = "ScreenWakeHelper"
    }
    
    private val powerManager = context.getSystemService(Context.POWER_SERVICE) as PowerManager
    private val keyguardManager = context.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
    private val devicePolicyManager = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
    
    private var wakeLock: PowerManager.WakeLock? = null
    
    fun wakeAndUnlockDevice(): Boolean {
        try {
            Log.d(TAG, "Starting wake and unlock sequence")
            
            // Step 1: Acquire wake lock to ensure CPU stays awake
            acquireWakeLock()
            
            // Step 2: Launch WakeActivity to turn screen on, dismiss keyguard, and navigate to home
            // WakeActivity handles all the complex window flags and keyguard dismissal
            if (!launchWakeActivity()) {
                Log.e(TAG, "Failed to launch WakeActivity")
                releaseWakeLock()
                return false
            }
            
            Log.d(TAG, "Wake and unlock sequence initiated successfully")
            return true
            
        } catch (e: Exception) {
            Log.e(TAG, "Error during wake/unlock sequence", e)
            releaseWakeLock()
            return false
        }
    }
    
    private fun acquireWakeLock() {
        try {
            // Acquire a wake lock to ensure CPU stays awake during streaming
            wakeLock = powerManager.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                "NexMDM::RemoteControlWakeLock"
            )
            
            wakeLock?.acquire(30 * 60 * 1000L) // 30 minutes timeout for safety
            Log.d(TAG, "Wake lock acquired for remote control session")
            
        } catch (e: Exception) {
            Log.e(TAG, "Failed to acquire wake lock", e)
        }
    }
    
    private fun launchWakeActivity(): Boolean {
        try {
            // Launch WakeActivity which will:
            // 1. Turn screen on (using window flags)
            // 2. Show when locked (using window flags)
            // 3. Request keyguard dismissal (using KeyguardManager.requestDismissKeyguard)
            // 4. Navigate to home screen
            // 5. Finish itself
            
            val wakeIntent = Intent(context, WakeActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            }
            
            context.startActivity(wakeIntent)
            Log.d(TAG, "WakeActivity launched to wake screen and dismiss keyguard")
            
            return true
            
        } catch (e: Exception) {
            Log.e(TAG, "Failed to launch WakeActivity", e)
            return false
        }
    }
    
    fun releaseWakeLock() {
        try {
            wakeLock?.let {
                if (it.isHeld) {
                    it.release()
                    Log.d(TAG, "Wake lock released")
                }
            }
            wakeLock = null
        } catch (e: Exception) {
            Log.e(TAG, "Error releasing wake lock", e)
        }
    }
}
