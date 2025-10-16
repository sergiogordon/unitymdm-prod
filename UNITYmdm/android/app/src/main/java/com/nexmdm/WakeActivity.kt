package com.nexmdm

import android.app.KeyguardManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.WindowManager
import androidx.appcompat.app.AppCompatActivity

class WakeActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "WakeActivity"
        private const val KEYGUARD_CHECK_INTERVAL_MS = 200L
        private const val KEYGUARD_CHECK_TIMEOUT_MS = 10000L
    }
    
    private val handler = Handler(Looper.getMainLooper())
    private var keyguardCheckStartTime = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        Log.d(TAG, "WakeActivity started to wake device for remote control")
        
        // Setup window flags to turn screen on and show when locked
        setupWindowFlags()
        
        // Request keyguard dismissal if supported
        // Note: goToHomeScreen() will be called from the callback when keyguard is dismissed
        requestKeyguardDismissal()
    }

    private fun setupWindowFlags() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            // Android 8.1+ (API 27+)
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            // Android 8.0 and below
            window.addFlags(
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
            )
        }
        
        // Keep screen on while activity is visible
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        
        Log.d(TAG, "Window flags set to turn screen on and show when locked")
    }

    private fun requestKeyguardDismissal() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            // Android 8.0+ (API 26+) - request keyguard dismissal with callbacks
            val keyguardManager = getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
            keyguardManager.requestDismissKeyguard(this, object : KeyguardManager.KeyguardDismissCallback() {
                override fun onDismissSucceeded() {
                    Log.d(TAG, "Keyguard dismissed successfully")
                    // Navigate to home only AFTER successful dismissal
                    goToHomeScreen()
                    finish()
                }

                override fun onDismissCancelled() {
                    Log.w(TAG, "Keyguard dismissal cancelled by user")
                    // User cancelled unlock - still go to home if device is unlocked
                    if (!keyguardManager.isKeyguardLocked) {
                        goToHomeScreen()
                    }
                    finish()
                }

                override fun onDismissError() {
                    Log.e(TAG, "Keyguard dismissal error")
                    // Error during dismissal - try to go home if unlocked
                    if (!keyguardManager.isKeyguardLocked) {
                        goToHomeScreen()
                    }
                    finish()
                }
            })
        } else {
            // Pre-Android 8.0 - use deprecated flag
            window.addFlags(WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD)
            Log.d(TAG, "Using FLAG_DISMISS_KEYGUARD for keyguard dismissal (pre-O)")
            
            // For pre-O, poll keyguard state until unlocked or timeout
            keyguardCheckStartTime = System.currentTimeMillis()
            checkKeyguardStateAndNavigate()
        }
    }
    
    private fun checkKeyguardStateAndNavigate() {
        val keyguardManager = getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
        val elapsed = System.currentTimeMillis() - keyguardCheckStartTime
        
        if (!keyguardManager.isKeyguardLocked) {
            // Keyguard is unlocked - navigate to home
            Log.d(TAG, "Keyguard unlocked after ${elapsed}ms, navigating to home")
            goToHomeScreen()
            finish()
        } else if (elapsed >= KEYGUARD_CHECK_TIMEOUT_MS) {
            // Timeout reached - log warning and finish
            Log.w(TAG, "Keyguard still locked after ${elapsed}ms timeout - manual unlock required")
            finish()
        } else {
            // Still locked, check again after interval
            handler.postDelayed({
                checkKeyguardStateAndNavigate()
            }, KEYGUARD_CHECK_INTERVAL_MS)
        }
    }
    
    override fun onDestroy() {
        super.onDestroy()
        // Clean up any pending handler callbacks
        handler.removeCallbacksAndMessages(null)
    }

    private fun goToHomeScreen() {
        try {
            val homeIntent = Intent(Intent.ACTION_MAIN).apply {
                addCategory(Intent.CATEGORY_HOME)
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            startActivity(homeIntent)
            Log.d(TAG, "Navigated to home screen")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to navigate to home screen", e)
        }
    }
}
