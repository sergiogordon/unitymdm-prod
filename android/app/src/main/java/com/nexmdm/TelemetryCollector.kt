package com.nexmdm

import android.Manifest
import android.app.ActivityManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.location.LocationManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import android.os.BatteryManager
import android.os.Build
import android.os.SystemClock
import android.telephony.TelephonyManager
import android.util.Log
import androidx.core.content.ContextCompat
import java.net.NetworkInterface

class TelemetryCollector(
    private val context: Context,
    private val powerMonitor: PowerManagementMonitor? = null,
    private val networkMonitor: NetworkMonitor? = null,
    private val queueManager: QueueManager? = null,
    private val securePrefs: SecurePreferences? = null
) {
    companion object {
        private const val MAX_RECENCY_SECONDS = 86400
    }

    fun getBatteryInfo(): BatteryInfo {
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

        val temp = batteryStatus?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0) ?: 0
        val tempC = temp / 10.0f

        return BatteryInfo(
            pct = pct,
            charging = charging,
            temperature_c = tempC
        )
    }

    fun getSystemInfo(): SystemInfo {
        val uptimeSeconds = SystemClock.elapsedRealtime() / 1000

        return SystemInfo(
            uptime_seconds = uptimeSeconds,
            android_version = Build.VERSION.RELEASE,
            sdk_int = Build.VERSION.SDK_INT,
            patch_level = Build.VERSION.SECURITY_PATCH,
            build_id = Build.ID,
            model = Build.MODEL,
            manufacturer = Build.MANUFACTURER
        )
    }

    fun getMemoryInfo(): MemoryInfo {
        val activityManager = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val memInfo = ActivityManager.MemoryInfo()
        activityManager.getMemoryInfo(memInfo)

        val totalMb = (memInfo.totalMem / 1024 / 1024).toInt()
        val availMb = (memInfo.availMem / 1024 / 1024).toInt()
        val pressurePct = if (totalMb > 0) ((totalMb - availMb) * 100 / totalMb) else 0

        return MemoryInfo(
            total_ram_mb = totalMb,
            avail_ram_mb = availMb,
            pressure_pct = pressurePct
        )
    }

    fun getNetworkInfo(): NetworkInfo {
        val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = connectivityManager.activeNetwork
        val capabilities = connectivityManager.getNetworkCapabilities(network)

        val transport = when {
            capabilities?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true -> "wifi"
            capabilities?.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) == true -> "cell"
            else -> "none"
        }

        val ssid = if (transport == "wifi") getWifiSsid() else null
        val carrier = if (transport == "cell") getCarrierName() else null
        val ip = getIpAddress()

        return NetworkInfo(
            transport = transport,
            ssid = ssid,
            carrier = carrier,
            ip = ip
        )
    }
    
    fun getReliabilityFlags(): ReliabilityFlags {
        val powerOk = powerMonitor?.isPowerOk() ?: true
        val dozeWhitelisted = powerMonitor?.isDozeWhitelisted() ?: false
        val netValidated = networkMonitor?.isNetworkValidated() ?: false
        
        return ReliabilityFlags(
            power_ok = powerOk,
            doze_whitelisted = dozeWhitelisted,
            net_validated = netValidated
        )
    }
    
    suspend fun getQueueDepth(): Int {
        return queueManager?.getQueueDepth() ?: 0
    }
    
    /**
     * Get how recently the monitored app was in the foreground using UsageEvents API.
     * This provides real-time foreground detection, unlike queryUsageStats which only
     * updates after a session ends.
     * 
     * Returns:
     * - 0 if the app is currently in foreground (last event was ACTIVITY_RESUMED)
     * - Seconds since last foreground if app is in background
     * - null if no data available or permission not granted
     */
    fun getMonitoredForegroundRecency(packageName: String): Int? {
        if (packageName.isEmpty()) {
            return null
        }
        
        try {
            val usageStatsManager = context.getSystemService(Context.USAGE_STATS_SERVICE) as? UsageStatsManager
                ?: run {
                    Log.w("TelemetryCollector", "UsageStatsManager not available")
                    return null
                }
            
            val now = System.currentTimeMillis()
            // Query last 24 hours to handle long-running foreground sessions
            // Unity/kiosk apps may stay in foreground for hours without new events
            val twentyFourHoursAgo = now - (24 * 60 * 60 * 1000)
            
            // Use queryEvents for real-time event data instead of aggregated stats
            val usageEvents = usageStatsManager.queryEvents(twentyFourHoursAgo, now)
            
            if (usageEvents == null) {
                Log.w("TelemetryCollector", "UsageEvents query returned null - permission may not be granted")
                return null
            }
            
            // Track active (resumed) activities by class name to handle multi-activity apps correctly
            // Key: activity class name, Value: true if currently resumed
            val activeActivities = mutableSetOf<String>()
            var lastBackgroundTime: Long = 0  // When ALL activities went to background
            var lastForegroundTime: Long = 0  // When ANY activity came to foreground
            var eventCount = 0
            
            val event = UsageEvents.Event()
            while (usageEvents.hasNextEvent()) {
                usageEvents.getNextEvent(event)
                
                if (event.packageName == packageName) {
                    eventCount++
                    val activityClass = event.className ?: "unknown"
                    
                    when (event.eventType) {
                        UsageEvents.Event.ACTIVITY_RESUMED -> {
                            // Activity moved to foreground
                            activeActivities.add(activityClass)
                            lastForegroundTime = event.timeStamp
                        }
                        UsageEvents.Event.ACTIVITY_PAUSED,
                        UsageEvents.Event.ACTIVITY_STOPPED -> {
                            // Activity moved to background/stopped
                            activeActivities.remove(activityClass)
                            // Only update background time if NO activities are now active
                            if (activeActivities.isEmpty()) {
                                lastBackgroundTime = event.timeStamp
                            }
                        }
                    }
                }
            }
            
            // If no events found for this package, fall back to aggregated stats
            if (eventCount == 0) {
                Log.d("TelemetryCollector", "No events found for $packageName in last 24 hours, trying aggregated stats")
                return getMonitoredForegroundRecencyFallback(packageName)
            }
            
            // Determine current state based on whether any activities are still active
            val result = when {
                // App has at least one activity in foreground
                activeActivities.isNotEmpty() -> {
                    Log.d("TelemetryCollector", "Package $packageName is CURRENTLY IN FOREGROUND (0s) - ${activeActivities.size} active activities: $activeActivities")
                    // Persist foreground state for long-running sessions
                    securePrefs?.lastKnownForegroundState = true
                    securePrefs?.lastForegroundStateTimestamp = now
                    0
                }
                // All activities are in background - calculate how long ago
                lastBackgroundTime > 0 -> {
                    val secondsAgo = ((now - lastBackgroundTime) / 1000).toInt()
                    Log.d("TelemetryCollector", "Package $packageName went to background $secondsAgo seconds ago")
                    // Persist background state
                    securePrefs?.lastKnownForegroundState = false
                    securePrefs?.lastForegroundStateTimestamp = lastBackgroundTime
                    clampRecency(secondsAgo)
                }
                // Had events but couldn't determine state clearly - use last foreground time
                lastForegroundTime > 0 -> {
                    val secondsAgo = ((now - lastForegroundTime) / 1000).toInt()
                    Log.d("TelemetryCollector", "Package $packageName last in foreground $secondsAgo seconds ago")
                    clampRecency(secondsAgo)
                }
                else -> {
                    Log.d("TelemetryCollector", "Package $packageName had $eventCount events but no clear foreground state")
                    null
                }
            }
            return result
        } catch (e: SecurityException) {
            Log.e("TelemetryCollector", "SecurityException: PACKAGE_USAGE_STATS permission not granted", e)
            return null
        } catch (e: Exception) {
            Log.e("TelemetryCollector", "Error getting monitored foreground recency via events", e)
            return null
        }
    }
    
    /**
     * Clamp recency value to backend's max (86400 seconds = 24 hours).
     * Values above this will cause heartbeat 422 rejections.
     */
    private fun clampRecency(value: Int): Int = value.coerceIn(0, MAX_RECENCY_SECONDS)
    
    /**
     * Fallback when no recent UsageEvents are available.
     * Uses persisted foreground state from previous observations, or returns null
     * to trigger backend's process-running fallback.
     */
    private fun getMonitoredForegroundRecencyFallback(packageName: String): Int? {
        // Check persisted state first - handles long-running sessions (>24 hours)
        val lastState = securePrefs?.lastKnownForegroundState
        val lastTimestamp = securePrefs?.lastForegroundStateTimestamp ?: 0
        
        if (lastTimestamp > 0 && lastState != null) {
            val now = System.currentTimeMillis()
            // Only trust persisted state if it's recent (within 7 days)
            val sevenDaysMs = 7 * 24 * 60 * 60 * 1000L
            if (now - lastTimestamp < sevenDaysMs) {
                return if (lastState) {
                    // Last known state was foreground - return 0
                    Log.d("TelemetryCollector", "Fallback: Using persisted FOREGROUND state for $packageName (0s)")
                    0
                } else {
                    // Last known state was background - calculate seconds ago and clamp to max
                    val secondsAgo = ((now - lastTimestamp) / 1000).toInt()
                    val clamped = clampRecency(secondsAgo)
                    Log.d("TelemetryCollector", "Fallback: Using persisted BACKGROUND state for $packageName ($clamped seconds ago, raw=$secondsAgo)")
                    clamped
                }
            }
        }
        
        // No valid persisted state - return null to trigger backend's process-running fallback
        Log.d("TelemetryCollector", "Fallback: No persisted state for $packageName, returning null to trigger process-running fallback")
        return null
    }
    
    fun isProcessRunning(packageName: String): Boolean? {
        if (packageName.isEmpty()) {
            return false
        }
        
        // ActivityManager.getRunningAppProcesses() only returns caller's own processes on Android 5.1+ (API 22+)
        // Use shell command 'ps' or 'pidof' instead, which works with device owner privileges
        var pidofProcess: Process? = null
        var psProcess: Process? = null
        
        try {
            // Try 'pidof' first (simpler and faster if available)
            // Escape packageName to prevent command injection
            // Replace single quotes with: end quote, escaped quote, start quote ('\'' in shell)
            val escapedPackageName = packageName.replace("'", "'\\''")
            val pidofCommand = arrayOf("sh", "-c", "pidof '$escapedPackageName'")
            pidofProcess = Runtime.getRuntime().exec(pidofCommand)
            
            val pidofReader = pidofProcess.inputStream.bufferedReader()
            val pidofErrorReader = pidofProcess.errorStream.bufferedReader()
            val pidofOutput = try {
                pidofReader.readText().trim()
            } finally {
                pidofReader.close()
            }
            // Drain error stream to prevent deadlock
            try {
                pidofErrorReader.readText() // Consume but ignore stderr
            } finally {
                pidofErrorReader.close()
            }
            
            val pidofExitCode = pidofProcess.waitFor()
            pidofProcess.destroy()
            
            if (pidofExitCode == 0 && pidofOutput.isNotEmpty()) {
                Log.d("TelemetryCollector", "Package $packageName process running (pidof): PID=$pidofOutput")
                return true
            }
            
            // Fallback to 'ps | grep' if pidof doesn't work or returns empty
            // Escape packageName to prevent command injection (already escaped above)
            val psCommand = arrayOf("sh", "-c", "ps -A | grep '$escapedPackageName' | grep -v grep")
            psProcess = Runtime.getRuntime().exec(psCommand)
            
            val psReader = psProcess.inputStream.bufferedReader()
            val psErrorReader = psProcess.errorStream.bufferedReader()
            val psOutput = try {
                psReader.readText().trim()
            } finally {
                psReader.close()
            }
            // Drain error stream to prevent deadlock
            try {
                psErrorReader.readText() // Consume but ignore stderr
            } finally {
                psErrorReader.close()
            }
            
            val psExitCode = psProcess.waitFor()
            psProcess.destroy()
            
            // Exit code 0 means grep found a match, non-zero means no match
            val isRunning = psExitCode == 0 && psOutput.isNotEmpty()
            
            if (isRunning) {
                Log.d("TelemetryCollector", "Package $packageName process running (ps): $psOutput")
            } else {
                Log.d("TelemetryCollector", "Package $packageName process not running")
            }
            
            return isRunning
        } catch (e: SecurityException) {
            Log.e("TelemetryCollector", "SecurityException checking process status", e)
            // Return null on errors so server can fall back to foreground data
            return null
        } catch (e: Exception) {
            Log.e("TelemetryCollector", "Error checking if process is running", e)
            // Return null on errors so server can fall back to foreground data
            return null
        } finally {
            // Ensure processes are destroyed even if exception occurs
            pidofProcess?.destroy()
            psProcess?.destroy()
        }
    }

    private fun getWifiSsid(): String? {
        try {
            // Check if location permission is granted (required for SSID on Android 10+)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val hasLocationPermission = PackageManager.PERMISSION_GRANTED ==
                    ContextCompat.checkSelfPermission(
                        context,
                        Manifest.permission.ACCESS_FINE_LOCATION
                    )
                
                if (!hasLocationPermission) {
                    Log.d("TelemetryCollector", "Location permission not granted, cannot retrieve SSID")
                    return null
                }
                
                // Check if location services are enabled (required for SSID on Android 10+)
                val locationManager = context.getSystemService(Context.LOCATION_SERVICE) as? LocationManager
                if (locationManager == null) {
                    Log.d("TelemetryCollector", "LocationManager service unavailable, cannot retrieve SSID")
                    return null
                }
                
                val locationEnabled = locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER) ||
                    locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)
                
                if (!locationEnabled) {
                    Log.d("TelemetryCollector", "Location services disabled, cannot retrieve SSID")
                    return null
                }
            }
            
            val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            val wifiInfo = wifiManager.connectionInfo
            val ssid = wifiInfo.ssid?.trim('"')
            return if (ssid == "<unknown ssid>" || ssid.isNullOrBlank()) null else ssid
        } catch (e: SecurityException) {
            Log.d("TelemetryCollector", "SecurityException retrieving SSID: ${e.message}")
            return null
        } catch (e: Exception) {
            Log.e("TelemetryCollector", "Error retrieving SSID", e)
            return null
        }
    }

    private fun getCarrierName(): String? {
        val telephonyManager = context.getSystemService(Context.TELEPHONY_SERVICE) as TelephonyManager
        val carrierName = telephonyManager.networkOperatorName
        // Return null for empty strings to ensure consistent null handling
        return if (carrierName.isNullOrBlank()) null else carrierName
    }

    private fun getIpAddress(): String? {
        try {
            val interfaces = NetworkInterface.getNetworkInterfaces()
            while (interfaces.hasMoreElements()) {
                val intf = interfaces.nextElement()
                val addrs = intf.inetAddresses
                while (addrs.hasMoreElements()) {
                    val addr = addrs.nextElement()
                    if (!addr.isLoopbackAddress && addr.address.size == 4) {
                        return addr.hostAddress
                    }
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
        return null
    }
}

data class BatteryInfo(
    val pct: Int,
    val charging: Boolean,
    val temperature_c: Float
)

data class SystemInfo(
    val uptime_seconds: Long,
    val android_version: String,
    val sdk_int: Int,
    val patch_level: String,
    val build_id: String,
    val model: String,
    val manufacturer: String
)

data class MemoryInfo(
    val total_ram_mb: Int,
    val avail_ram_mb: Int,
    val pressure_pct: Int
)

data class NetworkInfo(
    val transport: String,
    val ssid: String?,
    val carrier: String?,
    val ip: String?
)

data class ReliabilityFlags(
    val power_ok: Boolean,
    val doze_whitelisted: Boolean,
    val net_validated: Boolean
)
