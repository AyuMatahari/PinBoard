package com.example.model

data class PinterestBoard(
    val id: String,
    val title: String,
    val slug: String,
    val ownerUsername: String,
    val ownerDisplayName: String,
    val ownerAvatarUrl: String = "",
    val pinCount: Int,
    val followerCount: Int = 1250,
    val boardUrl: String,
    val description: String = "",
    val pins: List<PinItem> = emptyList(),
    val isCustom: Boolean = false,
    val customDomains: List<String> = emptyList(),
    val isDefault: Boolean = false,
    val isSpecialNonDeletable: Boolean = false
)
