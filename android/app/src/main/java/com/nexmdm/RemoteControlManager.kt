package com.nexmdm

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.annotation.RequiresApi

class RemoteControlManager(private val context: Context) {

    companion object {
        private const val TAG = "RemoteControlManager"
        
        @Volatile
        private var instance: RemoteControlManager? = null
        
        fun getInstance(context: Context): RemoteControlManager {
            return instance ?: synchronized(this) {
                instance ?: RemoteControlManager(context.applicationContext).also { instance = it }
            }
        }
    }

    private val permissionManager = DeviceOwnerPermissionManager(context)
    private val screenWakeHelper = ScreenWakeHelper(context)
    private var webSocketClient: WebSocketClient? = null
    private var isStreaming = false
    private var mediaProjectionResultCode: Int? = null
    private var mediaProjectionResultData: Intent? = null

    fun isDeviceOwner(): Boolean {
        return permissionManager.isDeviceOwner()
    }

    fun isAccessibilityServiceEnabled(): Boolean {
        return RemoteControlAccessibilityService.isServiceEnabled()
    }

    fun isScreenCaptureActive(): Boolean {
        return ScreenCaptureService.isRunning
    }

    fun isStreamingActive(): Boolean {
        return isStreaming && webSocketClient?.isConnected() == true
    }

    @RequiresApi(Build.VERSION_CODES.M)
    fun setupRemoteControl(): DeviceOwnerPermissionManager.PermissionGrantResult {
        Log.i(TAG, "Setting up remote control permissions")
        return permissionManager.grantAllRemoteControlPermissions()
    }

    fun requestMediaProjectionPermission(activity: Activity) {
        val intent = permissionManager.createMediaProjectionIntent()
        if (intent != null) {
            activity.startActivityForResult(
                intent,
                DeviceOwnerPermissionManager.MEDIA_PROJECTION_REQUEST_CODE
            )
        } else {
            Log.e(TAG, "Failed to create MediaProjection intent")
        }
    }

    fun handleMediaProjectionResult(resultCode: Int, resultData: Intent?) {
        if (resultCode == Activity.RESULT_OK && resultData != null) {
            Log.i(TAG, "MediaProjection permission granted")
            mediaProjectionResultCode = resultCode
            mediaProjectionResultData = resultData
        } else {
            Log.e(TAG, "MediaProjection permission denied")
        }
    }

    fun startRemoteControl(
        serverUrl: String,
        deviceToken: String,
        deviceId: String,
        onStreamingStarted: () -> Unit = {},
        onStreamingStopped: () -> Unit = {}
    ): Boolean {
        if (!isDeviceOwner()) {
            Log.e(TAG, "Cannot start remote control: Not Device Owner")
            return false
        }

        if (!RemoteControlAccessibilityService.isServiceEnabled()) {
            Log.e(TAG, "Cannot start remote control: Accessibility service not enabled")
            return false
        }

        val resultCode = mediaProjectionResultCode
        val resultData = mediaProjectionResultData
        
        if (resultCode == null || resultData == null) {
            Log.e(TAG, "Cannot start remote control: MediaProjection permission not granted")
            return false
        }

        Log.i(TAG, "Starting remote control streaming")
        
        // Wake screen, unlock device, and navigate to home before streaming
        Log.i(TAG, "Waking and unlocking device for remote control")
        if (!screenWakeHelper.wakeAndUnlockDevice()) {
            Log.w(TAG, "Failed to fully wake/unlock device, but continuing with stream")
        }

        webSocketClient = WebSocketClient(serverUrl, deviceToken, deviceId)
        
        webSocketClient?.connect(
            onConnected = {
                Log.i(TAG, "WebSocket connected, starting screen capture")
                startScreenCapture(resultCode, resultData)
                isStreaming = true
                onStreamingStarted()
            },
            onDisconnected = {
                Log.w(TAG, "WebSocket disconnected, stopping screen capture")
                stopScreenCapture()
                isStreaming = false
                
                // Release wake lock when disconnected to prevent battery drain
                screenWakeHelper.releaseWakeLock()
                
                onStreamingStopped()
            }
        )

        return true
    }

    private fun startScreenCapture(resultCode: Int, resultData: Intent) {
        val intent = Intent(context, ScreenCaptureService::class.java).apply {
            action = ScreenCaptureService.ACTION_START
            putExtra(ScreenCaptureService.EXTRA_RESULT_CODE, resultCode)
            putExtra(ScreenCaptureService.EXTRA_RESULT_DATA, resultData)
        }
        
        ScreenCaptureService.frameCallback = { jpegData, width, height ->
            webSocketClient?.sendFrame(jpegData, width, height)
        }
        
        context.startForegroundService(intent)
        Log.i(TAG, "Screen capture service started")
    }

    private fun stopScreenCapture() {
        val intent = Intent(context, ScreenCaptureService::class.java).apply {
            action = ScreenCaptureService.ACTION_STOP
        }
        context.startService(intent)
        
        ScreenCaptureService.frameCallback = null
        Log.i(TAG, "Screen capture service stopped")
    }

    fun stopRemoteControl() {
        Log.i(TAG, "Stopping remote control")
        
        isStreaming = false
        
        webSocketClient?.disconnect()
        webSocketClient?.cleanup()
        webSocketClient = null
        
        stopScreenCapture()
        
        // Release wake lock when stopping
        screenWakeHelper.releaseWakeLock()
        
        Log.i(TAG, "Remote control stopped")
    }

    fun getStatus(): RemoteControlStatus {
        return RemoteControlStatus(
            isDeviceOwner = isDeviceOwner(),
            isAccessibilityEnabled = isAccessibilityServiceEnabled(),
            isScreenCaptureActive = isScreenCaptureActive(),
            isWebSocketConnected = webSocketClient?.isConnected() ?: false,
            isStreaming = isStreamingActive(),
            hasMediaProjectionPermission = mediaProjectionResultCode != null && mediaProjectionResultData != null
        )
    }

    data class RemoteControlStatus(
        val isDeviceOwner: Boolean,
        val isAccessibilityEnabled: Boolean,
        val isScreenCaptureActive: Boolean,
        val isWebSocketConnected: Boolean,
        val isStreaming: Boolean,
        val hasMediaProjectionPermission: Boolean
    ) {
        val isFullyConfigured: Boolean
            get() = isDeviceOwner && isAccessibilityEnabled && hasMediaProjectionPermission
        
        val canStartStreaming: Boolean
            get() = isFullyConfigured && !isStreaming
    }
}
