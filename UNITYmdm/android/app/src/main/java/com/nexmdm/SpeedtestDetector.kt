package com.nexmdm

import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.util.Log

class SpeedtestDetector(private val context: Context) {
    
    companion object {
        private const val TAG = "SpeedtestDetector"
    }
    
    data class SpeedtestInfo(
        val installed: Boolean,
        val versionName: String?,
        val versionCode: Int?,
        val hasNotification: Boolean,
        val lastForegroundSeconds: Int?
    )
    
    fun detectSpeedtest(packageName: String): SpeedtestInfo {
        val installed = isPackageInstalled(packageName)
        
        if (!installed) {
            Log.w(TAG, "Package $packageName NOT found by isPackageInstalled()")
            return SpeedtestInfo(false, null, null, false, null)
        }
        
        Log.i(TAG, "Package $packageName found successfully")
        val (versionName, versionCode) = getPackageVersion(packageName)
        val lastForegroundSeconds = getLastForegroundTime(packageName)
        val hasNotification = lastForegroundSeconds != null && lastForegroundSeconds < 300
        
        return SpeedtestInfo(
            installed = true,
            versionName = versionName,
            versionCode = versionCode,
            hasNotification = hasNotification,
            lastForegroundSeconds = lastForegroundSeconds
        )
    }
    
    private fun isPackageInstalled(packageName: String): Boolean {
        // Primary method: getPackageInfo
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                context.packageManager.getPackageInfo(packageName, PackageManager.PackageInfoFlags.of(0))
            } else {
                context.packageManager.getPackageInfo(packageName, 0)
            }
            
            Log.i(TAG, "Package $packageName found via getPackageInfo")
            return true
        } catch (e: PackageManager.NameNotFoundException) {
            Log.w(TAG, "Package $packageName not found via getPackageInfo: ${e.message}")
            // Continue to fallback method below
        } catch (e: Exception) {
            Log.e(TAG, "Error with getPackageInfo for $packageName: ${e.message}")
            // Continue to fallback method below
        }
        
        // Fallback method: Check installed applications list
        try {
            val installedApps = context.packageManager.getInstalledApplications(PackageManager.GET_META_DATA)
            val found = installedApps.any { it.packageName == packageName }
            if (found) {
                Log.i(TAG, "Package $packageName found via getInstalledApplications fallback")
            } else {
                Log.w(TAG, "Package $packageName NOT found in installed applications list")
            }
            return found
        } catch (e: Exception) {
            Log.e(TAG, "Error checking installed applications: ${e.message}")
            return false
        }
    }
    
    private fun getPackageVersion(packageName: String): Pair<String?, Int?> {
        return try {
            val packageInfo = context.packageManager.getPackageInfo(packageName, 0)
            Pair(packageInfo.versionName, packageInfo.longVersionCode.toInt())
        } catch (e: Exception) {
            Pair(null, null)
        }
    }
    
    private fun getLastForegroundTime(packageName: String): Int? {
        try {
            val usageStatsManager = context.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
            val endTime = System.currentTimeMillis()
            val startTime = endTime - 1000 * 60 * 60 * 24 // Check last 24 hours instead of 1 hour
            
            val usageStats = usageStatsManager.queryUsageStats(
                UsageStatsManager.INTERVAL_DAILY,
                startTime,
                endTime
            )
            
            // Check if we got any stats at all - if null or empty, permission likely denied
            if (usageStats == null || usageStats.isEmpty()) {
                Log.w(TAG, "UsageStats query returned null or empty - likely permission issue")
                return -1 // -1 indicates permission denied
            }
            
            val appStats = usageStats.find { it.packageName == packageName }
            
            return if (appStats != null && appStats.lastTimeUsed > 0) {
                val seconds = ((endTime - appStats.lastTimeUsed) / 1000).toInt()
                Log.i(TAG, "App last used $seconds seconds ago")
                seconds
            } else {
                Log.i(TAG, "No usage data for $packageName (app never run or data cleared)")
                null // null indicates app never run or no recent usage
            }
        } catch (e: SecurityException) {
            Log.e(TAG, "SecurityException accessing usage stats - permission denied: ${e.message}")
            return -1 // -1 indicates permission denied
        } catch (e: Exception) {
            Log.e(TAG, "Error getting foreground time: ${e.message}", e)
            return -1 // -1 indicates error
        }
    }
}
