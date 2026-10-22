package com.example.scanner

import android.webkit.WebView
import com.example.model.PinItem
import kotlinx.coroutines.flow.StateFlow

/**
 * Isolated Pinterest Scanner Interface matching Implementation Brief Section 12.
 * Keeps the browser / feed capture layer cleanly separated from the rest of the Android application.
 */
interface PinterestScanner {
    /**
     * Observable lifecycle state of the scanner.
     */
    val state: StateFlow<ScannerState>

    /**
     * Real-time scan diagnostics matching Brief Section 21.
     */
    val diagnostics: StateFlow<ScanDiagnostics>

    /**
     * Initiates login flow on Pinterest via Google or native credentials (Section 2).
     */
    fun login(onComplete: () -> Unit = {})

    /**
     * Starts continuous feed scanning of a Pinterest board URL.
     * If stopOnKnownPinIds is provided, stops scanning as soon as a pin in this set is encountered.
     */
    fun startScan(boardUrl: String, stopOnKnownPinIds: Set<String> = emptySet(), targetBoardId: String? = null)

    /**
     * Pauses the auto-scrolling loop while preserving current progress and feed state.
     */
    fun pauseScan()

    /**
     * Resumes the auto-scrolling loop.
     */
    fun resumeScan()

    /**
     * Stops the scan and settles.
     */
    fun stopScan()

    /**
     * Triggers a manual single-step scroll (800-1000px) for testing purposes (Section 10).
     */
    fun stepScroll()

    /**
     * Returns the worker's WebView instance so it can be hosted in Compose for testing (Section 14).
     */
    fun getWebView(): WebView?

    /**
     * Registers a listener triggered whenever a new valid Pin is detected from BoardFeedResource (Section 3 & 4).
     */
    fun setOnPinDetectedListener(listener: (PinItem) -> Unit)

    /**
     * Returns all unique pins captured during the current or most recent scan, ordered by boardPosition.
     */
    fun getScannedPins(): List<PinItem>

    /**
     * Enables or disables network image blocking in the WebView worker.
     * Disabled (false) by default.
     */
    fun setImageBlockingEnabled(enabled: Boolean)

    /**
     * Cleans up resources.
     */
    fun destroy()
}

data class ScannerState(
    val isScanning: Boolean = false,
    val isPaused: Boolean = false,
    val isLoggedIn: Boolean = false,
    val currentBoardUrl: String = "",
    val currentBoardTitle: String = "",
    val detectedPinCount: Int = 0,
    val statusMessage: String = "Ready",
    val error: String? = null,
    val isImageBlockingEnabled: Boolean = false
)

data class ScanDiagnostics(
    val isLoggedIn: Boolean = false,
    val boardUrl: String = "",
    val uniquePins: Int = 0,
    val responseCount: Int = 0,
    val blockedImageRequests: Int = 0,
    val scrollIterations: Int = 0,
    val lastUniquePinCount: Int = 0,
    val documentHeight: Int = 0,
    val scanDurationSeconds: Long = 0L,
    val status: String = "Idle",
    val lastResponseUrl: String = "",
    val lastBookmark: String = "",
    val lastBatchPinCount: Int = 0,
    val lastDetectedPinTitle: String = "",
    val isImageBlockingEnabled: Boolean = false
)

sealed class ScanResult {
    data class Success(val boardUrl: String, val pins: List<PinItem>) : ScanResult()
    data class Error(val message: String) : ScanResult()
    object Stopped : ScanResult()
}
