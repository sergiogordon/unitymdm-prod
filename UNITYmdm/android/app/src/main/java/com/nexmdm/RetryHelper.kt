package com.nexmdm

import android.util.Log
import kotlinx.coroutines.delay
import kotlin.random.Random

object RetryHelper {
    private const val TAG = "RetryHelper"
    private const val MAX_RETRIES = 3
    private const val BASE_DELAY_MS = 1000L
    
    suspend fun <T> withRetry(
        operation: String,
        maxRetries: Int = MAX_RETRIES,
        block: suspend (attempt: Int) -> T
    ): T? {
        var lastException: Exception? = null
        
        for (attempt in 1..maxRetries) {
            try {
                val result = block(attempt)
                
                if (attempt > 1) {
                    Log.i(TAG, "$operation succeeded on attempt $attempt")
                }
                
                return result
            } catch (e: Exception) {
                lastException = e
                
                if (attempt < maxRetries) {
                    val delayMs = calculateBackoffDelay(attempt)
                    
                    Log.w(TAG, "$operation failed (attempt $attempt/$maxRetries), retrying in ${delayMs}ms: ${e.message}")
                    
                    delay(delayMs)
                } else {
                    Log.e(TAG, "$operation failed after $maxRetries attempts", e)
                }
            }
        }
        
        throw lastException ?: Exception("Operation failed after $maxRetries attempts")
    }
    
    private fun calculateBackoffDelay(attempt: Int): Long {
        val exponentialDelay = BASE_DELAY_MS * (1 shl (attempt - 1))
        
        val jitter = Random.nextLong(0, exponentialDelay / 2)
        
        val totalDelay = exponentialDelay + jitter
        
        return minOf(totalDelay, 30000L)
    }
}
