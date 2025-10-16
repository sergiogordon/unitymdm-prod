package com.nexmdm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
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
            val adminKey = intent.getStringExtra("token") ?: return
            val alias = intent.getStringExtra("alias") ?: "Device"
            val speedtestPackage = intent.getStringExtra("speedtest_package") ?: "org.zwanoo.android.speedtest"
            
            val pendingResult = goAsync()
            
            CoroutineScope(Dispatchers.IO).launch {
                try {
                    val deviceToken = registerDevice(serverUrl, adminKey, alias)
                    
                    if (deviceToken != null) {
                        val prefs = SecurePreferences(context)
                        prefs.serverUrl = serverUrl
                        prefs.deviceToken = deviceToken
                        prefs.deviceAlias = alias
                        prefs.speedtestPackage = speedtestPackage
                        
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
    
    private fun registerDevice(serverUrl: String, adminKey: String, alias: String): String? {
        return try {
            val client = OkHttpClient()
            val request = Request.Builder()
                .url("$serverUrl/v1/register?alias=$alias")
                .post("".toRequestBody("application/json".toMediaType()))
                .addHeader("X-Admin", adminKey)
                .build()
            
            val response = client.newCall(request).execute()
            if (response.isSuccessful) {
                val responseBody = response.body?.string()
                val json = JSONObject(responseBody ?: "{}")
                json.optString("device_token", null)
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
