package com.nexmdm

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update

@Dao
interface QueueDao {
    @Insert
    suspend fun insert(item: QueuedItem): Long
    
    @Update
    suspend fun update(item: QueuedItem)
    
    @Query("SELECT * FROM queued_items ORDER BY createdAt ASC, id ASC")
    suspend fun getAllOrdered(): List<QueuedItem>
    
    @Query("SELECT * FROM queued_items WHERE type = :type ORDER BY createdAt ASC, id ASC")
    suspend fun getByType(type: String): List<QueuedItem>
    
    @Query("SELECT * FROM queued_items WHERE requestId = :requestId ORDER BY createdAt ASC, id ASC")
    suspend fun getByRequestId(requestId: String): List<QueuedItem>
    
    @Query("SELECT COUNT(*) FROM queued_items")
    suspend fun getCount(): Int
    
    @Query("SELECT COUNT(*) FROM queued_items WHERE type = :type")
    suspend fun getCountByType(type: String): Int
    
    @Query("SELECT SUM(LENGTH(payload)) FROM queued_items")
    suspend fun getTotalSizeBytes(): Long?
    
    @Query("DELETE FROM queued_items WHERE id = :id")
    suspend fun delete(id: Long)
    
    @Query("DELETE FROM queued_items WHERE id IN (:ids)")
    suspend fun deleteByIds(ids: List<Long>)
    
    @Query("DELETE FROM queued_items WHERE type = :type")
    suspend fun deleteByType(type: String)
    
    @Query("DELETE FROM queued_items WHERE dedupeKey = :dedupeKey")
    suspend fun deleteByDedupeKey(dedupeKey: String)
    
    @Query("DELETE FROM queued_items")
    suspend fun deleteAll()
    
    @Query("SELECT * FROM queued_items WHERE dedupeKey = :dedupeKey LIMIT 1")
    suspend fun findByDedupeKey(dedupeKey: String): QueuedItem?
}
