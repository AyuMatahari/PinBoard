package com.example.model

/**
 * Represents a date-grouped collection ("Album") of pins.
 * Grouped either by day (e.g. "Oct 11, 2026") or by month (e.g. "October 2026").
 */
data class DateAlbum(
    val id: String,
    val title: String,
    val isMonthly: Boolean,
    val pins: List<PinItem>,
    val dateMillis: Long,
    val isFavorite: Boolean = false,
    val isCustomAlbum: Boolean = false,
    val parentAlbumId: String? = null,
    val subAlbums: List<DateAlbum> = emptyList()
)
