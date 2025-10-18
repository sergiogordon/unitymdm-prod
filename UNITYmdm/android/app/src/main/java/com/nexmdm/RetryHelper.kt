package com.nexmdm

import android.util.Log
import kotlinx.coroutines.delay
import kotlin.random.Random

object RetryHelper {
    private const val TAG = "RetryHelper"
    private const val MAX_RETRIES = 3
    private const val BASE_DELAY_MS = 2000L
    private const val MAX_DELAY_MS = 300000L
    
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
                    Log.i(TAG, "[retry.ok] operation=$operation attempt=$attempt")
                }
                
                return result
            } catch (e: Exception) {
                lastException = e
                
                if (attempt < maxRetries) {
                    val delayMs = calculateBackoffDelay(attempt)
                    
                    Log.w(TAG, "[retry.schedule] operation=$operation attempt=$attempt delay_ms=$delayMs error=${e.message}")
                    
                    delay(delayMs)
                } else {
                    Log.e(TAG, "[retry.exhausted] operation=$operation attempts=$maxRetries error=${e.message}", e)
                }
            }
        }
        
        throw lastException ?: Exception("Operation failed after $maxRetries attempts")
    }
    
    private fun calculateBackoffDelay(attempt: Int): Long {
        val exponentialDelay = BASE_DELAY_MS * (1 shl (attempt - 1))
        
        val cappedDelay = minOf(exponentialDelay, MAX_DELAY_MS)
        
        val jitter = Random.nextLong(0, cappedDelay + 1)
        
        return jitter
    }
}
