package com.nexmdm

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.os.Build
import android.util.Log
import android.view.KeyEvent
import android.view.accessibility.AccessibilityEvent
import androidx.annotation.RequiresApi

class RemoteControlAccessibilityService : AccessibilityService() {

    companion object {
        private const val TAG = "RemoteControlA11yService"
        
        @Volatile
        var instance: RemoteControlAccessibilityService? = null
            private set
        
        fun isServiceEnabled(): Boolean = instance != null
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        Log.i(TAG, "Accessibility service connected")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
    }

    override fun onInterrupt() {
        Log.d(TAG, "Accessibility service interrupted")
    }

    override fun onDestroy() {
        super.onDestroy()
        instance = null
        Log.i(TAG, "Accessibility service destroyed")
    }

    @RequiresApi(Build.VERSION_CODES.N)
    fun performTap(x: Float, y: Float, callback: (Boolean) -> Unit = {}) {
        Log.d(TAG, "Performing tap at ($x, $y)")
        
        val path = Path()
        path.moveTo(x, y)
        
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 50))
            .build()
        
        dispatchGesture(gesture, object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) {
                Log.d(TAG, "Tap gesture completed successfully")
                callback(true)
            }
            
            override fun onCancelled(gestureDescription: GestureDescription?) {
                Log.w(TAG, "Tap gesture cancelled")
                callback(false)
            }
        }, null)
    }

    @RequiresApi(Build.VERSION_CODES.N)
    fun performSwipe(
        startX: Float,
        startY: Float,
        endX: Float,
        endY: Float,
        durationMs: Long = 300,
        callback: (Boolean) -> Unit = {}
    ) {
        Log.d(TAG, "Performing swipe from ($startX, $startY) to ($endX, $endY)")
        
        val path = Path()
        path.moveTo(startX, startY)
        path.lineTo(endX, endY)
        
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, durationMs))
            .build()
        
        dispatchGesture(gesture, object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) {
                Log.d(TAG, "Swipe gesture completed successfully")
                callback(true)
            }
            
            override fun onCancelled(gestureDescription: GestureDescription?) {
                Log.w(TAG, "Swipe gesture cancelled")
                callback(false)
            }
        }, null)
    }

    fun performKeyEvent(keyCode: Int, callback: (Boolean) -> Unit = {}) {
        Log.d(TAG, "Performing key event: keyCode=$keyCode")
        
        try {
            val downEvent = KeyEvent(KeyEvent.ACTION_DOWN, keyCode)
            val upEvent = KeyEvent(KeyEvent.ACTION_UP, keyCode)
            
            val downSuccess = performGlobalAction(keyCode)
            
            if (!downSuccess) {
                Thread {
                    try {
                        Runtime.getRuntime().exec("input keyevent $keyCode")
                        callback(true)
                    } catch (e: Exception) {
                        Log.e(TAG, "Failed to execute key event via shell", e)
                        callback(false)
                    }
                }.start()
            } else {
                callback(true)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error performing key event", e)
            callback(false)
        }
    }

    fun performTextInput(text: String, callback: (Boolean) -> Unit = {}) {
        Log.d(TAG, "Performing text input: ${text.take(20)}...")
        
        Thread {
            try {
                val escapedText = text.replace(" ", "%s").replace("'", "\\'")
                Runtime.getRuntime().exec(arrayOf("input", "text", escapedText))
                callback(true)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to input text via shell", e)
                callback(false)
            }
        }.start()
    }

    fun performHomeAction(callback: (Boolean) -> Unit = {}) {
        Log.d(TAG, "Performing HOME action")
        val success = performGlobalAction(GLOBAL_ACTION_HOME)
        callback(success)
    }

    fun performBackAction(callback: (Boolean) -> Unit = {}) {
        Log.d(TAG, "Performing BACK action")
        val success = performGlobalAction(GLOBAL_ACTION_BACK)
        callback(success)
    }

    fun performRecentAppsAction(callback: (Boolean) -> Unit = {}) {
        Log.d(TAG, "Performing RECENTS action")
        val success = performGlobalAction(GLOBAL_ACTION_RECENTS)
        callback(success)
    }

    fun performPowerAction(callback: (Boolean) -> Unit = {}) {
        Log.d(TAG, "Performing POWER/LOCK_SCREEN action")
        val success = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            performGlobalAction(GLOBAL_ACTION_LOCK_SCREEN)
        } else {
            Thread {
                try {
                    Runtime.getRuntime().exec("input keyevent ${KeyEvent.KEYCODE_POWER}")
                    callback(true)
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to execute power action via shell", e)
                    callback(false)
                }
            }.start()
            return
        }
        callback(success)
    }

    fun performNotificationsAction(callback: (Boolean) -> Unit = {}) {
        Log.d(TAG, "Performing NOTIFICATIONS action")
        val success = performGlobalAction(GLOBAL_ACTION_NOTIFICATIONS)
        callback(success)
    }

    fun performQuickSettingsAction(callback: (Boolean) -> Unit = {}) {
        Log.d(TAG, "Performing QUICK_SETTINGS action")
        val success = performGlobalAction(GLOBAL_ACTION_QUICK_SETTINGS)
        callback(success)
    }
}
