package com.nexmdm

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "queue_items")
data class QueueItem(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    
    val type: String,
    
    val payload: String,
    
    val createdAt: Long = System.currentTimeMillis(),
    
    val ttlExpiry: Long = System.currentTimeMillis() + (24 * 60 * 60 * 1000),
    
    val retryCount: Int = 0,
    
    val lastRetryAt: Long = 0,
    
    val dedupeKey: String? = null
)
