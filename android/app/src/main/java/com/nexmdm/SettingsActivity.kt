package com.nexmdm

import android.app.admin.DevicePolicyManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity

class SettingsActivity : AppCompatActivity() {

    private lateinit var permissionManager: DeviceOwnerPermissionManager
    private lateinit var tvDeviceOwnerStatus: TextView
    private lateinit var tvPermissionsStatus: TextView
    private lateinit var btnRemoveDeviceOwner: Button
    private lateinit var btnEnableInstallApps: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        permissionManager = DeviceOwnerPermissionManager(this)

        tvDeviceOwnerStatus = findViewById(R.id.tvDeviceOwnerStatus)
        tvPermissionsStatus = findViewById(R.id.tvPermissionsStatus)
        btnRemoveDeviceOwner = findViewById(R.id.btnRemoveDeviceOwner)
        btnEnableInstallApps = findViewById(R.id.btnEnableInstallApps)
        val btnBack = findViewById<Button>(R.id.btnBack)

        updateStatus()

        btnRemoveDeviceOwner.setOnClickListener {
            showRemoveDeviceOwnerConfirmation()
        }

        btnEnableInstallApps.setOnClickListener {
            enableInstallUnknownApps()
        }

        btnBack.setOnClickListener {
            finish()
        }
    }

    private fun updateStatus() {
        val isDeviceOwner = permissionManager.isDeviceOwner()
        
        tvDeviceOwnerStatus.text = if (isDeviceOwner) {
            "Status: Device Owner (Active)"
        } else {
            "Status: Not Device Owner"
        }

        btnRemoveDeviceOwner.isEnabled = isDeviceOwner

        val hasInstallPermission = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            packageManager.canRequestPackageInstalls()
        } else {
            true
        }

        tvPermissionsStatus.text = "Install Unknown Apps: ${if (hasInstallPermission) "Granted ✓" else "Not granted"}"
        btnEnableInstallApps.isEnabled = isDeviceOwner && !hasInstallPermission
    }

    private fun showRemoveDeviceOwnerConfirmation() {
        AlertDialog.Builder(this)
            .setTitle("Remove Device Owner?")
            .setMessage(
                "This will remove Device Owner status from NexMDM.\n\n" +
                "After removal:\n" +
                "• You can uninstall the app normally\n" +
                "• Remote control features will be disabled\n" +
                "• Silent app installation will be disabled\n\n" +
                "Continue?"
            )
            .setPositiveButton("Remove") { _, _ ->
                removeDeviceOwner()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun removeDeviceOwner() {
        val success = permissionManager.removeDeviceOwner()
        
        if (success) {
            Toast.makeText(
                this,
                "Device Owner removed successfully. You can now uninstall the app.",
                Toast.LENGTH_LONG
            ).show()
            updateStatus()
        } else {
            Toast.makeText(
                this,
                "Failed to remove Device Owner. Please try via ADB or contact support.",
                Toast.LENGTH_LONG
            ).show()
        }
    }

    private fun enableInstallUnknownApps() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
            Toast.makeText(this, "Not supported on this Android version", Toast.LENGTH_SHORT).show()
            return
        }

        val success = permissionManager.enableInstallUnknownApps()
        
        if (success) {
            Toast.makeText(
                this,
                "Install Unknown Apps permission granted successfully",
                Toast.LENGTH_SHORT
            ).show()
            updateStatus()
        } else {
            Toast.makeText(
                this,
                "Failed to grant permission. Ensure you are Device Owner.",
                Toast.LENGTH_LONG
            ).show()
        }
    }
}
