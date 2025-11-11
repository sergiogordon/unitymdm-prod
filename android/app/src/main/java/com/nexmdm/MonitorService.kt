package com.nexmdm

import android.app.AlarmManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessaging
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

class MonitorService : Service() {
    
    companion object {
        private const val TAG = "MonitorService"
        private const val CHANNEL_ID = "monitor_channel"
        private const val NOTIFICATION_ID = 1
        private const val HEARTBEAT_INTERVAL_MS = 300_000L
        private const val WATCHDOG_INTERVAL_MS = 600_000L
    }
    
    private val handler = Handler(Looper.getMainLooper())
    private val serviceJob = Job()
    private val serviceScope = CoroutineScope(Dispatchers.IO + serviceJob)
    private lateinit var prefs: SecurePreferences
    private lateinit var telemetry: TelemetryCollector
    private lateinit var speedtestDetector: SpeedtestDetector
    private lateinit var queueManager: QueueManager
    private lateinit var networkMonitor: NetworkMonitor
    private lateinit var powerMonitor: PowerManagementMonitor
    private val gson = Gson()
    private var wakeLock: PowerManager.WakeLock? = null
    private lateinit var alarmManager: AlarmManager
    
    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()
    
    private val watchdogRunnable = object : Runnable {
        override fun run() {
            checkAndRestartIfNeeded()
            handler.postDelayed(this, WATCHDOG_INTERVAL_MS)
        }
    }
    
    override fun onCreate() {
        super.onCreate()
        
        setupCrashRecovery()
        
        prefs = SecurePreferences(this)
        queueManager = QueueManager(this, prefs, client)
        powerMonitor = PowerManagementMonitor(this)
        
        networkMonitor = NetworkMonitor(this) {
            serviceScope.launch {
                Log.d(TAG, "Network regained, draining queue")
                val result = queueManager.drainQueue(networkMonitor)
                Log.d(TAG, "Queue drain result: success=${result.successCount}, fail=${result.failCount}")
            }
        }
        networkMonitor.start()
        
        telemetry = TelemetryCollector(this, powerMonitor, networkMonitor, queueManager)
        speedtestDetector = SpeedtestDetector(this)
        alarmManager = getSystemService(Context.ALARM_SERVICE) as AlarmManager
        
        acquireWakeLock()
        
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, createNotification())
        
        registerFcmToken()
        
        scheduleNextHeartbeat(5000)
        handler.postDelayed(watchdogRunnable, WATCHDOG_INTERVAL_MS)
        
        handler.postDelayed({
            serviceScope.launch {
                Log.d(TAG, "Startup queue drain after 5s delay")
                val result = queueManager.drainQueue(networkMonitor)
                Log.d(TAG, "Startup drain result: success=${result.successCount}, fail=${result.failCount}")
            }
        }, 5000)
    }
    
    private fun setupCrashRecovery() {
        val defaultHandler = Thread.getDefaultUncaughtExceptionHandler()
        
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            try {
                Log.e(TAG, "CRASH: Uncaught exception in thread ${thread.name}", throwable)
                
                val restartIntent = Intent(applicationContext, MonitorService::class.java)
                restartIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                
                val pendingIntent = PendingIntent.getService(
                    applicationContext,
                    0,
                    restartIntent,
                    PendingIntent.FLAG_ONE_SHOT or PendingIntent.FLAG_IMMUTABLE
                )
                
                val alarmMgr = applicationContext.getSystemService(Context.ALARM_SERVICE) as AlarmManager
                alarmMgr.set(
                    AlarmManager.RTC_WAKEUP,
                    System.currentTimeMillis() + 2000,
                    pendingIntent
                )
                
                Log.d(TAG, "Scheduled service restart in 2 seconds")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to schedule service restart", e)
            } finally {
                defaultHandler?.uncaughtException(thread, throwable)
            }
        }
    }
    
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action
        val trigger = intent?.getStringExtra("trigger")
        val requestId = intent?.getStringExtra("request_id")
        val immediateHeartbeat = intent?.getBooleanExtra("immediate_heartbeat", false) ?: false
        val appUpdated = intent?.getBooleanExtra("app_updated", false) ?: false
        
        Log.d(TAG, "onStartCommand: action=$action, trigger=$trigger, requestId=$requestId, immediate=$immediateHeartbeat, appUpdated=$appUpdated")
        
        checkAndReportPendingInstallation()
        
        when {
            action == "HEARTBEAT_ALARM" -> {
                sendHeartbeat()
                scheduleNextHeartbeat()
            }
            immediateHeartbeat -> {
                cancelScheduledHeartbeat()
                sendHeartbeat(isPingResponse = true, pingRequestId = requestId)
                scheduleNextHeartbeat()
            }
        }
        
        return START_STICKY
    }
    
    override fun onDestroy() {
        super.onDestroy()
        cancelScheduledHeartbeat()
        handler.removeCallbacks(watchdogRunnable)
        networkMonitor.stop()
        releaseWakeLock()
        serviceJob.cancel()
    }
    
    override fun onBind(intent: Intent?): IBinder? {
        return null
    }
    
    private fun sendHeartbeat(isPingResponse: Boolean = false, pingRequestId: String? = null) {
        if (prefs.serverUrl.isEmpty() || prefs.deviceToken.isEmpty()) {
            return
        }
        
        serviceScope.launch {
            try {
                val payload = buildHeartbeatPayload(isPingResponse, pingRequestId)
                val json = gson.toJson(payload)
                
                queueManager.enqueueHeartbeat(json)
                Log.d(TAG, "Heartbeat enqueued (ping=${isPingResponse})")
                
                val result = queueManager.drainQueue(networkMonitor)
                if (result.successCount > 0) {
                    prefs.lastHeartbeatTime = System.currentTimeMillis()
                    Log.d(TAG, "Heartbeat delivered successfully")
                } else {
                    Log.d(TAG, "Heartbeat queued for later delivery")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error sending heartbeat", e)
            }
        }
    }

    private fun <T> T.asMap(): Map<String, Any?> {
        val json = gson.toJson(this)
        return gson.fromJson(json, object : TypeToken<Map<String, Any?>>() {}.type)
    }

    private suspend fun buildHeartbeatPayload(isPingResponse: Boolean = false, pingRequestId: String? = null): HeartbeatPayload {
        val speedtestInfo = speedtestDetector.detectSpeedtest(prefs.speedtestPackage)
        val unityInfo = speedtestDetector.detectSpeedtest("com.unitynetwork.unityapp")
        val apkInstaller = ApkInstaller(applicationContext)
        val reliabilityFlags = telemetry.getReliabilityFlags()
        val queueDepth = telemetry.getQueueDepth()
        val monitoredForegroundRecency = telemetry.getMonitoredForegroundRecency(prefs.monitoredPackage)
        
        val appVersionsMap = mutableMapOf<String, AppVersion>()
        appVersionsMap[prefs.speedtestPackage] = AppVersion(
            installed = speedtestInfo.installed,
            version_name = speedtestInfo.versionName,
            version_code = speedtestInfo.versionCode?.toLong() ?: 0L
        )
        appVersionsMap["com.unitynetwork.unityapp"] = AppVersion(
            installed = unityInfo.installed,
            version_name = unityInfo.versionName,
            version_code = unityInfo.versionCode?.toLong() ?: 0L
        )
        
        return HeartbeatPayload(
            device_id = prefs.deviceId,
            alias = prefs.deviceAlias,
            app_version = BuildConfig.VERSION_NAME,
            timestamp_utc = java.time.Instant.now().toString(),
            app_versions = appVersionsMap,
            speedtest_running_signals = SpeedtestRunningSignals(
                has_service_notification = speedtestInfo.hasNotification,
                foreground_recent_seconds = speedtestInfo.lastForegroundSeconds ?: -1
            ),
            battery = telemetry.getBatteryInfo().asMap(),
            system = telemetry.getSystemInfo().asMap(),
            memory = telemetry.getMemoryInfo().asMap(),
            network = telemetry.getNetworkInfo().asMap(),
            fcm_token = prefs.fcmToken.ifEmpty { null },
            is_ping_response = if (isPingResponse) true else null,
            ping_request_id = pingRequestId,
            self_heal_hints = null,
            is_device_owner = apkInstaller.isDeviceOwner(),
            power_ok = reliabilityFlags.power_ok,
            doze_whitelisted = reliabilityFlags.doze_whitelisted,
            net_validated = reliabilityFlags.net_validated,
            queue_depth = queueDepth,
            monitored_foreground_recent_s = monitoredForegroundRecency
        )
    }
    
    private fun registerFcmToken() {
        FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
            if (task.isSuccessful) {
                val token = task.result
                Log.d(TAG, "FCM token retrieved: ${token?.take(10)}...")
                
                if (token != null && token != prefs.fcmToken) {
                    prefs.fcmToken = token
                    uploadFcmTokenToServer(token)
                }
            } else {
                Log.e(TAG, "Failed to retrieve FCM token", task.exception)
            }
        }
    }
    
    private fun uploadFcmTokenToServer(token: String) {
        if (prefs.serverUrl.isEmpty() || prefs.deviceToken.isEmpty()) {
            return
        }
        
        serviceScope.launch {
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
    
    private fun acquireWakeLock() {
        try {
            val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
            wakeLock = powerManager.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                "NexMDM::HeartbeatWakeLock"
            )
            wakeLock?.acquire()
            Log.d(TAG, "PARTIAL_WAKE_LOCK acquired")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to acquire wake lock", e)
        }
    }
    
    private fun releaseWakeLock() {
        try {
            wakeLock?.let {
                if (it.isHeld) {
                    it.release()
                    Log.d(TAG, "PARTIAL_WAKE_LOCK released")
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to release wake lock", e)
        }
    }
    
    private fun checkAndReportPendingInstallation() {
        val pendingId = prefs.pendingInstallationId
        Log.d(TAG, "checkAndReportPendingInstallation: pendingInstallationId=$pendingId")
        
        if (pendingId > 0) {
            Log.i(TAG, "Found pending installation $pendingId - reporting as completed")
            
            serviceScope.launch {
                try {
                    val payload = mapOf(
                        "installation_id" to pendingId,
                        "status" to "completed",
                        "download_progress" to 100
                    )
                    
                    val json = gson.toJson(payload)
                    Log.d(TAG, "Sending completion report: $json")
                    
                    val request = Request.Builder()
                        .url("${prefs.serverUrl}/v1/apk/installation/update")
                        .post(json.toRequestBody("application/json".toMediaType()))
                        .addHeader("X-Device-Token", prefs.deviceToken)
                        .build()
                    
                    val response = client.newCall(request).execute()
                    
                    if (response.isSuccessful) {
                        Log.i(TAG, "✓ Successfully reported installation $pendingId as completed")
                        prefs.pendingInstallationId = -1
                        Log.d(TAG, "Cleared pendingInstallationId")
                    } else {
                        Log.e(TAG, "✗ Failed to report installation completion: HTTP ${response.code}")
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "✗ Error reporting installation completion", e)
                }
            }
        } else {
            Log.d(TAG, "No pending installation to report (pendingId=$pendingId)")
        }
    }
    
    private fun scheduleNextHeartbeat(delayMs: Long = HEARTBEAT_INTERVAL_MS) {
        try {
            val intent = Intent(this, AlarmReceiver::class.java)
            val pendingIntent = PendingIntent.getBroadcast(
                this,
                0,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            
            val triggerTime = System.currentTimeMillis() + delayMs
            
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                alarmManager.setExactAndAllowWhileIdle(
                    AlarmManager.RTC_WAKEUP,
                    triggerTime,
                    pendingIntent
                )
            } else {
                alarmManager.setExact(
                    AlarmManager.RTC_WAKEUP,
                    triggerTime,
                    pendingIntent
                )
            }
            
            Log.d(TAG, "Next heartbeat scheduled in ${delayMs / 1000}s using AlarmManager")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to schedule heartbeat alarm", e)
        }
    }
    
    private fun cancelScheduledHeartbeat() {
        try {
            val intent = Intent(this, AlarmReceiver::class.java)
            val pendingIntent = PendingIntent.getBroadcast(
                this,
                0,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            alarmManager.cancel(pendingIntent)
            Log.d(TAG, "Scheduled heartbeat alarm cancelled")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to cancel heartbeat alarm", e)
        }
    }
    
    private fun checkAndRestartIfNeeded() {
        val lastHeartbeat = prefs.lastHeartbeatTime
        val now = System.currentTimeMillis()
        val timeSinceLastHeartbeat = now - lastHeartbeat
        
        if (lastHeartbeat > 0 && timeSinceLastHeartbeat > WATCHDOG_INTERVAL_MS) {
            Log.w(TAG, "Watchdog: No heartbeat for ${timeSinceLastHeartbeat / 1000}s, triggering immediate heartbeat")
            
            cancelScheduledHeartbeat()
            sendHeartbeat(isPingResponse = false, pingRequestId = null)
            scheduleNextHeartbeat()
        }
    }
    
    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Device Monitor",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Keeps device monitoring active with enhanced stability and reliability"
        }
        
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(channel)
    }
    
    private fun createNotification(): Notification {
        val versionName = BuildConfig.VERSION_NAME
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("NexMDM Monitoring")
            .setContentText("Device active • v$versionName")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }
}
