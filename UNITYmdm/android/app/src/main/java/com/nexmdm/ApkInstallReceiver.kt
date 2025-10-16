package com.nexmdm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.util.Log

class ApkInstallReceiver : BroadcastReceiver() {
    private val TAG = "NexMDM.ApkInstallReceiver"

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
        when (intent.action) {
            "com.nexmdm.INSTALL_COMPLETE" -> {
                val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
                val sessionId = intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -1)
                val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)

                when (status) {
                    PackageInstaller.STATUS_SUCCESS -> {
                        Log.i(TAG, "Installation successful")
                        callbacks[sessionId]?.invoke(true, null)
                        callbacks.remove(sessionId)
                    }
                    PackageInstaller.STATUS_FAILURE,
                    PackageInstaller.STATUS_FAILURE_ABORTED,
                    PackageInstaller.STATUS_FAILURE_BLOCKED,
                    PackageInstaller.STATUS_FAILURE_CONFLICT,
                    PackageInstaller.STATUS_FAILURE_INCOMPATIBLE,
                    PackageInstaller.STATUS_FAILURE_INVALID,
                    PackageInstaller.STATUS_FAILURE_STORAGE -> {
                        Log.e(TAG, "Installation failed: $message")
                        callbacks[sessionId]?.invoke(false, message ?: "Installation failed")
                        callbacks.remove(sessionId)
                    }
                    PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                        Log.w(TAG, "Installation requires user action")
                        val confirmIntent = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)
                        if (confirmIntent != null) {
                            confirmIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            context.startActivity(confirmIntent)
                        }
                    }
                    else -> {
                        Log.w(TAG, "Unknown installation status: $status")
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
}
