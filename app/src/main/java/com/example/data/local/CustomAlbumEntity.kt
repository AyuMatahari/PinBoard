package com.example.data.local

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "custom_albums",
    indices = [
        Index(value = ["boardId"]),
        Index(value = ["parentAlbumId"]),
        Index(value = ["dateAddedMillis"])
    ]
)
data class CustomAlbumEntity(
    @PrimaryKey val id: String,
    val boardId: String,
    val parentAlbumId: String? = null,
    val title: String,
    val sourceUrl: String = "",
    val dateAddedMillis: Long = System.currentTimeMillis(),
    val orderIndex: Int = 0,
    val isFavorite: Boolean = false
)
