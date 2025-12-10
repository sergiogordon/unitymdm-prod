package com.nexmdm

import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.WindowManager
import androidx.appcompat.app.AppCompatActivity

class AppLauncherActivity : AppCompatActivity() {
    
    companion object {
        private const val TAG = "AppLauncherActivity"
        const val EXTRA_PACKAGE_NAME = "package_name"
        const val LAUNCHER_NOTIFICATION_ID = 1001
    }
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        setupFullscreen()
        
        val packageName = intent.getStringExtra(EXTRA_PACKAGE_NAME)
        
        if (packageName.isNullOrEmpty()) {
            Log.e(TAG, "No package name provided")
            finishAndRemoveTask()
            return
        }
        
        Log.i(TAG, "Launching app: $packageName")
        
        dismissNotification()
        launchTargetApp(packageName)
        finishAndRemoveTask()
    }
    
    private fun setupFullscreen() {
        window.addFlags(
            WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or
            WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD or
            WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
            WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
        )
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        }
    }
    
    private fun dismissNotification() {
        try {
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            notificationManager.cancel(LAUNCHER_NOTIFICATION_ID)
        } catch (e: Exception) {
            Log.e(TAG, "Error dismissing notification: ${e.message}")
        }
    }
    
    private fun launchTargetApp(packageName: String) {
        try {
            val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
            if (launchIntent != null) {
                launchIntent.addFlags(
                    Intent.FLAG_ACTIVITY_NEW_TASK or
                    Intent.FLAG_ACTIVITY_CLEAR_TOP or
                    Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED
                )
                startActivity(launchIntent)
                Log.i(TAG, "Successfully launched app: $packageName")
            } else {
                Log.w(TAG, "Could not get launch intent for package: $packageName (app may not have a launcher activity)")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to launch app $packageName: ${e.message}", e)
        }
    }
}
