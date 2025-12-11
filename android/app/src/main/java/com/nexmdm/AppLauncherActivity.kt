package com.nexmdm

import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.WindowManager
import androidx.appcompat.app.AppCompatActivity

class AppLauncherActivity : AppCompatActivity() {
    
    companion object {
        private const val TAG = "AppLauncherActivity"
        const val EXTRA_PACKAGE_NAME = "package_name"
        const val LAUNCHER_NOTIFICATION_ID = 1001
        private const val LAUNCH_DELAY_MS = 150L
    }
    
    private var targetPackageName: String? = null
    private var hasLaunched = false
    private val handler = Handler(Looper.getMainLooper())
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        setupFullscreen()
        
        targetPackageName = intent.getStringExtra(EXTRA_PACKAGE_NAME)
        
        if (targetPackageName.isNullOrEmpty()) {
            Log.e(TAG, "No package name provided")
            finishAndRemoveTask()
            return
        }
        
        Log.i(TAG, "AppLauncherActivity created for package: $targetPackageName")
        dismissNotification()
    }
    
    override fun onResume() {
        super.onResume()
        
        if (hasLaunched || targetPackageName.isNullOrEmpty()) {
            return
        }
        
        hasLaunched = true
        Log.i(TAG, "onResume: Scheduling app launch with ${LAUNCH_DELAY_MS}ms delay")
        
        handler.postDelayed({
            launchTargetApp(targetPackageName!!)
        }, LAUNCH_DELAY_MS)
    }
    
    override fun onDestroy() {
        super.onDestroy()
        handler.removeCallbacksAndMessages(null)
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
    
    private fun launchTargetApp(targetPackageName: String) {
        Log.i(TAG, "Attempting to launch app: $targetPackageName")
        
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                Log.d(TAG, "Android 12+: Using HOME intent workaround for potential unexported activity")
                val homeIntent = Intent(Intent.ACTION_MAIN).apply {
                    addCategory(Intent.CATEGORY_HOME)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                startActivity(homeIntent)
                
                handler.postDelayed({
                    launchAppDirect(targetPackageName)
                }, 200)
            } else {
                launchAppDirect(targetPackageName)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to launch app $targetPackageName: ${e.message}", e)
            finishAndRemoveTask()
        }
    }
    
    private fun launchAppDirect(targetPackageName: String) {
        try {
            val launchIntent = packageManager.getLaunchIntentForPackage(targetPackageName)
            if (launchIntent != null) {
                launchIntent.addFlags(
                    Intent.FLAG_ACTIVITY_NEW_TASK or
                    Intent.FLAG_ACTIVITY_CLEAR_TOP or
                    Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED
                )
                startActivity(launchIntent)
                Log.i(TAG, "Successfully launched app: $targetPackageName")
            } else {
                Log.w(TAG, "Could not get launch intent for package: $targetPackageName (app may not have a launcher activity)")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to launch app $targetPackageName: ${e.message}", e)
        } finally {
            finishAndRemoveTask()
        }
    }
}
