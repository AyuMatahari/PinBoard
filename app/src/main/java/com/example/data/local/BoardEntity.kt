package com.example.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey
import com.example.model.PinterestBoard

@Entity(tableName = "boards")
data class BoardEntity(
    @PrimaryKey val id: String,
    val title: String,
    val slug: String,
    val ownerUsername: String,
    val ownerDisplayName: String,
    val ownerAvatarUrl: String,
    val pinCount: Int,
    val followerCount: Int,
    val boardUrl: String,
    val description: String,
    val isCustom: Boolean = false,
    val customDomains: String = "", // Comma-separated list of domains e.g. "opu.com, unsplash.com"
    val isDefault: Boolean = false,
    val isSpecialNonDeletable: Boolean = false,
    val lastUpdatedMillis: Long = System.currentTimeMillis()
) {
    fun toPinterestBoard(pins: List<com.example.model.PinItem>): PinterestBoard = PinterestBoard(
        id = id,
        title = title,
        slug = slug,
        ownerUsername = ownerUsername,
        ownerDisplayName = ownerDisplayName,
        ownerAvatarUrl = ownerAvatarUrl,
        pinCount = pinCount.coerceAtLeast(pins.size),
        followerCount = followerCount,
        boardUrl = boardUrl,
        description = description,
        pins = pins,
        isCustom = isCustom,
        customDomains = if (customDomains.isBlank()) emptyList() else customDomains.split(",").map { it.trim() }.filter { it.isNotBlank() },
        isDefault = isDefault,
        isSpecialNonDeletable = isSpecialNonDeletable
    )

    companion object {
        fun fromPinterestBoard(board: PinterestBoard): BoardEntity = BoardEntity(
            id = board.id,
            title = board.title,
            slug = board.slug,
            ownerUsername = board.ownerUsername,
            ownerDisplayName = board.ownerDisplayName,
            ownerAvatarUrl = board.ownerAvatarUrl,
            pinCount = board.pinCount,
            followerCount = board.followerCount,
            boardUrl = board.boardUrl,
            description = board.description,
            isCustom = board.isCustom,
            customDomains = board.customDomains.joinToString(", "),
            isDefault = board.isDefault,
            isSpecialNonDeletable = board.isSpecialNonDeletable,
            lastUpdatedMillis = System.currentTimeMillis()
        )
    }
}
