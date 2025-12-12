package com.nexmdm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import com.google.gson.Gson
import java.util.concurrent.TimeUnit

class ApkInstallReceiver : BroadcastReceiver() {
    private val TAG = "NexMDM.ApkInstallReceiver"
    
    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()
    
    private val gson = Gson()

    companion object {
        private val callbacks = mutableMapOf<Int, (Boolean, String?) -> Unit>()
        private val uninstallCallbacks = mutableMapOf<Int, (Boolean, String?) -> Unit>()

        fun setCallback(sessionId: Int, callback: (Boolean, String?) -> Unit) {
            callbacks[sessionId] = callback
        }

        fun removeCallback(sessionId: Int) {
            callbacks.remove(sessionId)
        }

        fun setUninstallCallback(uninstallId: Int, callback: (Boolean, String?) -> Unit) {
            uninstallCallbacks[uninstallId] = callback
        }

        fun removeUninstallCallback(uninstallId: Int) {
            uninstallCallbacks.remove(uninstallId)
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        Log.d(TAG, "onReceive called - action: ${intent.action}, extras: ${intent.extras?.keySet()?.joinToString()}")
        
        when (intent.action) {
            "com.nexmdm.INSTALL_COMPLETE" -> {
                val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
                val sessionId = intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -1)
                val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)
                
                Log.d(TAG, "INSTALL_COMPLETE received - status: $status, sessionId: $sessionId, message: $message")
                Log.d(TAG, "Registered callbacks: ${callbacks.keys.joinToString()}")
                
                val callback = callbacks[sessionId]
                if (callback == null) {
                    Log.w(TAG, "No callback found for sessionId: $sessionId - callbacks may have been lost or sessionId mismatch")
                }

                when (status) {
                    PackageInstaller.STATUS_SUCCESS -> {
                        Log.i(TAG, "Installation successful for sessionId: $sessionId")
                        if (callback != null) {
                            Log.d(TAG, "Invoking success callback for sessionId: $sessionId")
                            callback.invoke(true, null)
                            callbacks.remove(sessionId)
                        } else {
                            Log.w(TAG, "SUCCESS received but no callback registered for sessionId: $sessionId - using fallback")
                            reportInstallStatusFallback(context, "completed", null)
                        }
                    }
                    PackageInstaller.STATUS_FAILURE,
                    PackageInstaller.STATUS_FAILURE_ABORTED,
                    PackageInstaller.STATUS_FAILURE_BLOCKED,
                    PackageInstaller.STATUS_FAILURE_CONFLICT,
                    PackageInstaller.STATUS_FAILURE_INCOMPATIBLE,
                    PackageInstaller.STATUS_FAILURE_INVALID,
                    PackageInstaller.STATUS_FAILURE_STORAGE -> {
                        Log.e(TAG, "Installation failed for sessionId: $sessionId - $message")
                        if (callback != null) {
                            Log.d(TAG, "Invoking failure callback for sessionId: $sessionId")
                            callback.invoke(false, message ?: "Installation failed")
                            callbacks.remove(sessionId)
                        } else {
                            Log.w(TAG, "FAILURE received but no callback registered for sessionId: $sessionId - using fallback")
                            reportInstallStatusFallback(context, "failed", message ?: "Installation failed")
                        }
                    }
                    PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                        Log.w(TAG, "Installation requires user action for sessionId: $sessionId")
                        val confirmIntent = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)
                        if (confirmIntent != null) {
                            confirmIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            context.startActivity(confirmIntent)
                        }
                    }
                    else -> {
                        Log.w(TAG, "Unknown installation status: $status for sessionId: $sessionId")
                    }
                }
            }
            "com.nexmdm.UNINSTALL_COMPLETE" -> {
                val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
                val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)
                val uninstallId = intent.getIntExtra("uninstall_id", -1)

                when (status) {
                    PackageInstaller.STATUS_SUCCESS -> {
                        Log.i(TAG, "Uninstallation successful")
                        uninstallCallbacks[uninstallId]?.invoke(true, null)
                        uninstallCallbacks.remove(uninstallId)
                    }
                    else -> {
                        Log.e(TAG, "Uninstallation failed: $message")
                        uninstallCallbacks[uninstallId]?.invoke(false, message ?: "Uninstallation failed")
                        uninstallCallbacks.remove(uninstallId)
                    }
                }
            }
        }
    }
    
    private fun reportInstallStatusFallback(context: Context, status: String, errorMessage: String?) {
        val prefs = SecurePreferences(context)
        val installationId = prefs.pendingInstallationId
        
        if (installationId <= 0) {
            Log.w(TAG, "No pending installation ID found in preferences, cannot report status via fallback")
            return
        }
        
        if (prefs.serverUrl.isEmpty() || prefs.deviceToken.isEmpty()) {
            Log.w(TAG, "Server URL or device token not configured, skipping fallback status report")
            return
        }
        
        Log.i(TAG, "Fallback: Reporting installation status directly - installationId: $installationId, status: $status")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val payload = mutableMapOf<String, Any>(
                    "installation_id" to installationId,
                    "status" to status,
                    "download_progress" to 100
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
                    Log.i(TAG, "Fallback: Installation status reported successfully: $status")
                    prefs.pendingInstallationId = -1
                } else {
                    Log.e(TAG, "Fallback: Failed to report installation status: ${response.code}")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Fallback: Error reporting installation status", e)
            }
        }
    }
}
