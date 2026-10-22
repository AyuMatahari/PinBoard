package com.example.data.local

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

/**
 * Event delivery outbox matching Implementation Brief Sections 18 & 20:
 * When a newly observed Pin is detected:
 * {
 *   "event_id": "pinterest:{board_id}:{pin_id}",
 *   "event": "pin_detected",
 *   "pin_id": "123456789",
 *   "board_url": "https://www.pinterest.com/user/board/",
 *   "board_position": 42,
 *   "first_seen_at": "2026-09-28T12:00:00Z",
 *   "pin_url": "https://www.pinterest.com/pin/123456789/",
 *   "image_url": "https://i.pinimg.com/..."
 * }
 */
@Entity(
    tableName = "pin_events",
    indices = [
        Index(value = ["board_id"]),
        Index(value = ["pin_id"]),
        Index(value = ["delivery_status"])
    ]
)
data class PinEventEntity(
    @PrimaryKey
    @ColumnInfo(name = "event_id") val eventId: String, // "pinterest:{board_id}:{pin_id}"
    @ColumnInfo(name = "board_id") val boardId: String,
    @ColumnInfo(name = "pin_id") val pinId: String,
    @ColumnInfo(name = "event") val event: String = "pin_detected",
    @ColumnInfo(name = "board_url") val boardUrl: String,
    @ColumnInfo(name = "board_position") val boardPosition: Int,
    @ColumnInfo(name = "first_seen_at") val firstSeenAt: String,
    @ColumnInfo(name = "pin_url") val pinUrl: String,
    @ColumnInfo(name = "image_url") val imageUrl: String?,
    @ColumnInfo(name = "delivery_status") val deliveryStatus: String = "pending",
    @ColumnInfo(name = "delivered_at") val deliveredAt: String? = null,
    @ColumnInfo(name = "retry_count") val retryCount: Int = 0,
    @ColumnInfo(name = "created_at_millis") val createdAtMillis: Long = System.currentTimeMillis()
)
