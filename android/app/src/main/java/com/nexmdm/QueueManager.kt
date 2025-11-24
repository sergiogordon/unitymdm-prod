package com.nexmdm

import android.content.Context
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.random.Random

class QueueManager(
    private val context: Context,
    private val prefs: SecurePreferences,
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()
) {
    
    companion object {
        private const val TAG = "QueueManager"
        private const val MAX_QUEUE_ITEMS = 500
        private const val MAX_QUEUE_SIZE_BYTES = 10 * 1024 * 1024
        private const val BASE_BACKOFF_MS = 2000L
        private const val MAX_BACKOFF_MS = 300000L
        private const val DEDUPE_BUCKET_SECONDS = 10
        private const val TYPE_HEARTBEAT = "heartbeat"
        private const val TYPE_ACTION_RESULT = "action_result"
    }
    
    private val db = QueueDatabase.getDatabase(context)
    private val dao = db.queueDao()
    
    suspend fun enqueueHeartbeat(payload: String) {
        withContext(Dispatchers.IO) {
            try {
                val currentBucket = System.currentTimeMillis() / 1000 / DEDUPE_BUCKET_SECONDS
                val dedupeKey = "${TYPE_HEARTBEAT}_${currentBucket}"
                
                val existing = dao.findByDedupeKey(dedupeKey)
                if (existing != null) {
                    dao.deleteByDedupeKey(dedupeKey)
                    Log.d(TAG, "Coalescing heartbeat in same ${DEDUPE_BUCKET_SECONDS}s bucket")
                }
                
                pruneIfNeeded()
                
                val item = QueueItem(
                    type = TYPE_HEARTBEAT,
                    payload = payload,
                    dedupeKey = dedupeKey
                )
                
                dao.insert(item)
                Log.d(TAG, "queue.enqueue: type=heartbeat")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to enqueue heartbeat", e)
            }
        }
    }
    
    suspend fun enqueueActionResult(payload: String) {
        withContext(Dispatchers.IO) {
            try {
                Log.i(TAG, "[ACK-FLOW-5] enqueueActionResult called with payload: $payload")
                
                pruneIfNeeded()
                
                val item = QueueItem(
                    type = TYPE_ACTION_RESULT,
                    payload = payload
                )
                
                dao.insert(item)
                
                Log.i(TAG, "[ACK-FLOW-6] Successfully inserted ACK into queue: id=${item.id}, type=action_result")
                
                val queueSize = dao.getAll().size
                Log.i(TAG, "[ACK-FLOW-7] Current queue size: $queueSize items")
            } catch (e: Exception) {
                Log.e(TAG, "[ACK-FLOW-ERROR] Failed to enqueue action result", e)
            }
        }
    }
    
    suspend fun drainQueue(networkMonitor: NetworkMonitor? = null): DrainResult {
        return withContext(Dispatchers.IO) {
            var successCount = 0
            var failCount = 0
            
            try {
                val validated = networkMonitor?.isNetworkValidated() ?: true
                if (!validated) {
                    Log.d(TAG, "queue.drain: skipped (network not validated)")
                    return@withContext DrainResult(0, 0)
                }
                
                val items = dao.getAll()
                Log.d(TAG, "queue.drain: attempting to send ${items.size} items")
                
                for (item in items) {
                    val shouldRetry = shouldRetryItem(item)
                    if (!shouldRetry) {
                        continue
                    }
                    
                    val sent = sendItem(item)
                    if (sent) {
                        dao.deleteById(item.id)
                        successCount++
                        Log.d(TAG, "deliver.ok: type=${item.type}, id=${item.id}")
                    } else {
                        failCount++
                        val updatedItem = item.copy(
                            retryCount = item.retryCount + 1,
                            lastRetryAt = System.currentTimeMillis()
                        )
                        dao.insert(updatedItem)
                        Log.d(TAG, "deliver.fail: type=${item.type}, id=${item.id}, retry=${item.retryCount + 1}")
                        
                        val backoff = calculateBackoff(item.retryCount + 1)
                        Log.d(TAG, "retry.schedule: next_retry_ms=${backoff}")
                    }
                }
                
                pruneExpired()
            } catch (e: Exception) {
                Log.e(TAG, "Queue drain failed", e)
            }
            
            DrainResult(successCount, failCount)
        }
    }
    
    private suspend fun sendItem(item: QueueItem): Boolean {
        val serverUrl = prefs.serverUrl
        val deviceToken = prefs.deviceToken
        val deviceId = prefs.deviceId
        
        if (item.type == TYPE_ACTION_RESULT) {
            Log.i(TAG, "[ACK-FLOW-8] sendItem called for ACTION_RESULT: id=${item.id}")
            Log.i(TAG, "[ACK-FLOW-9] serverUrl=$serverUrl, deviceId=$deviceId, hasToken=${deviceToken.isNotEmpty()}")
        }
        
        if (serverUrl.isEmpty() || deviceToken.isEmpty()) {
            if (item.type == TYPE_ACTION_RESULT) {
                Log.e(TAG, "[ACK-FLOW-ABORT] Missing credentials: serverUrl=${serverUrl.isEmpty()}, token=${deviceToken.isEmpty()}")
            }
            Log.w(TAG, "send.skip: type=${item.type}, id=${item.id}, missing_creds=true")
            return false
        }
        
        if (item.type == TYPE_ACTION_RESULT && deviceId.isEmpty()) {
            Log.e(TAG, "[ACK-FLOW-ABORT] Missing device_id for ACTION_RESULT")
            Log.w(TAG, "send.skip: type=${item.type}, id=${item.id}, missing_device_id=true")
            return false
        }
        
        if (item.type == TYPE_HEARTBEAT && deviceId.isEmpty()) {
            Log.w(TAG, "send.skip: type=${item.type}, id=${item.id}, missing_device_id=true")
            return false
        }
        
        val endpoint = when (item.type) {
            TYPE_HEARTBEAT -> "/v1/heartbeat"
            TYPE_ACTION_RESULT -> "/v1/devices/$deviceId/ack"
            else -> return false
        }
        
        if (item.type == TYPE_ACTION_RESULT) {
            Log.i(TAG, "[ACK-FLOW-10] Full ACK endpoint URL: $serverUrl$endpoint")
            Log.i(TAG, "[ACK-FLOW-11] ACK payload: ${item.payload}")
        }
        
        return try {
            val request = Request.Builder()
                .url("$serverUrl$endpoint")
                .post(item.payload.toRequestBody("application/json".toMediaType()))
                .addHeader("Authorization", "Bearer $deviceToken")
                .build()
            
            if (item.type == TYPE_ACTION_RESULT) {
                Log.i(TAG, "[ACK-FLOW-12] Sending ACK HTTP POST request...")
            }
            
            val response = client.newCall(request).execute()
            val success = response.isSuccessful
            
            if (item.type == TYPE_ACTION_RESULT) {
                if (success) {
                    val responseBody = response.body?.string() ?: ""
                    Log.i(TAG, "[ACK-FLOW-13] ✓ ACK sent successfully! HTTP ${response.code}, response: $responseBody")
                } else {
                    val responseBody = response.body?.string() ?: ""
                    Log.e(TAG, "[ACK-FLOW-ERROR] ✗ ACK send failed! HTTP ${response.code}, response: $responseBody")
                }
            }
            
            if (success) {
                Log.d(TAG, "send.ok: type=${item.type}, endpoint=$endpoint")
            } else {
                Log.w(TAG, "send.fail: type=${item.type}, endpoint=$endpoint, code=${response.code}")
            }
            
            success
        } catch (e: Exception) {
            if (item.type == TYPE_ACTION_RESULT) {
                Log.e(TAG, "[ACK-FLOW-ERROR] Network exception sending ACK", e)
            }
            Log.e(TAG, "Network error sending ${item.type}", e)
            false
        }
    }
    
    private fun shouldRetryItem(item: QueueItem): Boolean {
        val now = System.currentTimeMillis()
        
        if (now > item.ttlExpiry) {
            Log.d(TAG, "skip.expired: type=${item.type}, id=${item.id}, age_ms=${now - item.createdAt}")
            return false
        }
        
        if (item.lastRetryAt == 0L) {
            Log.d(TAG, "retry.ready: type=${item.type}, id=${item.id}, attempt=1")
            return true
        }
        
        val backoff = calculateBackoff(item.retryCount)
        val nextRetryTime = item.lastRetryAt + backoff
        val isReady = now >= nextRetryTime
        
        if (!isReady) {
            val waitMs = nextRetryTime - now
            Log.d(TAG, "skip.backoff: type=${item.type}, id=${item.id}, retry=${item.retryCount}, wait_ms=$waitMs")
            return false
        }
        
        Log.d(TAG, "retry.ready: type=${item.type}, id=${item.id}, attempt=${item.retryCount + 1}")
        return true
    }
    
    private fun calculateBackoff(retryCount: Int): Long {
        // Cap retry count to prevent overflow (2^20 * 2000ms = ~2B ms = ~24 days)
        val safeRetryCount = min(retryCount, 20)
        
        val exponentialBackoff = BASE_BACKOFF_MS * (2.0.pow(safeRetryCount.toDouble())).toLong()
        val cappedBackoff = min(exponentialBackoff, MAX_BACKOFF_MS)
        
        // Ensure jitter range is valid and positive
        val jitterRange = max(cappedBackoff / 4, 1L)
        val jitter = if (jitterRange > 0) {
            Random.nextLong(0, jitterRange)
        } else {
            0L
        }
        
        return cappedBackoff + jitter
    }
    
    private suspend fun pruneIfNeeded() {
        val count = dao.getCount()
        val size = dao.getTotalSize() ?: 0
        
        if (count > MAX_QUEUE_ITEMS) {
            val toDelete = count - MAX_QUEUE_ITEMS
            dao.deleteOldestByType(TYPE_HEARTBEAT, toDelete)
            Log.d(TAG, "queue.prune: removed $toDelete old heartbeats (count limit)")
        }
        
        if (size > MAX_QUEUE_SIZE_BYTES) {
            val heartbeatCount = dao.getCountByType(TYPE_HEARTBEAT)
            if (heartbeatCount > 0) {
                dao.deleteOldestByType(TYPE_HEARTBEAT, heartbeatCount / 2)
                Log.d(TAG, "queue.prune: removed oldest heartbeats (size limit)")
            }
        }
    }
    
    private suspend fun pruneExpired() {
        val deleted = dao.deleteExpired(System.currentTimeMillis())
        if (deleted > 0) {
            Log.d(TAG, "queue.prune: removed $deleted expired items")
        }
    }
    
    suspend fun getQueueDepth(): Int {
        return withContext(Dispatchers.IO) {
            dao.getCount()
        }
    }
    
    data class DrainResult(
        val successCount: Int,
        val failCount: Int
    )
}
