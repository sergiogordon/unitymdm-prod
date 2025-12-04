package com.nexmdm

import android.util.Log
import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

class HmacValidator(private val prefs: SecurePreferences) {
    
    companion object {
        private const val TAG = "HmacValidator"
        private const val HMAC_ALGORITHM = "HmacSHA256"
        private const val TIME_WINDOW_SECONDS = 300L
    }
    
    fun validateMessage(
        requestId: String,
        deviceId: String,
        action: String,
        timestamp: String,
        receivedHmac: String
    ): Boolean {
        return validateMessageWithPayload(requestId, deviceId, action, timestamp, receivedHmac, null)
    }
    
    fun validateMessageWithPayload(
        requestId: String,
        deviceId: String,
        action: String,
        timestamp: String,
        receivedHmac: String,
        payloadFields: Map<String, String>?
    ): Boolean {
        val primaryKey = prefs.hmacPrimaryKey
        val rotationKey = prefs.hmacRotationKey
        
        if (primaryKey.isEmpty()) {
            Log.w(TAG, "No HMAC key configured, skipping validation")
            return true
        }
        
        if (!isTimestampValid(timestamp)) {
            Log.w(TAG, "HMAC validation failed: timestamp out of window")
            return false
        }
        
        // Build base payload
        var payload = "$requestId|$deviceId|$action|$timestamp"
        
        // Append payload fields in sorted order (matching server-side implementation)
        if (payloadFields != null && payloadFields.isNotEmpty()) {
            val sortedFields = payloadFields.toList().sortedBy { it.first }
            val payloadStr = sortedFields
                .filter { it.second.isNotEmpty() }  // Only include non-empty values
                .joinToString("|") { "${it.first}:${it.second}" }
            if (payloadStr.isNotEmpty()) {
                payload += "|$payloadStr"
            }
        }
        
        val primaryHmac = computeHmac(payload, primaryKey)
        if (constantTimeEquals(receivedHmac, primaryHmac)) {
            Log.d(TAG, "HMAC validated with primary key")
            return true
        }
        
        if (rotationKey.isNotEmpty()) {
            val rotationHmac = computeHmac(payload, rotationKey)
            if (constantTimeEquals(receivedHmac, rotationHmac)) {
                Log.d(TAG, "HMAC validated with rotation key")
                return true
            }
        }
        
        Log.w(TAG, "HMAC validation failed: signature mismatch")
        return false
    }
    
    private fun computeHmac(payload: String, key: String): String {
        return try {
            val mac = Mac.getInstance(HMAC_ALGORITHM)
            val secretKey = SecretKeySpec(key.toByteArray(), HMAC_ALGORITHM)
            mac.init(secretKey)
            val hmacBytes = mac.doFinal(payload.toByteArray())
            bytesToHex(hmacBytes)
        } catch (e: Exception) {
            Log.e(TAG, "HMAC computation failed", e)
            ""
        }
    }
    
    private fun isTimestampValid(timestamp: String): Boolean {
        return try {
            val messageTime = java.time.Instant.parse(timestamp).epochSecond
            val currentTime = java.time.Instant.now().epochSecond
            val age = kotlin.math.abs(currentTime - messageTime)
            age <= TIME_WINDOW_SECONDS
        } catch (e: Exception) {
            Log.e(TAG, "Invalid timestamp format: $timestamp", e)
            false
        }
    }
    
    private fun constantTimeEquals(a: String, b: String): Boolean {
        if (a.length != b.length) {
            return false
        }
        
        var result = 0
        for (i in a.indices) {
            result = result or (a[i].code xor b[i].code)
        }
        return result == 0
    }
    
    private fun bytesToHex(bytes: ByteArray): String {
        val hexChars = CharArray(bytes.size * 2)
        for (i in bytes.indices) {
            val v = bytes[i].toInt() and 0xFF
            hexChars[i * 2] = "0123456789abcdef"[v ushr 4]
            hexChars[i * 2 + 1] = "0123456789abcdef"[v and 0x0F]
        }
        return String(hexChars)
    }
}
