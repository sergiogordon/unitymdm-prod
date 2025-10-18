package com.nexmdm

import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

class QueueManager(context: Context) {
    
    companion object {
        private const val TAG = "QueueManager"
        private const val MAX_QUEUE_ITEMS = 500
        private const val MAX_QUEUE_SIZE_BYTES = 10 * 1024 * 1024
        
        @Volatile
        private var INSTANCE: QueueManager? = null
        
        fun getInstance(context: Context): QueueManager {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: QueueManager(context.applicationContext).also { INSTANCE = it }
            }
        }
    }
    
    private val database = AppDatabase.getInstance(context)
    private val dao = database.queueDao()
    private val mutex = Mutex()
    
    suspend fun enqueue(
        type: String,
        payload: String,
        requestId: String? = null,
        dedupeKey: String? = null,
        ttlMs: Long? = null
    ): Long = withContext(Dispatchers.IO) {
        mutex.withLock {
            if (dedupeKey != null) {
                val existing = dao.findByDedupeKey(dedupeKey)
                if (existing != null) {
                    Log.d(TAG, "[queue.dedupe] key=$dedupeKey existing_id=${existing.id}")
                    dao.delete(existing.id)
                }
            }
            
            pruneIfNeeded()
            
            val item = QueuedItem(
                type = type,
                createdAt = System.currentTimeMillis(),
                payload = payload,
                requestId = requestId,
                dedupeKey = dedupeKey,
                ttlMs = ttlMs
            )
            
            val id = dao.insert(item)
            
            val count = dao.getCount()
            val sizeBytes = dao.getTotalSizeBytes() ?: 0L
            
            Log.i(TAG, "[queue.enqueue] type=$type id=$id request_id=$requestId queue_depth=$count queue_bytes=$sizeBytes")
            
            id
        }
    }
    
    suspend fun getQueueDepth(): Int = withContext(Dispatchers.IO) {
        dao.getCount()
    }
    
    suspend fun getQueueStats(): QueueStats = withContext(Dispatchers.IO) {
        val totalCount = dao.getCount()
        val heartbeatCount = dao.getCountByType(QueuedItem.TYPE_HEARTBEAT)
        val resultCount = dao.getCountByType(QueuedItem.TYPE_ACTION_RESULT)
        val totalBytes = dao.getTotalSizeBytes() ?: 0L
        
        QueueStats(
            totalItems = totalCount,
            heartbeatItems = heartbeatCount,
            resultItems = resultCount,
            totalBytes = totalBytes
        )
    }
    
    suspend fun drainQueue(
        onItem: suspend (QueuedItem) -> DrainResult
    ): DrainSummary = withContext(Dispatchers.IO) {
        mutex.withLock {
            val items = dao.getAllOrdered()
            
            if (items.isEmpty()) {
                return@withContext DrainSummary(
                    totalItems = 0,
                    successCount = 0,
                    failedCount = 0,
                    expiredCount = 0
                )
            }
            
            Log.i(TAG, "[queue.drain.start] items=${items.size}")
            
            var successCount = 0
            var failedCount = 0
            var expiredCount = 0
            
            for (item in items) {
                if (item.isExpired()) {
                    Log.w(TAG, "[queue.expired] id=${item.id} type=${item.type} age_ms=${System.currentTimeMillis() - item.createdAt}")
                    dao.delete(item.id)
                    expiredCount++
                    continue
                }
                
                try {
                    val result = onItem(item)
                    
                    when (result) {
                        is DrainResult.Success -> {
                            dao.delete(item.id)
                            successCount++
                            Log.d(TAG, "[queue.drain.ok] id=${item.id} type=${item.type} attempts=${item.attempts + 1}")
                        }
                        is DrainResult.Retry -> {
                            val updatedItem = item.copy(
                                attempts = item.attempts + 1,
                                lastAttemptAt = System.currentTimeMillis()
                            )
                            dao.update(updatedItem)
                            failedCount++
                            Log.w(TAG, "[queue.drain.retry] id=${item.id} type=${item.type} attempts=${updatedItem.attempts} reason=${result.reason}")
                        }
                        is DrainResult.Drop -> {
                            dao.delete(item.id)
                            failedCount++
                            Log.e(TAG, "[queue.drain.drop] id=${item.id} type=${item.type} reason=${result.reason}")
                        }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "[queue.drain.error] id=${item.id} error=${e.message}", e)
                    val updatedItem = item.copy(
                        attempts = item.attempts + 1,
                        lastAttemptAt = System.currentTimeMillis()
                    )
                    dao.update(updatedItem)
                    failedCount++
                }
            }
            
            Log.i(TAG, "[queue.drain.end] total=${items.size} success=$successCount failed=$failedCount expired=$expiredCount")
            
            DrainSummary(
                totalItems = items.size,
                successCount = successCount,
                failedCount = failedCount,
                expiredCount = expiredCount
            )
        }
    }
    
    private suspend fun pruneIfNeeded() {
        val count = dao.getCount()
        val sizeBytes = dao.getTotalSizeBytes() ?: 0L
        
        if (count <= MAX_QUEUE_ITEMS && sizeBytes <= MAX_QUEUE_SIZE_BYTES) {
            return
        }
        
        Log.w(TAG, "[queue.prune.start] count=$count max=$MAX_QUEUE_ITEMS size_bytes=$sizeBytes max_bytes=$MAX_QUEUE_SIZE_BYTES")
        
        val heartbeats = dao.getByType(QueuedItem.TYPE_HEARTBEAT)
        val results = dao.getByType(QueuedItem.TYPE_ACTION_RESULT)
        
        val heartbeatsToPrune = mutableListOf<Long>()
        
        if (heartbeats.size > 1) {
            val dedupeMap = mutableMapOf<String?, QueuedItem>()
            
            for (hb in heartbeats) {
                val key = hb.dedupeKey
                val existing = dedupeMap[key]
                
                if (existing != null) {
                    heartbeatsToPrune.add(existing.id)
                }
                dedupeMap[key] = hb
            }
        }
        
        val oldestHeartbeats = heartbeats
            .filter { it.id !in heartbeatsToPrune }
            .sortedBy { it.createdAt }
            .take(heartbeats.size - 1)
            .map { it.id }
        
        heartbeatsToPrune.addAll(oldestHeartbeats)
        
        if (heartbeatsToPrune.isNotEmpty()) {
            dao.deleteByIds(heartbeatsToPrune)
            Log.i(TAG, "[queue.prune] heartbeats_pruned=${heartbeatsToPrune.size} results_preserved=${results.size}")
        }
        
        val newCount = dao.getCount()
        if (newCount > MAX_QUEUE_ITEMS) {
            val overflow = newCount - MAX_QUEUE_ITEMS
            Log.e(TAG, "[queue.overflow] still_over_limit count=$newCount overflow=$overflow - this should not happen!")
        }
    }
    
    suspend fun clear() = withContext(Dispatchers.IO) {
        mutex.withLock {
            dao.deleteAll()
            Log.i(TAG, "[queue.clear] all items deleted")
        }
    }
    
    data class QueueStats(
        val totalItems: Int,
        val heartbeatItems: Int,
        val resultItems: Int,
        val totalBytes: Long
    )
    
    data class DrainSummary(
        val totalItems: Int,
        val successCount: Int,
        val failedCount: Int,
        val expiredCount: Int
    )
    
    sealed class DrainResult {
        object Success : DrainResult()
        data class Retry(val reason: String) : DrainResult()
        data class Drop(val reason: String) : DrainResult()
    }
}
