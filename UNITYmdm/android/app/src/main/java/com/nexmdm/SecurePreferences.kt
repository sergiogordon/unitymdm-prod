package com.nexmdm

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.util.UUID

class SecurePreferences(context: Context) {
    
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
            var id = prefs.getString("device_id", null)
            if (id == null) {
                id = UUID.randomUUID().toString()
                prefs.edit().putString("device_id", id).apply()
            }
            return id
        }
        set(value) = prefs.edit().putString("device_id", value).apply()
    
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
        get() = prefs.getString("speedtest_package", "org.zwanoo.android.speedtest") ?: "org.zwanoo.android.speedtest"
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
}
