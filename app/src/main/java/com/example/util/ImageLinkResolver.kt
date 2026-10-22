package com.example.util

import android.graphics.BitmapFactory
import com.example.model.PinItem
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.security.MessageDigest
import java.util.Locale
import java.util.concurrent.TimeUnit

/**
 * Data class representing an extracted image candidate for scoring.
 * Based on the two-pass browserless extraction architecture.
 */
data class ImageCandidate(
    val url: String,
    var source: String,
    var score: Float = 0f,
    var preliminaryScore: Float = 0f,
    var width: Int? = null,
    var height: Int? = null,
    var alt: String = "",
    var context: String = "",
    val sources: MutableSet<String> = mutableSetOf(source)
)

object ImageLinkResolver {
    private val client: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(12, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .followRedirects(true)
            .followSslRedirects(true)
            .build()
    }

    private const val USER_AGENT =
        "Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"

    private const val TOP_N_CANDIDATES = 5
    private const val MAX_IMAGE_BYTES = 512 * 1024 // 512 KB

    // Regexes for HTML parsing
    private val META_TAG_REGEX = Regex("""<meta\b[^>]*>""", RegexOption.IGNORE_CASE)
    private val SCRIPT_TAG_REGEX = Regex("""<script\b([^>]*)>([\s\S]*?)</script>""", RegexOption.IGNORE_CASE)
    private val IMG_TAG_REGEX = Regex("""<img\b[^>]*>""", RegexOption.IGNORE_CASE)
    private val SOURCE_TAG_REGEX = Regex("""<source\b[^>]*>""", RegexOption.IGNORE_CASE)
    private val ATTR_REGEX = Regex("""([a-zA-Z0-9_:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")

    // Title Tag Regexes
    private val OG_TITLE_REGEX = Regex("""<meta[^>]+property=["']og:title["'][^>]+content=["']([^"']+)["']""", RegexOption.IGNORE_CASE)
    private val TWITTER_TITLE_REGEX = Regex("""<meta[^>]+name=["']twitter:title["'][^>]+content=["']([^"']+)["']""", RegexOption.IGNORE_CASE)
    private val TITLE_TAG_REGEX = Regex("""<title[^>]*>([^<]+)</title>""", RegexOption.IGNORE_CASE)

    // Image Board Webpage patterns (4chan, Boorus, opened image viewers)
    private val FOURCHAN_FILE_REGEX = Regex("""<div[^>]+class=["']fileText["'][^>]*>[\s\S]*?<a[^>]+href=["']([^"']+)["']""", RegexOption.IGNORE_CASE)
    private val FOURCHAN_THUMB_REGEX = Regex("""<a[^>]+class=["']fileThumb["'][^>]+href=["']([^"']+)["']""", RegexOption.IGNORE_CASE)
    private val BOORU_IMAGE_ID_REGEX = Regex("""<img[^>]+id=["']image["'][^>]+src=["']([^"']+)["']""", RegexOption.IGNORE_CASE)
    private val BOORU_IMAGE_ID_ALT_REGEX = Regex("""<img[^>]+src=["']([^"']+)["'][^>]+id=["']image["']""", RegexOption.IGNORE_CASE)
    private val BOORU_CONTAINER_REGEX = Regex("""data-file-url=["']([^"']+)["']""", RegexOption.IGNORE_CASE)
    private val ORIGINAL_FILE_LINK_REGEX = Regex("""<a[^>]+class=["'][^"']*original-file[^"']*["'][^>]+href=["']([^"']+)["']""", RegexOption.IGNORE_CASE)

    /**
     * Resolves a URL into a PinItem.
     * Automatically decides whether the link is an image link or webpage:
     * - If image link: uses direct image URL, determines dimensions & size.
     * - If webpage: runs browserless two-pass main image extraction (candidates -> preliminary scoring -> top 5 dimension check -> final scoring).
     * Saves original webpage link in sourceUrl, and actual image URL in imageUrl.
     */
    suspend fun resolveLink(url: String, boardName: String = "Custom Board"): PinItem = withContext(Dispatchers.IO) {
        val cleanUrl = url.trim()
        val domain = LinkExtractor.extractHost(cleanUrl)
        val defaultTitle = LinkExtractor.extractTitleFromUrl(cleanUrl)
        val uniqueId = generateDeterministicPinId(cleanUrl)

        var finalImageUrl = cleanUrl
        var finalTitle = defaultTitle
        var mimeType = guessMimeType(cleanUrl)
        var fileSizeKb = 250L
        var isBroken = false
        var imageWidth = 1080
        var imageHeight = 1350
        val sourceWebpageUrl = cleanUrl

        try {
            val request = Request.Builder()
                .url(cleanUrl)
                .header("User-Agent", USER_AGENT)
                .header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,image/*,*/*;q=0.8")
                .header("Accept-Language", "en-US,en;q=0.9")
                .build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    isBroken = true
                } else {
                    val effectiveUrl = response.request.url.toString()
                    val contentType = response.header("Content-Type")?.lowercase(Locale.ROOT) ?: ""
                    val contentLength = response.header("Content-Length")?.toLongOrNull() ?: 0L
                    if (contentLength > 0) {
                        fileSizeKb = (contentLength / 1024L).coerceAtLeast(1L)
                    }

                    val isDirectImage = contentType.startsWith("image/")

                    if (isDirectImage) {
                        // Directly an image link
                        mimeType = contentType.substringBefore(";")
                        finalImageUrl = effectiveUrl

                        // Read dimensions if available
                        val dims = getImageDimensions(effectiveUrl)
                        if (dims != null) {
                            imageWidth = dims.first
                            imageHeight = dims.second
                        }
                    } else {
                        // Webpage link! Read HTML up to 512KB to extract main header / lead / board image
                        val htmlBody = response.body?.source()?.let { source ->
                            source.request(524288) // 512 KB
                            val buffer = source.buffer
                            val maxBytes = minOf(524288L, buffer.size)
                            buffer.clone().readUtf8(maxBytes)
                        } ?: ""

                        // Extract Page Title
                        val extractedTitle = extractTitleFromHtml(htmlBody)
                        if (extractedTitle.isNotBlank()) {
                            finalTitle = extractedTitle
                        }

                        // Run browserless two-pass main image extractor
                        val bestCandidate = extractMainImageTwoPass(htmlBody, effectiveUrl)
                        if (bestCandidate != null && bestCandidate.url.isNotBlank()) {
                            finalImageUrl = bestCandidate.url
                            mimeType = guessMimeType(finalImageUrl)
                            if (bestCandidate.width != null && bestCandidate.height != null) {
                                imageWidth = bestCandidate.width!!
                                imageHeight = bestCandidate.height!!
                            }

                            // Quick check for Content-Length and real Content-Type
                            try {
                                val imgCheckRequest = Request.Builder()
                                    .url(finalImageUrl)
                                    .header("User-Agent", USER_AGENT)
                                    .header("Referer", effectiveUrl)
                                    .build()

                                client.newCall(imgCheckRequest).execute().use { imgResp ->
                                    if (imgResp.isSuccessful) {
                                        val imgType = imgResp.header("Content-Type")?.lowercase(Locale.ROOT) ?: ""
                                        if (imgType.startsWith("image/")) {
                                            mimeType = imgType.substringBefore(";")
                                        }
                                        val imgLen = imgResp.header("Content-Length")?.toLongOrNull() ?: 0L
                                        if (imgLen > 0) {
                                            fileSizeKb = (imgLen / 1024L).coerceAtLeast(1L)
                                        }
                                    }
                                }
                            } catch (_: Exception) {}
                        } else {
                            // No image could be identified
                            isBroken = true
                        }
                    }
                }
            }
        } catch (_: Exception) {
            isBroken = true
        }

        PinItem(
            id = uniqueId,
            title = finalTitle,
            description = if (sourceWebpageUrl != finalImageUrl) "Imported from $domain" else "",
            imageUrl = finalImageUrl,
            thumbnailUrl = finalImageUrl,
            author = domain.ifBlank { "Web Source" },
            boardName = boardName,
            sourceUrl = sourceWebpageUrl,
            width = imageWidth,
            height = imageHeight,
            dominantColor = 0xFF2D2D2DL,
            dateAddedMillis = System.currentTimeMillis(),
            fileSizeKb = fileSizeKb,
            mimeType = mimeType,
            sourceDomain = domain,
            isBrokenOrUnreachable = isBroken
        )
    }

    /**
     * Resolves multiple main images from a webpage URL in document order (first main image first, last image last).
     * If the URL is directly an image, returns a single-item list.
     */
    suspend fun resolveMultipleLinks(url: String, boardName: String = "Custom Board"): List<PinItem> = withContext(Dispatchers.IO) {
        val cleanUrl = url.trim()
        val domain = LinkExtractor.extractHost(cleanUrl)
        val defaultTitle = LinkExtractor.extractTitleFromUrl(cleanUrl)

        try {
            val request = Request.Builder()
                .url(cleanUrl)
                .header("User-Agent", USER_AGENT)
                .header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,image/*,*/*;q=0.8")
                .header("Accept-Language", "en-US,en;q=0.9")
                .build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    return@withContext listOf(resolveLink(cleanUrl, boardName))
                }

                val effectiveUrl = response.request.url.toString()
                val contentType = response.header("Content-Type")?.lowercase(Locale.ROOT) ?: ""
                val isDirectImage = contentType.startsWith("image/")

                if (isDirectImage) {
                    return@withContext listOf(resolveLink(cleanUrl, boardName))
                }

                // Read HTML body up to 1 MB for full article / gallery extraction
                val htmlBody = response.body?.source()?.let { source ->
                    source.request(1048576) // 1 MB
                    val buffer = source.buffer
                    val maxBytes = minOf(1048576L, buffer.size)
                    buffer.clone().readUtf8(maxBytes)
                } ?: ""

                val extractedTitle = extractTitleFromHtml(htmlBody).ifBlank { defaultTitle }

                // Extract all candidate images in document order
                val candidateList = extractOrderedContentImages(htmlBody, effectiveUrl)

                if (candidateList.isEmpty()) {
                    return@withContext listOf(resolveLink(cleanUrl, boardName))
                }

                val baseTime = System.currentTimeMillis()
                val resultPins = candidateList.mapIndexed { index, cand ->
                    val pinId = generateDeterministicPinId("${cleanUrl}_multi_$index")
                    val itemTitle = if (cand.alt.isNotBlank() && cand.alt.length in 3..120 && !cand.alt.contains("image", ignoreCase = true)) {
                        cand.alt.trim()
                    } else if (index == 0) {
                        extractedTitle
                    } else {
                        "$extractedTitle (${index + 1})"
                    }

                    PinItem(
                        id = pinId,
                        title = itemTitle,
                        description = "Image ${index + 1} of ${candidateList.size} from $domain",
                        imageUrl = cand.url,
                        thumbnailUrl = cand.url,
                        author = domain.ifBlank { "Web Source" },
                        boardName = boardName,
                        sourceUrl = cleanUrl,
                        width = cand.width ?: 1080,
                        height = cand.height ?: 1440,
                        dominantColor = 0xFF2D2D2DL,
                        dateAddedMillis = baseTime + (index * 10L), // Strictly increasing for stable sorting
                        boardPosition = index,
                        fileSizeKb = 250L,
                        mimeType = guessMimeType(cand.url),
                        sourceDomain = domain,
                        isBrokenOrUnreachable = false
                    )
                }

                return@withContext resultPins
            }
        } catch (_: Exception) {
            return@withContext listOf(resolveLink(cleanUrl, boardName))
        }
    }

    fun extractOrderedContentImages(html: String, baseUrl: String): List<ImageCandidate> {
        val seenUrls = mutableSetOf<String>()
        val orderedCandidates = mutableListOf<ImageCandidate>()

        // 1. Check for lead / meta / json-ld / booru images that might appear first
        val leadImages = mutableListOf<ImageCandidate>()
        leadImages.addAll(extractImageBoardImages(html, baseUrl))
        leadImages.addAll(extractMetaImages(html, baseUrl))
        leadImages.addAll(extractJsonLdImages(html, baseUrl))

        val negativeWords = setOf(
            "logo", "icon", "avatar", "profile", "emoji",
            "favicon", "sprite", "badge", "button", "tracking",
            "pixel", "thumb_small", "ad-", "ad_", "advertisement",
            "share-button", "social-share", "navigation", "nav-"
        )

        fun isUnwanted(url: String, alt: String, context: String): Boolean {
            val lower = "$url $alt $context".lowercase(Locale.ROOT)
            if (url.startsWith("data:")) return true
            if (url.endsWith(".svg", ignoreCase = true)) return true
            for (w in negativeWords) {
                if (lower.contains(w)) return true
            }
            return false
        }

        // Add lead images if they are good quality
        for (cand in leadImages) {
            val norm = normalizeUrl(cand.url)
            if (!seenUrls.contains(norm) && !isUnwanted(cand.url, cand.alt, cand.context)) {
                seenUrls.add(norm)
                orderedCandidates.add(cand)
            }
        }

        // 2. Sequential scan of <img> and <a> tags in HTML in document order
        val aTagWithImgRegex = Regex("""<a\b[^>]*href=["']([^"']+\.(?:jpe?g|png|webp|gif|avif)(?:\?[^"']*)?)["'][^>]*>([\s\S]*?<img\b[^>]*>)""", RegexOption.IGNORE_CASE)
        val linkedMatches = aTagWithImgRegex.findAll(html).toList()
        for (m in linkedMatches) {
            val fullImgUrl = resolveAbsoluteUrl(baseUrl, m.groupValues[1])
            val imgTag = m.groupValues[2]
            val attrs = parseTagAttributes(imgTag)
            val alt = attrs["alt"] ?: ""
            val cls = attrs["class"] ?: ""
            val norm = normalizeUrl(fullImgUrl)
            if (!seenUrls.contains(norm) && !isUnwanted(fullImgUrl, alt, cls)) {
                seenUrls.add(norm)
                orderedCandidates.add(
                    ImageCandidate(
                        url = fullImgUrl,
                        source = "LINKED_IMG",
                        alt = alt,
                        context = cls,
                        sources = mutableSetOf("LINKED_IMG")
                    )
                )
            }
        }

        // 3. Scan all <img> tags in document order
        IMG_TAG_REGEX.findAll(html).forEach { match ->
            val attrs = parseTagAttributes(match.value)
            val rawUrl = getImageUrlFromAttrs(attrs)
            if (!rawUrl.isNullOrBlank() && looksLikeImageUrl(rawUrl)) {
                val fullUrl = resolveAbsoluteUrl(baseUrl, rawUrl)
                val norm = normalizeUrl(fullUrl)
                val alt = attrs["alt"] ?: ""
                val cls = attrs["class"] ?: ""
                val width = attrs["width"]?.toIntOrNull()
                val height = attrs["height"]?.toIntOrNull()

                val tooSmall = (width != null && width < 120) || (height != null && height < 120)

                if (!tooSmall && !seenUrls.contains(norm) && !isUnwanted(fullUrl, alt, cls)) {
                    seenUrls.add(norm)
                    orderedCandidates.add(
                        ImageCandidate(
                            url = fullUrl,
                            source = "IMG",
                            alt = alt,
                            context = cls,
                            width = width,
                            height = height,
                            sources = mutableSetOf("IMG")
                        )
                    )
                }
            }
        }

        return orderedCandidates
    }

    /**
     * Browserless two-pass main-image extractor:
     * 1. Extract all candidates from HTML (meta, JSON-LD, imageboard, img, picture/srcset).
     * 2. Calculate cheap preliminary score for each candidate.
     * 3. Sort and take top N candidates (default 5).
     * 4. Download bounded image data for those top candidates and read actual width/height.
     * 5. Recalculate final score with dimensions.
     * 6. Return candidate with the highest final score.
     */
    fun extractMainImageTwoPass(html: String, pageUrl: String): ImageCandidate? {
        val candidates = mutableListOf<ImageCandidate>()

        // 1. Meta images (OpenGraph, Twitter, Thumbnail, Itemprop)
        candidates.addAll(extractMetaImages(html, pageUrl))

        // 2. JSON-LD images
        candidates.addAll(extractJsonLdImages(html, pageUrl))

        // 3. Image board specific patterns
        candidates.addAll(extractImageBoardImages(html, pageUrl))

        // 4. HTML img & picture/source tags
        candidates.addAll(extractHtmlImages(html, pageUrl))

        // Merge duplicates by normalized URL
        val merged = mergeDuplicates(candidates).toMutableList()
        if (merged.isEmpty()) return null

        // Pass 1: Cheap preliminary scoring
        for (candidate in merged) {
            candidate.preliminaryScore = scoreCandidate(candidate, pageUrl, useDimensions = false)
            candidate.score = candidate.preliminaryScore
        }

        merged.sortByDescending { it.preliminaryScore }

        // Top N candidates for dimension inspection
        val topCandidates = merged.take(TOP_N_CANDIDATES)

        // Pass 2: Download bounded data to read actual image dimensions
        for (candidate in topCandidates) {
            val dimensions = getImageDimensions(candidate.url)
            if (dimensions != null) {
                candidate.width = dimensions.first
                candidate.height = dimensions.second
            }
            candidate.score = scoreCandidate(candidate, pageUrl, useDimensions = true)
        }

        // Final sort
        merged.sortByDescending { it.score }
        return merged.firstOrNull()
    }

    // =========================================================
    // Candidate Extraction
    // =========================================================

    private fun extractMetaImages(html: String, baseUrl: String): List<ImageCandidate> {
        val candidates = mutableListOf<ImageCandidate>()

        META_TAG_REGEX.findAll(html).forEach { match ->
            val attrs = parseTagAttributes(match.value)
            val prop = (attrs["property"] ?: attrs["name"] ?: "").lowercase(Locale.ROOT).trim()
            val content = attrs["content"]?.trim() ?: ""

            if (content.isNotBlank() && !content.startsWith("data:")) {
                when {
                    prop in setOf("og:image", "og:image:url", "og:image:secure_url") -> {
                        candidates.add(
                            ImageCandidate(
                                url = resolveAbsoluteUrl(baseUrl, content),
                                source = "OPEN_GRAPH",
                                score = 100f,
                                sources = mutableSetOf("OPEN_GRAPH")
                            )
                        )
                    }
                    prop in setOf("twitter:image", "twitter:image:src") -> {
                        candidates.add(
                            ImageCandidate(
                                url = resolveAbsoluteUrl(baseUrl, content),
                                source = "TWITTER",
                                score = 90f,
                                sources = mutableSetOf("TWITTER")
                            )
                        )
                    }
                    prop == "thumbnail" || prop == "image" || attrs["itemprop"]?.equals("image", ignoreCase = true) == true -> {
                        candidates.add(
                            ImageCandidate(
                                url = resolveAbsoluteUrl(baseUrl, content),
                                source = "META",
                                score = 60f,
                                sources = mutableSetOf("META")
                            )
                        )
                    }
                }
            }
        }

        return candidates
    }

    private fun extractJsonLdImages(html: String, baseUrl: String): List<ImageCandidate> {
        val candidates = mutableListOf<ImageCandidate>()

        SCRIPT_TAG_REGEX.findAll(html).forEach { match ->
            val openTag = match.groupValues[1]
            if (openTag.contains("application/ld+json", ignoreCase = true)) {
                val raw = match.groupValues[2].trim()
                    .removePrefix("<!--").removeSuffix("-->")
                    .removePrefix("/*<![CDATA[*/").removeSuffix("/*]]>*/")
                    .trim()
                if (raw.isNotBlank()) {
                    // Direct string or array: "image": "..." or "image": ["..."]
                    val directRegex = Regex(""""(?:image|thumbnailUrl|contentUrl|leadImage)"\s*:\s*(?:["']([^"']+)["']|\[\s*["']([^"']+)["'])""", RegexOption.IGNORE_CASE)
                    directRegex.findAll(raw).forEach { m ->
                        val u = m.groupValues[1].ifEmpty { m.groupValues[2] }.trim()
                        if (u.isNotBlank() && looksLikeImageUrl(u)) {
                            candidates.add(
                                ImageCandidate(
                                    url = resolveAbsoluteUrl(baseUrl, u),
                                    source = "JSON_LD",
                                    score = 70f,
                                    sources = mutableSetOf("JSON_LD")
                                )
                            )
                        }
                    }

                    // Nested object: "image": { ... "url": "..." }
                    val nestedRegex = Regex(""""(?:image|thumbnailUrl)"\s*:\s*\{[^}]*"(?:url|contentUrl)"\s*:\s*["']([^"']+)["']""", RegexOption.IGNORE_CASE)
                    nestedRegex.findAll(raw).forEach { m ->
                        val u = m.groupValues[1].trim()
                        if (u.isNotBlank() && looksLikeImageUrl(u)) {
                            candidates.add(
                                ImageCandidate(
                                    url = resolveAbsoluteUrl(baseUrl, u),
                                    source = "JSON_LD",
                                    score = 70f,
                                    sources = mutableSetOf("JSON_LD")
                                )
                            )
                        }
                    }

                    // Also try JSONObject traversal if available at runtime
                    try {
                        if (raw.startsWith("{")) {
                            val json = JSONObject(raw)
                            findJsonImages(json).forEach { imgUrl ->
                                candidates.add(
                                    ImageCandidate(
                                        url = resolveAbsoluteUrl(baseUrl, imgUrl),
                                        source = "JSON_LD",
                                        score = 70f,
                                        sources = mutableSetOf("JSON_LD")
                                    )
                                )
                            }
                        } else if (raw.startsWith("[")) {
                            val arr = JSONArray(raw)
                            for (i in 0 until arr.length()) {
                                val obj = arr.optJSONObject(i)
                                if (obj != null) {
                                    findJsonImages(obj).forEach { imgUrl ->
                                        candidates.add(
                                            ImageCandidate(
                                                url = resolveAbsoluteUrl(baseUrl, imgUrl),
                                                source = "JSON_LD",
                                                score = 70f,
                                                sources = mutableSetOf("JSON_LD")
                                            )
                                        )
                                    }
                                }
                            }
                        }
                    } catch (_: Throwable) {}
                }
            }
        }

        return candidates
    }

    private fun findJsonImages(obj: JSONObject): List<String> {
        val found = mutableListOf<String>()
        val keys = obj.keys()
        while (keys.hasNext()) {
            val key = keys.next()
            val lower = key.lowercase(Locale.ROOT)
            val value = obj.opt(key) ?: continue

            if (lower in setOf("image", "thumbnailurl", "contenturl", "leadimage")) {
                extractImageValues(value, found)
            } else if (value is JSONObject) {
                found.addAll(findJsonImages(value))
            } else if (value is JSONArray) {
                for (i in 0 until value.length()) {
                    val item = value.opt(i)
                    if (item is JSONObject) {
                        found.addAll(findJsonImages(item))
                    }
                }
            }
        }
        return found
    }

    private fun extractImageValues(value: Any, found: MutableList<String>) {
        when (value) {
            is String -> if (value.isNotBlank() && !value.startsWith("data:")) found.add(value)
            is JSONArray -> {
                for (i in 0 until value.length()) {
                    val item = value.opt(i)
                    if (item is String && item.isNotBlank() && !item.startsWith("data:")) {
                        found.add(item)
                    } else if (item is JSONObject) {
                        val u = item.optString("url", "").ifBlank { item.optString("contentUrl", "") }
                        if (u.isNotBlank() && !u.startsWith("data:")) found.add(u)
                    }
                }
            }
            is JSONObject -> {
                val u = value.optString("url", "").ifBlank { value.optString("contentUrl", "") }
                if (u.isNotBlank() && !u.startsWith("data:")) found.add(u)
            }
        }
    }

    private fun extractImageBoardImages(html: String, baseUrl: String): List<ImageCandidate> {
        val candidates = mutableListOf<ImageCandidate>()

        FOURCHAN_FILE_REGEX.find(html)?.let {
            candidates.add(
                ImageCandidate(
                    url = resolveAbsoluteUrl(baseUrl, it.groupValues[1]),
                    source = "BOARD",
                    score = 100f,
                    context = "4chan file image",
                    sources = mutableSetOf("BOARD")
                )
            )
        }
        FOURCHAN_THUMB_REGEX.find(html)?.let {
            candidates.add(
                ImageCandidate(
                    url = resolveAbsoluteUrl(baseUrl, it.groupValues[1]),
                    source = "BOARD",
                    score = 90f,
                    context = "4chan thumb image",
                    sources = mutableSetOf("BOARD")
                )
            )
        }
        BOORU_IMAGE_ID_REGEX.find(html)?.let {
            candidates.add(
                ImageCandidate(
                    url = resolveAbsoluteUrl(baseUrl, it.groupValues[1]),
                    source = "BOARD",
                    score = 100f,
                    context = "booru main image",
                    sources = mutableSetOf("BOARD")
                )
            )
        }
        BOORU_IMAGE_ID_ALT_REGEX.find(html)?.let {
            candidates.add(
                ImageCandidate(
                    url = resolveAbsoluteUrl(baseUrl, it.groupValues[1]),
                    source = "BOARD",
                    score = 100f,
                    context = "booru main image",
                    sources = mutableSetOf("BOARD")
                )
            )
        }
        BOORU_CONTAINER_REGEX.find(html)?.let {
            candidates.add(
                ImageCandidate(
                    url = resolveAbsoluteUrl(baseUrl, it.groupValues[1]),
                    source = "BOARD",
                    score = 100f,
                    context = "booru data-file-url",
                    sources = mutableSetOf("BOARD")
                )
            )
        }
        ORIGINAL_FILE_LINK_REGEX.find(html)?.let {
            candidates.add(
                ImageCandidate(
                    url = resolveAbsoluteUrl(baseUrl, it.groupValues[1]),
                    source = "BOARD",
                    score = 95f,
                    context = "original file link",
                    sources = mutableSetOf("BOARD")
                )
            )
        }

        return candidates
    }

    private fun extractHtmlImages(html: String, baseUrl: String): List<ImageCandidate> {
        val candidates = mutableListOf<ImageCandidate>()

        // <img> tags
        IMG_TAG_REGEX.findAll(html).forEach { match ->
            val attrs = parseTagAttributes(match.value)
            val imgUrl = getImageUrlFromAttrs(attrs)

            if (!imgUrl.isNullOrBlank() && looksLikeImageUrl(imgUrl)) {
                val fullUrl = resolveAbsoluteUrl(baseUrl, imgUrl)
                val width = attrs["width"]?.toIntOrNull()
                val height = attrs["height"]?.toIntOrNull()
                val alt = attrs["alt"] ?: ""
                val cls = attrs["class"] ?: ""
                val id = attrs["id"] ?: ""

                // Context surrounding the image
                val idx = match.range.first
                val contextSnippet = html.substring((idx - 250).coerceAtLeast(0), idx).lowercase(Locale.ROOT)
                val isArticle = contextSnippet.contains("<article")
                val isFigure = contextSnippet.contains("<figure")
                val isMain = contextSnippet.contains("<main")
                val isHeader = contextSnippet.contains("<header")

                val context = buildString {
                    append(cls).append(" ").append(id)
                    if (isArticle) append(" article")
                    if (isFigure) append(" figure")
                    if (isMain) append(" main")
                    if (isHeader) append(" header")
                }.trim()

                candidates.add(
                    ImageCandidate(
                        url = fullUrl,
                        source = "IMG",
                        width = width,
                        height = height,
                        alt = alt,
                        context = context,
                        sources = mutableSetOf("IMG")
                    )
                )
            }
        }

        // <source srcset=""> inside <picture>
        SOURCE_TAG_REGEX.findAll(html).forEach { match ->
            val attrs = parseTagAttributes(match.value)
            val srcset = attrs["srcset"]
            if (!srcset.isNullOrBlank()) {
                val bestUrl = bestSrcsetUrl(srcset)
                if (!bestUrl.isNullOrBlank() && looksLikeImageUrl(bestUrl)) {
                    candidates.add(
                        ImageCandidate(
                            url = resolveAbsoluteUrl(baseUrl, bestUrl),
                            source = "PICTURE",
                            context = "picture source srcset",
                            sources = mutableSetOf("PICTURE")
                        )
                    )
                }
            }
        }

        return candidates
    }

    private fun getImageUrlFromAttrs(attrs: Map<String, String>): String? {
        for (attr in listOf("src", "data-src", "data-original", "data-lazy-src", "data-image")) {
            val v = attrs[attr]
            if (!v.isNullOrBlank() && looksLikeImageUrl(v)) {
                return v
            }
        }
        val srcset = attrs["srcset"]
        if (!srcset.isNullOrBlank()) {
            return bestSrcsetUrl(srcset)
        }
        return null
    }

    private fun bestSrcsetUrl(srcset: String): String? {
        val candidates = mutableListOf<Pair<Float, String>>()

        for (part in srcset.split(",")) {
            val trimmed = part.trim()
            if (trimmed.isEmpty()) continue

            val pieces = trimmed.split(Regex("""\s+"""))
            val url = pieces[0]
            val descriptor = if (pieces.size > 1) pieces[1] else ""
            var score = 0f

            val wMatch = Regex("""(\d+)w""").find(descriptor)
            if (wMatch != null) {
                score = wMatch.groupValues[1].toFloatOrNull() ?: 0f
            }
            val xMatch = Regex("""([\d.]+)x""").find(descriptor)
            if (xMatch != null) {
                score = (xMatch.groupValues[1].toFloatOrNull() ?: 0f) * 1000f
            }

            candidates.add(Pair(score, url))
        }

        if (candidates.isEmpty()) return null
        candidates.sortByDescending { it.first }
        return candidates[0].second
    }

    // =========================================================
    // Candidate Merging
    // =========================================================

    private fun mergeDuplicates(candidates: List<ImageCandidate>): List<ImageCandidate> {
        val merged = mutableMapOf<String, ImageCandidate>()

        for (candidate in candidates) {
            val key = normalizeUrl(candidate.url)
            val existing = merged[key]

            if (existing == null) {
                merged[key] = candidate
            } else {
                existing.sources.addAll(candidate.sources)

                if (sourcePriority(candidate.source) > sourcePriority(existing.source)) {
                    existing.source = candidate.source
                }

                if (existing.width == null && candidate.width != null) {
                    existing.width = candidate.width
                }
                if (existing.height == null && candidate.height != null) {
                    existing.height = candidate.height
                }
                if (existing.alt.isBlank() && candidate.alt.isNotBlank()) {
                    existing.alt = candidate.alt
                }
                if (candidate.context.isNotBlank()) {
                    if (!existing.context.contains(candidate.context)) {
                        existing.context = "${existing.context} ${candidate.context}".trim()
                    }
                }
            }
        }

        return merged.values.toList()
    }

    private fun sourcePriority(source: String): Int {
        return when (source) {
            "OPEN_GRAPH" -> 5
            "BOARD" -> 4
            "TWITTER" -> 3
            "JSON_LD" -> 2
            "PICTURE" -> 1
            else -> 0
        }
    }

    private fun normalizeUrl(url: String): String {
        return url.trim().lowercase(Locale.ROOT)
    }

    // =========================================================
    // Preliminary + Final Scoring
    // =========================================================

    private fun scoreCandidate(
        candidate: ImageCandidate,
        pageUrl: String,
        useDimensions: Boolean
    ): Float {
        var score = 0f
        val urlLower = candidate.url.lowercase(Locale.ROOT)
        val text = "${candidate.alt} ${candidate.context} $urlLower".lowercase(Locale.ROOT)

        // 1. Source score
        val sourceScores = mapOf(
            "OPEN_GRAPH" to 100f,
            "BOARD" to 100f,
            "TWITTER" to 90f,
            "JSON_LD" to 70f,
            "META" to 60f,
            "PICTURE" to 0f,
            "IMG" to 0f
        )
        val sourceEvidence = candidate.sources.mapNotNull { sourceScores[it] }.maxOrNull() ?: 0f
        score += sourceEvidence

        // 2. DOM context
        val contextLower = candidate.context.lowercase(Locale.ROOT)
        if (contextLower.contains("article")) score += 25f
        if (contextLower.contains("main")) score += 15f
        if (contextLower.contains("figure")) score += 10f
        if (contextLower.contains("header")) score += 10f

        // 3. Positive semantic keywords
        val positiveWords = listOf(
            "hero", "featured", "article-image", "article_image",
            "post-image", "post_image", "content-image", "content_image",
            "main-image", "main_image", "media", "original", "full", "header"
        )
        for (word in positiveWords) {
            if (text.contains(word)) score += 10f
        }

        // 4. Negative semantic keywords
        val negativeWords = listOf(
            "logo", "icon", "avatar", "profile", "emoji",
            "favicon", "sprite", "badge", "button", "tracking", "pixel", "thumbnail"
        )
        for (word in negativeWords) {
            if (text.contains(word)) score -= 30f
        }

        // 5. Format
        if (urlLower.startsWith("data:")) score -= 100f
        if (urlLower.endsWith(".svg")) score -= 50f

        // 6. Actual / declared dimensions
        if (useDimensions && candidate.width != null && candidate.height != null) {
            val w = candidate.width!!
            val h = candidate.height!!
            val area = w.toLong() * h.toLong()
            when {
                area >= 1_000_000 -> score += 30f
                area >= 500_000 -> score += 20f
                area >= 100_000 -> score += 10f
                area < 10_000 -> score -= 40f
            }
            if (h > 0) {
                val ratio = w.toFloat() / h.toFloat()
                if (ratio > 10f || ratio < 0.1f) {
                    score -= 30f
                }
            }
        }

        // 7. Same-host bonus
        val pageHost = LinkExtractor.extractHost(pageUrl)
        val imageHost = LinkExtractor.extractHost(candidate.url)
        if (pageHost.isNotBlank() && imageHost.isNotBlank() && pageHost == imageHost) {
            score += 5f
        }

        return score
    }

    // =========================================================
    // Image Dimension Retrieval (Bounded Byte Download)
    // =========================================================

    /**
     * Downloads a bounded amount of image data (up to 512KB) and identifies image dimensions
     * using BitmapFactory.Options.inJustDecodeBounds = true without allocating full bitmap memory.
     */
    fun getImageDimensions(imageUrl: String): Pair<Int, Int>? {
        if (imageUrl.startsWith("data:") || imageUrl.isBlank()) return null

        return try {
            val request = Request.Builder()
                .url(imageUrl)
                .header("User-Agent", USER_AGENT)
                .header("Accept", "image/avif,image/webp,image/apng,image/svg+xml,image/*;q=0.8,*/*;q=0.5")
                .build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) return null
                val contentType = response.header("Content-Type")?.lowercase(Locale.ROOT) ?: ""
                if (contentType.contains("text/html")) return null

                val byteStream = response.body?.byteStream() ?: return null
                val buffer = ByteArray(MAX_IMAGE_BYTES)
                var totalRead = 0
                val chunkSize = 16 * 1024

                while (totalRead < buffer.size) {
                    val read = byteStream.read(buffer, totalRead, minOf(chunkSize, buffer.size - totalRead))
                    if (read <= 0) break
                    totalRead += read

                    // Try to identify dimensions as early as possible
                    val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                    BitmapFactory.decodeByteArray(buffer, 0, totalRead, options)
                    if (options.outWidth > 0 && options.outHeight > 0) {
                        return Pair(options.outWidth, options.outHeight)
                    }
                }

                if (totalRead > 0) {
                    val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                    BitmapFactory.decodeByteArray(buffer, 0, totalRead, options)
                    if (options.outWidth > 0 && options.outHeight > 0) {
                        return Pair(options.outWidth, options.outHeight)
                    }
                }
                null
            }
        } catch (_: Exception) {
            null
        }
    }

    // =========================================================
    // Helpers
    // =========================================================

    private fun parseTagAttributes(tagHtml: String): Map<String, String> {
        val attrs = mutableMapOf<String, String>()
        ATTR_REGEX.findAll(tagHtml).forEach { match ->
            val name = match.groupValues[1].lowercase(Locale.ROOT)
            val value = match.groupValues[2].ifEmpty {
                match.groupValues[3].ifEmpty {
                    match.groupValues[4]
                }
            }
            attrs[name] = cleanHtmlEntities(value)
        }
        return attrs
    }

    fun extractTitleFromHtml(html: String): String {
        val raw = OG_TITLE_REGEX.find(html)?.groupValues?.getOrNull(1)
            ?: TWITTER_TITLE_REGEX.find(html)?.groupValues?.getOrNull(1)
            ?: TITLE_TAG_REGEX.find(html)?.groupValues?.getOrNull(1)
            ?: return ""

        return cleanHtmlEntities(raw).trim()
    }

    private fun looksLikeImageUrl(url: String): Boolean {
        if (url.startsWith("data:")) return false
        val lower = url.lowercase(Locale.ROOT)
        if (lower.startsWith("javascript:") || lower.startsWith("mailto:")) return false
        return true
    }

    fun resolveAbsoluteUrl(baseUrl: String, relativeUrl: String): String {
        return try {
            val trimmed = relativeUrl.trim()
            if (trimmed.startsWith("//")) {
                val scheme = URI(baseUrl).scheme ?: "https"
                "$scheme:$trimmed"
            } else if (trimmed.startsWith("http://", ignoreCase = true) || trimmed.startsWith("https://", ignoreCase = true)) {
                trimmed
            } else {
                URI(baseUrl).resolve(trimmed).toString()
            }
        } catch (_: Exception) {
            relativeUrl
        }
    }

    private fun cleanHtmlEntities(text: String): String {
        return text
            .replace("&amp;", "&")
            .replace("&#39;", "'")
            .replace("&quot;", "\"")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&nbsp;", " ")
    }

    fun guessMimeType(url: String): String {
        val lower = url.lowercase(Locale.ROOT).substringBefore('?').substringBefore('#')
        return when {
            lower.endsWith(".png") -> "image/png"
            lower.endsWith(".webp") -> "image/webp"
            lower.endsWith(".gif") -> "image/gif"
            lower.endsWith(".svg") -> "image/svg+xml"
            lower.endsWith(".avif") -> "image/avif"
            else -> "image/jpeg"
        }
    }

    fun generateDeterministicPinId(canonicalUrl: String): String {
        return try {
            val md = MessageDigest.getInstance("MD5")
            val bytes = md.digest(canonicalUrl.trim().toByteArray(Charsets.UTF_8))
            "pin_" + bytes.joinToString("") { "%02x".format(it) }.take(16)
        } catch (_: Exception) {
            "pin_${canonicalUrl.hashCode().toString().replace('-', 'n')}"
        }
    }
}
