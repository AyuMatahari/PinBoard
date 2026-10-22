package com.example.data.local

import androidx.room.Entity
import androidx.room.Index
import com.example.model.PinItem

@Entity(
    tableName = "pins",
    primaryKeys = ["id", "boardId"],
    indices = [
        Index(value = ["boardId"]),
        Index(value = ["orderIndex"]),
        Index(value = ["boardPosition"]),
        Index(value = ["imageUrl"]),
        Index(value = ["albumId"])
    ]
)
data class PinEntity(
    val id: String,
    val boardId: String,
    val title: String,
    val description: String,
    val imageUrl: String,
    val thumbnailUrl: String,
    val author: String,
    val boardName: String,
    val sourceUrl: String,
    val width: Int,
    val height: Int,
    val dominantColor: Long,
    val dateAddedMillis: Long,
    val savesCount: Int,
    val likesCount: Int,
    val fileSizeKb: Long,
    val orderIndex: Int,
    val boardPosition: Int = orderIndex,
    val firstSeenAt: String = "",
    val firstSeenAtMillis: Long = dateAddedMillis,
    val pinterestCreatedAt: String? = null,
    val deliveryStatus: String = "pending",
    val deliveredAt: String? = null,
    val mimeType: String = "image/jpeg",
    val sourceDomain: String = "",
    val isBrokenOrUnreachable: Boolean = false,
    val albumId: String? = null
) {
    fun toPinItem(): PinItem = PinItem(
        id = id,
        title = title,
        description = description,
        imageUrl = imageUrl,
        thumbnailUrl = thumbnailUrl,
        author = author,
        boardName = boardName,
        sourceUrl = sourceUrl,
        width = width,
        height = height,
        dominantColor = dominantColor,
        dateAddedMillis = dateAddedMillis,
        savesCount = savesCount,
        likesCount = likesCount,
        fileSizeKb = fileSizeKb,
        boardPosition = orderIndex,
        firstSeenAt = firstSeenAt,
        firstSeenAtMillis = firstSeenAtMillis,
        pinterestCreatedAt = pinterestCreatedAt,
        deliveryStatus = deliveryStatus,
        deliveredAt = deliveredAt,
        mimeType = mimeType,
        sourceDomain = sourceDomain,
        isBrokenOrUnreachable = isBrokenOrUnreachable,
        albumId = albumId
    )

    companion object {
        fun fromPinItem(item: PinItem, boardId: String, orderIndex: Int): PinEntity = PinEntity(
            id = item.id,
            boardId = boardId,
            title = item.title,
            description = item.description,
            imageUrl = item.imageUrl,
            thumbnailUrl = item.thumbnailUrl,
            author = item.author,
            boardName = item.boardName,
            sourceUrl = item.sourceUrl,
            width = item.width,
            height = item.height,
            dominantColor = item.dominantColor,
            dateAddedMillis = item.dateAddedMillis,
            savesCount = item.savesCount,
            likesCount = item.likesCount,
            fileSizeKb = item.fileSizeKb,
            orderIndex = orderIndex,
            boardPosition = orderIndex,
            firstSeenAt = item.firstSeenAt,
            firstSeenAtMillis = item.firstSeenAtMillis,
            pinterestCreatedAt = item.pinterestCreatedAt,
            deliveryStatus = item.deliveryStatus,
            deliveredAt = item.deliveredAt,
            mimeType = item.mimeType,
            sourceDomain = item.sourceDomain,
            isBrokenOrUnreachable = item.isBrokenOrUnreachable,
            albumId = item.albumId
        )
    }
}
