# NexMDM QR Code Enrollment - Android Implementation

## Overview
This guide shows how to add QR code enrollment to your NexMDM Android app.

## Dependencies

Add to your `app/build.gradle`:
```gradle
dependencies {
    implementation 'com.journeyapps:zxing-android-embedded:4.3.0'
    implementation 'com.google.zxing:core:3.5.2'
    implementation 'com.squareup.okhttp3:okhttp:4.12.0'
    implementation 'com.google.code.gson:gson:2.10.1'
}
```

## 1. QR Scanner Activity

Create `QREnrollmentActivity.kt`:

```kotlin
package com.unitymicro.mdm

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.zxing.integration.android.IntentIntegrator
import com.google.zxing.integration.android.IntentResult
import com.google.gson.Gson
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

data class QREnrollmentData(
    val server_url: String,
    val admin_key: String,
    val alias: String
)

data class RegisterResponse(
    val device_token: String,
    val device_id: String
)

class QREnrollmentActivity : AppCompatActivity() {
    private val client = OkHttpClient()
    private val gson = Gson()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Start QR scanner immediately
        val integrator = IntentIntegrator(this)
        integrator.setDesiredBarcodeFormats(IntentIntegrator.QR_CODE)
        integrator.setPrompt("Scan NexMDM enrollment QR code")
        integrator.setCameraId(0)
        integrator.setBeepEnabled(true)
        integrator.setBarcodeImageEnabled(false)
        integrator.initiateScan()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        val result: IntentResult = IntentIntegrator.parseActivityResult(requestCode, resultCode, data)
        
        if (result.contents != null) {
            try {
                val enrollmentData = gson.fromJson(result.contents, QREnrollmentData::class.java)
                registerDevice(enrollmentData)
            } catch (e: Exception) {
                Toast.makeText(this, "Invalid QR code format", Toast.LENGTH_LONG).show()
                finish()
            }
        } else {
            super.onActivityResult(requestCode, resultCode, data)
            finish()
        }
    }

    private fun registerDevice(enrollmentData: QREnrollmentData) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Step 1: Register with backend
                val registerUrl = "${enrollmentData.server_url}/v1/register?alias=${enrollmentData.alias}"
                val request = Request.Builder()
                    .url(registerUrl)
                    .post("".toRequestBody())
                    .addHeader("X-Admin", enrollmentData.admin_key)
                    .build()

                val response = client.newCall(request).execute()
                
                if (!response.isSuccessful) {
                    withContext(Dispatchers.Main) {
                        Toast.makeText(
                            this@QREnrollmentActivity,
                            "Registration failed: ${response.code}",
                            Toast.LENGTH_LONG
                        ).show()
                        finish()
                    }
                    return@launch
                }

                val registerResponse = gson.fromJson(
                    response.body?.string(),
                    RegisterResponse::class.java
                )

                // Step 2: Save credentials securely
                saveCredentials(
                    enrollmentData.server_url,
                    registerResponse.device_token,
                    enrollmentData.alias,
                    registerResponse.device_id
                )

                withContext(Dispatchers.Main) {
                    Toast.makeText(
                        this@QREnrollmentActivity,
                        "✓ Enrolled as ${enrollmentData.alias}",
                        Toast.LENGTH_LONG
                    ).show()
                    
                    // Start the MDM service
                    val serviceIntent = Intent(this@QREnrollmentActivity, MDMService::class.java)
                    startForegroundService(serviceIntent)
                    
                    finish()
                }

            } catch (e: IOException) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(
                        this@QREnrollmentActivity,
                        "Network error: ${e.message}",
                        Toast.LENGTH_LONG
                    ).show()
                    finish()
                }
            }
        }
    }

    private fun saveCredentials(serverUrl: String, token: String, alias: String, deviceId: String) {
        val prefs = getSharedPreferences("mdm_config", MODE_PRIVATE)
        prefs.edit().apply {
            putString("server_url", serverUrl)
            putString("device_token", token)
            putString("device_alias", alias)
            putString("device_id", deviceId)
            putBoolean("enrolled", true)
            apply()
        }
    }
}
```

## 2. Add to AndroidManifest.xml

```xml
<uses-permission android:name="android.permission.CAMERA" />

<application>
    <!-- Add this activity -->
    <activity
        android:name=".QREnrollmentActivity"
        android:exported="true"
        android:theme="@style/Theme.AppCompat.NoActionBar">
        <intent-filter>
            <action android:name="android.intent.action.MAIN" />
            <category android:name="android.intent.category.LAUNCHER" />
        </intent-filter>
    </activity>
    
    <!-- Your existing MDM service -->
    <service
        android:name=".MDMService"
        android:enabled="true"
        android:exported="false"
        android:foregroundServiceType="dataSync" />
</application>
```

## 3. Request Camera Permission (if needed)

Add to your activity:

```kotlin
private fun checkCameraPermission() {
    if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) 
        != PackageManager.PERMISSION_GRANTED) {
        ActivityCompat.requestPermissions(
            this,
            arrayOf(Manifest.permission.CAMERA),
            CAMERA_PERMISSION_REQUEST
        )
    }
}
```

## Usage Flow

1. **User opens NexMDM app** → QR scanner launches automatically
2. **User scans QR code** from dashboard settings panel
3. **App registers** with backend using embedded credentials
4. **App starts heartbeat service** automatically
5. **Device appears** in dashboard within 2 minutes

## Testing

1. Open dashboard settings → Enter device alias → Generate QR code
2. Open NexMDM Android app (or build debug APK)
3. Point camera at QR code
4. Verify device appears in dashboard
5. Check that heartbeats are being sent every 2 minutes

## Security Notes

- Admin key is transmitted only during initial registration
- Device token is stored in SharedPreferences (consider using EncryptedSharedPreferences for production)
- QR codes contain sensitive credentials - don't share screenshots
- Server URL and admin key are embedded in QR for convenience

## Next Steps

After enrollment:
1. Grant Usage Access permission (for app monitoring)
2. Grant Notification Listener permission (for Unity app detection)
3. Device will automatically send heartbeats every 2 minutes
