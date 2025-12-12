package com.nexmdm

import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.pm.PackageInstaller
import android.net.Uri
import android.os.Build
import android.util.Log
import java.io.File
import java.io.FileInputStream
import java.io.IOException

class ApkInstaller(private val context: Context) {
    private val TAG = "NexMDM.ApkInstaller"
    private val devicePolicyManager = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
    private val adminComponent = ComponentName(context, NexDeviceAdminReceiver::class.java)

    fun isDeviceOwner(): Boolean {
        return devicePolicyManager.isDeviceOwnerApp(context.packageName)
    }

    fun installApkSilently(apkFile: File, callback: (Boolean, String?) -> Unit) {
        if (!isDeviceOwner()) {
            Log.e(TAG, "Not a device owner - cannot install silently")
            callback(false, "Device not enrolled as Device Owner")
            return
        }

        if (!apkFile.exists()) {
            Log.e(TAG, "APK file does not exist: ${apkFile.absolutePath}")
            callback(false, "APK file not found")
            return
        }

        try {
            installUsingPackageInstaller(apkFile, callback)
        } catch (e: Exception) {
            Log.e(TAG, "Installation failed", e)
            callback(false, "Installation error: ${e.message}")
        }
    }

    private fun installUsingPackageInstaller(apkFile: File, callback: (Boolean, String?) -> Unit) {
        try {
            val packageInstaller = context.packageManager.packageInstaller
            val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
            
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
            }

            val sessionId = packageInstaller.createSession(params)
            val session = packageInstaller.openSession(sessionId)

            session.openWrite("package", 0, -1).use { output ->
                FileInputStream(apkFile).use { input ->
                    input.copyTo(output)
                    session.fsync(output)
                }
            }

            val intent = android.content.Intent(context, ApkInstallReceiver::class.java).apply {
                action = "com.nexmdm.INSTALL_COMPLETE"
                putExtra("callback_id", System.currentTimeMillis())
            }
            
            val pendingIntent = android.app.PendingIntent.getBroadcast(
                context,
                sessionId,
                intent,
                android.app.PendingIntent.FLAG_UPDATE_CURRENT or android.app.PendingIntent.FLAG_MUTABLE
            )

            Log.d(TAG, "Registering callback for sessionId: $sessionId")
            ApkInstallReceiver.setCallback(sessionId) { success, error ->
                Log.d(TAG, "Callback invoked for sessionId: $sessionId - success: $success, error: $error")
                callback(success, error)
            }

            session.commit(pendingIntent.intentSender)
            Log.i(TAG, "APK installation session committed: $sessionId")
            session.close()
            Log.d(TAG, "Session closed for sessionId: $sessionId")
        } catch (e: IOException) {
            Log.e(TAG, "PackageInstaller session failed", e)
            callback(false, "Session error: ${e.message}")
        }
    }

    fun uninstallPackage(packageName: String, callback: (Boolean, String?) -> Unit) {
        if (!isDeviceOwner()) {
            Log.e(TAG, "Not a device owner - cannot uninstall silently")
            callback(false, "Device not enrolled as Device Owner")
            return
        }

        try {
            val packageInstaller = context.packageManager.packageInstaller
            val uninstallId = System.currentTimeMillis().toInt()
            
            val intent = android.content.Intent(context, ApkInstallReceiver::class.java).apply {
                action = "com.nexmdm.UNINSTALL_COMPLETE"
                putExtra("uninstall_id", uninstallId)
            }
            
            val pendingIntent = android.app.PendingIntent.getBroadcast(
                context,
                uninstallId,
                intent,
                android.app.PendingIntent.FLAG_UPDATE_CURRENT or android.app.PendingIntent.FLAG_MUTABLE
            )

            ApkInstallReceiver.setUninstallCallback(uninstallId, callback)
            packageInstaller.uninstall(packageName, pendingIntent.intentSender)
            Log.i(TAG, "Uninstall initiated for: $packageName")
        } catch (e: Exception) {
            Log.e(TAG, "Uninstall failed", e)
            callback(false, "Uninstall error: ${e.message}")
        }
    }
}
