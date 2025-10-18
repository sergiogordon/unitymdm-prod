package com.nexmdm

import android.util.Log
import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

object HmacValidator {
    private const val TAG = "HmacValidator"
    
    fun computeHmacSignature(
        requestId: String,
        deviceId: String,
        action: String,
        timestamp: String,
        hmacSecret: String
    ): String {
        val message = "$requestId|$deviceId|$action|$timestamp"
        
        return try {
            val mac = Mac.getInstance("HmacSHA256")
            val secretKey = SecretKeySpec(hmacSecret.toByteArray(Charsets.UTF_8), "HmacSHA256")
            mac.init(secretKey)
            
            val hashBytes = mac.doFinal(message.toByteArray(Charsets.UTF_8))
            hashBytes.joinToString("") { "%02x".format(it) }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to compute HMAC signature", e)
            ""
        }
    }
    
    fun verifyHmacSignature(
        requestId: String,
        deviceId: String,
        action: String,
        timestamp: String,
        providedSignature: String,
        hmacSecret: String
    ): Boolean {
        if (hmacSecret.isEmpty()) {
            Log.w(TAG, "HMAC secret not configured")
            return false
        }
        
        if (providedSignature.isEmpty()) {
            Log.w(TAG, "No HMAC signature provided")
            return false
        }
        
        val expectedSignature = computeHmacSignature(requestId, deviceId, action, timestamp, hmacSecret)
        
        if (expectedSignature.isEmpty()) {
            Log.e(TAG, "Failed to compute expected signature")
            return false
        }
        
        val isValid = messageDigestEquals(expectedSignature, providedSignature)
        
        if (!isValid) {
            Log.w(TAG, "HMAC validation failed for action: $action, request_id: $requestId")
        }
        
        return isValid
    }
    
    private fun messageDigestEquals(a: String, b: String): Boolean {
        if (a.length != b.length) {
            return false
        }
        
        var result = 0
        for (i in a.indices) {
            result = result or (a[i].code xor b[i].code)
        }
        
        return result == 0
    }
}
