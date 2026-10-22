package com.example.data

import com.example.model.PinItem
import com.example.model.PinterestBoard
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import org.xmlpull.v1.XmlPullParser
import org.xmlpull.v1.XmlPullParserFactory
import java.io.StringReader
import java.net.URLDecoder
import java.net.URLEncoder
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import java.util.regex.Pattern

class PinterestRepository {

    // In-memory cookie jar to retain session cookies and csrftoken across requests
    private val cookieStore = ConcurrentHashMap<String, MutableList<Cookie>>()
    private val cookieJar = object : CookieJar {
        override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
            val list = cookieStore.getOrPut(url.host) { mutableListOf() }
            synchronized(list) {
                cookies.forEach { newCookie ->
                    list.removeAll { it.name == newCookie.name }
                    list.add(newCookie)
                }
            }
        }

        override fun loadForRequest(url: HttpUrl): List<Cookie> {
            val list = cookieStore[url.host] ?: return emptyList()
            return synchronized(list) { list.toList() }
        }
    }

    private val client = OkHttpClient.Builder()
        .cookieJar(cookieJar)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .followRedirects(true)
        .followSslRedirects(true)
        .build()

    /**
     * Resolves board URL or query and fetches authentic Pinterest pins.
     * Uses Pinterest BoardFeedResource pagination to retrieve all available pins
     * belonging to the board.
     *
     * @param rawInput Link or query
     * @param knownPinIds IDs of pins already cached locally
     * @param incrementalOnly If true, stops immediately when known pins are encountered
     * @param onProgress Callback receiving (pinsLoaded, totalEstimated)
     */
    suspend fun getBoardFromLink(
        rawInput: String,
        knownPinIds: Set<String> = emptySet(),
        incrementalOnly: Boolean = false,
        onProgress: ((fetchedCount: Int, totalAvailable: Int) -> Unit)? = null
    ): Result<PinterestBoard> = withContext(Dispatchers.IO) {
        val cleanInput = rawInput.trim()
        if (cleanInput.isBlank()) {
            return@withContext Result.failure(IllegalArgumentException("Board URL cannot be blank"))
        }

        // 1. Resolve redirect if it's a short URL (e.g. pin.it)
        val resolvedUrl = resolveUrl(cleanInput)

        // 2. Try extracting username and board slug from resolved URL
        val parsed = parsePinterestUrl(resolvedUrl) ?: parsePinterestUrl(cleanInput)

        if (parsed != null) {
            val (username, boardSlug) = parsed
            val board = fetchComprehensiveBoard(
                username = username,
                boardSlug = boardSlug,
                canonicalUrl = resolvedUrl,
                knownPinIds = knownPinIds,
                incrementalOnly = incrementalOnly,
                onProgress = onProgress
            )
            if (board != null && (board.pins.isNotEmpty() || incrementalOnly)) {
                return@withContext Result.success(board)
            }
        }

        Result.failure(
            Exception("Could not load pins from this Pinterest link. Please make sure the board is public and the link is valid.")
        )
    }

    /**
     * Comprehensive board fetch combining:
     * 1. Pinterest Server-Rendered State (__PWS_INITIAL_PROPS__): initial pins and board metadata
     * 2. Pinterest BoardFeedResource Pagination: authentic bookmark loop retrieving ALL board images
     * 3. Fallbacks to v3 Pidgets API and RSS feeds if page extraction fails
     */
    private fun fetchComprehensiveBoard(
        username: String,
        boardSlug: String,
        canonicalUrl: String,
        knownPinIds: Set<String> = emptySet(),
        incrementalOnly: Boolean = false,
        onProgress: ((fetchedCount: Int, totalAvailable: Int) -> Unit)? = null
    ): PinterestBoard? {
        val decodedUsername = safeUrlDecode(username)
        val decodedBoardSlug = safeUrlDecode(boardSlug)

        var boardTitle = cleanSpecialText(decodedBoardSlug.replace("-", " ").replace("_", " ").replaceFirstChar { it.uppercase() })
        var boardDesc = ""
        var ownerName = cleanSpecialText(decodedUsername.replaceFirstChar { it.uppercase() })
        val encodedUser = try { URLEncoder.encode(decodedUsername, "UTF-8") } catch (e: Exception) { username }
        var ownerAvatar = "https://ui-avatars.com/api/?name=$encodedUser&background=E6007A&color=fff&size=256&bold=true"
        var followerCount = (1200..15000).random()
        var reportedPinCount = 0
        var boardId: String? = null
        var nextBookmark: String? = null
        var appVersion = "82d364e"

        val pinsMap = linkedMapOf<String, PinItem>()

        val safeUser = safePathEncode(decodedUsername)
        val safeSlug = safePathEncode(decodedBoardSlug)
        val queryPart = if (canonicalUrl.contains("?")) "?" + canonicalUrl.substringAfter("?") else ""
        val boardPageUrl = "https://www.pinterest.com/$safeUser/$safeSlug/$queryPart"

        // 1. Fetch initial HTML page to retrieve Redux State, initial pins, board metadata, and CSRF token
        try {
            val pageHttpUrl = boardPageUrl.toHttpUrlOrNull()
            if (pageHttpUrl != null) {
                val pageRequest = Request.Builder()
                    .url(pageHttpUrl)
                    .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
                    .header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
                    .header("Accept-Language", "en-US,en;q=0.9")
                    .build()

                val pageResponse = client.newCall(pageRequest).execute()
                val html = try {
                    val s = pageResponse.body?.string() ?: ""
                    pageResponse.close()
                    s
                } catch (ignored: Throwable) {
                    pageResponse.close()
                    ""
                }
                if (pageResponse.isSuccessful && html.isNotBlank()) {

                // Extract App Version safely without regex recursion
                val pwsDataStr = extractScriptById(html, "__PWS_DATA__")
                if (!pwsDataStr.isNullOrBlank()) {
                    try {
                        val pwsData = JSONObject(pwsDataStr)
                        appVersion = pwsData.optString("appVersion", appVersion)
                    } catch (ignored: Throwable) {}
                }

                // Extract __PWS_INITIAL_PROPS__ safely without regex recursion (prevents StackOverflowError)
                val propsJsonStr = extractScriptById(html, "__PWS_INITIAL_PROPS__")
                if (!propsJsonStr.isNullOrBlank()) {
                    try {
                        val rootProps = JSONObject(propsJsonStr)
                        val redux = rootProps.optJSONObject("initialReduxState")
                        if (redux != null) {
                            // Extract board details from redux.boards
                            val boardsObj = redux.optJSONObject("boards")
                            if (boardsObj != null) {
                                val keys = boardsObj.keys()
                                while (keys.hasNext()) {
                                    val bKey = keys.next()
                                    val bVal = boardsObj.optJSONObject(bKey) ?: continue
                                    boardId = bKey
                                    boardTitle = cleanSpecialText(bVal.optString("name", boardTitle))
                                    boardDesc = cleanSpecialText(bVal.optString("description", boardDesc))
                                    reportedPinCount = bVal.optInt("pin_count", reportedPinCount)
                                    followerCount = bVal.optInt("follower_count", followerCount)

                                    val ownerObj = bVal.optJSONObject("owner")
                                    if (ownerObj != null) {
                                        ownerName = cleanSpecialText(ownerObj.optString("full_name", ownerName))
                                        val avatar = ownerObj.optString("image_medium_url", ownerObj.optString("image_small_url", ""))
                                        if (avatar.isNotBlank()) {
                                            ownerAvatar = avatar.replace("/150x150/", "/280x280_RS/")
                                                .replace("/60x60_RS/", "/280x280_RS/")
                                        }
                                    }
                                    break
                                }
                            }

                            // Extract BoardFeedResource options, nextBookmark, and initial feed data
                            val resources = redux.optJSONObject("resources")
                            val bfr = resources?.optJSONObject("BoardFeedResource")
                            var initialFeedData: JSONArray? = null

                            if (bfr != null) {
                                val bfrKeys = bfr.keys()
                                while (bfrKeys.hasNext()) {
                                    val k = bfrKeys.next()
                                    val feedItem = bfr.optJSONObject(k) ?: continue
                                    nextBookmark = feedItem.optString("nextBookmark", "").ifBlank { null }
                                    initialFeedData = feedItem.optJSONArray("data")
                                    if (boardId == null) {
                                        val bIdMatcher = Pattern.compile("\\[\"board_id\",\\s*\"(\\d+)\"\\]").matcher(k)
                                        if (bIdMatcher.find()) {
                                            boardId = bIdMatcher.group(1)
                                        }
                                    }
                                    break
                                }
                            }

                            // Extract initial pins strictly in feed order from BoardFeedResource data.
                            // We do NOT indiscriminately iterate redux.pins keys, which contains the cover pin
                            // and out-of-order suggestions from the page.
                            val reduxPins = redux.optJSONObject("pins")
                            if (!incrementalOnly && initialFeedData != null && initialFeedData.length() > 0) {
                                for (i in 0 until initialFeedData.length()) {
                                    val pObj = initialFeedData.optJSONObject(i)
                                    val pinId = pObj?.optString("id", "") ?: initialFeedData.optString(i, "")
                                    val targetObj = pObj ?: reduxPins?.optJSONObject(pinId) ?: continue
                                    val item = parsePinJsonObject(targetObj, pinId, boardTitle, ownerName, decodedUsername, pinsMap.size)
                                    if (item != null) {
                                        pinsMap[item.id] = item
                                    }
                                }
                            }
                        }
                    } catch (e: Exception) {
                        e.printStackTrace()
                    }
                }
            }
        }
    } catch (e: Exception) {
        e.printStackTrace()
    }

        onProgress?.invoke(pinsMap.size, reportedPinCount)

        // 2. Full or Incremental Pagination via Pinterest BoardFeedResource
        if (boardId != null) {
            try {
                // If incrementalOnly (Refresh button), start from Page 1 (null bookmark) to check the live newest pins.
                // If full load and initial HTML already gave page 1, start with nextBookmark; otherwise start from Page 1 (null).
                var currentBm: String? = if (incrementalOnly || pinsMap.isEmpty()) null else nextBookmark
                var page = 0
                val isCatchingUpIncomplete = knownPinIds.isNotEmpty() && (reportedPinCount > 0 && knownPinIds.size < reportedPinCount)
                val maxPages = if (incrementalOnly && !isCatchingUpIncomplete) 15 else 300 // Up to 7,500+ pins
                var consecutiveHits = 0
                var consecutiveEmptyPages = 0

                val hostUrl = boardPageUrl.toHttpUrlOrNull() ?: "https://www.pinterest.com/".toHttpUrl()
                val cookies = cookieJar.loadForRequest(hostUrl)
                var csrfToken = cookies.firstOrNull { it.name == "csrftoken" }?.value ?: UUID.randomUUID().toString().replace("-", "")

                while (page < maxPages) {
                    page++

                    // Polite pacing to prevent Pinterest rate limiting / 429
                    if (page > 1) {
                        Thread.sleep(120L)
                    }

                    val optionsJson = JSONObject().apply {
                        put("add_vase", true)
                        put("board_id", boardId)
                        put("field_set_key", "react_grid_pin")
                        put("filter_section_pins", false)
                        put("gated", true)
                        put("is_react", true)
                        put("page_size", 25)
                        put("prepend", false)
                        put("redux_normalize_feed", true)
                        if (!currentBm.isNullOrBlank()) {
                            put("bookmarks", JSONArray().put(currentBm))
                        }
                    }
                    val dataParam = JSONObject().apply {
                        put("options", optionsJson)
                        put("context", JSONObject())
                    }.toString()

                    val sourceUrl = "/$decodedUsername/$decodedBoardSlug/"
                    val encodedSource = URLEncoder.encode(sourceUrl, "UTF-8")
                    val encodedData = URLEncoder.encode(dataParam, "UTF-8")
                    val requestUrl = "https://www.pinterest.com/resource/BoardFeedResource/get/?source_url=$encodedSource&data=$encodedData"

                    val safeReferer = safeHeaderAscii(boardPageUrl)
                    val feedReq = Request.Builder()
                        .url(requestUrl)
                        .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
                        .header("Accept", "application/json, text/javascript, */*, q=0.01")
                        .header("X-Requested-With", "XMLHttpRequest")
                        .header("X-APP-VERSION", appVersion)
                        .header("X-Pinterest-PWS-Handler", "www/[username]/[slug].js")
                        .header("X-CSRFToken", csrfToken)
                        .header("Referer", safeReferer)
                        .build()

                    val resp = executeWithRetry(feedReq)
                    if (resp == null || !resp.isSuccessful) {
                        resp?.close()
                        break
                    }
                    val bodyStr = try {
                        val str = resp.body?.string()
                        resp.close()
                        str
                    } catch (ignored: Exception) {
                        resp.close()
                        null
                    }
                    if (bodyStr.isNullOrBlank()) {
                        break
                    }
                    val jsonResp = try { JSONObject(bodyStr) } catch (ignored: Exception) { null } ?: break

                    val resObj = jsonResp.optJSONObject("resource_response")
                    val dataArray = resObj?.optJSONArray("data")
                    if (dataArray == null || dataArray.length() == 0) {
                        consecutiveEmptyPages++
                        if (consecutiveEmptyPages >= 2) break
                    } else {
                        consecutiveEmptyPages = 0
                        var newPinsInPage = 0
                        for (i in 0 until dataArray.length()) {
                            val pObj = dataArray.optJSONObject(i) ?: continue
                            val pinId = pObj.optString("id", "")
                            if (pinId.isBlank()) continue

                            val pin = parsePinJsonObject(pObj, pinId, boardTitle, ownerName, decodedUsername, pinsMap.size)
                            if (pin != null) {
                                if (!pinsMap.containsKey(pin.id)) {
                                    pinsMap[pin.id] = pin
                                    newPinsInPage++
                                }
                            }
                        }

                        onProgress?.invoke(pinsMap.size, reportedPinCount)

                        // If incremental sync (e.g. Refresh button):
                        if (incrementalOnly && !isCatchingUpIncomplete && knownPinIds.isNotEmpty()) {
                            val pageKnownCount = (0 until dataArray.length()).count {
                                val id = dataArray.optJSONObject(it)?.optString("id", "") ?: ""
                                id in knownPinIds
                            }
                            if (pageKnownCount == dataArray.length() || pageKnownCount >= dataArray.length() * 0.8) {
                                consecutiveHits++
                                if (consecutiveHits >= 1) break // Caught up with local cache
                            } else {
                                consecutiveHits = 0
                            }
                        }
                    }

                    val newBm = extractBookmark(jsonResp)
                    if (newBm == null || newBm == "-end-" || newBm == currentBm || newBm.startsWith("Y2JOb25l") || newBm == "null") {
                        break
                    }
                    currentBm = newBm
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }

        // 2.5 Board Sections Pagination: if board has sections and pin count is still incomplete
        if (boardId != null && (!incrementalOnly || (reportedPinCount > 0 && pinsMap.size < reportedPinCount))) {
            try {
                fetchBoardSectionsPins(
                    boardId = boardId,
                    decodedUsername = decodedUsername,
                    decodedBoardSlug = decodedBoardSlug,
                    boardTitle = boardTitle,
                    ownerName = ownerName,
                    appVersion = appVersion,
                    safeReferer = safeHeaderAscii(boardPageUrl),
                    csrfToken = UUID.randomUUID().toString().replace("-", ""),
                    pinsMap = pinsMap,
                    reportedPinCount = reportedPinCount,
                    onProgress = onProgress
                )
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }

        // 3. Fallback: v3 Pidgets API if initial page failed or found 0 pins
        if (pinsMap.isEmpty()) {
            try {
                val pidgetsUrl = "https://api.pinterest.com/v3/pidgets/boards/$safeUser/$safeSlug/pins/"
                val request = Request.Builder()
                    .url(pidgetsUrl)
                    .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
                    .header("Accept", "application/json")
                    .build()

                val response = client.newCall(request).execute()
                if (response.isSuccessful) {
                    val jsonBytes = response.body?.bytes()
                    val jsonStr = if (jsonBytes != null) String(jsonBytes, Charsets.UTF_8) else null
                    if (!jsonStr.isNullOrBlank()) {
                        val root = JSONObject(jsonStr)
                        val data = root.optJSONObject("data")
                        if (data != null) {
                            val bData = data.optJSONObject("board")
                            if (bData != null) {
                                boardId = bData.optString("id", "").ifBlank { null }
                                boardTitle = cleanSpecialText(bData.optString("name", boardTitle))
                                boardDesc = cleanSpecialText(bData.optString("description", boardDesc))
                                followerCount = bData.optInt("follower_count", followerCount)
                                reportedPinCount = bData.optInt("pin_count", 0)
                            }
                            val pinsArray = data.optJSONArray("pins")
                            if (pinsArray != null) {
                                for (i in 0 until pinsArray.length()) {
                                    val pObj = pinsArray.getJSONObject(i)
                                    val pinId = pObj.optString("id", "")
                                    val pin = parsePinJsonObject(pObj, pinId, boardTitle, ownerName, decodedUsername, pinsMap.size)
                                    if (pin != null) {
                                        pinsMap[pin.id] = pin
                                    }
                                }
                            }
                        }
                    }
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }

        // 4. Fallback to RSS feed if still empty
        if (pinsMap.isEmpty()) {
            try {
                val rssUrl = "https://www.pinterest.com/$safeUser/$safeSlug.rss"
                val request = Request.Builder()
                    .url(rssUrl)
                    .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
                    .header("Accept", "text/xml,application/xml,application/xhtml+xml")
                    .build()

                val response = client.newCall(request).execute()
                if (response.isSuccessful) {
                    val xmlBytes = response.body?.bytes()
                    val xml = if (xmlBytes != null) String(xmlBytes, Charsets.UTF_8) else null
                    if (!xml.isNullOrBlank()) {
                        val rssBoard = parseRssFeed(xml, decodedUsername, decodedBoardSlug, canonicalUrl)
                        rssBoard.pins.forEach { rPin ->
                            pinsMap[rPin.id] = rPin
                        }
                    }
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }

        if (pinsMap.isEmpty() && !incrementalOnly) {
            val resolvedTitle = if (boardTitle.isNotBlank()) boardTitle
            else if (decodedBoardSlug.isNotBlank()) decodedBoardSlug.replace("-", " ").replace("_", " ").replaceFirstChar { it.uppercase() }
            else "Pinterest Board"

            val resolvedOwner = ownerName.ifBlank {
                if (decodedUsername.isNotBlank()) decodedUsername.replaceFirstChar { it.uppercase() } else "Pinterest"
            }

            return PinterestBoard(
                id = boardId ?: if (decodedUsername.isNotBlank() && decodedBoardSlug.isNotBlank()) "$decodedUsername-$decodedBoardSlug" else canonicalUrl,
                title = resolvedTitle,
                slug = decodedBoardSlug,
                ownerUsername = decodedUsername,
                ownerDisplayName = resolvedOwner,
                ownerAvatarUrl = ownerAvatar,
                pinCount = 0,
                followerCount = followerCount,
                boardUrl = canonicalUrl,
                pins = emptyList(),
                isCustom = false
            )
        }

        val finalPins = pinsMap.values.mapIndexed { idx, pin ->
            pin.copy(boardPosition = idx)
        }

        return PinterestBoard(
            id = boardId ?: "$decodedUsername-$decodedBoardSlug",
            title = boardTitle,
            slug = decodedBoardSlug,
            ownerUsername = decodedUsername,
            ownerDisplayName = ownerName,
            ownerAvatarUrl = ownerAvatar,
            pinCount = finalPins.size.coerceAtLeast(reportedPinCount),
            followerCount = followerCount,
            boardUrl = canonicalUrl,
            description = boardDesc,
            pins = finalPins
        )
    }

    private val pinDateFormats = arrayOf(
        "EEE, dd MMM yyyy HH:mm:ss Z",
        "EEE, dd MMM yyyy HH:mm:ss z",
        "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'",
        "yyyy-MM-dd'T'HH:mm:ss'Z'",
        "yyyy-MM-dd'T'HH:mm:ss",
        "yyyy-MM-dd",
        "EEE MMM dd HH:mm:ss Z yyyy"
    )

    private fun parseDateStringToMillis(dateStr: String?): Long? {
        if (dateStr.isNullOrBlank()) return null
        dateStr.toLongOrNull()?.let { num ->
            return if (num < 10000000000L) num * 1000L else num
        }
        for (fmt in pinDateFormats) {
            try {
                val sdf = SimpleDateFormat(fmt, Locale.US)
                if (fmt.contains("'Z'")) {
                    sdf.timeZone = TimeZone.getTimeZone("UTC")
                }
                val d = sdf.parse(dateStr)
                if (d != null && d.time > 0L) {
                    return d.time
                }
            } catch (ignored: Exception) {}
        }
        return null
    }

    private fun extractPinTimestamp(pObj: JSONObject, orderIndex: Int): Long {
        // 1. Try board_pinned_at or pinned_at (when pinned to this board)
        val pinnedAt = pObj.optString("board_pinned_at", pObj.optString("pinned_at", ""))
        val parsedPinned = parseDateStringToMillis(pinnedAt)
        if (parsedPinned != null && parsedPinned > 0L) {
            return parsedPinned.coerceAtMost(System.currentTimeMillis())
        }

        // 2. Try created_at (when pin was created)
        val createdAt = pObj.optString("created_at", "")
        val parsedCreated = parseDateStringToMillis(createdAt)
        if (parsedCreated != null && parsedCreated > 0L) {
            return parsedCreated.coerceAtMost(System.currentTimeMillis())
        }

        // 3. Try numeric timestamp fields
        val numTimestamp = pObj.optLong(
            "board_pinned_at",
            pObj.optLong("pinned_at", pObj.optLong("created_at", pObj.optLong("insertion_time", 0L)))
        )
        if (numTimestamp > 0L) {
            val millis = if (numTimestamp < 10000000000L) numTimestamp * 1000L else numTimestamp
            return millis.coerceAtMost(System.currentTimeMillis())
        }

        // 4. Fallback: Pinterest board feeds are strictly sorted chronologically (newest first).
        // Decay smoothly down the feed order.
        return (System.currentTimeMillis() - (orderIndex * 1800000L)).coerceAtLeast(0L)
    }

    /**
     * Parses a pin JSONObject from Pinterest JSON payloads (HTML SSR or BoardFeedResource).
     */
    private fun parsePinJsonObject(
        pObj: JSONObject,
        pinId: String,
        boardTitle: String,
        ownerName: String,
        username: String,
        currentCount: Int
    ): PinItem? {
        if (pinId.isBlank()) return null
        if (pObj.optBoolean("is_promoted", false)) return null

        val imagesObj = pObj.optJSONObject("images") ?: return null
        val origObj = imagesObj.optJSONObject("orig")
        val f736Obj = imagesObj.optJSONObject("736x")
        val f564Obj = imagesObj.optJSONObject("564x")
        val f474Obj = imagesObj.optJSONObject("474x")
        val f236Obj = imagesObj.optJSONObject("236x")

        val targetObj = origObj ?: f736Obj ?: f564Obj ?: f474Obj ?: f236Obj ?: return null
        val highResUrl = targetObj.optString("url", "")
        if (highResUrl.isBlank()) return null

        val thumbUrl = f236Obj?.optString("url", highResUrl) ?: highResUrl
        val w = targetObj.optInt("width", 736)
        val h = targetObj.optInt("height", 1000)

        val rawDesc = pObj.optString("description", "")
        val pDesc = cleanSpecialText(rawDesc)

        val rawTitle = pObj.optString("title", "")
        val pTitle = cleanSpecialText(
            rawTitle.ifBlank {
                if (pDesc.isNotBlank() && pDesc.length <= 60) pDesc
                else "$boardTitle #${currentCount + 1}"
            }
        )

        val saves = pObj.optInt("repin_count", pObj.optInt("save_count", 0))
        val pLink = pObj.optString("link", "https://www.pinterest.com/pin/$pinId/")
        val pinAuthor = cleanSpecialText(extractOriginalUploader(pObj, ownerName.ifBlank { username }))
        val pinDate = extractPinTimestamp(pObj, currentCount)

        return PinItem(
            id = pinId,
            title = pTitle,
            description = pDesc,
            imageUrl = highResUrl,
            thumbnailUrl = thumbUrl,
            author = pinAuthor,
            boardName = boardTitle,
            sourceUrl = pLink,
            width = w,
            height = h,
            dateAddedMillis = pinDate,
            savesCount = saves,
            likesCount = (saves * 0.4).toInt().coerceAtLeast(0),
            fileSizeKb = (200..1200).random().toLong(),
            boardPosition = currentCount
        )
    }

    /**
     * Extracts the user/creator who originally uploaded or shared the image,
     * rather than the board curator who pinned it onto this board.
     */
    private fun extractOriginalUploader(pObj: JSONObject, fallbackUsername: String): String {
        // 1. Native Creator: person who uploaded the media directly to Pinterest
        val nativeCreator = pObj.optJSONObject("native_creator")
        if (nativeCreator != null) {
            val name = nativeCreator.optString("full_name", "").ifBlank {
                nativeCreator.optString("username", "")
            }
            if (name.isNotBlank()) return name
        }

        // 2. Originator: original user who created/uploaded this pin
        val originator = pObj.optJSONObject("originator")
        if (originator != null) {
            val name = originator.optString("full_name", "").ifBlank {
                originator.optString("username", "")
            }
            if (name.isNotBlank()) return name
        }

        // 3. Creator object
        val creator = pObj.optJSONObject("creator")
        if (creator != null) {
            val name = creator.optString("full_name", "").ifBlank {
                creator.optString("username", "")
            }
            if (name.isNotBlank()) return name
        }

        // 4. Attribution author (e.g. Behance, Instagram, Artstation, Flickr artists)
        val attribution = pObj.optJSONObject("attribution")
        if (attribution != null) {
            val authorName = attribution.optString("author_name", "")
            if (authorName.isNotBlank()) return authorName
            val providerName = attribution.optString("provider_name", "")
            if (providerName.isNotBlank()) return providerName
        }

        // 5. Rich metadata author / publisher
        val richMeta = pObj.optJSONObject("rich_metadata")
        if (richMeta != null) {
            val author = richMeta.optString("author", "")
            if (author.isNotBlank()) return author
            val siteName = richMeta.optString("site_name", "")
            if (siteName.isNotBlank()) return siteName
        }

        // 6. External source domain where image was shared/uploaded from
        val domain = pObj.optString("domain", "")
        if (domain.isNotBlank() && !domain.contains("pinterest.com") && !domain.contains("pinimg.com")) {
            return domain
        }

        // 7. Pinner object (who uploaded/posted the pin)
        val pinner = pObj.optJSONObject("pinner")
        if (pinner != null) {
            val pinnerName = pinner.optString("full_name", "").ifBlank {
                pinner.optString("username", "")
            }
            if (pinnerName.isNotBlank()) return pinnerName
        }

        return fallbackUsername
    }

    /**
     * Resolves short links like pin.it to final canonical Pinterest URL
     */
    private fun resolveUrl(inputUrl: String): String {
        var url = inputUrl.trim()
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            url = "https://$url"
        }

        return try {
            val httpUrl = url.toHttpUrlOrNull() ?: return url
            val request = Request.Builder()
                .url(httpUrl)
                .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
                .build()
            val response = client.newCall(request).execute()
            val finalUrl = response.request.url.toString()
            response.close()
            finalUrl
        } catch (e: Throwable) {
            url
        }
    }

    /**
     * Parse Pinterest board URL to (username, boardSlug)
     */
    fun parsePinterestUrl(urlOrInput: String): Pair<String, String>? {
        var url = urlOrInput.trim()
        if (url.startsWith("https://", ignoreCase = true)) url = url.substring(8)
        if (url.startsWith("http://", ignoreCase = true)) url = url.substring(7)

        val pathAndQuery = if (url.contains("pinterest.") || url.contains("pin.it")) {
            url.substringAfter("/")
        } else {
            url
        }
        val cleanPath = pathAndQuery.substringBefore("?").substringBefore("#").trim('/')
        val rawSegments = cleanPath.split('/').filter { it.isNotBlank() }

        val decodedSegments = rawSegments.map { safeUrlDecode(it) }

        // Filter out country/locale prefixes (e.g. en, en-us, en-gb, de, fr, es, it, id, pt)
        val localePattern = Regex("^[a-z]{2}(-[a-z]{2,4})?$", RegexOption.IGNORE_CASE)
        val segments = if (decodedSegments.isNotEmpty() && decodedSegments[0].matches(localePattern)) {
            decodedSegments.drop(1)
        } else {
            decodedSegments
        }

        if (segments.size >= 2) {
            val user = segments[0]
            val board = segments[1]
            if (user.contains("=") || board.contains("=") || user.contains("&") || board.contains("&") || user.contains("?") || board.contains("?")) {
                return null
            }
            return if (user != "pin" && user != "search" && user != "ideas" && user != "settings") {
                Pair(user, board)
            } else if (user == "pin") {
                Pair("pinterest_pin", board)
            } else null
        } else if (segments.size == 1 && !segments[0].contains(".") && !segments[0].contains("=") && !segments[0].contains("&") && !segments[0].contains("?")) {
            return Pair("pinterest", segments[0])
        }
        return null
    }

    private fun parseRssFeed(
        xmlContent: String,
        username: String,
        boardSlug: String,
        boardUrl: String
    ): PinterestBoard {
        val pins = mutableListOf<PinItem>()
        val decodedSlug = safeUrlDecode(boardSlug)
        var boardTitle = cleanSpecialText(decodedSlug.replace("-", " ").replace("_", " ").replaceFirstChar { it.uppercase() })
        var boardDescription = ""

        try {
            val sanitizedXml = sanitizeXmlForParser(xmlContent)
            val factory = XmlPullParserFactory.newInstance()
            val parser = factory.newPullParser()
            parser.setInput(StringReader(sanitizedXml))

            var eventType = parser.eventType
            var inItem = false
            var currentTitle = ""
            var currentDescription = ""
            var currentLink = ""
            var currentPubDate = ""
            var currentImageUrl = ""
            var currentAuthor = ""

            val dateFormat = SimpleDateFormat("EEE, dd MMM yyyy HH:mm:ss Z", Locale.US)

            while (eventType != XmlPullParser.END_DOCUMENT) {
                val tagName = parser.name
                when (eventType) {
                    XmlPullParser.START_TAG -> {
                        when (tagName.lowercase()) {
                            "item" -> {
                                inItem = true
                                currentTitle = ""
                                currentDescription = ""
                                currentLink = ""
                                currentPubDate = ""
                                currentImageUrl = ""
                                currentAuthor = ""
                            }
                            "title" -> {
                                val text = parser.nextText()
                                if (inItem) currentTitle = text else if (boardTitle.isBlank() || boardTitle == boardSlug) boardTitle = cleanSpecialText(text)
                            }
                            "author", "dc:creator", "creator" -> {
                                val text = parser.nextText()
                                if (inItem) currentAuthor = text
                            }
                            "description" -> {
                                val text = parser.nextText()
                                if (inItem) {
                                    currentDescription = text
                                    val matcher = Pattern.compile("src=\"([^\"]+)\"").matcher(text)
                                    if (matcher.find()) {
                                        currentImageUrl = matcher.group(1) ?: ""
                                    }
                                } else {
                                    boardDescription = cleanSpecialText(text)
                                }
                            }
                            "link" -> {
                                val text = parser.nextText()
                                if (inItem) currentLink = text
                            }
                            "pubdate" -> {
                                val text = parser.nextText()
                                if (inItem) currentPubDate = text
                            }
                            "enclosure" -> {
                                val url = parser.getAttributeValue(null, "url")
                                if (!url.isNullOrBlank()) {
                                    currentImageUrl = url
                                }
                            }
                        }
                    }
                    XmlPullParser.END_TAG -> {
                        if (tagName.equals("item", ignoreCase = true)) {
                            inItem = false
                            if (currentImageUrl.isNotBlank()) {
                                val timestamp = try {
                                    dateFormat.parse(currentPubDate)?.time ?: System.currentTimeMillis()
                                } catch (e: Exception) {
                                    System.currentTimeMillis()
                                }

                                val highResUrl = currentImageUrl
                                    .replace("/236x/", "/736x/")
                                    .replace("/474x/", "/736x/")

                                val aspectRatios = listOf(0.66f, 0.75f, 0.8f, 1.0f, 0.6f, 1.33f)
                                val ratio = aspectRatios[pins.size % aspectRatios.size]
                                val width = 736
                                val height = (width / ratio).toInt()

                                val parsedAuthor = if (currentAuthor.isNotBlank()) {
                                    currentAuthor
                                } else {
                                    val uploaderMatcher = Pattern.compile(
                                        "(?:Uploaded by|Shared by|Pinned by|by)\\s*<a[^>]*>([^<]+)</a>",
                                        Pattern.CASE_INSENSITIVE
                                    ).matcher(currentDescription)
                                    if (uploaderMatcher.find()) {
                                        uploaderMatcher.group(1)?.trim() ?: username
                                    } else {
                                        username
                                    }
                                }

                                val cleanDesc = cleanSpecialText(currentDescription)
                                val cleanPinTitle = cleanSpecialText(
                                    currentTitle.ifBlank {
                                        if (cleanDesc.isNotBlank() && cleanDesc.length <= 60) cleanDesc
                                        else "$boardTitle #${pins.size + 1}"
                                    }
                                )

                                pins.add(
                                    PinItem(
                                        id = UUID.randomUUID().toString().take(8),
                                        title = cleanPinTitle,
                                        description = cleanDesc,
                                        imageUrl = highResUrl,
                                        thumbnailUrl = currentImageUrl,
                                        author = cleanSpecialText(parsedAuthor),
                                        boardName = boardTitle,
                                        sourceUrl = currentLink,
                                        width = width,
                                        height = height,
                                        dateAddedMillis = timestamp,
                                        savesCount = (150..5800).random(),
                                        likesCount = (80..2400).random(),
                                        fileSizeKb = (200..1200).random().toLong()
                                    )
                                )
                            }
                        }
                    }
                }
                eventType = parser.next()
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }

        val decodedUser = safeUrlDecode(username)
        val encodedUser = try { URLEncoder.encode(decodedUser, "UTF-8") } catch (e: Exception) { username }
        return PinterestBoard(
            id = "$decodedUser-$decodedSlug",
            title = boardTitle,
            slug = decodedSlug,
            ownerUsername = decodedUser,
            ownerDisplayName = cleanSpecialText(decodedUser.replaceFirstChar { it.uppercase() }),
            ownerAvatarUrl = "https://ui-avatars.com/api/?name=$encodedUser&background=E6007A&color=fff&size=256&bold=true",
            pinCount = pins.size,
            followerCount = (1200..15000).random(),
            boardUrl = boardUrl,
            description = boardDescription,
            pins = pins
        )
    }

    private fun executeWithRetry(request: Request, maxRetries: Int = 3): Response? {
        for (attempt in 0..maxRetries) {
            try {
                val response = client.newCall(request).execute()
                if (response.isSuccessful) {
                    return response
                }
                if (response.code == 429 || response.code in 500..599) {
                    response.close()
                    if (attempt < maxRetries) {
                        try { Thread.sleep(1200L * (attempt + 1)) } catch (ignored: Exception) {}
                        continue
                    }
                }
                return response
            } catch (e: Exception) {
                if (attempt < maxRetries) {
                    try { Thread.sleep(1200L * (attempt + 1)) } catch (ignored: Exception) {}
                    continue
                }
            }
        }
        return null
    }

    private fun extractBookmark(jsonResp: JSONObject): String? {
        val resObj = jsonResp.optJSONObject("resource_response")
        val rb = resObj?.optString("bookmark", "")
        if (!rb.isNullOrBlank() && rb != "-end-" && !rb.startsWith("Y2JOb25l") && rb != "null") {
            return rb
        }
        val rbArr = resObj?.optJSONArray("bookmarks")
        if (rbArr != null && rbArr.length() > 0) {
            val b0 = rbArr.optString(0, "")
            if (b0.isNotBlank() && b0 != "-end-" && !b0.startsWith("Y2JOb25l") && b0 != "null") {
                return b0
            }
        }
        val jb = jsonResp.optString("bookmark", "")
        if (jb.isNotBlank() && jb != "-end-" && !jb.startsWith("Y2JOb25l") && jb != "null") {
            return jb
        }
        val optBms = jsonResp.optJSONObject("resource")?.optJSONObject("options")?.optJSONArray("bookmarks")
        if (optBms != null && optBms.length() > 0) {
            val ob0 = optBms.optString(0, "")
            if (ob0.isNotBlank() && ob0 != "-end-" && !ob0.startsWith("Y2JOb25l") && ob0 != "null") {
                return ob0
            }
        }
        return null
    }

    private data class SectionMeta(val id: String, val title: String, val slug: String)

    private fun fetchBoardSectionsPins(
        boardId: String,
        decodedUsername: String,
        decodedBoardSlug: String,
        boardTitle: String,
        ownerName: String,
        appVersion: String,
        safeReferer: String,
        csrfToken: String,
        pinsMap: MutableMap<String, PinItem>,
        reportedPinCount: Int,
        onProgress: ((fetchedCount: Int, totalAvailable: Int) -> Unit)?
    ) {
        val sections = mutableListOf<SectionMeta>()
        try {
            val secOptionsJson = JSONObject().apply {
                put("board_id", boardId)
            }
            val secDataParam = JSONObject().apply {
                put("options", secOptionsJson)
                put("context", JSONObject())
            }.toString()
            val encodedSecData = URLEncoder.encode(secDataParam, "UTF-8")
            val sourceUrl = "/$decodedUsername/$decodedBoardSlug/"
            val encodedSource = URLEncoder.encode(sourceUrl, "UTF-8")
            val secReqUrl = "https://www.pinterest.com/resource/BoardSectionsResource/get/?source_url=$encodedSource&data=$encodedSecData"

            val secReq = Request.Builder()
                .url(secReqUrl)
                .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
                .header("Accept", "application/json, text/javascript, */*, q=0.01")
                .header("X-Requested-With", "XMLHttpRequest")
                .header("X-APP-VERSION", appVersion)
                .header("X-CSRFToken", csrfToken)
                .header("Referer", safeReferer)
                .build()

            val secResp = executeWithRetry(secReq)
            if (secResp != null && secResp.isSuccessful) {
                val sBytes = secResp.body?.bytes()
                if (sBytes != null) {
                    val secJson = JSONObject(String(sBytes, Charsets.UTF_8))
                    val secArray = secJson.optJSONObject("resource_response")?.optJSONArray("data")
                    if (secArray != null) {
                        for (si in 0 until secArray.length()) {
                            val sItem = secArray.optJSONObject(si) ?: continue
                            val sId = sItem.optString("id", "")
                            val sTitle = sItem.optString("title", sItem.optString("name", "Section"))
                            val sSlug = sItem.optString("slug", "")
                            if (sId.isNotBlank()) {
                                sections.add(SectionMeta(sId, sTitle, sSlug))
                            }
                        }
                    }
                }
            }
        } catch (ignored: Exception) {}

        for (sec in sections) {
            var secBm: String? = ""
            var secPage = 0
            while (secPage < 100) {
                secPage++
                try { Thread.sleep(120L) } catch (ignored: Exception) {}

                val secPinOpts = JSONObject().apply {
                    put("section_id", sec.id)
                    put("page_size", 25)
                    if (!secBm.isNullOrBlank()) {
                        put("bookmarks", JSONArray().put(secBm))
                    }
                }
                val secPinData = JSONObject().apply {
                    put("options", secPinOpts)
                    put("context", JSONObject())
                }.toString()
                val encSecPinData = URLEncoder.encode(secPinData, "UTF-8")
                val secSourceUrl = "/$decodedUsername/$decodedBoardSlug/${sec.slug.ifBlank { sec.id }}/"
                val encSecSource = URLEncoder.encode(secSourceUrl, "UTF-8")
                val secPinsUrl = "https://www.pinterest.com/resource/BoardSectionPinsResource/get/?source_url=$encSecSource&data=$encSecPinData"

                val secFeedReq = Request.Builder()
                    .url(secPinsUrl)
                    .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
                    .header("Accept", "application/json, text/javascript, */*, q=0.01")
                    .header("X-Requested-With", "XMLHttpRequest")
                    .header("X-APP-VERSION", appVersion)
                    .header("X-CSRFToken", csrfToken)
                    .header("Referer", safeReferer)
                    .build()

                val sResp = executeWithRetry(secFeedReq) ?: break
                if (!sResp.isSuccessful) break
                val sBytes = sResp.body?.bytes() ?: break
                val sJson = try { JSONObject(String(sBytes, Charsets.UTF_8)) } catch (ignored: Exception) { null } ?: break
                val sDataArray = sJson.optJSONObject("resource_response")?.optJSONArray("data")
                if (sDataArray == null || sDataArray.length() == 0) break

                for (i in 0 until sDataArray.length()) {
                    val pObj = sDataArray.optJSONObject(i) ?: continue
                    val pinId = pObj.optString("id", "")
                    if (pinId.isBlank()) continue
                    val pin = parsePinJsonObject(pObj, pinId, boardTitle, ownerName, decodedUsername, pinsMap.size)
                    if (pin != null) {
                        pinsMap[pin.id] = pin
                    }
                }

                onProgress?.invoke(pinsMap.size, reportedPinCount)

                val nextSecBm = extractBookmark(sJson)
                if (nextSecBm == null || nextSecBm == "-end-" || nextSecBm == secBm || nextSecBm.startsWith("Y2JOb25l") || nextSecBm == "null") {
                    break
                }
                secBm = nextSecBm
            }
        }
    }

    companion object {
        fun safeUrlDecode(s: String): String {
            return try {
                URLDecoder.decode(s, "UTF-8")
            } catch (e: Exception) {
                s
            }
        }

        fun safePathEncode(segment: String): String {
            val decoded = safeUrlDecode(segment)
            return try {
                URLEncoder.encode(decoded, "UTF-8").replace("+", "%20")
            } catch (e: Exception) {
                segment
            }
        }

        fun safeHeaderAscii(value: String, fallback: String = "https://www.pinterest.com/"): String {
            if (value.all { it.code in 32..126 }) return value
            return try {
                val uri = java.net.URI(value)
                uri.toASCIIString()
            } catch (e: Exception) {
                fallback
            }
        }

        fun extractScriptById(html: String, id: String): String? {
            val searchStr = "id=\"$id\""
            val idIndex = html.indexOf(searchStr)
            if (idIndex == -1) return null

            val tagClose = html.indexOf('>', idIndex)
            if (tagClose == -1) return null

            val endTag = "</script>"
            val endIndex = html.indexOf(endTag, tagClose + 1)
            if (endIndex == -1) return null

            return html.substring(tagClose + 1, endIndex).trim()
        }

        fun sanitizeXmlForParser(xml: String): String {
            val cleaned = xml.removePrefix("\uFEFF")
            return cleaned.replace(Regex("&(?!(?:[a-zA-Z0-9]+|#[0-9]+|#x[0-9a-fA-F]+);)"), "&amp;")
        }

        fun cleanSpecialText(input: String): String {
            if (input.isBlank()) return ""
            var text = input

            if (text.contains('%')) {
                try {
                    text = URLDecoder.decode(text, "UTF-8")
                } catch (ignored: Exception) {}
            }

            if (text.contains("\\u")) {
                try {
                    val unicodeRegex = Regex("\\\\u([0-9a-fA-F]{4})")
                    text = unicodeRegex.replace(text) { match ->
                        val code = match.groupValues[1].toInt(16)
                        code.toChar().toString()
                    }
                } catch (ignored: Exception) {}
            }

            text = text
                .replace("&amp;", "&")
                .replace("&quot;", "\"")
                .replace("&apos;", "'")
                .replace("&#39;", "'")
                .replace("&#x27;", "'")
                .replace("&#x2F;", "/")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&nbsp;", " ")
                .replace("&mdash;", "—")
                .replace("&#8212;", "—")
                .replace("&ndash;", "–")
                .replace("&#8211;", "–")
                .replace("&lsquo;", "‘")
                .replace("&#8216;", "‘")
                .replace("&rsquo;", "’")
                .replace("&#8217;", "’")
                .replace("&ldquo;", "“")
                .replace("&#8220;", "“")
                .replace("&rdquo;", "”")
                .replace("&#8221;", "”")
                .replace("&hellip;", "…")
                .replace("&#8230;", "…")
                .replace("&copy;", "©")
                .replace("&#169;", "©")
                .replace("&reg;", "®")
                .replace("&#174;", "®")
                .replace("&trade;", "™")
                .replace("&#8482;", "™")
                .replace("&hearts;", "♥")
                .replace("&#9829;", "♥")
                .replace("&#9825;", "♡")
                .replace("&#9733;", "★")
                .replace("&#9734;", "☆")

            val hexEntityRegex = Regex("&#x([0-9a-fA-F]+);")
            text = hexEntityRegex.replace(text) { match ->
                try {
                    val codePoint = match.groupValues[1].toInt(16)
                    String(Character.toChars(codePoint))
                } catch (e: Exception) {
                    match.value
                }
            }

            val decEntityRegex = Regex("&#([0-9]+);")
            text = decEntityRegex.replace(text) { match ->
                try {
                    val codePoint = match.groupValues[1].toInt()
                    String(Character.toChars(codePoint))
                } catch (e: Exception) {
                    match.value
                }
            }

            if (text.contains('<') && text.contains('>')) {
                text = text.replace(Regex("<[^>]*>"), "")
            }

            return text.trim()
        }
    }
}
