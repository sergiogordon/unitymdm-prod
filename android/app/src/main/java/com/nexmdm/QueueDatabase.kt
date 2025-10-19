package com.nexmdm

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(entities = [QueueItem::class], version = 1, exportSchema = false)
abstract class QueueDatabase : RoomDatabase() {
    
    abstract fun queueDao(): QueueDao
    
    companion object {
        @Volatile
        private var INSTANCE: QueueDatabase? = null
        
        fun getDatabase(context: Context): QueueDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    QueueDatabase::class.java,
                    "nexmdm_queue"
                )
                    .fallbackToDestructiveMigration()
                    .build()
                INSTANCE = instance
                instance
            }
        }
    }
}
