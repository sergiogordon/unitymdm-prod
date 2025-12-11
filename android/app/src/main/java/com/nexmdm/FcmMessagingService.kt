package com.nexmdm

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import java.net.HttpURLConnection
import java.net.URL
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import com.google.gson.Gson
import java.util.concurrent.TimeUnit
import java.util.concurrent.Executors

class FcmMessagingService : FirebaseMessagingService() {
    
    companion object {
        private const val TAG = "FcmMessagingService"
        private const val RING_CHANNEL_ID = "ring_channel"
        private const val RING_NOTIFICATION_ID = 999
        private const val LAUNCHER_CHANNEL_ID = "launcher_channel"
    }
    
    private val gson = Gson()
    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()
    
    override fun onNewToken(token: String) {
        super.onNewToken(token)
        Log.d(TAG, "New FCM token: ${token.take(10)}...")
        
        val prefs = SecurePreferences(this)
        prefs.fcmToken = token
        
        sendTokenToServer(token)
    }
    
    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)
        
        Log.d(TAG, "FCM message received: ${message.data}")
        
        val action = message.data["action"] ?: ""
        val requestId = message.data["request_id"] ?: message.data["correlation_id"] ?: ""
        val timestamp = message.data["ts"] ?: ""
        val hmac = message.data["hmac"] ?: ""
        
        val prefs = SecurePreferences(this)
        val deviceId = prefs.deviceId
        
        if (prefs.hmacPrimaryKey.isNotEmpty()) {
            val validator = HmacValidator(prefs)
            
            // For remote_exec actions, include critical payload fields in validation
            val isValid = if (action == "remote_exec_fcm" || action == "remote_exec_shell") {
                val payloadFields = mutableMapOf<String, String>()
                
                if (action == "remote_exec_shell") {
                    // Include command field for shell commands
                    message.data["command"]?.let { payloadFields["command"] = it }
                } else if (action == "remote_exec_fcm") {
                    // Include critical fields for FCM commands
                    message.data["type"]?.let { payloadFields["type"] = it }
                    message.data["package_name"]?.let { payloadFields["package_name"] = it }
                    message.data["enable"]?.let { payloadFields["enable"] = it }
                    message.data["duration"]?.let { payloadFields["duration"] = it }
                }
                
                validator.validateMessageWithPayload(requestId, deviceId, action, timestamp, hmac, payloadFields)
            } else {
                validator.validateMessage(requestId, deviceId, action, timestamp, hmac)
            }
            
            if (!isValid) {
                Log.w(TAG, "HMAC validation failed for action=$action, rejecting message")
                return
            }
        }
        
        when (action) {
            "ping" -> {
                handlePingRequest(requestId)
            }
            "wake" -> {
                handleWakeRequest()
            }
            "ring" -> {
                handleRingRequest(message.data["duration"]?.toIntOrNull() ?: 30)
            }
            "install_apk", "deploy_update" -> {
                handleApkInstallRequest(message.data)
            }
            "remote_control" -> {
                handleRemoteControlCommand(message.data)
            }
            "grant_permissions" -> {
                handleGrantPermissionsRequest()
            }
            "list_packages" -> {
                handleListPackagesRequest()
            }
            "launch_app" -> {
                handleLaunchAppRequest(message.data)
            }
            "reboot" -> {
                handleRebootRequest()
            }
            "restart_app" -> {
                handleRestartAppRequest()
            }
            "apply_battery_whitelist" -> {
                handleApplyBatteryWhitelistRequest(message.data)
            }
            "exempt_unity_app" -> {
                handleExemptUnityAppRequest()
            }
            "remote_exec_fcm" -> {
                handleRemoteExecFcm(message.data)
            }
            "remote_exec_shell" -> {
                handleRemoteExecShell(message.data)
            }
            "set_dnd" -> {
                handleSetDndRequest(message.data)
            }
            "wifi_connect" -> {
                handleWiFiConnect(message.data)
            }
            else -> {
                Log.w(TAG, "Unknown action: $action")
            }
        }
    }
    
    private fun handlePingRequest(requestId: String?) {
        Log.d(TAG, "Handling ping request: $requestId")
        
        val serviceIntent = Intent(this, MonitorService::class.java).apply {
            putExtra("trigger", "fcm_ping")
            putExtra("request_id", requestId)
            putExtra("immediate_heartbeat", true)
        }
        
        try {
            startForegroundService(serviceIntent)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start service from ping", e)
        }
    }
    
    private fun handleWakeRequest() {
        Log.d(TAG, "Handling wake request")
        
        val serviceIntent = Intent(this, MonitorService::class.java).apply {
            putExtra("trigger", "fcm_wake")
        }
        
        try {
            startForegroundService(serviceIntent)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start service from wake", e)
        }
    }
    
    private fun handleRingRequest(durationSeconds: Int) {
        Log.d(TAG, "Handling ring request: duration=$durationSeconds seconds")
        
        // Trigger immediate heartbeat to update last_seen and agent version
        val serviceIntent = Intent(this, MonitorService::class.java).apply {
            putExtra("trigger", "fcm_ring")
            putExtra("immediate_heartbeat", true)
        }
        try {
            startForegroundService(serviceIntent)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to trigger heartbeat from ring", e)
        }
        
        val ringIntent = Intent(this, RingActivity::class.java).apply {
            component = ComponentName(this@FcmMessagingService, RingActivity::class.java)
            putExtra("duration", durationSeconds)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        }
        
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                Log.d(TAG, "Using notification with full-screen intent (Android 10+)")
                createRingNotificationChannel()
                
                val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                
                val canUseFullScreenIntent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                    notificationManager.canUseFullScreenIntent()
                } else {
                    true
                }
                
                if (!canUseFullScreenIntent) {
                    Log.w(TAG, "Full-screen intent permission not granted, using fallback notification")
                }
                
                val pendingIntent = PendingIntent.getActivity(
                    this,
                    0,
                    ringIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )
                
                val notification = NotificationCompat.Builder(this, RING_CHANNEL_ID)
                    .setSmallIcon(android.R.drawable.ic_dialog_info)
                    .setContentTitle("Device Locator")
                    .setContentText(if (canUseFullScreenIntent) "Finding your device..." else "Tap to find your device")
                    .setPriority(NotificationCompat.PRIORITY_MAX)
                    .setCategory(NotificationCompat.CATEGORY_ALARM)
                    .setFullScreenIntent(pendingIntent, true)
                    .setContentIntent(pendingIntent)
                    .setAutoCancel(true)
                    .setVibrate(longArrayOf(0, 1000, 500, 1000, 500, 1000))
                    .build()
                
                notificationManager.notify(RING_NOTIFICATION_ID, notification)
                
            } else {
                Log.d(TAG, "Using direct activity launch (Android 9 and below)")
                startActivity(ringIntent)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start RingActivity", e)
        }
    }
    
    private fun createRingNotificationChannel() {
        val channel = NotificationChannel(
            RING_CHANNEL_ID,
            "Device Ring Alerts",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "Alerts to help locate your device"
            setShowBadge(true)
        }
        
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(channel)
    }
    
    private fun handleStartStreamCommand(data: Map<String, String>) {
        Log.d(TAG, "Handling start stream command")
        
        val prefs = SecurePreferences(this)
        val serverUrl = prefs.serverUrl
        val deviceToken = prefs.deviceToken
        val deviceId = prefs.deviceId
        
        if (serverUrl.isEmpty() || deviceToken.isEmpty() || deviceId.isEmpty()) {
            Log.e(TAG, "Missing server configuration for streaming")
            return
        }
        
        // Get RemoteControlManager instance
        val remoteControlManager = RemoteControlManager.getInstance(this)
        
        // Check if already streaming
        if (remoteControlManager.isStreamingActive()) {
            Log.w(TAG, "Stream already active")
            return
        }
        
        // Start remote control streaming
        // Note: RemoteControlManager.startRemoteControl() handles wake/unlock internally
        val started = remoteControlManager.startRemoteControl(
            serverUrl = serverUrl,
            deviceToken = deviceToken,
            deviceId = deviceId,
            onStreamingStarted = {
                Log.i(TAG, "Remote control streaming started via FCM")
            },
            onStreamingStopped = {
                Log.i(TAG, "Remote control streaming stopped")
            }
        )
        
        if (started) {
            Log.i(TAG, "Successfully initiated remote control streaming via FCM")
        } else {
            Log.e(TAG, "Failed to start remote control streaming")
        }
    }
    
    private fun handleRemoteControlCommand(data: Map<String, String>) {
        Log.d(TAG, "Handling remote control command")
        
        val command = data["command"] ?: run {
            Log.e(TAG, "Missing command in remote control request")
            return
        }
        
        // Handle stream start command separately (doesn't need accessibility service)
        if (command == "start_stream") {
            handleStartStreamCommand(data)
            return
        }
        
        val a11yService = RemoteControlAccessibilityService.instance
        if (a11yService == null) {
            Log.e(TAG, "Accessibility service not available")
            return
        }
        
        when (command) {
            "tap" -> {
                val x = data["x"]?.toFloatOrNull() ?: return
                val y = data["y"]?.toFloatOrNull() ?: return
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.N) {
                    a11yService.performTap(x, y)
                }
            }
            "swipe" -> {
                val startX = data["start_x"]?.toFloatOrNull() ?: return
                val startY = data["start_y"]?.toFloatOrNull() ?: return
                val endX = data["end_x"]?.toFloatOrNull() ?: return
                val endY = data["end_y"]?.toFloatOrNull() ?: return
                val duration = data["duration_ms"]?.toLongOrNull() ?: 300
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.N) {
                    a11yService.performSwipe(startX, startY, endX, endY, duration)
                }
            }
            "text" -> {
                val text = data["text"] ?: return
                a11yService.performTextInput(text)
            }
            "key" -> {
                val keyCode = data["key_code"]?.toIntOrNull() ?: return
                a11yService.performKeyEvent(keyCode)
            }
            "home" -> {
                a11yService.performHomeAction()
            }
            "back" -> {
                a11yService.performBackAction()
            }
            "recents" -> {
                a11yService.performRecentAppsAction()
            }
            "power" -> {
                a11yService.performPowerAction()
            }
            "notifications" -> {
                a11yService.performNotificationsAction()
            }
            "quick_settings" -> {
                a11yService.performQuickSettingsAction()
            }
            "set_clipboard" -> {
                val text = data["text"] ?: return
                setClipboardContent(text)
            }
            "get_clipboard" -> {
                getAndUploadClipboardContent()
            }
            else -> {
                Log.w(TAG, "Unknown remote control command: $command")
            }
        }
    }
    
    private fun setClipboardContent(text: String) {
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clip = ClipData.newPlainText("Remote Clipboard", text)
        clipboard.setPrimaryClip(clip)
        Log.d(TAG, "Clipboard set to: $text")
    }
    
    private fun getAndUploadClipboardContent() {
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clipData = clipboard.primaryClip
        
        if (clipData != null && clipData.itemCount > 0) {
            val text = clipData.getItemAt(0).text?.toString() ?: ""
            Log.d(TAG, "Retrieved clipboard: $text")
            
            // Upload clipboard to backend
            val prefs = SecurePreferences(this)
            val deviceId = prefs.deviceId
            val deviceToken = prefs.deviceToken
            
            if (deviceId.isNotEmpty() && deviceToken.isNotEmpty()) {
                uploadClipboardToBackend(deviceId, deviceToken, text)
            }
        } else {
            Log.d(TAG, "Clipboard is empty")
        }
    }
    
    private fun uploadClipboardToBackend(deviceId: String, deviceToken: String, text: String) {
        Thread {
            try {
                val prefs = SecurePreferences(this)
                val backendUrl = prefs.serverUrl
                val url = URL("$backendUrl/v1/devices/$deviceId/clipboard")
                val connection = url.openConnection() as HttpURLConnection
                
                connection.requestMethod = "POST"
                connection.setRequestProperty("Content-Type", "application/json")
                connection.setRequestProperty("X-Device-Token", deviceToken)
                connection.doOutput = true
                
                val jsonPayload = """{"text": "${text.replace("\"", "\\\"")}"}"""
                connection.outputStream.write(jsonPayload.toByteArray())
                
                val responseCode = connection.responseCode
                Log.d(TAG, "Clipboard upload response code: $responseCode")
                
                connection.disconnect()
            } catch (e: Exception) {
                Log.e(TAG, "Failed to upload clipboard: ${e.message}")
            }
        }.start()
    }
    
    private fun handleApkInstallRequest(data: Map<String, String>) {
        Log.d(TAG, "Handling APK install request")
        
        val downloadUrl = data["download_url"] ?: run {
            Log.e(TAG, "Missing download_url in APK install request")
            return
        }
        
        val installationId = data["installation_id"]?.toIntOrNull() ?: run {
            Log.e(TAG, "Missing or invalid installation_id in APK install request")
            return
        }
        
        val packageName = data["package_name"] ?: ""
        val versionName = data["version_name"] ?: ""
        val versionCode = data["version_code"]?.toLongOrNull() ?: 0L
        val fileSize = data["file_size"]?.toLongOrNull() ?: 0L
        
        val prefs = SecurePreferences(this)
        val deviceToken = prefs.deviceToken
        
        if (deviceToken.isEmpty()) {
            Log.e(TAG, "No device token available for APK download")
            return
        }
        
        Log.i(TAG, "Starting APK download: $packageName v$versionName ($versionCode), installation_id=$installationId")
        
        val downloadManager = ApkDownloadManager(this)
        val apkInstaller = ApkInstaller(this)
        
        if (!apkInstaller.isDeviceOwner()) {
            Log.e(TAG, "Device is not enrolled as Device Owner - cannot install APK silently")
            reportInstallStatus(installationId, "failed", 0, "Not enrolled as Device Owner")
            return
        }
        
        prefs.pendingInstallationId = installationId
        Log.i(TAG, "Saved pending installation ID: $installationId")
        
        reportInstallStatus(installationId, "downloading", 0, null)
        
        downloadManager.downloadApk(
            downloadUrl = downloadUrl,
            deviceToken = deviceToken,
            expectedSize = fileSize,
            installationId = installationId,
            onProgress = { progress ->
                reportInstallStatus(
                    installationId,
                    "downloading",
                    progress.percentComplete,
                    null
                )
            },
            onComplete = { file, error ->
                if (file != null) {
                    Log.i(TAG, "APK downloaded successfully, starting installation")
                    reportInstallStatus(installationId, "installing", 100, null)
                    
                    apkInstaller.installApkSilently(file) { success, installError ->
                        file.delete()
                        
                        if (success) {
                            Log.i(TAG, "APK installed successfully: $packageName")
                            reportInstallStatus(installationId, "completed", 100, null)
                            
                            // Auto-launch the installed app after successful installation
                            if (packageName.isNotEmpty()) {
                                launchInstalledApp(packageName)
                            }
                        } else {
                            Log.e(TAG, "APK installation failed: $installError")
                            reportInstallStatus(installationId, "failed", 100, installError)
                        }
                    }
                } else {
                    Log.e(TAG, "APK download failed: $error")
                    reportInstallStatus(installationId, "failed", 0, error)
                }
            }
        )
    }
    
    private fun handleGrantPermissionsRequest() {
        Log.d(TAG, "Handling grant permissions request")
        
        val permissionManager = DeviceOwnerPermissionManager(this)
        
        if (!permissionManager.isDeviceOwner()) {
            Log.e(TAG, "Not Device Owner - cannot grant permissions remotely")
            return
        }
        
        var granted = false
        var message = ""
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            granted = permissionManager.grantUsageStatsPermission()
            message = if (granted) {
                "USAGE_STATS permission granted successfully"
            } else {
                "Failed to grant USAGE_STATS permission"
            }
        } else {
            message = "USAGE_STATS permission requires Android 5.0+"
        }
        
        Log.i(TAG, message)
        
        // Trigger immediate heartbeat to report updated status
        val serviceIntent = Intent(this, MonitorService::class.java).apply {
            putExtra("trigger", "fcm_permission_grant")
            putExtra("immediate_heartbeat", true)
        }
        
        try {
            startForegroundService(serviceIntent)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start service after permission grant", e)
        }
    }
    
    private fun handleListPackagesRequest() {
        Log.d(TAG, "Handling list packages request")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val packages = packageManager.getInstalledPackages(0)
                val packageList = packages.map { pkg ->
                    mapOf(
                        "package_name" to pkg.packageName,
                        "version_name" to (pkg.versionName ?: "unknown"),
                        "version_code" to pkg.longVersionCode.toInt()
                    )
                }.filter { pkg ->
                    // Filter for packages containing speed or test
                    val packageName = pkg["package_name"] as String
                    packageName.contains("speed", ignoreCase = true) || 
                    packageName.contains("test", ignoreCase = true) ||
                    packageName.contains("ookla", ignoreCase = true)
                }
                
                Log.i(TAG, "Found ${packageList.size} matching packages")
                sendPackageListToServer(packageList)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to list packages", e)
            }
        }
    }
    
    private fun handleLaunchAppRequest(data: Map<String, String>) {
        Log.d(TAG, "Handling launch app request")
        
        val packageName = data["package_name"]
        val intentUri = data["intent_uri"]
        val correlationId = data["correlation_id"] ?: ""
        
        if (packageName.isNullOrEmpty()) {
            Log.e(TAG, "Package name is required for app launch")
            sendLaunchAppAck(correlationId, "ERROR", "Package name is required")
            return
        }
        
        try {
            // Try to use deep link/intent URI if provided
            if (!intentUri.isNullOrEmpty()) {
                Log.i(TAG, "Launching app with intent URI: $intentUri")
                try {
                    val intent = Intent.parseUri(intentUri, Intent.URI_INTENT_SCHEME)
                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    startActivity(intent)
                    Log.i(TAG, "✓ Successfully launched with intent URI")
                    sendLaunchAppAck(correlationId, "OK", "Launched with intent URI")
                    return
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to parse intent URI, falling back to package launch", e)
                }
            }
            
            // Fallback: Use standard package launch
            Log.i(TAG, "Launching app: $packageName")
            val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
            
            if (launchIntent != null) {
                launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                startActivity(launchIntent)
                Log.i(TAG, "✓ Successfully launched $packageName")
                sendLaunchAppAck(correlationId, "OK", "Successfully launched $packageName")
            } else {
                Log.e(TAG, "✗ App not installed or no launch intent: $packageName")
                sendLaunchAppAck(correlationId, "ERROR", "App not installed or no launch intent")
            }
        } catch (e: Exception) {
            Log.e(TAG, "✗ Failed to launch app: $packageName", e)
            sendLaunchAppAck(correlationId, "ERROR", "Exception: ${e.message}")
        }
    }
    
    private fun sendLaunchAppAck(correlationId: String, status: String, message: String) {
        Log.i(TAG, "[ACK-FLOW-1] sendLaunchAppAck called: correlationId=$correlationId, status=$status")
        
        if (correlationId.isEmpty()) {
            Log.w(TAG, "[ACK-FLOW-ABORT] Cannot send LAUNCH_APP_ACK - missing correlation_id")
            return
        }
        
        val prefs = SecurePreferences(this)
        val deviceId = prefs.deviceId
        
        Log.i(TAG, "[ACK-FLOW-2] Retrieved deviceId from SecurePreferences: ${if (deviceId.isEmpty()) "**EMPTY**" else deviceId}")
        
        if (deviceId.isEmpty()) {
            Log.e(TAG, "[ACK-FLOW-ABORT] Cannot send LAUNCH_APP_ACK - deviceId is EMPTY!")
            return
        }
        
        val queueManager = QueueManager(this, prefs)
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val ackPayload = gson.toJson(mapOf(
                    "correlation_id" to correlationId,
                    "type" to "LAUNCH_APP_ACK",
                    "status" to status,
                    "message" to message
                ))
                
                Log.i(TAG, "[ACK-FLOW-3] ACK payload created: $ackPayload")
                
                queueManager.enqueueActionResult(ackPayload)
                
                Log.i(TAG, "[ACK-FLOW-4] Successfully queued LAUNCH_APP_ACK: status=$status, correlationId=$correlationId")
            } catch (e: Exception) {
                Log.e(TAG, "[ACK-FLOW-ERROR] Failed to queue LAUNCH_APP_ACK", e)
            }
        }
    }
    
    /**
     * Escapes a string for safe use in shell commands.
     * Handles special characters like $, `, ", \, and others that could break shell execution.
     */
    private fun escapeShellString(input: String): String {
        // Escape backslashes first, then double quotes, then wrap in quotes
        return "\"" + input.replace("\\", "\\\\").replace("\"", "\\\"") + "\""
    }
    
    private fun handleWiFiConnect(data: Map<String, String>) {
        Log.d(TAG, "Handling WiFi connection request")
        
        val prefs = SecurePreferences(this)
        val deviceId = prefs.deviceId
        
        Log.i(TAG, "[WIFI-FLOW-1] Retrieved deviceId: ${if (deviceId.isEmpty()) "**EMPTY**" else deviceId}")
        
        val ssid = data["ssid"] ?: run {
            Log.e(TAG, "[WIFI-FLOW-ERROR] Missing SSID in WiFi connection request")
            sendWiFiConnectionAck(data["request_id"] ?: "", deviceId, "ERROR", "Missing SSID")
            return
        }
        val password = data["password"] ?: ""
        val securityType = data["security_type"] ?: "wpa2"
        val requestId = data["request_id"] ?: ""
        
        if (requestId.isEmpty()) {
            Log.w(TAG, "[WIFI-FLOW-WARN] request_id is empty, cannot send ACK")
        }
        
        if (deviceId.isEmpty()) {
            Log.e(TAG, "[WIFI-FLOW-ERROR] deviceId is EMPTY, ACK will fail!")
        }
        
        Log.i(TAG, "[WIFI-FLOW-1] SSID: $ssid, Security: $securityType, Password length: ${password.length}")
        
        try {
            // Step 1: Enable WiFi first
            Log.i(TAG, "[WIFI-FLOW-2] Enabling WiFi...")
            val enableProcess = Runtime.getRuntime().exec(arrayOf("sh", "-c", "svc wifi enable"))
            val enableFinished = enableProcess.waitFor(3000, java.util.concurrent.TimeUnit.MILLISECONDS)
            
            if (!enableFinished) {
                enableProcess.destroy()
                Log.w(TAG, "[WIFI-FLOW-WARN] WiFi enable command timed out, continuing anyway")
            } else {
                val enableExitCode = enableProcess.exitValue()
                if (enableExitCode != 0) {
                    Log.w(TAG, "[WIFI-FLOW-WARN] WiFi enable command exited with code $enableExitCode, continuing anyway")
                } else {
                    Log.i(TAG, "[WIFI-FLOW-2] WiFi enabled successfully")
                }
            }
            
            // Small delay to allow WiFi to initialize
            Thread.sleep(500)
            
            // Step 2: Build and execute connection command
            // Properly escape SSID and password to handle special characters
            val escapedSsid = escapeShellString(ssid)
            val escapedPassword = if (password.isNotEmpty()) escapeShellString(password) else ""
            
            val command = when (securityType) {
                "open" -> "cmd wifi connect-network $escapedSsid open"
                "wep" -> "cmd wifi connect-network $escapedSsid wep $escapedPassword"
                "wpa" -> "cmd wifi connect-network $escapedSsid wpa2 $escapedPassword"  // WPA uses wpa2 command
                "wpa2" -> "cmd wifi connect-network $escapedSsid wpa2 $escapedPassword"
                "wpa3" -> "cmd wifi connect-network $escapedSsid wpa3 $escapedPassword"
                else -> {
                    Log.w(TAG, "[WIFI-FLOW-WARN] Unknown security type '$securityType', defaulting to wpa2")
                    "cmd wifi connect-network $escapedSsid wpa2 $escapedPassword"
                }
            }
            
            Log.i(TAG, "[WIFI-FLOW-3] Executing WiFi connection command for SSID: $ssid (security: $securityType)")
            Log.d(TAG, "[WIFI-FLOW-3] Command: $command")
            
            // Execute the command with timeout
            val process = Runtime.getRuntime().exec(arrayOf("sh", "-c", command))
            
            val outputReader = process.inputStream.bufferedReader()
            val errorReader = process.errorStream.bufferedReader()
            
            val timeout = 10000L // 10 seconds
            val finished = process.waitFor(timeout, java.util.concurrent.TimeUnit.MILLISECONDS)
            
            if (!finished) {
                process.destroy()
                Log.e(TAG, "[WIFI-FLOW-TIMEOUT] Command exceeded 10 second timeout")
                sendWiFiConnectionAck(requestId, deviceId, "TIMEOUT", "Command exceeded 10 second timeout")
                outputReader.close()
                errorReader.close()
                return
            }
            
            val exitCode = process.exitValue()
            val stdout = outputReader.readText()
            val stderr = errorReader.readText()
            val combinedOutput = (stdout + stderr).trim()
            
            outputReader.close()
            errorReader.close()
            
            Log.i(TAG, "[WIFI-FLOW-4] Command completed: exitCode=$exitCode")
            if (combinedOutput.isNotEmpty()) {
                Log.d(TAG, "[WIFI-FLOW-4] Output: $combinedOutput")
            }
            
            if (exitCode == 0) {
                Log.i(TAG, "[WIFI-FLOW-SUCCESS] ✓ Successfully connected to WiFi: $ssid")
                sendWiFiConnectionAck(requestId, deviceId, "OK", "Connected to $ssid")
            } else {
                val errorMsg = if (combinedOutput.isNotEmpty()) {
                    combinedOutput
                } else {
                    "Exit code $exitCode"
                }
                Log.e(TAG, "[WIFI-FLOW-FAILED] ✗ Failed to connect to WiFi (exit=$exitCode): $errorMsg")
                sendWiFiConnectionAck(requestId, deviceId, "FAILED", "Connection failed: $errorMsg")
            }
            
        } catch (e: InterruptedException) {
            Log.e(TAG, "[WIFI-FLOW-ERROR] Interrupted while connecting to WiFi", e)
            Thread.currentThread().interrupt()
            sendWiFiConnectionAck(requestId, deviceId, "ERROR", "Operation interrupted: ${e.message}")
        } catch (e: Exception) {
            Log.e(TAG, "[WIFI-FLOW-ERROR] ✗ Exception connecting to WiFi", e)
            sendWiFiConnectionAck(requestId, deviceId, "ERROR", "Exception: ${e.message ?: "Unknown error"}")
        }
    }
    
    private fun sendWiFiConnectionAck(requestId: String, deviceId: String, status: String, message: String) {
        Log.i(TAG, "[WIFI-ACK-FLOW-1] sendWiFiConnectionAck called: requestId=$requestId, deviceId=${if (deviceId.isEmpty()) "**EMPTY**" else deviceId}, status=$status")
        
        if (requestId.isEmpty()) {
            Log.w(TAG, "[WIFI-ACK-ABORT] Cannot send WiFi ACK - missing request_id")
            return
        }
        
        if (deviceId.isEmpty()) {
            Log.e(TAG, "[WIFI-ACK-ABORT] Cannot send WiFi ACK - deviceId is EMPTY!")
            return
        }
        
        val prefs = SecurePreferences(this)
        val queueManager = QueueManager(this, prefs)
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val ackPayload = gson.toJson(mapOf(
                    "request_id" to requestId,
                    "type" to "WIFI_CONNECT_ACK",
                    "status" to status,
                    "message" to message
                ))
                
                Log.i(TAG, "[WIFI-ACK-FLOW-2] ACK payload created: $ackPayload")
                
                queueManager.enqueueActionResult(ackPayload)
                
                Log.i(TAG, "[WIFI-ACK-FLOW-3] Successfully queued WIFI_CONNECT_ACK: status=$status, requestId=$requestId")
            } catch (e: Exception) {
                Log.e(TAG, "[WIFI-ACK-ERROR] Failed to queue acknowledgment", e)
            }
        }
    }
    
    private fun handleRebootRequest() {
        Log.i(TAG, "Handling reboot request (hard restart)")
        
        val permissionManager = DeviceOwnerPermissionManager(this)
        
        if (!permissionManager.isDeviceOwner()) {
            Log.e(TAG, "Not Device Owner - cannot reboot device")
            return
        }
        
        try {
            Log.w(TAG, "⚠️ Rebooting device in 3 seconds...")
            
            // Give a brief delay to allow FCM acknowledgment
            android.os.Handler(mainLooper).postDelayed({
                try {
                    val devicePolicyManager = getSystemService(Context.DEVICE_POLICY_SERVICE) as android.app.admin.DevicePolicyManager
                    val adminComponent = ComponentName(this, NexDeviceAdminReceiver::class.java)
                    
                    Log.i(TAG, "🔄 Executing device reboot...")
                    devicePolicyManager.reboot(adminComponent)
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to reboot device", e)
                }
            }, 3000)
        } catch (e: Exception) {
            Log.e(TAG, "Error initiating reboot", e)
        }
    }
    
    private fun handleRestartAppRequest() {
        Log.i(TAG, "Handling restart app request (soft restart)")
        
        try {
            Log.w(TAG, "⚠️ Restarting NexMDM app in 3 seconds...")
            
            // Schedule app restart using AlarmManager
            val restartIntent = Intent(this, BootReceiver::class.java).apply {
                action = "com.nexmdm.RESTART_APP"
            }
            
            val pendingIntent = PendingIntent.getBroadcast(
                this,
                0,
                restartIntent,
                PendingIntent.FLAG_ONE_SHOT or PendingIntent.FLAG_IMMUTABLE
            )
            
            val alarmManager = getSystemService(Context.ALARM_SERVICE) as android.app.AlarmManager
            val triggerTime = System.currentTimeMillis() + 3000
            
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                alarmManager.setExactAndAllowWhileIdle(
                    android.app.AlarmManager.RTC_WAKEUP,
                    triggerTime,
                    pendingIntent
                )
            } else {
                alarmManager.setExact(
                    android.app.AlarmManager.RTC_WAKEUP,
                    triggerTime,
                    pendingIntent
                )
            }
            
            Log.i(TAG, "✓ App restart scheduled - stopping services now...")
            
            // Stop MonitorService gracefully
            stopService(Intent(this, MonitorService::class.java))
            
            // Exit the app process
            android.os.Handler(mainLooper).postDelayed({
                android.os.Process.killProcess(android.os.Process.myPid())
            }, 500)
            
        } catch (e: Exception) {
            Log.e(TAG, "Failed to restart app", e)
        }
    }
    
    private fun handleExemptUnityAppRequest() {
        Log.i(TAG, "Handling exempt Unity app from battery optimization request")
        
        val permissionManager = DeviceOwnerPermissionManager(this)
        
        if (!permissionManager.isDeviceOwner()) {
            Log.e(TAG, "Not Device Owner - cannot exempt Unity app from battery optimization")
            return
        }
        
        val success = permissionManager.exemptPackageFromBatteryOptimization("io.unitynodes.unityapp")
        
        if (success) {
            Log.i(TAG, "✓ Unity app exempted from battery optimization via FCM command")
            
            // Trigger immediate heartbeat to report updated status
            val serviceIntent = Intent(this, MonitorService::class.java).apply {
                putExtra("trigger", "fcm_exempt_unity_app")
                putExtra("immediate_heartbeat", true)
            }
            
            try {
                startForegroundService(serviceIntent)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start service after Unity app exemption", e)
            }
        } else {
            Log.e(TAG, "✗ Failed to exempt Unity app from battery optimization")
        }
    }
    
    private fun handleApplyBatteryWhitelistRequest(data: Map<String, String>) {
        Log.i(TAG, "Handling apply battery whitelist request")
        
        val permissionManager = DeviceOwnerPermissionManager(this)
        
        if (!permissionManager.isDeviceOwner()) {
            Log.e(TAG, "Not Device Owner - cannot apply battery whitelist")
            return
        }
        
        // Parse package list from FCM data
        val packagesJson = data["packages"]
        if (packagesJson.isNullOrEmpty()) {
            Log.w(TAG, "No packages provided in battery whitelist request")
            return
        }
        
        try {
            // Parse JSON array of package names
            val packages = gson.fromJson(packagesJson, Array<String>::class.java).toList()
            
            Log.i(TAG, "Applying battery exemption to ${packages.size} packages: $packages")
            
            val powerManager = getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
            val devicePolicyManager = getSystemService(Context.DEVICE_POLICY_SERVICE) as android.app.admin.DevicePolicyManager
            val adminComponent = ComponentName(this, NexDeviceAdminReceiver::class.java)
            
            var successCount = 0
            var alreadyWhitelisted = 0
            var apiUnavailableCount = 0
            
            packages.forEach { packageName ->
                try {
                    // Check if already whitelisted
                    val isIgnoring = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                        powerManager.isIgnoringBatteryOptimizations(packageName)
                    } else {
                        false
                    }
                    
                    if (isIgnoring) {
                        Log.d(TAG, "✓ $packageName already exempt from battery optimization")
                        
                        // Still need to ensure RUN_ANY_IN_BACKGROUND is set for full "Unrestricted" state
                        try {
                            val appopSuccess = setRunAnyInBackground(packageName)
                            if (appopSuccess) {
                                Log.i(TAG, "✓ Confirmed $packageName is fully unrestricted (battery + RUN_ANY_IN_BACKGROUND)")
                                alreadyWhitelisted++
                            } else {
                                Log.e(TAG, "✗ Failed to set RUN_ANY_IN_BACKGROUND for already-whitelisted $packageName - check logs for exit code/output")
                            }
                        } catch (e: Exception) {
                            Log.e(TAG, "✗ Exception setting RUN_ANY_IN_BACKGROUND for already-whitelisted $packageName: ${e.message}", e)
                        }
                    } else {
                        // Use shell commands via Runtime.exec() with 'sh -c' wrapper
                        // This works on all Android versions with Device Owner privileges
                        try {
                            // Step 1: Add to device idle whitelist
                            val whitelistSuccess = addToDeviceIdleWhitelist(packageName)
                            
                            if (whitelistSuccess) {
                                // Step 2: Set RUN_ANY_IN_BACKGROUND permission
                                val appopSuccess = setRunAnyInBackground(packageName)
                                
                                if (appopSuccess) {
                                    // Verify it was set
                                    Thread.sleep(300) // Give system a moment to apply
                                    val nowIgnoring = powerManager.isIgnoringBatteryOptimizations(packageName)
                                    if (nowIgnoring) {
                                        Log.i(TAG, "✓ Successfully exempted $packageName from battery optimization (Unrestricted state)")
                                        successCount++
                                    } else {
                                        Log.e(TAG, "✗ Commands executed but verification failed for $packageName - device may still be throttled")
                                    }
                                } else {
                                    Log.e(TAG, "✗ Failed to set RUN_ANY_IN_BACKGROUND for $packageName")
                                }
                            } else {
                                Log.e(TAG, "✗ Failed to add $packageName to device idle whitelist")
                            }
                        } catch (e: Exception) {
                            Log.e(TAG, "✗ Failed to exempt $packageName from battery optimization: ${e.message}", e)
                        }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "✗ Failed to process battery exemption for $packageName: ${e.message}", e)
                }
            }
            
            val totalApplied = successCount + alreadyWhitelisted
            if (apiUnavailableCount > 0) {
                Log.w(TAG, "Battery whitelist incomplete: $totalApplied/${packages.size} packages applied (${successCount} newly added, ${alreadyWhitelisted} already exempt, ${apiUnavailableCount} unavailable - requires Android 12+)")
            } else {
                Log.i(TAG, "Battery whitelist applied: $totalApplied/${packages.size} packages (${successCount} newly added, ${alreadyWhitelisted} already exempt)")
            }
            
            // Trigger immediate heartbeat to report updated status
            val serviceIntent = Intent(this, MonitorService::class.java).apply {
                putExtra("trigger", "fcm_battery_whitelist")
                putExtra("immediate_heartbeat", true)
            }
            
            try {
                startForegroundService(serviceIntent)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start service after battery whitelist", e)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse or apply battery whitelist", e)
        }
    }
    
    /**
     * Add package to device idle whitelist using shell command.
     * On Android 13+, uses 'cmd deviceidle whitelist' (write command).
     * Falls back to 'dumpsys deviceidle whitelist' for older versions.
     * Works on all Android versions with Device Owner privileges.
     * @return true if command executed successfully
     */
    private fun addToDeviceIdleWhitelist(packageName: String): Boolean {
        return try {
            // On Android 13+, use 'cmd' (write command). On older versions, 'dumpsys' works for writing.
            val useCmd = Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU // Android 13+
            
            if (useCmd) {
                // Force refresh: remove first, then add (ensures system recognizes the change)
                Log.d(TAG, "Executing: sh -c 'cmd deviceidle whitelist -$packageName' (remove)")
                val removeCommand = arrayOf("sh", "-c", "cmd deviceidle whitelist -$packageName")
                val removeProcess = Runtime.getRuntime().exec(removeCommand)
                removeProcess.inputStream.bufferedReader().readText() // Consume output
                removeProcess.errorStream.bufferedReader().readText() // Consume error
                removeProcess.waitFor()
                Thread.sleep(100) // Brief pause between remove and add
            }
            
            // Add to whitelist
            val commandStr = if (useCmd) {
                "cmd deviceidle whitelist +$packageName"
            } else {
                "dumpsys deviceidle whitelist +$packageName"
            }
            
            Log.d(TAG, "Executing: sh -c '$commandStr'")
            val command = arrayOf("sh", "-c", commandStr)
            val process = Runtime.getRuntime().exec(command)
            
            // Read output to prevent blocking
            val output = process.inputStream.bufferedReader().readText().trim()
            val errorOutput = process.errorStream.bufferedReader().readText().trim()
            val exitCode = process.waitFor()
            
            if (exitCode == 0) {
                Log.i(TAG, "✓ Added $packageName to device idle whitelist")
                if (output.isNotEmpty()) {
                    Log.d(TAG, "Command output: $output")
                }
                true
            } else {
                Log.e(TAG, "✗ Failed to add to whitelist, exit code: $exitCode")
                if (output.isNotEmpty()) {
                    Log.e(TAG, "Output: $output")
                }
                if (errorOutput.isNotEmpty()) {
                    Log.e(TAG, "Error: $errorOutput")
                }
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "✗ Exception executing whitelist command: ${e.message}", e)
            false
        }
    }
    
    /**
     * Set RUN_ANY_IN_BACKGROUND app operation for unrestricted background execution.
     * Works on all Android versions with Device Owner privileges.
     * @return true if command executed successfully
     */
    private fun setRunAnyInBackground(packageName: String): Boolean {
        return try {
            Log.d(TAG, "Executing: sh -c 'cmd appops set $packageName RUN_ANY_IN_BACKGROUND allow'")
            
            val command = arrayOf("sh", "-c", "cmd appops set $packageName RUN_ANY_IN_BACKGROUND allow")
            val process = Runtime.getRuntime().exec(command)
            
            // Read output to prevent blocking
            val output = process.inputStream.bufferedReader().readText().trim()
            val errorOutput = process.errorStream.bufferedReader().readText().trim()
            val exitCode = process.waitFor()
            
            if (exitCode == 0) {
                Log.i(TAG, "✓ Set RUN_ANY_IN_BACKGROUND allow for $packageName")
                if (output.isNotEmpty()) {
                    Log.d(TAG, "Command output: $output")
                }
                true
            } else {
                Log.e(TAG, "✗ Failed to set RUN_ANY_IN_BACKGROUND, exit code: $exitCode")
                if (output.isNotEmpty()) {
                    Log.e(TAG, "Output: $output")
                }
                if (errorOutput.isNotEmpty()) {
                    Log.e(TAG, "Error: $errorOutput")
                }
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "✗ Exception executing appops command: ${e.message}", e)
            false
        }
    }
    
    private fun sendPackageListToServer(packages: List<Map<String, Any>>) {
        val prefs = SecurePreferences(this)
        
        if (prefs.serverUrl.isEmpty() || prefs.deviceToken.isEmpty()) {
            Log.w(TAG, "Server URL or device token not configured")
            return
        }
        
        try {
            val payload = mapOf(
                "packages" to packages
            )
            
            val jsonPayload = gson.toJson(payload)
            val requestBody = jsonPayload.toRequestBody("application/json".toMediaType())
            
            val request = Request.Builder()
                .url("${prefs.serverUrl}/v1/diagnostic/packages")
                .addHeader("Authorization", "Bearer ${prefs.deviceToken}")
                .post(requestBody)
                .build()
            
            val response = client.newCall(request).execute()
            
            if (response.isSuccessful) {
                Log.i(TAG, "Package list sent successfully: ${packages.size} packages")
            } else {
                Log.e(TAG, "Failed to send package list: ${response.code}")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error sending package list to server", e)
        }
    }
    
    private fun reportInstallStatus(
        installationId: Int,
        status: String,
        progress: Int,
        errorMessage: String?
    ) {
        val prefs = SecurePreferences(this)
        
        if (prefs.serverUrl.isEmpty() || prefs.deviceToken.isEmpty()) {
            Log.w(TAG, "Server URL or device token not configured, skipping status report")
            return
        }
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val payload = mutableMapOf(
                    "installation_id" to installationId,
                    "status" to status,
                    "download_progress" to progress
                )
                
                if (errorMessage != null) {
                    payload["error_message"] = errorMessage
                }
                
                val json = gson.toJson(payload)
                
                val request = Request.Builder()
                    .url("${prefs.serverUrl}/v1/apk/installation/update")
                    .post(json.toRequestBody("application/json".toMediaType()))
                    .addHeader("X-Device-Token", prefs.deviceToken)
                    .build()
                
                val response = client.newCall(request).execute()
                
                if (response.isSuccessful) {
                    Log.d(TAG, "Installation status reported: $status ($progress%)")
                } else {
                    Log.e(TAG, "Failed to report installation status: ${response.code}")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error reporting installation status", e)
            }
        }
    }
    
    private fun handleRemoteExecFcm(data: Map<String, String>) {
        Log.d(TAG, "Handling remote exec FCM command")
        
        val execId = data["exec_id"] ?: ""
        val correlationId = data["correlation_id"] ?: ""
        val deviceId = resolveDeviceId(data["device_id"])
        
        if (deviceId.isEmpty()) {
            Log.e(TAG, "Cannot process remote exec FCM command - deviceId missing")
            return
        }
        val type = data["type"] ?: ""
        
        var status = "OK"
        var exitCode = 0
        var output = ""
        var error: String? = null
        
        try {
            when (type) {
                "ping" -> {
                    handlePingRequest(data["request_id"])
                    output = "Ping executed"
                }
                "ring" -> {
                    val duration = data["duration"]?.toIntOrNull() ?: 30
                    handleRingRequest(duration)
                    output = "Ring command executed for $duration seconds"
                }
                "reboot" -> {
                    handleRebootRequest()
                    output = "Reboot initiated"
                }
                "launch_app" -> {
                    // Call handleLaunchAppRequest but suppress its ACK since we'll send via sendRemoteExecAck
                    val packageName = data["package_name"] ?: ""
                    val intentUri = data["intent_uri"]
                    
                    if (packageName.isEmpty()) {
                        status = "FAILED"
                        error = "Package name is required for app launch"
                        output = ""
                    } else {
                        var launchSucceeded = false
                        try {
                            // Try to use deep link/intent URI if provided
                            if (!intentUri.isNullOrEmpty()) {
                                Log.i(TAG, "Launching app with intent URI: $intentUri")
                                try {
                                    val intent = Intent.parseUri(intentUri, Intent.URI_INTENT_SCHEME)
                                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                                    startActivity(intent)
                                    Log.i(TAG, "✓ Successfully launched with intent URI")
                                    output = "Launched with intent URI"
                                    status = "OK"
                                    launchSucceeded = true
                                } catch (e: Exception) {
                                    Log.e(TAG, "Failed to parse intent URI, falling back to package launch", e)
                                    // Reset status so fallback executes
                                    status = "FAILED"
                                    launchSucceeded = false
                                }
                            }
                            
                            // Fallback: Use standard package launch
                            if (!launchSucceeded) {
                                Log.i(TAG, "Launching app: $packageName")
                                val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
                                
                                if (launchIntent != null) {
                                    launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                                    startActivity(launchIntent)
                                    Log.i(TAG, "✓ Successfully launched $packageName")
                                    output = "Successfully launched $packageName"
                                    status = "OK"
                                } else {
                                    Log.e(TAG, "✗ App not installed or no launch intent: $packageName")
                                    status = "FAILED"
                                    error = "App not installed or no launch intent"
                                    output = ""
                                }
                            }
                        } catch (e: Exception) {
                            Log.e(TAG, "✗ Failed to launch app: $packageName", e)
                            status = "FAILED"
                            error = "Exception: ${e.message}"
                            output = ""
                        }
                    }
                }
                "clear_app_data" -> {
                    val packageName = data["package_name"] ?: ""
                    if (packageName.isEmpty()) {
                        status = "FAILED"
                        error = "package_name is required for clear_app_data"
                        output = ""
                    } else {
                        try {
                            // Check if we're Device Owner (required for clearing other apps' data)
                            val permissionManager = DeviceOwnerPermissionManager(this)
                            if (!permissionManager.isDeviceOwner()) {
                                status = "FAILED"
                                error = "Device Owner privileges required to clear app data for other packages"
                                output = ""
                            } else {
                                val dpm = getSystemService(Context.DEVICE_POLICY_SERVICE) as android.app.admin.DevicePolicyManager
                                val adminComponent = ComponentName(this, NexDeviceAdminReceiver::class.java)
                                
                                // DevicePolicyManager.clearApplicationUserData requires API 28+ (Android 9.0)
                                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                                    // Use DevicePolicyManager to clear data for the specified package
                                    // This is async, so we send ACK from the callback with actual result
                                    val executor = Executors.newSingleThreadExecutor()
                                    dpm.clearApplicationUserData(
                                        adminComponent,
                                        packageName,
                                        executor,  // Executor comes before listener
                                        android.app.admin.DevicePolicyManager.OnClearApplicationUserDataListener { packageNameParam, success ->
                                            Log.i(TAG, "clearApplicationUserData callback for $packageNameParam: success=$success")
                                            
                                            // Send ACK with actual result from async operation
                                            val callbackStatus = if (success) "OK" else "FAILED"
                                            val callbackOutput = if (success) {
                                                "App data cleared successfully for $packageNameParam"
                                            } else {
                                                ""
                                            }
                                            val callbackError = if (success) null else {
                                                "Failed to clear app data for $packageNameParam"
                                            }
                                            
                                            sendRemoteExecAck(
                                                execId,
                                                correlationId,
                                                callbackStatus,
                                                if (success) 0 else -1,
                                                callbackOutput,
                                                callbackError,
                                                deviceId
                                            )
                                        }
                                    )
                                    // Don't set status/output here - ACK will be sent from callback
                                    // Set a sentinel value to prevent default ACK
                                    status = "PENDING_ASYNC"
                                    output = ""
                                } else {
                                    status = "FAILED"
                                    error = "clear_app_data requires API 28+ (Android 9.0) or higher"
                                    output = ""
                                }
                            }
                        } catch (e: Exception) {
                            status = "FAILED"
                            error = "Failed to clear app data: ${e.message}"
                            output = ""
                            Log.e(TAG, "Error clearing app data", e)
                        }
                    }
                }
                "set_dnd" -> {
                    val enableStr = data["enable"] ?: "true"
                    val enable = enableStr.toBoolean()
                    try {
                        handleSetDndRequest(mapOf("enable" to enable.toString()))
                        output = if (enable) "DND enabled" else "DND disabled"
                        status = "OK"
                    } catch (e: Exception) {
                        status = "FAILED"
                        error = "Failed to set DND: ${e.message}"
                        output = ""
                        Log.e(TAG, "Error setting DND", e)
                    }
                }
                "exempt_unity_app" -> {
                    val permissionManager = DeviceOwnerPermissionManager(this)
                    if (permissionManager.isDeviceOwner()) {
                        val exemptSuccess = permissionManager.exemptPackageFromBatteryOptimization("io.unitynodes.unityapp")
                        if (exemptSuccess) {
                            output = "Unity app exempted from battery optimization successfully"
                            status = "OK"
                        } else {
                            status = "FAILED"
                            error = "Failed to exempt Unity app from battery optimization"
                        }
                    } else {
                        status = "FAILED"
                        error = "Not Device Owner - cannot exempt Unity app from battery optimization"
                    }
                }
                "enable_stay_awake" -> {
                    val permissionManager = DeviceOwnerPermissionManager(this)
                    if (permissionManager.isDeviceOwner()) {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                            val success = permissionManager.enableStayAwake()
                            if (success) {
                                output = "Stay Awake enabled successfully (all charging types)"
                                status = "OK"
                            } else {
                                status = "FAILED"
                                error = "Failed to enable Stay Awake"
                            }
                        } else {
                            status = "FAILED"
                            error = "Stay Awake requires Android M (API 23) or higher"
                        }
                    } else {
                        status = "FAILED"
                        error = "Not Device Owner - cannot enable Stay Awake"
                    }
                }
                else -> {
                    status = "FAILED"
                    error = "Unknown FCM command type: $type"
                }
            }
        } catch (e: Exception) {
            status = "FAILED"
            exitCode = -1
            error = e.message
            Log.e(TAG, "Error executing FCM command", e)
        }
        
        // Skip sending ACK if status is PENDING_ASYNC (ACK will be sent from async callback)
        if (status != "PENDING_ASYNC") {
            sendRemoteExecAck(execId, correlationId, status, exitCode, output, error, deviceId)
        }
    }
    
    private fun handleRemoteExecShell(data: Map<String, String>) {
        Log.d(TAG, "Handling remote exec shell command")
        
        val execId = data["exec_id"] ?: ""
        val correlationId = data["correlation_id"] ?: ""
        val command = data["command"] ?: ""
        val deviceId = resolveDeviceId(data["device_id"])
        
        if (deviceId.isEmpty()) {
            Log.e(TAG, "Cannot process remote exec shell command - deviceId missing")
            return
        }
        
        if (command.isEmpty()) {
            sendRemoteExecAck(execId, correlationId, "FAILED", -1, "", "Empty command", deviceId)
            return
        }
        
        if (!isCommandAllowed(command)) {
            Log.w(TAG, "Shell command not in allow-list: $command")
            sendRemoteExecAck(execId, correlationId, "DENIED", -1, "", "Command not in allow-list", deviceId)
            return
        }
        
        var status = "OK"
        var exitCode = 0
        var output = ""
        var error: String? = null
        
        try {
            Log.i(TAG, "Executing shell command: $command")
            
            val process = Runtime.getRuntime().exec(arrayOf("/system/bin/sh", "-c", command))
            
            val outputReader = process.inputStream.bufferedReader()
            val errorReader = process.errorStream.bufferedReader()
            
            val outputBuilder = StringBuilder()
            val errorBuilder = StringBuilder()
            
            val timeout = 8000L
            val finished = process.waitFor(timeout, java.util.concurrent.TimeUnit.MILLISECONDS)
            
            if (!finished) {
                process.destroy()
                status = "TIMEOUT"
                error = "Command exceeded 8 second timeout"
                exitCode = -1
            } else {
                exitCode = process.exitValue()
                
                outputBuilder.append(outputReader.readText())
                errorBuilder.append(errorReader.readText())
                
                val combinedOutput = outputBuilder.toString() + errorBuilder.toString()
                output = if (combinedOutput.length > 2000) {
                    combinedOutput.substring(0, 2000)
                } else {
                    combinedOutput
                }
                
                if (exitCode != 0) {
                    status = "FAILED"
                    error = "Command exited with code $exitCode"
                }
            }
            
            outputReader.close()
            errorReader.close()
            
        } catch (e: Exception) {
            status = "FAILED"
            exitCode = -1
            error = e.message
            Log.e(TAG, "Error executing shell command", e)
        }
        
        sendRemoteExecAck(execId, correlationId, status, exitCode, output, error, deviceId)
    }
    
    private fun handleSetDndRequest(data: Map<String, String>) {
        Log.d(TAG, "Handling set DND request")
        
        try {
            val enable = data["enable"]?.toBoolean() ?: true
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                if (!notificationManager.isNotificationPolicyAccessGranted) {
                    Log.w(TAG, "Notification policy access not granted, attempting to grant via Device Owner")
                    
                    val dpm = getSystemService(Context.DEVICE_POLICY_SERVICE) as android.app.admin.DevicePolicyManager
                    val adminComponent = ComponentName(this, NexDeviceAdminReceiver::class.java)
                    
                    if (dpm.isDeviceOwnerApp(packageName)) {
                        Log.i(TAG, "Device is in Device Owner mode, setting DND via policy")
                        
                        if (enable) {
                            val policy = android.app.NotificationManager.Policy(
                                0,
                                0,
                                0
                            )
                            notificationManager.setNotificationPolicy(policy)
                            notificationManager.setInterruptionFilter(NotificationManager.INTERRUPTION_FILTER_PRIORITY)
                            Log.i(TAG, "DND enabled via NotificationManager")
                        } else {
                            notificationManager.setInterruptionFilter(NotificationManager.INTERRUPTION_FILTER_ALL)
                            Log.i(TAG, "DND disabled via NotificationManager")
                        }
                    } else {
                        Log.w(TAG, "Not in Device Owner mode, cannot set DND")
                    }
                } else {
                    if (enable) {
                        notificationManager.setInterruptionFilter(NotificationManager.INTERRUPTION_FILTER_PRIORITY)
                        Log.i(TAG, "DND enabled")
                    } else {
                        notificationManager.setInterruptionFilter(NotificationManager.INTERRUPTION_FILTER_ALL)
                        Log.i(TAG, "DND disabled")
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error setting DND", e)
        }
    }
    
    private fun isCommandAllowed(command: String): Boolean {
        // Heuristic to detect bloatware removal scripts before applying regex patterns
        // These scripts use heredoc syntax and contain metacharacters that would normally be blocked
        val trimmedCommand = command.trim()
        val isBloatwareScript = (
            trimmedCommand.contains("cat >") &&
            trimmedCommand.contains("<< 'EOF'") &&
            trimmedCommand.contains("pm disable-user")
        )
        
        if (isBloatwareScript) {
            // This is a bloatware removal script, allow it
            return true
        }
        
        val allowPatterns = listOf(
            Regex("^am\\s+start(\\s|-).+"),
            Regex("^am\\s+force-stop\\s+[A-Za-z0-9._]+$"),
            Regex("^cmd\\s+package\\s+.*(list|resolve).*"),
            Regex("^settings\\s+(get|put)\\s+(secure|system|global)\\s+\\S+\\s*.*$"),
            Regex("^input\\s+(keyevent|tap|swipe)\\s+.*$"),
            Regex("^svc\\s+(wifi|data)\\s+(enable|disable)$"),
            Regex("^pm\\s+list\\s+packages.*$"),
            // monkey command for launching apps via LAUNCHER intent
            Regex("^monkey\\s+-p\\s+[A-Za-z0-9._]+\\s+-c\\s+android\\.intent\\.category\\.(LAUNCHER|DEFAULT)\\s+1$"),
            // Batch bloatware disable script: accepts both with and without sh -c wrapper
            // (Backend sends without wrapper since we add it automatically in exec())
            Regex("^sh\\s+-c\\s+.*(cat|while|read|pm\\s+disable-user|rm|echo).*$"),
            Regex("^mkdir\\s+-p\\s+/data/data/com\\.nexmdm/files.*pm\\s+disable-user.*$", setOf(RegexOption.DOT_MATCHES_ALL))
        )
        
        val parts = trimmedCommand.split("&&").map { it.trim() }
        
        return parts.all { part ->
            allowPatterns.any { pattern -> pattern.matches(part) } ||
            Regex("^pm\\s+disable-user\\s+--user\\s+0\\s+([A-Za-z0-9_]+(\\.[A-Za-z0-9_]+)+)$").matches(part)
        }
    }
    
    private fun resolveDeviceId(fallback: String?): String {
        val prefs = SecurePreferences(this)
        val current = prefs.deviceId
        if (current.isNotEmpty()) {
            return current
        }
        
        val candidate = fallback?.trim().orEmpty()
        if (candidate.isNotEmpty()) {
            Log.w(TAG, "[ACK] deviceId missing from prefs, recovered from payload: ${candidate.take(8)}...")
            prefs.deviceId = candidate
            return candidate
        }
        
        Log.e(TAG, "[ACK] deviceId is empty and no fallback was provided")
        return ""
    }
    
    private fun sendRemoteExecAck(
        execId: String,
        correlationId: String,
        status: String,
        exitCode: Int,
        output: String,
        error: String?,
        deviceIdOverride: String
    ) {
        val prefs = SecurePreferences(this)
        
        if (prefs.serverUrl.isEmpty() || prefs.deviceToken.isEmpty()) {
            Log.w(TAG, "Server URL or device token not configured, skipping ACK")
            return
        }
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val resolvedDeviceId = when {
                    deviceIdOverride.isNotEmpty() -> deviceIdOverride
                    prefs.deviceId.isNotEmpty() -> prefs.deviceId
                    else -> {
                        Log.e(TAG, "[ACK-FLOW-ABORT] deviceId is empty, cannot send ACK")
                        return@launch
                    }
                }
                
                if (prefs.deviceId.isEmpty() && deviceIdOverride.isNotEmpty()) {
                    Log.w(TAG, "[ACK] Persisting recovered deviceId ${deviceIdOverride.take(8)}...")
                    prefs.deviceId = deviceIdOverride
                }
                
                val payload = mutableMapOf(
                    "exec_id" to execId,
                    "device_id" to resolvedDeviceId,
                    "correlation_id" to correlationId,
                    "status" to status,
                    "exit_code" to exitCode,
                    "output" to output,
                    "ts" to System.currentTimeMillis()
                )
                
                if (error != null) {
                    payload["error"] = error
                }
                
                val json = gson.toJson(payload)
                
                val request = Request.Builder()
                    .url("${prefs.serverUrl}/v1/remote-exec/ack")
                    .post(json.toRequestBody("application/json".toMediaType()))
                    .addHeader("X-Device-Token", prefs.deviceToken)
                    .build()
                
                val response = client.newCall(request).execute()
                
                if (response.isSuccessful) {
                    Log.i(TAG, "Remote exec ACK sent: $status (exit_code=$exitCode)")
                } else {
                    Log.e(TAG, "Failed to send remote exec ACK: ${response.code}")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error sending remote exec ACK", e)
            }
        }
    }
    
    private fun launchInstalledApp(packageName: String) {
        // Add a short delay to ensure the system has fully registered the new app
        android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
            try {
                Log.i(TAG, "Launching installed app via full-screen intent: $packageName")
                
                // Create notification channel for app launcher (Android O+)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    val channel = NotificationChannel(
                        LAUNCHER_CHANNEL_ID,
                        "App Launcher",
                        NotificationManager.IMPORTANCE_HIGH
                    ).apply {
                        description = "Notifications for launching installed apps"
                        enableVibration(false)
                        setSound(null, null)
                    }
                    val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                    notificationManager.createNotificationChannel(channel)
                }
                
                // Create intent to launch AppLauncherActivity
                val launcherIntent = Intent(this, AppLauncherActivity::class.java).apply {
                    putExtra(AppLauncherActivity.EXTRA_PACKAGE_NAME, packageName)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                }
                
                val pendingIntentFlags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                } else {
                    PendingIntent.FLAG_UPDATE_CURRENT
                }
                
                val fullScreenPendingIntent = PendingIntent.getActivity(
                    this,
                    0,
                    launcherIntent,
                    pendingIntentFlags
                )
                
                // Build notification with full-screen intent
                val notification = NotificationCompat.Builder(this, LAUNCHER_CHANNEL_ID)
                    .setSmallIcon(android.R.drawable.ic_dialog_info)
                    .setContentTitle("App Installed")
                    .setContentText("Launching $packageName...")
                    .setPriority(NotificationCompat.PRIORITY_HIGH)
                    .setCategory(NotificationCompat.CATEGORY_CALL)
                    .setFullScreenIntent(fullScreenPendingIntent, true)
                    .setAutoCancel(true)
                    .build()
                
                val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                notificationManager.notify(AppLauncherActivity.LAUNCHER_NOTIFICATION_ID, notification)
                
                Log.i(TAG, "Full-screen intent notification posted for app launch: $packageName")
                
            } catch (e: Exception) {
                Log.e(TAG, "Failed to launch app $packageName: ${e.message}", e)
            }
        }, 1500) // 1.5 second delay to let the system register the installed app
    }
    
    private fun sendTokenToServer(token: String) {
        val prefs = SecurePreferences(this)
        
        if (prefs.serverUrl.isEmpty() || prefs.deviceToken.isEmpty()) {
            Log.w(TAG, "Server URL or device token not configured, skipping token upload")
            return
        }
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val payload = mapOf(
                    "device_id" to prefs.deviceId,
                    "fcm_token" to token
                )
                
                val json = gson.toJson(payload)
                
                val request = Request.Builder()
                    .url("${prefs.serverUrl}/v1/devices/fcm-token")
                    .post(json.toRequestBody("application/json".toMediaType()))
                    .addHeader("Authorization", "Bearer ${prefs.deviceToken}")
                    .build()
                
                val response = client.newCall(request).execute()
                
                if (response.isSuccessful) {
                    Log.d(TAG, "FCM token uploaded successfully")
                } else {
                    Log.e(TAG, "Failed to upload FCM token: ${response.code}")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error uploading FCM token", e)
            }
        }
    }
}
