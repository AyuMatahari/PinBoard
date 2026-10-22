package com.example.model

data class BoardHistoryItem(
    val url: String,
    val title: String,
    val ownerName: String,
    val ownerAvatarUrl: String = "",
    val pinCount: Int = 0,
    val timestamp: Long = System.currentTimeMillis(),
    val isCustom: Boolean = false,
    val boardId: String = ""
)
