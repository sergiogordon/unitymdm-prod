package com.nexmdm

import android.Manifest
import android.app.ActivityManager
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
    private val queueManager: QueueManager? = null
) {

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
    
    fun getMonitoredForegroundRecency(packageName: String): Int? {
        if (packageName.isEmpty()) {
            return null
        }
        
        try {
            val usageStatsManager = context.getSystemService(Context.USAGE_STATS_SERVICE) as? UsageStatsManager
                ?: return null
            
            val now = System.currentTimeMillis()
            val oneHourAgo = now - (60 * 60 * 1000)
            
            val stats = usageStatsManager.queryUsageStats(
                UsageStatsManager.INTERVAL_DAILY,
                oneHourAgo,
                now
            )
            
            if (stats.isNullOrEmpty()) {
                Log.w("TelemetryCollector", "UsageStats not available - PACKAGE_USAGE_STATS permission may not be granted")
                return null
            }
            
            val packageStats = stats.find { it.packageName == packageName }
            
            return if (packageStats != null && packageStats.lastTimeUsed > 0) {
                val secondsAgo = ((now - packageStats.lastTimeUsed) / 1000).toInt()
                Log.d("TelemetryCollector", "Package $packageName last used $secondsAgo seconds ago")
                secondsAgo
            } else {
                Log.d("TelemetryCollector", "Package $packageName not found in usage stats")
                null
            }
        } catch (e: SecurityException) {
            Log.e("TelemetryCollector", "SecurityException: PACKAGE_USAGE_STATS permission not granted", e)
            return null
        } catch (e: Exception) {
            Log.e("TelemetryCollector", "Error getting monitored foreground recency", e)
            return null
        }
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
