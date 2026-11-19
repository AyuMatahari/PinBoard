package com.example.util

/**
 * Centralised MIME / extension resolution for images.
 *
 * Priority (highest → lowest):
 *   1. HTTP Content-Type header (authoritative — reflects actual bytes)
 *   2. pin.mimeType if it isn't the default "image/jpeg"
 *   3. URL extension
 *   4. "image/jpeg" fallback
 *
 * This is what makes GIFs survive round-trips: Pinterest's CDN may serve
 * .jpg-named URLs that return `Content-Type: image/gif`, so we always
 * believe the actual server response over the filename.
 */
object ImageMimeUtils {

    fun resolveMime(pinMime: String, imageUrl: String, contentTypeHeader: String? = null): String {
        if (!contentTypeHeader.isNullOrBlank() && contentTypeHeader.startsWith("image/", ignoreCase = true)) {
            return contentTypeHeader.substringBefore(";").trim().lowercase()
        }
        val pm = pinMime.lowercase().substringBefore(";").trim()
        if (pm.isNotBlank() && pm != "image/jpeg") return pm
        val fromUrl = mimeFromUrl(imageUrl)
        if (fromUrl != null) return fromUrl
        return pm.ifBlank { "image/jpeg" }
    }

    fun mimeFromUrl(url: String): String? {
        if (url.isBlank()) return null
        val lower = url.lowercase().substringBefore('?').substringBefore('#')
        return when {
            lower.endsWith(".gif") -> "image/gif"
            lower.endsWith(".png") -> "image/png"
            lower.endsWith(".webp") -> "image/webp"
            lower.endsWith(".avif") -> "image/avif"
            lower.endsWith(".svg") -> "image/svg+xml"
            lower.endsWith(".bmp") -> "image/bmp"
            lower.endsWith(".heic") -> "image/heic"
            lower.endsWith(".jpeg") || lower.endsWith(".jpg") -> "image/jpeg"
            else -> null
        }
    }

    fun extensionFor(mime: String): String = when (mime.lowercase().substringBefore(";").trim()) {
        "image/gif" -> "gif"
        "image/png" -> "png"
        "image/webp" -> "webp"
        "image/avif" -> "avif"
        "image/svg+xml" -> "svg"
        "image/bmp" -> "bmp"
        "image/heic" -> "heic"
        else -> "jpg"
    }

    fun isAnimated(mime: String, url: String): Boolean {
        if (mime.lowercase().contains("gif")) return true
        val lower = url.lowercase().substringBefore('?').substringBefore('#')
        return lower.endsWith(".gif")
    }
}
