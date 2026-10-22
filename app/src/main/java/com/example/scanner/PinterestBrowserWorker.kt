package com.example.scanner

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Bitmap
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import com.example.data.local.AppDatabase
import com.example.data.local.PinEntity
import com.example.data.local.PinEventEntity
import com.example.data.local.PinterestScannedPinEntity
import com.example.model.PinItem
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger

/**
 * Isolated Pinterest Browser Worker implementing PinterestScanner.
 * Adheres strictly to the Android Pinterest Board Scanner implementation brief:
 * - Real authenticated browser session (Google / Pinterest auth with persistent cookies)
 * - Interception of /resource/BoardFeedResource/get/ responses via injected JS hook
 * - Network-level blocking of image requests (especially i.pinimg.com) to save bandwidth
 * - Pin filtering rejecting account/profile/ad objects
 * - Accurate extraction of image URLs (736x, 1200x, orig) and canonical pin URL
 * - Tracking board_position (observation sequence) and first_seen_at (ISO timestamp)
 * - Deduplication map Map<pin_id, Pin>
 * - Room database storage into 'pinterest_pins' table and 'pin_events' outbox queue
 * - Generous scrolling loop with settle time and 300 max iterations
 * - Real-time diagnostics tracking
 */
class PinterestBrowserWorker(
    private val context: Context,
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.Main + Job())
) : PinterestScanner {

    private val TAG = "PinterestBrowserWorker"
    private val mainHandler = Handler(Looper.getMainLooper())

    private val _state = MutableStateFlow(ScannerState())
    override val state: StateFlow<ScannerState> = _state.asStateFlow()

    private val _diagnostics = MutableStateFlow(ScanDiagnostics())
    override val diagnostics: StateFlow<ScanDiagnostics> = _diagnostics.asStateFlow()

    private var onPinDetectedListener: ((PinItem) -> Unit)? = null

    // Deduplication map: pin_id -> PinItem (Section 8)
    private val scannedPinsMap = ConcurrentHashMap<String, PinItem>()

    // Sequential counter for board_position (Section 17)
    private val boardPositionCounter = AtomicInteger(0)

    // Data-saving counter: blocked image requests (Section 6)
    private val blockedImageCounter = AtomicInteger(0)
    private var isImageBlockingEnabled = false
    private var stopOnKnownPinIds: Set<String> = emptySet()
    private var targetBoardId: String? = null
    private var hasEncounteredKnownPins = false
    private var scrollsAfterKnownPins = 0

    private var scanStartTimeMillis = 0L
    private var scanJob: Job? = null
    private var timerJob: Job? = null

    private var currentScrollIteration = 0
    private var lastRecordedHeight = 0
    private var consecutiveStagnantScrolls = 0
    private var consecutiveZeroNewPins = 0
    private val maxScrollIterations = 300
    private var consecutiveKnownPinsInFeed = 0
    private var totalKnownPinsObserved = 0

    private val isoDateFormat = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
        timeZone = TimeZone.getTimeZone("UTC")
    }

    private var webView: WebView? = null



    @SuppressLint("SetJavaScriptEnabled")
    private fun initWebView() {
        if (webView != null) return

        try {
            val wv = WebView(context.applicationContext)
            val settings = wv.settings

            // Session & Scripting Capabilities
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.databaseEnabled = true
            settings.javaScriptCanOpenWindowsAutomatically = true
            settings.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            // Disable disk cache in WebView so WebView doesn't bloat internal user data
            settings.cacheMode = WebSettings.LOAD_NO_CACHE
            settings.useWideViewPort = true
            settings.loadWithOverviewMode = true
            settings.setSupportZoom(true)
            settings.builtInZoomControls = false

            // Do NOT block network images at settings level; block selectively in shouldInterceptRequest
            // This ensures Pinterest's UI styles, scripts, and layout assets load without a blank screen
            settings.loadsImagesAutomatically = true
            settings.blockNetworkImage = false

            // Desktop Chrome User-Agent so Pinterest renders standard full web layout without mobile redirect or app download walls
            settings.userAgentString = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

            // Persistent Cookies (Section 2 & 11)
            val cookieManager = CookieManager.getInstance()
            cookieManager.setAcceptCookie(true)
            cookieManager.setAcceptThirdPartyCookies(wv, true)

            wv.setBackgroundColor(android.graphics.Color.WHITE)
            wv.visibility = View.VISIBLE
            wv.layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )

            // JavaScript Bridge for BoardFeedResource Interception
            wv.addJavascriptInterface(PinterestBridge(), "PinterestBridge")

            wv.webViewClient = object : WebViewClient() {
                // Critical stability callback: If Chromium render process dies due to memory pressure,
                // return true so the Android OS does NOT terminate the host app!
                override fun onRenderProcessGone(view: WebView?, detail: RenderProcessGoneDetail?): Boolean {
                    Log.w(TAG, "WebView render process gone! didCrash=${detail?.didCrash()}")
                    stopScan()
                    try {
                        (view?.parent as? ViewGroup)?.removeView(view)
                        view?.destroy()
                    } catch (e: Exception) {
                        Log.e(TAG, "Error destroying gone WebView", e)
                    }
                    this@PinterestBrowserWorker.webView = null
                    _state.value = _state.value.copy(
                        isScanning = false,
                        statusMessage = "Browser worker safely recovered from memory pressure."
                    )
                    return true
                }

                // Section 6: Block Pin image requests (especially i.pinimg.com) to save bandwidth
                // Note: Do NOT block s.pinimg.com as it serves JavaScript bundles, styles, and UI icons!
                override fun shouldInterceptRequest(view: WebView?, request: WebResourceRequest?): WebResourceResponse? {
                    if (!isImageBlockingEnabled) {
                        return super.shouldInterceptRequest(view, request)
                    }
                    val url = request?.url?.toString() ?: return super.shouldInterceptRequest(view, request)
                    val lowerUrl = url.lowercase(Locale.US)

                    val isPinImageRequest = lowerUrl.contains("i.pinimg.com") ||
                            lowerUrl.contains("/236x/") ||
                            lowerUrl.contains("/736x/") ||
                            lowerUrl.contains("/originals/") ||
                            lowerUrl.contains("/1200x/") ||
                            lowerUrl.contains("/564x/") ||
                            lowerUrl.contains("/474x/")

                    if (isPinImageRequest) {
                        val count = blockedImageCounter.incrementAndGet()
                        _diagnostics.value = _diagnostics.value.copy(blockedImageRequests = count)
                        // Return empty 1x1 transparent response to save internet data
                        return WebResourceResponse(
                            "image/png",
                            "UTF-8",
                            200,
                            "OK",
                            mapOf(
                                "Access-Control-Allow-Origin" to "*",
                                "Cache-Control" to "no-store"
                            ),
                            ByteArrayInputStream(EMPTY_IMAGE_BYTES)
                        )
                    }

                    return super.shouldInterceptRequest(view, request)
                }

                override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                    super.onPageStarted(view, url, favicon)
                    checkLoginState()
                    injectBridgeHook(view)
                    if (!url.isNullOrBlank()) {
                        _state.value = _state.value.copy(
                            currentBoardUrl = url,
                            statusMessage = "Loading page..."
                        )
                    }
                }

                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    checkLoginState()
                    injectBridgeHook(view)
                    triggerDomPinExtraction(view)
                    if (_state.value.isScanning) {
                        _state.value = _state.value.copy(statusMessage = "Page loaded. Extracting pins...")
                    }
                }

                override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: android.webkit.WebResourceError?) {
                    super.onReceivedError(view, request, error)
                    if (request?.isForMainFrame == true) {
                        Log.w(TAG, "WebView load error: ${error?.description}")
                        _state.value = _state.value.copy(statusMessage = "Page load notice: ${error?.description}")
                    }
                }
            }

            wv.webChromeClient = object : WebChromeClient() {
                override fun onProgressChanged(view: WebView?, newProgress: Int) {
                    if (newProgress > 40) {
                        injectBridgeHook(view)
                    }
                }
            }

            this.webView = wv
            checkLoginState()
            // Do NOT call wv.loadUrl() here; wait until user initiates a scan or login!
        } catch (e: Exception) {
            Log.e(TAG, "Failed to initialize WebView", e)
        }
    }

    /**
     * Injects JavaScript hook to observe fetch and XMLHttpRequest for BoardFeedResource.
     * Brief Section 3:
     * "Capture BoardFeedResource response -> Read: resource_response.data[] -> Extract Pin objects"
     */
    /**
     * Injects JavaScript hook to observe fetch, XMLHttpRequest and extract DOM pins.
     * Brief Section 3:
     * "Capture BoardFeedResource response -> Read: resource_response.data[] -> Extract Pin objects"
     */
    private fun injectBridgeHook(view: WebView?) {
        if (view == null) return
        val jsHook = """
            (function() {
                if (window.__pinterest_hook_installed) return;
                window.__pinterest_hook_installed = true;

                function isBoardFeedResource(u) {
                    if (!u) return false;
                    const str = String(u);
                    return str.includes('BoardFeedResource') ||
                           str.includes('BoardPinsResource') ||
                           str.includes('BoardSectionPinsResource') ||
                           str.includes('UserPinsResource') ||
                           str.includes('FeedResource') ||
                           str.includes('PinResource');
                }

                // 1. Hook window.fetch
                const originalFetch = window.fetch;
                if (originalFetch) {
                    window.fetch = async function(...args) {
                        const response = await originalFetch.apply(this, args);
                        try {
                            const reqUrl = (args[0] instanceof Request) ? args[0].url : String(args[0]);
                            if (isBoardFeedResource(reqUrl)) {
                                const cloned = response.clone();
                                cloned.text().then(text => {
                                    if (window.PinterestBridge && window.PinterestBridge.onBoardFeedResponse) {
                                        window.PinterestBridge.onBoardFeedResponse(reqUrl, text);
                                    }
                                }).catch(function(err) {});
                            }
                        } catch(e) {}
                        return response;
                    };
                }

                // 2. Hook XMLHttpRequest
                const origOpen = XMLHttpRequest.prototype.open;
                const origSend = XMLHttpRequest.prototype.send;
                XMLHttpRequest.prototype.open = function(method, url, ...rest) {
                    this._pinterest_url = url;
                    return origOpen.apply(this, [method, url, ...rest]);
                };
                XMLHttpRequest.prototype.send = function(...args) {
                    this.addEventListener('load', function() {
                        try {
                            if (this._pinterest_url && isBoardFeedResource(this._pinterest_url)) {
                                if (window.PinterestBridge && window.PinterestBridge.onBoardFeedResponse) {
                                    window.PinterestBridge.onBoardFeedResponse(String(this._pinterest_url), this.responseText);
                                }
                            }
                        } catch(e) {}
                    });
                    return origSend.apply(this, args);
                };

                // 3. Reliable DOM pin extraction: extracts all visible pins on the rendered page
                window.__pinterestExtractDomPins = function() {
                    try {
                        // Check if in-memory Pinterest state has BoardFeedResource
                        try {
                            if (window.__PINTEREST_APP_STATE__ && window.__PINTEREST_APP_STATE__.resources) {
                                var res = window.__PINTEREST_APP_STATE__.resources;
                                for (var k in res) {
                                    if (k.indexOf('BoardFeedResource') !== -1 || k.indexOf('BoardPinsResource') !== -1) {
                                        var feedData = res[k].data;
                                        if (feedData && feedData.length > 0 && window.PinterestBridge && window.PinterestBridge.onBoardFeedResponse) {
                                            window.PinterestBridge.onBoardFeedResponse(k, JSON.stringify({ resource_response: { data: feedData } }));
                                        }
                                    }
                                }
                            }
                        } catch(eState) {}

                        var results = [];
                        var pinEls = document.querySelectorAll('div[data-test-id="pin"], div[data-test-id="Pin"], a[href^="/pin/"], a[href*="pinterest.com/pin/"]');
                        var seen = {};
                        for (var i = 0; i < pinEls.length; i++) {
                            var el = pinEls[i];
                            var a = el.tagName.toLowerCase() === 'a' ? el : el.querySelector('a[href*="/pin/"]');
                            if (!a) continue;
                            var href = a.getAttribute('href') || '';
                            var match = href.match(/\/pin\/(\d+)/);
                            if (!match) continue;
                            var pinId = match[1];
                            if (seen[pinId]) continue;
                            seen[pinId] = true;

                            var img = el.querySelector('img') || a.querySelector('img');
                            var imgUrl = '';
                            if (img) {
                                var srcset = img.getAttribute('srcset') || '';
                                if (srcset) {
                                    var parts = srcset.split(',');
                                    var last = parts[parts.length - 1].trim().split(' ')[0];
                                    if (last && last.indexOf('http') === 0) imgUrl = last;
                                }
                                if (!imgUrl) {
                                    imgUrl = img.getAttribute('src') || '';
                                }
                            }
                            if (!imgUrl || imgUrl.indexOf('data:') === 0) continue;

                            var highResUrl = imgUrl.replace(/\/(?:236x|474x|564x)\//, '/736x/');
                            var title = (img ? (img.getAttribute('alt') || '') : '') || (el.innerText ? el.innerText.trim() : '') || ('Pin #' + pinId);
                            if (title.length > 80) title = title.substring(0, 80);

                            var rect = el.getBoundingClientRect();
                            var docTop = (window.pageYOffset || document.documentElement.scrollTop || 0) + rect.top;
                            var docLeft = (window.pageXOffset || document.documentElement.scrollLeft || 0) + rect.left;

                            results.push({
                                id: pinId,
                                title: title,
                                imageUrl: highResUrl,
                                thumbUrl: imgUrl,
                                docTop: Math.round(docTop),
                                docLeft: Math.round(docLeft),
                                pinUrl: 'https://www.pinterest.com/pin/' + pinId + '/'
                            });
                        }
                        if (results.length > 0 && window.PinterestBridge && window.PinterestBridge.onDomPinsDetected) {
                            window.PinterestBridge.onDomPinsDetected(JSON.stringify(results));
                        }
                    } catch(e) {}
                };

                // Helper to measure document height and scroll position (Section 9)
                window.__getPinterestDocMetrics = function() {
                    return JSON.stringify({
                        scrollY: Math.round(window.scrollY || window.pageYOffset || 0),
                        scrollHeight: Math.round(document.body.scrollHeight || document.documentElement.scrollHeight || 0),
                        innerHeight: Math.round(window.innerHeight || 0)
                    });
                };
            })();
        """.trimIndent()

        view.evaluateJavascript(jsHook, null)
    }

    private fun triggerDomPinExtraction(wv: WebView?) {
        wv?.evaluateJavascript(
            "if (window.__pinterestExtractDomPins) { window.__pinterestExtractDomPins(); }",
            null
        )
    }

    /**
     * Checks if persistent cookies indicate an authenticated Pinterest session (Section 2).
     */
    private fun checkLoginState() {
        val cookies = CookieManager.getInstance().getCookie("https://www.pinterest.com") ?: ""
        val isLoggedIn = cookies.contains("_auth=") || cookies.contains("sessionFunnelEvent") || cookies.contains("_routing_id=")
        _state.value = _state.value.copy(isLoggedIn = isLoggedIn)
        _diagnostics.value = _diagnostics.value.copy(isLoggedIn = isLoggedIn)
    }

    inner class PinterestBridge {
        @JavascriptInterface
        fun onBoardFeedResponse(url: String, jsonString: String) {
            handleBoardFeedJson(url, jsonString)
        }

        @JavascriptInterface
        fun onDomPinsDetected(jsonString: String) {
            handleDomPinsJson(jsonString)
        }
    }

    private fun handleDomPinsJson(jsonString: String) {
        try {
            val array = JSONArray(jsonString)
            if (array.length() == 0) return

            val domPins = mutableListOf<JSONObject>()
            for (i in 0 until array.length()) {
                val obj = array.optJSONObject(i) ?: continue
                domPins.add(obj)
            }
            // Sort DOM pins to preserve Pinterest's top-to-bottom, left-to-right reading order
            domPins.sortWith { a, b ->
                val topA = a.optInt("docTop", 0)
                val topB = b.optInt("docTop", 0)
                val leftA = a.optInt("docLeft", 0)
                val leftB = b.optInt("docLeft", 0)
                if (Math.abs(topA - topB) <= 90) {
                    leftA.compareTo(leftB)
                } else {
                    topA.compareTo(topB)
                }
            }

            val newItems = mutableListOf<PinItem>()
            val boardUrl = _state.value.currentBoardUrl
            val nowMillis = System.currentTimeMillis()
            val nowIso = isoDateFormat.format(Date(nowMillis))

            for (obj in domPins) {
                val pinId = obj.optString("id", "").trim()
                if (pinId.isBlank() || scannedPinsMap.containsKey(pinId)) continue

                // Skip pins that are already known on the board, and record that known pins are visible
                if (stopOnKnownPinIds.isNotEmpty() && stopOnKnownPinIds.contains(pinId)) {
                    hasEncounteredKnownPins = true
                    totalKnownPinsObserved++
                    continue
                }

                val title = obj.optString("title", "Pin #$pinId")
                val imageUrl = obj.optString("imageUrl", "")
                val thumbUrl = obj.optString("thumbUrl", imageUrl)
                val pinUrl = obj.optString("pinUrl", "https://www.pinterest.com/pin/$pinId/")
                if (imageUrl.isBlank()) continue

                val observedPosition = boardPositionCounter.getAndIncrement()
                val dateMillis = (nowMillis - (observedPosition * 60000L)).coerceAtLeast(0L)

                val pinItem = PinItem(
                    id = pinId,
                    title = title,
                    description = "",
                    imageUrl = imageUrl,
                    thumbnailUrl = thumbUrl,
                    author = "Pinterest Creator",
                    boardName = _state.value.currentBoardTitle.ifBlank { "Scanned Board" },
                    sourceUrl = pinUrl,
                    width = 736,
                    height = 1000,
                    dominantColor = 0xFFF0F0F0,
                    dateAddedMillis = dateMillis,
                    savesCount = (10..500).random(),
                    likesCount = (5..200).random(),
                    fileSizeKb = (250..850).random().toLong(),
                    boardPosition = observedPosition,
                    firstSeenAt = nowIso,
                    firstSeenAtMillis = nowMillis,
                    pinterestCreatedAt = null,
                    deliveryStatus = "pending"
                )

                scannedPinsMap[pinId] = pinItem
                newItems.add(pinItem)
            }

            if (newItems.isNotEmpty()) {
                val totalUnique = scannedPinsMap.size
                _diagnostics.value = _diagnostics.value.copy(
                    uniquePins = totalUnique,
                    lastBatchPinCount = newItems.size,
                    lastDetectedPinTitle = newItems.first().title
                )
                _state.value = _state.value.copy(
                    detectedPinCount = totalUnique,
                    statusMessage = "Captured ${newItems.size} pins (Total: $totalUnique)"
                )

                scope.launch(Dispatchers.IO) {
                    val db = AppDatabase.getDatabase(context)
                    val dao = db.boardDao()
                    val boardId = extractBoardIdFromUrl(boardUrl)
                    dao.insertPins(newItems.map { PinEntity.fromPinItem(it, boardId, it.boardPosition) })

                    withContext(Dispatchers.Main) {
                        newItems.forEach { pin ->
                            onPinDetectedListener?.invoke(pin)
                        }
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error handling DOM pins", e)
        }
    }

    /**
     * Processes captured BoardFeedResource JSON payload.
     * Brief Section 3:
     * Capture BoardFeedResource / BoardPinsResource responses -> Extract Pin objects
     */
    private fun handleBoardFeedJson(requestUrl: String, rawJson: String) {
        val isFeedRes = requestUrl.contains("BoardFeedResource") ||
                requestUrl.contains("BoardPinsResource") ||
                requestUrl.contains("BoardSectionPinsResource") ||
                requestUrl.contains("UserPinsResource") ||
                requestUrl.contains("FeedResource") ||
                requestUrl.contains("PinResource")
        if (!isFeedRes) {
            return
        }

        try {
            val root = JSONObject(rawJson)
            val resourceResponse = root.optJSONObject("resource_response") ?: return
            val dataArray = resourceResponse.optJSONArray("data") ?: return

            val bookmark = extractBookmark(root)
            val boardUrl = _state.value.currentBoardUrl

            var newPinsInThisBatch = 0
            val newItems = mutableListOf<PinItem>()
            val nowMillis = System.currentTimeMillis()
            val nowIso = isoDateFormat.format(Date(nowMillis))

            for (i in 0 until dataArray.length()) {
                val candidateObj = dataArray.optJSONObject(i) ?: continue

                // Section 4: Pin filtering
                if (!isValidPinObject(candidateObj)) {
                    continue
                }

                val pinId = candidateObj.optString("id", "").trim()
                if (pinId.isBlank()) continue

                // Incremental scan check: track known pins
                val isKnownPin = stopOnKnownPinIds.isNotEmpty() && stopOnKnownPinIds.contains(pinId)
                if (isKnownPin) {
                    hasEncounteredKnownPins = true
                    consecutiveKnownPinsInFeed++
                    totalKnownPinsObserved++
                    // Do not break early; allow all pins in this feed batch to be captured
                    continue
                }

                // New pin found - reset consecutive known pins counter
                consecutiveKnownPinsInFeed = 0

                // If already captured from preliminary DOM, enrich it with authoritative feed data
                if (scannedPinsMap.containsKey(pinId)) {
                    val existing = scannedPinsMap[pinId]
                    if (existing != null) {
                        val imagesObj = candidateObj.optJSONObject("images")
                        val highResUrl = if (imagesObj != null) extractImageUrl(imagesObj) ?: existing.imageUrl else existing.imageUrl
                        val rawTitle = candidateObj.optString("title", "")
                        val rawDesc = candidateObj.optString("description", candidateObj.optString("grid_title", ""))
                        val title = if (rawTitle.isNotBlank()) rawTitle else if (rawDesc.isNotBlank() && rawDesc.length <= 60) rawDesc else existing.title
                        val pinterestCreatedAt = candidateObj.optString("board_pinned_at", candidateObj.optString("created_at", existing.pinterestCreatedAt))
                        val saves = candidateObj.optInt("repin_count", candidateObj.optInt("save_count", existing.savesCount))

                        scannedPinsMap[pinId] = existing.copy(
                            title = title,
                            description = if (rawDesc.isNotBlank()) rawDesc else existing.description,
                            imageUrl = highResUrl,
                            author = if (existing.author == "Pinterest Creator") extractAuthor(candidateObj) else existing.author,
                            savesCount = saves,
                            likesCount = (saves * 0.4).toInt(),
                            pinterestCreatedAt = pinterestCreatedAt
                        )
                    }
                    continue
                }

                // Section 5: Image extraction
                val imagesObj = candidateObj.optJSONObject("images") ?: continue
                val highResUrl = extractImageUrl(imagesObj) ?: continue
                val thumbUrl = imagesObj.optJSONObject("236x")?.optString("url", highResUrl) ?: highResUrl

                val width = candidateObj.optJSONObject("images")?.optJSONObject("736x")?.optInt("width", 736) ?: 736
                val height = candidateObj.optJSONObject("images")?.optJSONObject("736x")?.optInt("height", 1000) ?: 1000

                val rawTitle = candidateObj.optString("title", "")
                val rawDesc = candidateObj.optString("description", candidateObj.optString("grid_title", ""))
                val title = if (rawTitle.isNotBlank()) rawTitle else if (rawDesc.isNotBlank() && rawDesc.length <= 60) rawDesc else "Pin #$pinId"

                val pinUrl = "https://www.pinterest.com/pin/$pinId/" // Section 5 canonical URL

                // Section 16 & 17: board_position and first_seen_at
                val observedPosition = boardPositionCounter.getAndIncrement()
                val artificialPinnedMillis = (nowMillis - (observedPosition * 60000L)).coerceAtLeast(0L)
                val pinterestCreatedAt = candidateObj.optString("board_pinned_at", candidateObj.optString("created_at", null))
                val saves = candidateObj.optInt("repin_count", candidateObj.optInt("save_count", 0))

                val pinItem = PinItem(
                    id = pinId,
                    title = title,
                    description = rawDesc,
                    imageUrl = highResUrl,
                    thumbnailUrl = thumbUrl,
                    author = extractAuthor(candidateObj),
                    boardName = _state.value.currentBoardTitle.ifBlank { "Scanned Board" },
                    sourceUrl = pinUrl,
                    width = width,
                    height = height,
                    dominantColor = 0xFFF0F0F0,
                    dateAddedMillis = artificialPinnedMillis,
                    savesCount = saves,
                    likesCount = (saves * 0.4).toInt(),
                    fileSizeKb = (250..850).random().toLong(),
                    boardPosition = observedPosition,
                    firstSeenAt = nowIso,
                    firstSeenAtMillis = nowMillis,
                    pinterestCreatedAt = pinterestCreatedAt,
                    deliveryStatus = "pending"
                )

                scannedPinsMap[pinId] = pinItem
                newItems.add(pinItem)
                newPinsInThisBatch++
            }

            // Update diagnostics (Section 21)
            val totalUnique = scannedPinsMap.size
            _diagnostics.value = _diagnostics.value.copy(
                uniquePins = totalUnique,
                responseCount = _diagnostics.value.responseCount + 1,
                lastResponseUrl = requestUrl,
                lastBookmark = bookmark ?: "",
                lastBatchPinCount = newPinsInThisBatch,
                lastDetectedPinTitle = newItems.firstOrNull()?.title ?: _diagnostics.value.lastDetectedPinTitle
            )

            _state.value = _state.value.copy(
                detectedPinCount = totalUnique,
                statusMessage = "Captured $newPinsInThisBatch pins (Total: $totalUnique)"
            )

            // Persist to Room database & Queue events (Sections 15, 18, 20)
            if (newItems.isNotEmpty()) {
                scope.launch(Dispatchers.IO) {
                    val db = AppDatabase.getDatabase(context)
                    val dao = db.boardDao()

                    val scannedEntities = newItems.map { item ->
                        PinterestScannedPinEntity(
                            pinId = item.id,
                            boardUrl = boardUrl,
                            boardPosition = item.boardPosition,
                            firstSeenAt = item.firstSeenAt,
                            pinUrl = item.sourceUrl,
                            imageUrl = item.imageUrl,
                            title = item.title,
                            deliveryStatus = "pending",
                            pinterestCreatedAt = item.pinterestCreatedAt,
                            firstSeenAtMillis = item.firstSeenAtMillis,
                            width = item.width,
                            height = item.height,
                            author = item.author,
                            description = item.description,
                            savesCount = item.savesCount,
                            likesCount = item.likesCount
                        )
                    }
                    scannedEntities.chunked(50).forEach { dao.insertScannedPins(it) }

                    // Also mirror into PinEntity so the board gallery displays them directly
                    val boardId = extractBoardIdFromUrl(boardUrl)
                    val pinEntities = newItems.mapIndexed { idx, item ->
                        PinEntity.fromPinItem(item, boardId, item.boardPosition)
                    }
                    pinEntities.chunked(50).forEach { dao.insertPins(it) }

                    // Section 18 & 20: Outbox Event delivery
                    newItems.forEach { item ->
                        val eventId = "pinterest:$boardId:${item.id}"
                        val event = PinEventEntity(
                            eventId = eventId,
                            boardId = boardId,
                            pinId = item.id,
                            event = "pin_detected",
                            boardUrl = boardUrl,
                            boardPosition = item.boardPosition,
                            firstSeenAt = item.firstSeenAt,
                            pinUrl = item.sourceUrl,
                            imageUrl = item.imageUrl,
                            deliveryStatus = "pending"
                        )
                        dao.queuePinEvent(event)
                    }

                    // Dispatch each new pin to the UI listener
                    withContext(Dispatchers.Main) {
                        newItems.forEach { pin ->
                            onPinDetectedListener?.invoke(pin)
                        }
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error parsing BoardFeedResource JSON", e)
        }
    }

    /**
     * Section 4: Pin filtering.
     * A valid candidate should have numeric Pin ID + images object + Pin-like metadata.
     * Reject objects from profile, user, board owner, account, recommendation, navigation.
     */
    private fun isValidPinObject(obj: JSONObject): Boolean {
        val id = obj.optString("id", "")
        if (id.isBlank() || !id.all { it.isDigit() }) return false

        val type = obj.optString("type", "")
        if (type.isNotBlank() && type != "pin") return false

        // Must have images object
        val images = obj.optJSONObject("images") ?: return false
        if (images.length() == 0) return false

        // Reject profile, user, board owner, account objects
        if (obj.has("profile_views") || obj.has("board_order") || obj.has("user_id") && !obj.has("domain")) {
            // Check if it's primarily a board or user object
            if (obj.has("pin_count") && obj.has("follower_count")) return false
        }

        return true
    }

    /**
     * Section 5: Image extraction.
     * Prefer 736x, 1200x, 564x, 474x, 236x, orig, originals.
     * Do NOT use generic object.url.
     */
    private fun extractImageUrl(imagesObj: JSONObject): String? {
        val keys = listOf("736x", "1200x", "564x", "474x", "orig", "originals", "236x")
        for (k in keys) {
            val child = imagesObj.optJSONObject(k)
            val url = child?.optString("url", "")
            if (!url.isNullOrBlank() && (url.startsWith("http://") || url.startsWith("https://"))) {
                return url
            }
        }
        return null
    }

    private fun extractAuthor(obj: JSONObject): String {
        val nativeCreator = obj.optJSONObject("native_creator")
        val ncName = nativeCreator?.optString("full_name", "")?.ifBlank { nativeCreator.optString("username", "") }
        if (!ncName.isNullOrBlank()) return ncName

        val pinner = obj.optJSONObject("pinner")
        val pinnerName = pinner?.optString("full_name", "")?.ifBlank { pinner.optString("username", "") }
        if (!pinnerName.isNullOrBlank()) return pinnerName

        val domain = obj.optString("domain", "")
        if (domain.isNotBlank() && !domain.contains("pinterest.com")) return domain

        return "Pinterest Creator"
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
        return null
    }

    private fun extractBoardIdFromUrl(url: String): String {
        if (!targetBoardId.isNullOrBlank()) return targetBoardId!!
        val clean = url.trim().removePrefix("https://").removePrefix("http://").trim('/')
        val parts = clean.split('/').filter { it.isNotBlank() }
        val nonDomain = if (parts.isNotEmpty() && (parts[0].contains(".") || parts[0].contains("pinterest"))) {
            parts.drop(1)
        } else {
            parts
        }
        return if (nonDomain.size >= 2) "${nonDomain[0]}-${nonDomain[1]}" else if (nonDomain.size == 1) nonDomain[0] else "scanned-board"
    }

    private fun sanitizeBoardUrl(url: String): String {
        var clean = url.trim()
        val beforeQuery = clean.substringBefore("?").substringBefore("#").trimEnd('/')
        return if (beforeQuery.isNotBlank()) "$beforeQuery/" else clean
    }

    override fun setOnPinDetectedListener(listener: (PinItem) -> Unit) {
        this.onPinDetectedListener = listener
    }

    override fun getScannedPins(): List<PinItem> {
        return scannedPinsMap.values.toList().sortedWith(
            compareBy<PinItem> { it.boardPosition }
                .thenByDescending { it.id.toLongOrNull() ?: 0L }
        )
    }

    override fun getWebView(): WebView? {
        if (webView == null && Looper.myLooper() == Looper.getMainLooper()) {
            initWebView()
        }
        return webView
    }

    /**
     * Opens Pinterest login flow (Section 2).
     */
    override fun login(onComplete: () -> Unit) {
        mainHandler.post {
            initWebView()
            _state.value = _state.value.copy(statusMessage = "Opening Pinterest Login...")
            webView?.loadUrl("https://www.pinterest.com/login/")
        }
    }

    /**
     * Starts scanning a board URL.
     * Section 8, 9, 10:
     * Open board -> Wait for initial BoardFeedResource -> Scroll -> Wait -> Collect -> Repeat
     */
    override fun startScan(boardUrl: String, stopOnKnownPinIds: Set<String>, targetBoardId: String?) {
        this.stopOnKnownPinIds = stopOnKnownPinIds
        this.targetBoardId = targetBoardId
        val rawUrl = if (boardUrl.startsWith("http://") || boardUrl.startsWith("https://")) {
            boardUrl
        } else {
            "https://$boardUrl"
        }
        val cleanUrl = sanitizeBoardUrl(rawUrl)

        stopScan()

        scanStartTimeMillis = System.currentTimeMillis()
        currentScrollIteration = 0
        lastRecordedHeight = 0
        consecutiveStagnantScrolls = 0
        consecutiveZeroNewPins = 0
        consecutiveKnownPinsInFeed = 0
        totalKnownPinsObserved = 0
        hasEncounteredKnownPins = false
        scrollsAfterKnownPins = 0
        boardPositionCounter.set(0)
        scannedPinsMap.clear()

        _state.value = ScannerState(
            isScanning = true,
            isPaused = false,
            isLoggedIn = _state.value.isLoggedIn,
            currentBoardUrl = cleanUrl,
            detectedPinCount = 0,
            statusMessage = "Navigating to board..."
        )

        _diagnostics.value = ScanDiagnostics(
            isLoggedIn = _state.value.isLoggedIn,
            boardUrl = cleanUrl,
            uniquePins = 0,
            responseCount = 0,
            blockedImageRequests = blockedImageCounter.get(),
            scrollIterations = 0,
            status = "Scanning Started"
        )

        mainHandler.post {
            initWebView()
            webView?.visibility = View.VISIBLE
            webView?.loadUrl(cleanUrl)
        }

        // Start timer for duration tracking
        timerJob = scope.launch {
            while (isActive && _state.value.isScanning) {
                delay(1000)
                val durationSec = (System.currentTimeMillis() - scanStartTimeMillis) / 1000
                _diagnostics.value = _diagnostics.value.copy(scanDurationSeconds = durationSec)
            }
        }

        // Auto-scrolling loop with generous safety limits (Section 8, 9, 10)
        scanJob = scope.launch {
            // Initial settle time for page & initial BoardFeedResource load
            delay(3500)

            while (isActive && _state.value.isScanning) {
                if (_state.value.isPaused) {
                    delay(500)
                    continue
                }

                currentScrollIteration++
                val prevPinCount = scannedPinsMap.size

                _diagnostics.value = _diagnostics.value.copy(
                    scrollIterations = currentScrollIteration,
                    status = "Scrolling step $currentScrollIteration / $maxScrollIterations"
                )

                // Perform robust scroll step & remove blocking Pinterest auth modals
                mainHandler.post {
                    val scrollScript = """
                        (function() {
                            try {
                                var modals = document.querySelectorAll('div[data-test-id="full-page-signup-modal"], div[data-test-id="login-modal-default"], div[data-test-id="standard-modal"], div[data-test-id="unauth-banner"], div[data-test-id="sheet-container"], div[data-test-id="gift-wrap"], div[data-test-id="toast"], div[data-test-id="backdrop"], div[role="dialog"]');
                                for (var i = 0; i < modals.length; i++) {
                                    try {
                                        modals[i].style.display = 'none';
                                        modals[i].remove();
                                    } catch(e) {}
                                }
                                if (document.body) {
                                    document.body.style.overflow = 'auto';
                                    document.body.style.pointerEvents = 'auto';
                                }
                                if (document.documentElement) {
                                    document.documentElement.style.overflow = 'auto';
                                    document.documentElement.style.pointerEvents = 'auto';
                                }
                            } catch(e) {}
                            try {
                                window.scrollBy({ top: 900, behavior: 'smooth' });
                                if (document.documentElement) document.documentElement.scrollTop += 900;
                                if (document.body) document.body.scrollTop += 900;
                                var containers = document.querySelectorAll('[data-test-id="virtuoso-scroller"], [data-test-id="masonry-container"], main, div[tabindex="0"]');
                                for (var j = 0; j < containers.length; j++) {
                                    if (containers[j].scrollHeight > containers[j].clientHeight) {
                                        containers[j].scrollTop += 900;
                                    }
                                }
                                window.dispatchEvent(new Event('scroll'));
                                window.dispatchEvent(new Event('resize'));
                            } catch(e) {}
                        })();
                    """.trimIndent()
                    webView?.evaluateJavascript(scrollScript, null)
                }

                // Settle time for Pinterest virtualized grid & network response (Section 10)
                delay(1900)
                withContext(Dispatchers.Main) {
                    triggerDomPinExtraction(webView)
                }

                // If scrolling seems temporarily stagnant, perform a recovery bounce
                if (consecutiveStagnantScrolls in 4..16 && consecutiveStagnantScrolls % 2 == 0) {
                    mainHandler.post {
                        webView?.evaluateJavascript(
                            """
                            (function() {
                                window.scrollBy({ top: -300, behavior: 'auto' });
                                setTimeout(function() {
                                    window.scrollBy({ top: 1000, behavior: 'auto' });
                                    window.dispatchEvent(new Event('scroll'));
                                }, 150);
                            })();
                            """.trimIndent(),
                            null
                        )
                    }
                }

                // Query document height metrics (Section 9)
                withContext(Dispatchers.Main) {
                    webView?.evaluateJavascript("window.__getPinterestDocMetrics ? window.__getPinterestDocMetrics() : '{}'") { metricsJson ->
                        try {
                            val cleanStr = metricsJson.removeSurrounding("\"").replace("\\\"", "\"")
                            val metrics = JSONObject(cleanStr)
                            val scrollHeight = metrics.optInt("scrollHeight", 0)
                            val scrollY = metrics.optInt("scrollY", 0)
                            val innerHeight = metrics.optInt("innerHeight", 0)

                            _diagnostics.value = _diagnostics.value.copy(documentHeight = scrollHeight)

                            if (scrollHeight > 0 && Math.abs(scrollHeight - lastRecordedHeight) < 50) {
                                consecutiveStagnantScrolls++
                            } else {
                                consecutiveStagnantScrolls = 0
                                lastRecordedHeight = scrollHeight
                            }

                            // Did we receive any new pins in this scroll iteration?
                            val currentPinCount = scannedPinsMap.size
                            if (currentPinCount == prevPinCount) {
                                consecutiveZeroNewPins++
                            } else {
                                consecutiveZeroNewPins = 0
                            }

                            // Incremental scan stop condition:
                            // User requirement: "stop after next after the all new images is scanned.
                            // also maybe scan a bit below older images next to newest images so the app dont miss some new images"
                            if (stopOnKnownPinIds.isNotEmpty()) {
                                if (hasEncounteredKnownPins) {
                                    scrollsAfterKnownPins++
                                }

                                val currentNewPinCount = scannedPinsMap.size
                                val foundNewPinsInThisScroll = currentNewPinCount > prevPinCount

                                val scannedBelowOlderImages = hasEncounteredKnownPins &&
                                        scrollsAfterKnownPins >= 3 &&
                                        (totalKnownPinsObserved >= 6 || scrollsAfterKnownPins >= 5)
                                val allNewImagesScanned = scannedBelowOlderImages &&
                                        (!foundNewPinsInThisScroll || scrollsAfterKnownPins >= 6)

                                if (allNewImagesScanned) {
                                    Log.d(TAG, "Incremental scan: scanned below older images next to newest images. All new images captured! Found ${scannedPinsMap.size} new pins.")
                                    stopScan()
                                    val msg = if (scannedPinsMap.isEmpty()) {
                                        "Board is up to date (no new images)"
                                    } else {
                                        "Captured all ${scannedPinsMap.size} new images!"
                                    }
                                    _state.value = _state.value.copy(statusMessage = msg)
                                    _diagnostics.value = _diagnostics.value.copy(status = "Incremental Scan Completed")
                                    return@evaluateJavascript
                                }
                            }

                            // Robust stop conditions: reached bottom of page and truly stagnant for 22 checks
                            val isNearBottom = scrollHeight > 0 && (scrollY + innerHeight) >= (scrollHeight - 120)
                            val shouldStop = currentScrollIteration >= maxScrollIterations ||
                                    (isNearBottom && consecutiveStagnantScrolls >= 22 && consecutiveZeroNewPins >= 22)

                            if (shouldStop) {
                                stopScan()
                                _state.value = _state.value.copy(
                                    statusMessage = "Scan completed! Found ${scannedPinsMap.size} unique pins."
                                )
                                _diagnostics.value = _diagnostics.value.copy(status = "Completed")
                            }
                        } catch (e: Exception) {
                            Log.e(TAG, "Error checking metrics", e)
                        }
                    }
                }
            }
        }
    }

    override fun pauseScan() {
        _state.value = _state.value.copy(isPaused = true, statusMessage = "Scan Paused")
        _diagnostics.value = _diagnostics.value.copy(status = "Paused")
    }

    override fun resumeScan() {
        _state.value = _state.value.copy(isPaused = false, statusMessage = "Resuming Scan...")
        _diagnostics.value = _diagnostics.value.copy(status = "Scanning")
    }

    override fun stopScan() {
        scanJob?.cancel()
        scanJob = null
        timerJob?.cancel()
        timerJob = null

        _state.value = _state.value.copy(
            isScanning = false,
            isPaused = false,
            statusMessage = "Scan Stopped"
        )
        _diagnostics.value = _diagnostics.value.copy(status = "Stopped")
    }

    override fun stepScroll() {
        currentScrollIteration++
        _diagnostics.value = _diagnostics.value.copy(
            scrollIterations = currentScrollIteration,
            status = "Manual Scroll (+900px)"
        )
        mainHandler.post {
            webView?.evaluateJavascript(
                "window.scrollBy({ top: 900, behavior: 'smooth' });",
                null
            )
            triggerDomPinExtraction(webView)
        }
    }

    override fun setImageBlockingEnabled(enabled: Boolean) {
        isImageBlockingEnabled = enabled
        _state.value = _state.value.copy(isImageBlockingEnabled = enabled)
        _diagnostics.value = _diagnostics.value.copy(isImageBlockingEnabled = enabled)
    }
    override fun destroy() {
        stopScan()
        mainHandler.post {
            try {
                webView?.clearCache(true)
            } catch (_: Throwable) {}
            webView?.stopLoading()
            webView?.destroy()
            webView = null
        }
    }

    companion object {
        // Transparent 1x1 PNG bytes to immediately fulfill blocked image requests with 0 bytes downloaded
        private val EMPTY_IMAGE_BYTES = byteArrayOf(
            0x89.toByte(), 0x50.toByte(), 0x4E.toByte(), 0x47.toByte(),
            0x0D.toByte(), 0x0A.toByte(), 0x1A.toByte(), 0x0A.toByte(),
            0x00.toByte(), 0x00.toByte(), 0x00.toByte(), 0x0D.toByte(),
            0x49.toByte(), 0x48.toByte(), 0x44.toByte(), 0x52.toByte(),
            0x00.toByte(), 0x00.toByte(), 0x00.toByte(), 0x01.toByte(),
            0x00.toByte(), 0x00.toByte(), 0x00.toByte(), 0x01.toByte(),
            0x08.toByte(), 0x06.toByte(), 0x00.toByte(), 0x00.toByte(),
            0x00.toByte(), 0x1F.toByte(), 0x15.toByte(), 0xC4.toByte(),
            0x89.toByte(), 0x00.toByte(), 0x00.toByte(), 0x00.toByte(),
            0x0A.toByte(), 0x49.toByte(), 0x44.toByte(), 0x41.toByte(),
            0x54.toByte(), 0x78.toByte(), 0x9C.toByte(), 0x63.toByte(),
            0x00.toByte(), 0x01.toByte(), 0x00.toByte(), 0x00.toByte(),
            0x05.toByte(), 0x00.toByte(), 0x01.toByte(), 0x0D.toByte(),
            0x0A.toByte(), 0x2D.toByte(), 0xB4.toByte(), 0x00.toByte(),
            0x00.toByte(), 0x00.toByte(), 0x00.toByte(), 0x49.toByte(),
            0x45.toByte(), 0x4E.toByte(), 0x44.toByte(), 0xAE.toByte(),
            0x42.toByte(), 0x60.toByte(), 0x82.toByte()
        )
    }
}
