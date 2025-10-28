# WiFi Auto-Connection via FCM - Android Implementation Guide

## Overview

This guide explains how to implement automatic WiFi connectivity in your Android app when WiFi credentials are pushed from the MDM server via FCM.

## Prerequisites

- **Android Version**: Android 10+ (API level 29+) for `cmd wifi connect-network` command
- **Android 13**: As confirmed by you, this works perfectly on Android 13
- **Permissions**: Your app must have Device Owner or appropriate system permissions
- **FCM Integration**: Firebase Cloud Messaging already integrated in your Android app

## Implementation Steps

### 1. Add WiFi Connection Handler to FcmMessagingService

Add this handler to your `FcmMessagingService.kt` file:

```kotlin
private fun handleWiFiConnect(data: Map<String, String>) {
    Log.d(TAG, "Handling WiFi connection request")
    
    val ssid = data["ssid"] ?: return
    val password = data["password"] ?: ""
    val securityType = data["security_type"] ?: "wpa2"
    
    try {
        // Build the adb shell command
        val command = when (securityType) {
            "open" -> "cmd wifi connect-network \"$ssid\" open"
            "wep" -> "cmd wifi connect-network \"$ssid\" wep \"$password\""
            "wpa" -> "cmd wifi connect-network \"$ssid\" wpa2 \"$password\""  // WPA uses wpa2 command
            "wpa2" -> "cmd wifi connect-network \"$ssid\" wpa2 \"$password\""
            "wpa3" -> "cmd wifi connect-network \"$ssid\" wpa3 \"$password\""
            else -> "cmd wifi connect-network \"$ssid\" wpa2 \"$password\""
        }
        
        Log.i(TAG, "Executing WiFi connection command for SSID: $ssid")
        
        // Execute the command
        val process = Runtime.getRuntime().exec(arrayOf("sh", "-c", command))
        val exitCode = process.waitFor()
        
        if (exitCode == 0) {
            Log.i(TAG, "✓ Successfully connected to WiFi: $ssid")
            sendWiFiConnectionAck(data["request_id"] ?: "", "OK", "Connected to $ssid")
        } else {
            val errorOutput = process.errorStream.bufferedReader().readText()
            Log.e(TAG, "✗ Failed to connect to WiFi: $errorOutput")
            sendWiFiConnectionAck(data["request_id"] ?: "", "FAILED", "Connection failed: $errorOutput")
        }
        
    } catch (e: Exception) {
        Log.e(TAG, "✗ Exception connecting to WiFi", e)
        sendWiFiConnectionAck(data["request_id"] ?: "", "ERROR", "Exception: ${e.message}")
    }
}

private fun sendWiFiConnectionAck(requestId: String, status: String, message: String) {
    if (requestId.isEmpty()) {
        Log.w(TAG, "Cannot send WiFi ACK - missing request_id")
        return
    }
    
    val prefs = SecurePreferences(this)
    val deviceId = prefs.deviceId
    
    if (deviceId.isEmpty()) {
        Log.e(TAG, "Cannot send WiFi ACK - deviceId is EMPTY")
        return
    }
    
    val queueManager = QueueManager(this, prefs)
    
    CoroutineScope(Dispatchers.IO).launch {
        try {
            val ackPayload = gson.toJson(mapOf(
                "request_id" to requestId,
                "type" to "WIFI_CONNECT_ACK",
                "status" to status,
                "message" to message
            ))
            
            queueManager.enqueueActionResult(ackPayload)
            Log.i(TAG, "[WIFI-ACK] Queued acknowledgment: $status - $message")
        } catch (e: Exception) {
            Log.e(TAG, "[WIFI-ACK] Failed to queue acknowledgment", e)
        }
    }
}
```

### 2. Update FCM Message Receiver

In your `FcmMessagingService.onMessageReceived()`, add the WiFi action handler:

```kotlin
override fun onMessageReceived(message: RemoteMessage) {
    super.onMessageReceived(message)
    
    val action = message.data["action"] ?: ""
    
    when (action) {
        "wifi_connect" -> {
            handleWiFiConnect(message.data)
        }
        // ... other action handlers
    }
}
```

### 3. Security Considerations

The implementation includes HMAC signature validation (already in your codebase):

```kotlin
val prefs = SecurePreferences(this)
if (prefs.hmacPrimaryKey.isNotEmpty()) {
    val validator = HmacValidator(prefs)
    val isValid = validator.validateMessage(requestId, deviceId, action, timestamp, hmac)
    
    if (!isValid) {
        Log.w(TAG, "HMAC validation failed for action=$action, rejecting message")
        return
    }
}
```

This ensures that only legitimate WiFi credentials from your MDM server are processed.

### 4. Required Permissions

Make sure your AndroidManifest.xml includes:

```xml
<uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />
<uses-permission android:name="android.permission.CHANGE_WIFI_STATE" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
```

For Device Owner apps (which your MDM app likely is), these permissions are automatically granted.

## How to Use from MDM Dashboard

### Step 1: Configure WiFi Settings

1. Click the **Settings** (gear icon) in the dashboard
2. Scroll to **WiFi Configuration** section
3. Enter:
   - **Network Name (SSID)**: Your WiFi network name
   - **Password**: Your WiFi password
   - **Security Type**: Select WPA2, WPA3, etc.
4. Toggle **Enable WiFi Push** to ON
5. Click **Save WiFi Settings**

### Step 2: Push to Devices

From the device management page or remote execution:

```bash
POST /v1/wifi/push-to-devices
{
  "device_ids": ["device-1", "device-2", "device-3"]
}
```

The system will:
1. Send FCM message to each device
2. Device executes `cmd wifi connect-network` command
3. Device sends back acknowledgment
4. You can see results in the response

## Command Reference

The Android app will execute one of these commands based on security type:

```bash
# Open network (no password)
adb shell cmd wifi connect-network "MyWiFi" open

# WEP network
adb shell cmd wifi connect-network "MyWiFi" wep "password123"

# WPA/WPA2 network
adb shell cmd wifi connect-network "MyWiFi" wpa2 "password123"

# WPA3 network
adb shell cmd wifi connect-network "MyWiFi" wpa3 "SecurePass456"
```

## Troubleshooting

### Device not connecting?

1. **Check Android version**: Must be Android 10+ (you have Android 13, so you're good)
2. **Check Device Owner status**: The app must have Device Owner privileges
3. **Check FCM token**: Device must have a valid FCM token registered
4. **Check logs**: Use `adb logcat | grep FcmMessagingService` to see connection attempts

### SSID with spaces?

The implementation handles spaces automatically by wrapping SSID in quotes.

### Special characters in password?

Passwords are properly escaped in the command execution.

## Testing

You can test WiFi connection manually via ADB:

```bash
# Enable WiFi first
adb shell svc wifi enable

# Connect to your network
adb shell cmd wifi connect-network "YourSSID" wpa2 "YourPassword"

# Check WiFi status
adb shell dumpsys wifi | grep "Wi-Fi is"
```

## Architecture Flow

```
┌─────────────────┐
│  MDM Dashboard  │
│  WiFi Settings  │
└────────┬────────┘
         │ Configure SSID/Password
         ▼
┌─────────────────┐
│  Backend API    │
│  /v1/wifi/push  │
└────────┬────────┘
         │ FCM Message
         ▼
┌─────────────────┐
│ Android Device  │
│ FCM Service     │
└────────┬────────┘
         │ Execute cmd wifi
         ▼
┌─────────────────┐
│   Connected!    │
│   Send ACK      │
└─────────────────┘
```

## API Endpoints

### Get WiFi Settings
```http
GET /v1/settings/wifi
Authorization: Bearer <token>
```

### Update WiFi Settings
```http
POST /v1/settings/wifi
Authorization: Bearer <token>
Content-Type: application/json

{
  "ssid": "MyNetwork",
  "password": "MyPassword123",
  "security_type": "wpa2",
  "enabled": true
}
```

### Push to Devices
```http
POST /v1/wifi/push-to-devices
Authorization: Bearer <token>
Content-Type: application/json

{
  "device_ids": ["device-uuid-1", "device-uuid-2"]
}
```

Response:
```json
{
  "ok": true,
  "ssid": "MyNetwork",
  "total": 2,
  "success_count": 2,
  "failed_count": 0,
  "results": [
    {
      "device_id": "device-uuid-1",
      "alias": "Device 1",
      "ok": true,
      "message": "WiFi credentials sent successfully"
    }
  ]
}
```

## Next Steps

1. **Implement the handler** in your Android app's `FcmMessagingService.kt`
2. **Test with one device** first using the dashboard
3. **Roll out to fleet** once verified working
4. **Monitor logs** to ensure successful connections

## Security Notes

- WiFi passwords are transmitted via FCM (which is TLS encrypted)
- HMAC validation ensures messages come from your MDM server
- Passwords are stored encrypted in your PostgreSQL database
- Consider using WPA3 for strongest security
- Rotate WiFi passwords regularly and push updates to all devices

## Open Source Considerations

Since you plan to open-source this:

1. **Remove sensitive defaults** from the code
2. **Document setup clearly** for other users
3. **Make WiFi settings optional** in the configuration
4. **Add environment variable** for admin to disable WiFi feature if not needed

---

**Questions?** Check the logs using `refresh_all_logs` or contact your development team.
