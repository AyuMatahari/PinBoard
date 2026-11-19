package com.example.util

/**
 * MIME / extension resolution with magic-byte fallback.
 *
 * Priority (highest → lowest):
 *   1. Magic-byte sniff       (ground truth — actual image bytes)
 *   2. HTTP Content-Type      (server's claim)
 *   3. pin.mimeType           (cached, if not default)
 *   4. URL extension
 *   5. "image/jpeg"           (final fallback)
 */
object ImageMimeUtils {

    fun resolveMime(
        pinMime: String,
        imageUrl: String,
        contentTypeHeader: String? = null,
        sampleBytes: ByteArray? = null,
        sampleLength: Int = 0
    ): String {
        // 1. Magic bytes
        if (sampleBytes != null && sampleLength > 0) {
            sniffMimeFromBytes(sampleBytes, sampleLength)?.let { return it }
        }
        // 2. Content-Type header
        if (!contentTypeHeader.isNullOrBlank()) {
            val ct = contentTypeHeader.substringBefore(";").trim().lowercase()
            if (ct.startsWith("image/")) return ct
        }
        // 3. pin.mimeType
        val pm = pinMime.lowercase().substringBefore(";").trim()
        if (pm.startsWith("image/") && pm != "image/jpeg") return pm
        // 4. URL
        mimeFromUrl(imageUrl)?.let { return it }
        // 5. jpg fallback
        return "image/jpeg"
    }

    fun sniffMimeFromBytes(bytes: ByteArray, length: Int): String? {
        if (length < 2) return null
        fun b(i: Int): Int = bytes[i].toInt() and 0xFF

        // JPEG: FF D8 FF
        if (length >= 3 && b(0) == 0xFF && b(1) == 0xD8 && b(2) == 0xFF) return "image/jpeg"

        // PNG: 89 50 4E 47 0D 0A 1A 0A
        if (length >= 8 && b(0) == 0x89 && b(1) == 0x50 && b(2) == 0x4E && b(3) == 0x47
            && b(4) == 0x0D && b(5) == 0x0A && b(6) == 0x1A && b(7) == 0x0A) return "image/png"

        // GIF: 'GIF8' (GIF87a / GIF89a)
        if (length >= 4 && b(0) == 0x47 && b(1) == 0x49 && b(2) == 0x46 && b(3) == 0x38) return "image/gif"

        // WebP: 'RIFF' ..... 'WEBP'
        if (length >= 12 && b(0) == 0x52 && b(1) == 0x49 && b(2) == 0x46 && b(3) == 0x46
            && b(8) == 0x57 && b(9) == 0x45 && b(10) == 0x42 && b(11) == 0x50) return "image/webp"

        // BMP: 'BM'
        if (b(0) == 0x42 && b(1) == 0x4D) return "image/bmp"

        // AVIF / HEIC: ....'ftyp'brand
        if (length >= 12 && b(4) == 0x66 && b(5) == 0x74 && b(6) == 0x79 && b(7) == 0x70) {
            val brand = String(bytes, 8, 4, Charsets.US_ASCII)
            when (brand) {
                "avif", "avis" -> return "image/avif"
                "heic", "heix", "heif", "mif1", "msf1" -> return "image/heic"
            }
        }

        // SVG (loose — starts with '<svg' or '<?xml')
        if (length >= 4) {
            val head = String(bytes, 0, minOf(length, 64), Charsets.US_ASCII).trimStart()
            if (head.startsWith("<svg", ignoreCase = true)) return "image/svg+xml"
        }

        return null
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
