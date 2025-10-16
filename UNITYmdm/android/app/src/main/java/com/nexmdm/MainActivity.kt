package com.nexmdm

import android.Manifest
import android.app.AppOpsManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

class MainActivity : AppCompatActivity() {
    
    private lateinit var prefs: SecurePreferences
    
    private val requestLocationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            Toast.makeText(this, "Location permission granted for WiFi SSID access", Toast.LENGTH_SHORT).show()
        } else {
            Toast.makeText(this, "WiFi SSID will show as 'unknown' without location permission", Toast.LENGTH_LONG).show()
        }
    }
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        
        prefs = SecurePreferences(this)
        
        val etServerUrl = findViewById<EditText>(R.id.etServerUrl)
        val etToken = findViewById<EditText>(R.id.etToken)
        val etAlias = findViewById<EditText>(R.id.etAlias)
        val etSpeedtestPackage = findViewById<EditText>(R.id.etSpeedtestPackage)
        val btnSave = findViewById<Button>(R.id.btnSave)
        val btnPermissions = findViewById<Button>(R.id.btnPermissions)
        val btnSettings = findViewById<Button>(R.id.btnSettings)
        val tvStatus = findViewById<TextView>(R.id.tvStatus)
        
        etServerUrl.setText(prefs.serverUrl)
        etToken.setText(prefs.deviceToken)
        etAlias.setText(prefs.deviceAlias)
        etSpeedtestPackage.setText(prefs.speedtestPackage)
        
        btnSave.setOnClickListener {
            prefs.serverUrl = etServerUrl.text.toString()
            prefs.deviceToken = etToken.text.toString()
            prefs.deviceAlias = etAlias.text.toString()
            prefs.speedtestPackage = etSpeedtestPackage.text.toString()
            
            startMonitorService()
            
            tvStatus.text = "✅ Configuration saved. Monitoring started."
        }
        
        btnPermissions.setOnClickListener {
            requestPermissions()
        }

        btnSettings.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        
        updateStatus(tvStatus)
        checkLocationPermission()
    }
    
    private fun startMonitorService() {
        val intent = Intent(this, MonitorService::class.java)
        startForegroundService(intent)
    }
    
    private fun checkLocationPermission() {
        if (ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.ACCESS_FINE_LOCATION
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            requestLocationPermissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION)
        }
    }
    
    private fun requestPermissions() {
        if (!hasUsageStatsPermission()) {
            startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
        }
    }
    
    private fun hasUsageStatsPermission(): Boolean {
        val appOps = getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val mode = appOps.checkOpNoThrow(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            android.os.Process.myUid(),
            packageName
        )
        return mode == AppOpsManager.MODE_ALLOWED
    }
    
    private fun updateStatus(tvStatus: TextView) {
        val configured = prefs.serverUrl.isNotEmpty() && prefs.deviceToken.isNotEmpty()
        val hasPerms = hasUsageStatsPermission()
        
        tvStatus.text = when {
            !configured -> "Not configured"
            !hasPerms -> "Usage Stats permission required"  
            else -> "✅ Active & monitoring"
        }
    }
}
