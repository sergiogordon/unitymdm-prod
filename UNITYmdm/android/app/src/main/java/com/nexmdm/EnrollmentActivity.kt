package com.nexmdm

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.widget.Button
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.google.zxing.integration.android.IntentIntegrator
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class EnrollmentActivity : AppCompatActivity() {
    
    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            startQRScanner()
        } else {
            Toast.makeText(this, "Camera permission required for QR scanning", Toast.LENGTH_SHORT).show()
        }
    }
    
    private val fullScreenIntentSettingsLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { _ ->
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
            if (notificationManager.canUseFullScreenIntent()) {
                Toast.makeText(
                    this,
                    "Full-screen alerts enabled successfully!",
                    Toast.LENGTH_SHORT
                ).show()
            } else {
                Toast.makeText(
                    this,
                    "Warning: Ring alerts will require manual interaction",
                    Toast.LENGTH_LONG
                ).show()
            }
        }
        startMainActivity()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        val prefs = SecurePreferences(this)
        if (prefs.serverUrl.isNotEmpty() && prefs.deviceToken.isNotEmpty()) {
            startMainActivity()
            return
        }
        
        setContentView(R.layout.activity_enrollment)
        
        findViewById<Button>(R.id.btn_scan_qr).setOnClickListener {
            checkCameraPermissionAndScan()
        }
        
        findViewById<Button>(R.id.btn_manual_config).setOnClickListener {
            startMainActivity()
        }
    }

    private fun checkCameraPermissionAndScan() {
        when {
            ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.CAMERA
            ) == PackageManager.PERMISSION_GRANTED -> {
                startQRScanner()
            }
            else -> {
                requestPermissionLauncher.launch(Manifest.permission.CAMERA)
            }
        }
    }

    private fun startQRScanner() {
        IntentIntegrator(this).apply {
            setDesiredBarcodeFormats(IntentIntegrator.QR_CODE)
            setPrompt("Scan enrollment QR code from dashboard")
            setBeepEnabled(true)
            setBarcodeImageEnabled(false)
            setOrientationLocked(false)
            initiateScan()
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        val result = IntentIntegrator.parseActivityResult(requestCode, resultCode, data)
        if (result != null) {
            if (result.contents != null) {
                handleQRCodeResult(result.contents)
            } else {
                Toast.makeText(this, "Scan cancelled", Toast.LENGTH_SHORT).show()
            }
        } else {
            super.onActivityResult(requestCode, resultCode, data)
        }
    }

    private fun handleQRCodeResult(qrContent: String) {
        try {
            val json = JSONObject(qrContent)
            val serverUrl = json.getString("server_url")
            val adminKey = json.getString("admin_key")
            val alias = json.getString("alias")
            
            Toast.makeText(this, "Enrolling device: $alias", Toast.LENGTH_SHORT).show()
            
            enrollDevice(serverUrl, adminKey, alias)
            
        } catch (e: Exception) {
            Toast.makeText(this, "Invalid QR code: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    private fun enrollDevice(serverUrl: String, adminKey: String, alias: String) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val url = URL("$serverUrl/v1/register?alias=$alias")
                val connection = url.openConnection() as HttpURLConnection
                connection.requestMethod = "POST"
                connection.setRequestProperty("X-Admin", adminKey)
                connection.setRequestProperty("Content-Type", "application/json")
                connection.connectTimeout = 10000
                connection.readTimeout = 10000
                
                val responseCode = connection.responseCode
                if (responseCode == HttpURLConnection.HTTP_OK) {
                    val response = connection.inputStream.bufferedReader().readText()
                    val responseJson = JSONObject(response)
                    val deviceToken = responseJson.getString("device_token")
                    val deviceId = responseJson.getString("device_id")
                    
                    saveCredentials(serverUrl, deviceToken, deviceId, alias)
                    
                    withContext(Dispatchers.Main) {
                        Toast.makeText(
                            this@EnrollmentActivity,
                            "Device enrolled successfully!",
                            Toast.LENGTH_LONG
                        ).show()
                        
                        val serviceIntent = Intent(this@EnrollmentActivity, MonitorService::class.java)
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                            startForegroundService(serviceIntent)
                        } else {
                            startService(serviceIntent)
                        }
                        
                        checkAndPromptBatteryOptimization()
                    }
                } else {
                    val error = connection.errorStream?.bufferedReader()?.readText() ?: "Unknown error"
                    withContext(Dispatchers.Main) {
                        Toast.makeText(
                            this@EnrollmentActivity,
                            "Enrollment failed: $error",
                            Toast.LENGTH_LONG
                        ).show()
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(
                        this@EnrollmentActivity,
                        "Network error: ${e.message}",
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        }
    }

    private fun saveCredentials(serverUrl: String, deviceToken: String, deviceId: String, alias: String) {
        val prefs = SecurePreferences(this)
        prefs.serverUrl = serverUrl
        prefs.deviceToken = deviceToken
        prefs.deviceId = deviceId
        prefs.deviceAlias = alias
    }
    
    private fun checkAndPromptBatteryOptimization() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val permissionManager = DeviceOwnerPermissionManager(this)
            
            // If Device Owner, automatically disable Doze and Adaptive Battery
            if (permissionManager.isDeviceOwner()) {
                val result = permissionManager.disableAllPowerManagement()
                
                if (result.success) {
                    Toast.makeText(
                        this,
                        "Power management disabled - heartbeats guaranteed 24/7",
                        Toast.LENGTH_LONG
                    ).show()
                } else {
                    Toast.makeText(
                        this,
                        "Warning: ${result.message}",
                        Toast.LENGTH_LONG
                    ).show()
                }
                
                checkAndPromptFullScreenIntent()
            } else {
                // Not Device Owner - use legacy battery optimization prompt
                val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
                val packageName = packageName
                
                if (!powerManager.isIgnoringBatteryOptimizations(packageName)) {
                    AlertDialog.Builder(this)
                        .setTitle("Battery Optimization")
                        .setMessage("To ensure reliable device monitoring, NexMDM needs to run continuously even when the screen is off.\n\n" +
                                   "Please disable battery optimization for this app in the next screen.")
                        .setPositiveButton("Open Settings") { _, _ ->
                            try {
                                val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                                    data = Uri.parse("package:$packageName")
                                }
                                startActivity(intent)
                            } catch (e: Exception) {
                                val intent = Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)
                                startActivity(intent)
                            }
                            checkAndPromptFullScreenIntent()
                        }
                        .setNegativeButton("Skip") { _, _ ->
                            Toast.makeText(
                                this,
                                "Warning: Monitoring may stop when screen is off",
                                Toast.LENGTH_LONG
                            ).show()
                            checkAndPromptFullScreenIntent()
                        }
                        .setCancelable(false)
                        .show()
                } else {
                    checkAndPromptFullScreenIntent()
                }
            }
        } else {
            checkAndPromptFullScreenIntent()
        }
    }
    
    private fun checkAndPromptFullScreenIntent() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
            
            if (!notificationManager.canUseFullScreenIntent()) {
                AlertDialog.Builder(this)
                    .setTitle("Full-Screen Alerts")
                    .setMessage("NexMDM can send full-screen alerts to help locate your device remotely.\n\n" +
                               "This allows the device to ring loudly and flash even when locked or sleeping.\n\n" +
                               "Please enable 'Display over other apps' permission in the next screen.")
                    .setPositiveButton("Open Settings") { _, _ ->
                        try {
                            val intent = Intent(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT).apply {
                                data = Uri.parse("package:$packageName")
                            }
                            fullScreenIntentSettingsLauncher.launch(intent)
                        } catch (e: Exception) {
                            Toast.makeText(
                                this,
                                "Please enable full-screen intent in app settings",
                                Toast.LENGTH_LONG
                            ).show()
                            startMainActivity()
                        }
                    }
                    .setNegativeButton("Skip") { _, _ ->
                        Toast.makeText(
                            this,
                            "Warning: Ring alerts will require manual interaction",
                            Toast.LENGTH_LONG
                        ).show()
                        startMainActivity()
                    }
                    .setCancelable(false)
                    .show()
            } else {
                startMainActivity()
            }
        } else {
            startMainActivity()
        }
    }
    
    private fun startMainActivity() {
        startActivity(Intent(this, MainActivity::class.java))
        finish()
    }
}
