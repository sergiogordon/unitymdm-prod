package com.nexmdm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

class BootReceiver : BroadcastReceiver() {
    
    companion object {
        private const val TAG = "NexMDM.BootReceiver"
    }
    
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED -> {
                Log.i(TAG, "Device boot completed - checking enrollment")
                startServiceIfEnrolled(context, "boot")
            }
            Intent.ACTION_MY_PACKAGE_REPLACED -> {
                Log.i(TAG, "App was updated - restarting service")
                startServiceIfEnrolled(context, "update")
            }
            "com.nexmdm.RESTART_APP" -> {
                Log.i(TAG, "App restart requested - restarting service")
                startServiceIfEnrolled(context, "restart")
            }
        }
    }
    
    private fun startServiceIfEnrolled(context: Context, trigger: String) {
        val prefs = SecurePreferences(context)
        
        if (prefs.serverUrl.isNotEmpty() && prefs.deviceToken.isNotEmpty()) {
            val serviceIntent = Intent(context, MonitorService::class.java).apply {
                putExtra("trigger", trigger)
                if (trigger == "update") {
                    putExtra("app_updated", true)
                }
            }
            context.startForegroundService(serviceIntent)
            Log.i(TAG, "MonitorService started (trigger: $trigger)")
        } else {
            Log.w(TAG, "Device not enrolled - service not started")
        }
    }
}
