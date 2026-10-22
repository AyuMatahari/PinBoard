package com.example.util

import java.net.URI
import java.util.Locale

object LinkExtractor {
    // Regex matching http or https URLs in unstructured free-form text
    private val URL_REGEX = Regex(
        """https?://[a-zA-Z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+""",
        RegexOption.IGNORE_CASE
    )

    /**
     * Extracts all distinct HTTP/HTTPS links from unstructured text.
     */
    fun extractLinks(text: String): List<String> {
        if (text.isBlank()) return emptyList()
        return URL_REGEX.findAll(text)
            .map { it.value.trim().trimEnd('.', ',', ';', ':', ')', ']', '>', '"', '\'', '}') }
            .filter { it.isNotBlank() && (it.startsWith("http://", ignoreCase = true) || it.startsWith("https://", ignoreCase = true)) }
            .distinct()
            .toList()
    }

    /**
     * Extracts host domain from a URL (e.g. "https://i.opu.com/images3" -> "i.opu.com").
     */
    fun extractHost(url: String): String {
        return try {
            val uri = URI(url)
            uri.host?.lowercase(Locale.ROOT)?.removePrefix("www.") ?: ""
        } catch (_: Exception) {
            ""
        }
    }

    /**
     * Checks if a URL's host matches any of the given domain patterns.
     * e.g. domain "opu.com" matches "opu.com", "i.opu.com", "cdn.opu.com".
     */
    fun matchesAnyDomain(url: String, domainPatterns: List<String>): Boolean {
        if (domainPatterns.isEmpty()) return false
        val host = extractHost(url)
        if (host.isBlank()) return false

        return domainPatterns.any { rawPattern ->
            val pattern = rawPattern.trim().lowercase(Locale.ROOT)
                .removePrefix("http://")
                .removePrefix("https://")
                .removePrefix("www.")
                .substringBefore("/")
                .trim()
            if (pattern.isBlank()) false
            else host == pattern || host.endsWith(".$pattern")
        }
    }

    /**
     * Helper to derive a clean human-readable title from an image URL filename.
     */
    fun extractTitleFromUrl(url: String): String {
        return try {
            val path = URI(url).path ?: ""
            val lastSegment = path.substringAfterLast('/').substringBeforeLast('.')
            if (lastSegment.isNotBlank() && lastSegment.length > 2) {
                lastSegment.replace('_', ' ').replace('-', ' ').replace('+', ' ')
                    .replaceFirstChar { if (it.isLowerCase()) it.titlecase(Locale.ROOT) else it.toString() }
            } else {
                "Image ${url.hashCode().toString().takeLast(4)}"
            }
        } catch (_: Exception) {
            "Shared Image"
        }
    }
}
