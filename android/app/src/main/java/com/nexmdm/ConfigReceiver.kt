package com.nexmdm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

class ConfigReceiver : BroadcastReceiver() {
    
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == "com.nexmdm.CONFIGURE") {
            val serverUrl = intent.getStringExtra("server_url") ?: return
            val adminKey = intent.getStringExtra("admin_key") ?: return
            val alias = intent.getStringExtra("alias") ?: "Device"
            val hmacPrimaryKey = intent.getStringExtra("hmac_primary_key") ?: ""
            val hmacRotationKey = intent.getStringExtra("hmac_rotation_key") ?: ""
            
            val pendingResult = goAsync()
            
            CoroutineScope(Dispatchers.IO).launch {
                try {
                    val result = registerDevice(serverUrl, adminKey, alias)
                    
                    if (result != null) {
                        val prefs = SecurePreferences(context)
                        prefs.serverUrl = serverUrl
                        prefs.deviceToken = result.deviceToken
                        prefs.deviceId = result.deviceId
                        prefs.deviceAlias = alias
                        prefs.speedtestPackage = "com.unitynetwork.unityapp"
                        prefs.needsReEnrollment = false
                        prefs.consecutive401Count = 0
                        
                        if (hmacPrimaryKey.isNotEmpty()) {
                            prefs.hmacPrimaryKey = hmacPrimaryKey
                            Log.d("ConfigReceiver", "HMAC primary key configured")
                        }
                        if (hmacRotationKey.isNotEmpty()) {
                            prefs.hmacRotationKey = hmacRotationKey
                            Log.d("ConfigReceiver", "HMAC rotation key configured")
                        }
                        
                        // Apply battery optimization exemption for Unity app if Device Owner
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                            val permissionManager = DeviceOwnerPermissionManager(context)
                            if (permissionManager.isDeviceOwner()) {
                                val success = permissionManager.exemptPackageFromBatteryOptimization("com.unitynetwork.unityapp")
                                if (success) {
                                    Log.i("ConfigReceiver", "✓ Unity app exempted from battery optimization")
                                } else {
                                    Log.e("ConfigReceiver", "✗ Failed to exempt Unity app from battery optimization")
                                }
                            } else {
                                Log.d("ConfigReceiver", "Not Device Owner - skipping battery optimization exemption")
                            }
                        }
                        
                        val serviceIntent = Intent(context, MonitorService::class.java)
                        context.startForegroundService(serviceIntent)
                        
                        Log.d("ConfigReceiver", "Device registered and configured: $alias")
                    } else {
                        Log.e("ConfigReceiver", "Failed to register device")
                    }
                } catch (e: Exception) {
                    Log.e("ConfigReceiver", "Error during registration: ${e.message}", e)
                } finally {
                    pendingResult.finish()
                }
            }
        }
    }
    
    data class RegistrationResult(
        val deviceToken: String,
        val deviceId: String
    )
    
    private fun registerDevice(serverUrl: String, adminKey: String, alias: String): RegistrationResult? {
        return try {
            val client = OkHttpClient()
            
            val jsonBody = JSONObject()
            jsonBody.put("alias", alias)
            
            val request = Request.Builder()
                .url("$serverUrl/v1/register")
                .post(jsonBody.toString().toRequestBody("application/json".toMediaType()))
                .addHeader("X-Admin-Key", adminKey)
                .build()
            
            val response = client.newCall(request).execute()
            if (response.isSuccessful) {
                val responseBody = response.body?.string()
                val json = JSONObject(responseBody ?: "{}")
                val deviceToken = json.optString("device_token", null)
                val deviceId = json.optString("device_id", null)
                
                if (deviceToken != null && deviceId != null) {
                    Log.d("ConfigReceiver", "Registration successful: device_id=${deviceId.take(8)}...")
                    RegistrationResult(deviceToken, deviceId)
                } else {
                    Log.e("ConfigReceiver", "Registration response missing device_token or device_id")
                    null
                }
            } else {
                Log.e("ConfigReceiver", "Registration failed: ${response.code}")
                null
            }
        } catch (e: Exception) {
            Log.e("ConfigReceiver", "Network error during registration: ${e.message}", e)
            null
        }
    }
}
