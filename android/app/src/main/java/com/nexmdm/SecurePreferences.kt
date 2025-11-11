package com.nexmdm

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

class SecurePreferences(context: Context) {
    
    companion object {
        private const val TAG = "SecurePreferences"
    }
    
    private val masterKey = MasterKey.Builder(context)
        .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
        .build()
    
    private val prefs: SharedPreferences = EncryptedSharedPreferences.create(
        context,
        "secure_prefs",
        masterKey,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )
    
    var deviceId: String
        get() {
            val id = prefs.getString("device_id", "") ?: ""
            Log.d(TAG, "deviceId.get: ${if (id.isEmpty()) "EMPTY" else "${id.take(8)}..."}")
            return id
        }
        set(value) {
            Log.d(TAG, "deviceId.set: ${if (value.isEmpty()) "EMPTY" else "${value.take(8)}..."}")
            prefs.edit().putString("device_id", value).commit()
        }
    
    var serverUrl: String
        get() = prefs.getString("server_url", "") ?: ""
        set(value) = prefs.edit().putString("server_url", value).apply()
    
    var deviceToken: String
        get() = prefs.getString("device_token", "") ?: ""
        set(value) = prefs.edit().putString("device_token", value).apply()
    
    var deviceAlias: String
        get() = prefs.getString("device_alias", "Unknown") ?: "Unknown"
        set(value) = prefs.edit().putString("device_alias", value).apply()
    
    var speedtestPackage: String
        get() = prefs.getString("speedtest_package", "com.unitynetwork.unityapp") ?: "com.unitynetwork.unityapp"
        set(value) = prefs.edit().putString("speedtest_package", value).apply()
    
    var lastHeartbeatTime: Long
        get() = prefs.getLong("last_heartbeat", 0)
        set(value) = prefs.edit().putLong("last_heartbeat", value).apply()
    
    var fcmToken: String
        get() = prefs.getString("fcm_token", "") ?: ""
        set(value) = prefs.edit().putString("fcm_token", value).apply()
    
    var pendingInstallationId: Int
        get() = prefs.getInt("pending_installation_id", -1)
        set(value) = prefs.edit().putInt("pending_installation_id", value).apply()
    
    var hmacPrimaryKey: String
        get() = prefs.getString("hmac_primary_key", "") ?: ""
        set(value) = prefs.edit().putString("hmac_primary_key", value).apply()
    
    var hmacRotationKey: String
        get() = prefs.getString("hmac_rotation_key", "") ?: ""
        set(value) = prefs.edit().putString("hmac_rotation_key", value).apply()
    
    var monitoredPackage: String
        get() = prefs.getString("monitored_package", "com.unitynetwork.unityapp") ?: "com.unitynetwork.unityapp"
        set(value) = prefs.edit().putString("monitored_package", value).apply()
    
    fun clearAllCredentials() {
        Log.d(TAG, "clearAllCredentials: clearing all stored data")
        prefs.edit().clear().commit()
    }
}
