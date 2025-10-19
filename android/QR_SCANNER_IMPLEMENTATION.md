# QR Scanner Implementation Guide

This guide shows how to add QR code scanning functionality to the NexMDM Android app for device enrollment.

## Step 1: Add ZXing Dependency

Add the ZXing library to your `app/build.gradle`:

```gradle
dependencies {
    // Existing dependencies...
    
    // ZXing for QR code scanning
    implementation 'com.journeyapps:zxing-android-embedded:4.3.0'
    implementation 'com.google.zxing:core:3.5.2'
}
```

## Step 2: Add Camera Permission

Add camera permission to `AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.CAMERA" />
<uses-feature android:name="android.hardware.camera" android:required="false" />
```

## Step 3: Create Enrollment Activity

Create `EnrollmentActivity.kt`:

```kotlin
package com.unitymicro.mdm

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Bundle
import android.widget.Button
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
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
            Toast.makeText(this, "Camera permission required", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_enrollment)
        
        findViewById<Button>(R.id.btn_scan_qr).setOnClickListener {
            checkCameraPermissionAndScan()
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
            setPrompt("Scan enrollment QR code")
            setBeepEnabled(true)
            setBarcodeImageEnabled(false)
            setOrientationLocked(false)
            initiateScan()
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: android.content.Intent?) {
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
            // Parse the enrollment JSON payload
            val json = JSONObject(qrContent)
            val serverUrl = json.getString("server_url")
            val adminKey = json.getString("admin_key")
            val alias = json.getString("alias")
            
            // Show loading
            Toast.makeText(this, "Enrolling device...", Toast.LENGTH_SHORT).show()
            
            // Enroll device
            enrollDevice(serverUrl, adminKey, alias)
            
        } catch (e: Exception) {
            Toast.makeText(this, "Invalid QR code: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    private fun enrollDevice(serverUrl: String, adminKey: String, alias: String) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Register device with backend
                val url = URL("$serverUrl/v1/register?alias=$alias")
                val connection = url.openConnection() as HttpURLConnection
                connection.requestMethod = "POST"
                connection.setRequestProperty("X-Admin", adminKey)
                connection.setRequestProperty("Content-Type", "application/json")
                
                val responseCode = connection.responseCode
                if (responseCode == HttpURLConnection.HTTP_OK) {
                    val response = connection.inputStream.bufferedReader().readText()
                    val responseJson = JSONObject(response)
                    val deviceToken = responseJson.getString("device_token")
                    val deviceId = responseJson.getString("device_id")
                    
                    // Save credentials to encrypted storage
                    saveCredentials(serverUrl, deviceToken, deviceId, alias)
                    
                    withContext(Dispatchers.Main) {
                        Toast.makeText(
                            this@EnrollmentActivity,
                            "Device enrolled successfully!",
                            Toast.LENGTH_LONG
                        ).show()
                        
                        // Start the monitoring service
                        val serviceIntent = Intent(this@EnrollmentActivity, MonitorService::class.java)
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                            startForegroundService(serviceIntent)
                        } else {
                            startService(serviceIntent)
                        }
                        
                        // Close enrollment activity
                        finish()
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
}
```

## Step 4: Create Layout

Create `res/layout/activity_enrollment.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:padding="24dp"
    android:gravity="center">

    <ImageView
        android:layout_width="120dp"
        android:layout_height="120dp"
        android:src="@mipmap/ic_launcher"
        android:layout_marginBottom="32dp"/>

    <TextView
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="NexMDM Enrollment"
        android:textSize="24sp"
        android:textStyle="bold"
        android:layout_marginBottom="16dp"/>

    <TextView
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="Scan the enrollment QR code from your dashboard to register this device"
        android:textAlignment="center"
        android:layout_marginBottom="32dp"/>

    <Button
        android:id="@+id/btn_scan_qr"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="Scan QR Code"
        android:textSize="16sp"
        android:padding="16dp"/>

</LinearLayout>
```

## Step 5: Update AndroidManifest.xml

Add the enrollment activity:

```xml
<activity
    android:name=".EnrollmentActivity"
    android:exported="true"
    android:screenOrientation="portrait">
    <intent-filter>
        <action android:name="android.intent.action.MAIN" />
        <category android:name="android.intent.category.LAUNCHER" />
    </intent-filter>
</activity>
```

## Step 6: Boot Behavior

Your existing `BootReceiver.kt` already handles auto-start on boot - it checks if credentials exist in `SecurePreferences` and starts MonitorService if enrolled:

```kotlin
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            val prefs = SecurePreferences(context)
            
            // If device is enrolled (has credentials), start monitoring service
            if (prefs.serverUrl.isNotEmpty() && prefs.deviceToken.isNotEmpty()) {
                val serviceIntent = Intent(context, MonitorService::class.java)
                context.startForegroundService(serviceIntent)
            }
        }
    }
}
```

**Note:** If device is not enrolled, BootReceiver does nothing. To auto-launch EnrollmentActivity on boot when not enrolled, add an `else` branch with the enrollment activity intent.

## Testing the Flow

1. **Build and install the APK** on a test device
2. **Generate Install QR** from dashboard → Scan with phone camera → Download APK
3. **Open NexMDM app** → Tap "Scan QR Code"
4. **Generate Enrollment QR** from dashboard with a device alias
5. **Scan the enrollment QR** with the app
6. Device should register and start sending heartbeats

## Security Notes

- The enrollment QR contains sensitive data (admin key) - only display it in secure environments
- Consider using encrypted storage (EncryptedSharedPreferences) for production
- Implement QR code expiration for enhanced security
- Validate server URL format before attempting enrollment

## Troubleshooting

- **Camera permission denied**: Check AndroidManifest.xml has camera permission
- **Invalid QR code**: Ensure QR contains valid JSON with server_url, admin_key, and alias fields
- **Network error**: Verify server URL is accessible from the device
- **Enrollment failed**: Check admin key is correct in Replit Secrets
