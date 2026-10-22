package com.example.model

data class PinItem(
    val id: String,
    val title: String,
    val description: String = "",
    val imageUrl: String,
    val thumbnailUrl: String = imageUrl,
    val author: String = "Pinterest Creator",
    val boardName: String = "Inspiration Board",
    val sourceUrl: String = "",
    val width: Int = 1080,
    val height: Int = 1440,
    val dominantColor: Long = 0xFFEFEFEF,
    val dateAddedMillis: Long = System.currentTimeMillis(),
    val savesCount: Int = 0,
    val likesCount: Int = 0,
    val fileSizeKb: Long = 250L,
    // Fields based on Android Pinterest Board Scanner brief (Sections 15-18)
    val boardPosition: Int = 0,
    val firstSeenAt: String = "",
    val firstSeenAtMillis: Long = dateAddedMillis,
    val pinterestCreatedAt: String? = null,
    val deliveryStatus: String = "pending",
    val deliveredAt: String? = null,
    // User requirement: "the images may have name and media information too. handle this."
    val mimeType: String = "image/jpeg",
    val sourceDomain: String = "",
    val isBrokenOrUnreachable: Boolean = false,
    val albumId: String? = null
) {
    val aspectRatio: Float
        get() = if (height > 0 && width > 0) {
            val ratio = width.toFloat() / height.toFloat()
            if (ratio.isNaN() || ratio.isInfinite() || ratio <= 0f) 0.75f else ratio.coerceIn(0.4f, 2.5f)
        } else 0.75f

    val formattedDimensions: String
        get() = "${width} × ${height}"

    val formattedFileSize: String
        get() = if (fileSizeKb >= 1024) {
            String.format(java.util.Locale.US, "%.1f MB", fileSizeKb / 1024.0)
        } else {
            "$fileSizeKb KB"
        }

    val displayDomain: String
        get() = sourceDomain.ifBlank {
            try {
                java.net.URI(sourceUrl.ifBlank { imageUrl }).host?.removePrefix("www.") ?: ""
            } catch (_: Exception) {
                ""
            }
        }
}
