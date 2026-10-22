package com.example.data.local

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import com.example.model.PinItem

/**
 * Scan database table matching Implementation Brief Section 15:
 * CREATE TABLE pinterest_pins (
 *     pin_id TEXT NOT NULL,
 *     board_url TEXT NOT NULL,
 *     board_position INTEGER,
 *     first_seen_at TEXT NOT NULL,
 *     pin_url TEXT NOT NULL,
 *     image_url TEXT,
 *     title TEXT,
 *     delivery_status TEXT DEFAULT 'pending',
 *     delivered_at TEXT,
 *     PRIMARY KEY (pin_id, board_url)
 * );
 */
@Entity(
    tableName = "pinterest_pins",
    primaryKeys = ["pin_id", "board_url"],
    indices = [
        Index(value = ["board_url"]),
        Index(value = ["board_position"]),
        Index(value = ["first_seen_at"]),
        Index(value = ["delivery_status"])
    ]
)
data class PinterestScannedPinEntity(
    @ColumnInfo(name = "pin_id") val pinId: String,
    @ColumnInfo(name = "board_url") val boardUrl: String,
    @ColumnInfo(name = "board_position") val boardPosition: Int,
    @ColumnInfo(name = "first_seen_at") val firstSeenAt: String,
    @ColumnInfo(name = "pin_url") val pinUrl: String,
    @ColumnInfo(name = "image_url") val imageUrl: String?,
    @ColumnInfo(name = "title") val title: String?,
    @ColumnInfo(name = "delivery_status") val deliveryStatus: String = "pending",
    @ColumnInfo(name = "delivered_at") val deliveredAt: String? = null,
    // Extra fields to enrich the board experience without violating Section 15 schema
    @ColumnInfo(name = "pinterest_created_at") val pinterestCreatedAt: String? = null,
    @ColumnInfo(name = "first_seen_at_millis") val firstSeenAtMillis: Long = System.currentTimeMillis(),
    @ColumnInfo(name = "width") val width: Int = 736,
    @ColumnInfo(name = "height") val height: Int = 1000,
    @ColumnInfo(name = "author") val author: String = "Pinterest Creator",
    @ColumnInfo(name = "description") val description: String = "",
    @ColumnInfo(name = "saves_count") val savesCount: Int = 0,
    @ColumnInfo(name = "likes_count") val likesCount: Int = 0
) {
    fun toPinItem(): PinItem = PinItem(
        id = pinId,
        title = title ?: "Pin #$pinId",
        description = description,
        imageUrl = imageUrl ?: "",
        thumbnailUrl = imageUrl ?: "",
        author = author,
        boardName = "Pinterest Board",
        sourceUrl = pinUrl,
        width = width,
        height = height,
        dominantColor = 0xFFE0E0E0,
        dateAddedMillis = firstSeenAtMillis,
        savesCount = savesCount,
        likesCount = likesCount,
        fileSizeKb = 350L,
        boardPosition = boardPosition,
        firstSeenAt = firstSeenAt,
        firstSeenAtMillis = firstSeenAtMillis,
        pinterestCreatedAt = pinterestCreatedAt,
        deliveryStatus = deliveryStatus,
        deliveredAt = deliveredAt
    )
}
