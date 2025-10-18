package com.nexmdm

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "queued_items")
data class QueuedItem(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    
    val type: String,
    
    val createdAt: Long,
    
    val payload: String,
    
    val requestId: String? = null,
    
    val dedupeKey: String? = null,
    
    val attempts: Int = 0,
    
    val ttlMs: Long? = null,
    
    val lastAttemptAt: Long? = null
) {
    companion object {
        const val TYPE_HEARTBEAT = "hb"
        const val TYPE_ACTION_RESULT = "result"
        
        const val TTL_24_HOURS_MS = 24L * 60 * 60 * 1000
    }
    
    fun isExpired(): Boolean {
        if (ttlMs == null) return false
        return System.currentTimeMillis() - createdAt > ttlMs
    }
}
