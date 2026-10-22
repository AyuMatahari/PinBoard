package com.example.scanner

import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import android.util.Log
import com.example.data.local.AppDatabase
import com.example.data.local.PinEntity
import com.example.model.PinItem
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

/**
 * Isolated Background Service running in process ":browser_worker".
 * Protects the main application and Compose UI from memory spikes,
 * heavy JavaScript execution, or Chromium rendering issues when scanning Pinterest boards.
 */
class BrowserWorkerService : Service() {

    private val TAG = "BrowserWorkerService"
    private val serviceScope = CoroutineScope(Dispatchers.Main + Job())
    private var browserWorker: PinterestBrowserWorker? = null

    companion object {
        const val ACTION_START_SCAN = "com.example.scanner.ACTION_START_SCAN"
        const val ACTION_STOP_SCAN = "com.example.scanner.ACTION_STOP_SCAN"

        const val ACTION_SCAN_STATUS = "com.example.scanner.ACTION_SCAN_STATUS"
        const val ACTION_SCAN_FINISHED = "com.example.scanner.ACTION_SCAN_FINISHED"

        const val EXTRA_BOARD_URL = "extra_board_url"
        const val EXTRA_KNOWN_IDS = "extra_known_ids"
        const val EXTRA_NEW_PINS_COUNT = "extra_new_pins_count"
        const val EXTRA_STATUS_MESSAGE = "extra_status_message"
        const val EXTRA_IS_SCANNING = "extra_is_scanning"

        fun startScan(context: Context, boardUrl: String, knownPinIds: Set<String>) {
            val intent = Intent(context, BrowserWorkerService::class.java).apply {
                action = ACTION_START_SCAN
                putExtra(EXTRA_BOARD_URL, boardUrl)
                putStringArrayListExtra(EXTRA_KNOWN_IDS, ArrayList(knownPinIds))
            }
            try {
                context.startService(intent)
            } catch (e: Exception) {
                Log.e("BrowserWorkerService", "Failed to start BrowserWorkerService", e)
            }
        }

        fun stopScan(context: Context) {
            val intent = Intent(context, BrowserWorkerService::class.java).apply {
                action = ACTION_STOP_SCAN
            }
            try {
                context.startService(intent)
            } catch (e: Exception) {
                Log.e("BrowserWorkerService", "Failed to stop BrowserWorkerService", e)
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "BrowserWorkerService created in process :browser_worker")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START_SCAN -> {
                val boardUrl = intent.getStringExtra(EXTRA_BOARD_URL) ?: return START_NOT_STICKY
                val knownIdsList = intent.getStringArrayListExtra(EXTRA_KNOWN_IDS) ?: arrayListOf()
                startBackgroundScan(boardUrl, knownIdsList.toSet())
            }
            ACTION_STOP_SCAN -> {
                stopBackgroundScan()
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }

    private fun startBackgroundScan(boardUrl: String, knownIds: Set<String>) {
        stopBackgroundScan()

        val worker = PinterestBrowserWorker(applicationContext, serviceScope)
        browserWorker = worker

        val discoveredNewPins = mutableListOf<PinItem>()
        var wasScanning = false

        worker.setOnPinDetectedListener { pin ->
            if (!knownIds.contains(pin.id)) {
                synchronized(discoveredNewPins) {
                    if (discoveredNewPins.none { it.id == pin.id }) {
                        discoveredNewPins.add(pin)
                    }
                }
            }
        }

        serviceScope.launch {
            worker.state.collectLatest { state ->
                val statusIntent = Intent(ACTION_SCAN_STATUS).apply {
                    setPackage(packageName)
                    putExtra(EXTRA_IS_SCANNING, state.isScanning)
                    putExtra(EXTRA_STATUS_MESSAGE, state.statusMessage)
                    putExtra(EXTRA_NEW_PINS_COUNT, discoveredNewPins.size)
                }
                sendBroadcast(statusIntent)

                if (wasScanning && !state.isScanning) {
                    // Scan has completed in the background process
                    onScanFinished(boardUrl, discoveredNewPins.toList(), knownIds)
                }
                wasScanning = state.isScanning
            }
        }

        worker.startScan(boardUrl, knownIds)
    }

    private fun onScanFinished(boardUrl: String, newPins: List<PinItem>, knownIds: Set<String>) {
        Log.i(TAG, "Background scan finished with ${newPins.size} new pins for $boardUrl")
        serviceScope.launch(Dispatchers.IO) {
            try {
                if (newPins.isNotEmpty()) {
                    val db = AppDatabase.getDatabase(applicationContext)
                    val dao = db.boardDao()
                    val boardId = extractBoardIdFromUrl(boardUrl)
                    val entities = newPins.mapIndexed { idx, item ->
                        PinEntity.fromPinItem(item, boardId, idx)
                    }
                    dao.upsertPinsSafely(entities)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error persisting scanned pins in service", e)
            } finally {
                val finishIntent = Intent(ACTION_SCAN_FINISHED).apply {
                    setPackage(packageName)
                    putExtra(EXTRA_BOARD_URL, boardUrl)
                    putExtra(EXTRA_NEW_PINS_COUNT, newPins.size)
                }
                sendBroadcast(finishIntent)
                stopSelf()
            }
        }
    }

    private fun stopBackgroundScan() {
        browserWorker?.stopScan()
        browserWorker?.destroy()
        browserWorker = null
    }

    private fun extractBoardIdFromUrl(url: String): String {
        val clean = url.trim().removePrefix("https://").removePrefix("http://").trim('/')
        val parts = clean.split('/').filter { it.isNotBlank() }
        val nonDomain = if (parts.isNotEmpty() && (parts[0].contains(".") || parts[0].contains("pinterest"))) {
            parts.drop(1)
        } else {
            parts
        }
        return if (nonDomain.size >= 2) "${nonDomain[0]}-${nonDomain[1]}" else if (nonDomain.size == 1) nonDomain[0] else "scanned-board"
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.i(TAG, "BrowserWorkerService destroying")
        stopBackgroundScan()
        serviceScope.cancel()
    }
}
