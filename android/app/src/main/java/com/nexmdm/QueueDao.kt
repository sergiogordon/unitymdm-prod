package com.nexmdm

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface QueueDao {
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(item: QueueItem): Long
    
    @Query("SELECT * FROM queue_items ORDER BY createdAt ASC")
    suspend fun getAll(): List<QueueItem>
    
    @Query("SELECT * FROM queue_items WHERE type = :type ORDER BY createdAt ASC LIMIT :limit")
    suspend fun getByType(type: String, limit: Int = 100): List<QueueItem>
    
    @Query("SELECT COUNT(*) FROM queue_items")
    suspend fun getCount(): Int
    
    @Query("SELECT COUNT(*) FROM queue_items WHERE type = :type")
    suspend fun getCountByType(type: String): Int
    
    @Query("SELECT SUM(LENGTH(payload)) FROM queue_items")
    suspend fun getTotalSize(): Long?
    
    @Query("DELETE FROM queue_items WHERE id = :id")
    suspend fun deleteById(id: Long)
    
    @Query("DELETE FROM queue_items WHERE ttlExpiry < :currentTime")
    suspend fun deleteExpired(currentTime: Long): Int
    
    @Query("WITH to_delete AS (SELECT id FROM queue_items WHERE type = :type ORDER BY createdAt ASC LIMIT :limit) DELETE FROM queue_items WHERE id IN (SELECT id FROM to_delete)")
    suspend fun deleteOldestByType(type: String, limit: Int): Int
    
    @Query("SELECT * FROM queue_items WHERE dedupeKey = :key LIMIT 1")
    suspend fun findByDedupeKey(key: String): QueueItem?
    
    @Query("DELETE FROM queue_items WHERE dedupeKey = :key")
    suspend fun deleteByDedupeKey(key: String)
    
    @Query("DELETE FROM queue_items")
    suspend fun deleteAll()
}
