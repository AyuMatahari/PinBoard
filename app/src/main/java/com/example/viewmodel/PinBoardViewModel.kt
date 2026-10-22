package com.example.viewmodel

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.data.PinterestRepository
import com.example.data.local.AppDatabase
import com.example.data.local.BoardDao
import com.example.data.local.BoardEntity
import com.example.data.local.CustomAlbumEntity
import com.example.data.local.PinEntity
import com.example.model.BoardHistoryItem
import com.example.model.DateAlbum
import com.example.model.PinItem
import com.example.model.PinterestBoard
import com.example.model.SortOption
import com.example.scanner.BrowserWorkerService
import com.example.scanner.PinterestBrowserWorker
import com.example.scanner.ScanDiagnostics
import com.example.scanner.ScannerState
import com.example.util.DownloadProgress
import com.example.util.Downloader
import com.example.util.ImageLinkResolver
import com.example.util.LinkExtractor
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

data class DeletedPinsUndoState(
    val boardId: String,
    val pins: List<PinItem>,
    val imageUrls: List<String> = pins.map { it.imageUrl }
)

enum class AlbumPosition { TOP_OF_BOARD, TOP_SELECTED, MIDDLE_SELECTED, BOTTOM_SELECTED }

enum class AlbumTransferMode { COPY, MOVE }

data class PendingAlbumTransfer(
    val pinIds: Set<String>,
    val mode: AlbumTransferMode,
    val sourceBoardId: String,
    val savedSelectionPinIds: Set<String>,
    val savedSelectionAlbumIds: Set<String>
)

data class DeletedBoardUndoState(
    val board: PinterestBoard,
    val pins: List<PinItem>
)

class PinBoardViewModel(
    private val repository: PinterestRepository = PinterestRepository()
) : ViewModel() {

    private var appContext: Context? = null

    private var _browserWorker: PinterestBrowserWorker? = null
    val browserWorker: PinterestBrowserWorker?
        get() = _browserWorker

    private val _scannerState = MutableStateFlow(ScannerState())
    val scannerState: StateFlow<ScannerState> = _scannerState.asStateFlow()

    private val _scannerDiagnostics = MutableStateFlow(ScanDiagnostics())
    val scannerDiagnostics: StateFlow<ScanDiagnostics> = _scannerDiagnostics.asStateFlow()

    private val _isBrowserTestingVisible = MutableStateFlow(false)
    val isBrowserTestingVisible: StateFlow<Boolean> = _isBrowserTestingVisible.asStateFlow()

    private var isIncrementalScan = false
    private val incrementalNewPins = java.util.Collections.synchronizedList(mutableListOf<PinItem>())
    private var scanBroadcastReceiver: BroadcastReceiver? = null

    private val _currentBoard = MutableStateFlow<PinterestBoard?>(null)
    val currentBoard: StateFlow<PinterestBoard?> = _currentBoard.asStateFlow()

    private val _rawPins = MutableStateFlow<List<PinItem>>(emptyList())

    private val _columnCount = MutableStateFlow(2)
    val columnCount: StateFlow<Int> = _columnCount.asStateFlow()

    private val _sortOption = MutableStateFlow(SortOption.DATE_NEWEST)
    val sortOption: StateFlow<SortOption> = _sortOption.asStateFlow()

    private val _searchQuery = MutableStateFlow("")
    val searchQuery: StateFlow<String> = _searchQuery.asStateFlow()

    private val _selectedPinIds = MutableStateFlow<Set<String>>(emptySet())
    val selectedPinIds: StateFlow<Set<String>> = _selectedPinIds.asStateFlow()

    private val _selectedAlbumIds = MutableStateFlow<Set<String>>(emptySet())
    val selectedAlbumIds: StateFlow<Set<String>> = _selectedAlbumIds.asStateFlow()

    private val _snackbarActionLabel = MutableStateFlow<String?>(null)
    val snackbarActionLabel: StateFlow<String?> = _snackbarActionLabel.asStateFlow()

    private val _snackbarAction = MutableStateFlow<(() -> Unit)?>(null)

    private val _pendingAlbumTransfer = MutableStateFlow<PendingAlbumTransfer?>(null)
    val pendingAlbumTransfer: StateFlow<PendingAlbumTransfer?> = _pendingAlbumTransfer.asStateFlow()

    private val _repositioningAlbumId = MutableStateFlow<String?>(null)
    val repositioningAlbumId: StateFlow<String?> = _repositioningAlbumId.asStateFlow()

    private val _scrollToAlbumId = MutableStateFlow<String?>(null)
    val scrollToAlbumId: StateFlow<String?> = _scrollToAlbumId.asStateFlow()

    private val _isSelectionMode = MutableStateFlow(false)
    val isSelectionMode: StateFlow<Boolean> = _isSelectionMode.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _isSyncing = MutableStateFlow(false)
    val isSyncing: StateFlow<Boolean> = _isSyncing.asStateFlow()

    private val _loadingProgress = MutableStateFlow<Pair<Int, Int>?>(null)
    val loadingProgress: StateFlow<Pair<Int, Int>?> = _loadingProgress.asStateFlow()

    private val _downloadProgress = MutableStateFlow<DownloadProgress?>(null)
    val downloadProgress: StateFlow<DownloadProgress?> = _downloadProgress.asStateFlow()

    private val _fullscreenPinIndex = MutableStateFlow<Int?>(null)
    val fullscreenPinIndex: StateFlow<Int?> = _fullscreenPinIndex.asStateFlow()

    private val _snackbarMessage = MutableStateFlow<String?>(null)
    val snackbarMessage: StateFlow<String?> = _snackbarMessage.asStateFlow()

    companion object {
        const val INITIAL_BATCH_SIZE = 36
        const val BATCH_INCREMENT = 24

        val DEFAULT_DUMP_BOARD = PinterestBoard(
            id = "board_dump",
            title = "Dump board",
            slug = "dump",
            ownerUsername = "you",
            ownerDisplayName = "Dump board",
            ownerAvatarUrl = "",
            pinCount = 0,
            boardUrl = "custom://dump",
            description = "Default dump board for quick saves and fallback",
            pins = emptyList(),
            isCustom = true,
            isDefault = true,
            isSpecialNonDeletable = true
        )

        val DEFAULT_MY_SAVE_BOARD = PinterestBoard(
            id = "board_my_save",
            title = "My Save",
            slug = "my-save",
            ownerUsername = "you",
            ownerDisplayName = "My Save",
            ownerAvatarUrl = "",
            pinCount = 0,
            boardUrl = "custom://my_save",
            description = "Custom board for saved items",
            pins = emptyList(),
            isCustom = true,
            isDefault = false,
            isSpecialNonDeletable = true
        )

        val DEFAULT_FAVORITES_BOARD = PinterestBoard(
            id = "board_favorites",
            title = "Favorites",
            slug = "favorites",
            ownerUsername = "you",
            ownerDisplayName = "Favorites",
            ownerAvatarUrl = "",
            pinCount = 0,
            boardUrl = "custom://favorites",
            description = "Your favorite images",
            pins = emptyList(),
            isCustom = true,
            isDefault = false,
            isSpecialNonDeletable = true
        )

        val DEFAULT_SPECIAL_HISTORY = listOf(
            BoardHistoryItem(
                url = "custom://dump",
                title = "Dump board",
                ownerName = "Dump board",
                ownerAvatarUrl = "",
                pinCount = 0,
                isCustom = true,
                boardId = "board_dump"
            ),
            BoardHistoryItem(
                url = "custom://my_save",
                title = "My Save",
                ownerName = "My Save",
                ownerAvatarUrl = "",
                pinCount = 0,
                isCustom = true,
                boardId = "board_my_save"
            ),
            BoardHistoryItem(
                url = "custom://favorites",
                title = "Favorites",
                ownerName = "Favorites",
                ownerAvatarUrl = "",
                pinCount = 0,
                isCustom = true,
                boardId = "board_favorites"
            )
        )
    }

    private val _boardHistory = MutableStateFlow<List<BoardHistoryItem>>(DEFAULT_SPECIAL_HISTORY)
    val boardHistory: StateFlow<List<BoardHistoryItem>> = _boardHistory.asStateFlow()

    private val _separateByDate = MutableStateFlow(false)
    val separateByDate: StateFlow<Boolean> = _separateByDate.asStateFlow()

    private val _groupByAlbum = MutableStateFlow(false)
    val groupByAlbum: StateFlow<Boolean> = _groupByAlbum.asStateFlow()

    private val _activeAlbum = MutableStateFlow<DateAlbum?>(null)
    val activeAlbum: StateFlow<DateAlbum?> = _activeAlbum.asStateFlow()

    private val _rememberPerBoardSettings = MutableStateFlow(true)
    val rememberPerBoardSettings: StateFlow<Boolean> = _rememberPerBoardSettings.asStateFlow()

    private val _hidePinTitlesAndAuthors = MutableStateFlow(false)
    val hidePinTitlesAndAuthors: StateFlow<Boolean> = _hidePinTitlesAndAuthors.asStateFlow()

    private val _portraitAlbumCards = MutableStateFlow(false)
    val portraitAlbumCards: StateFlow<Boolean> = _portraitAlbumCards.asStateFlow()

    private val _disableArrowNavigation = MutableStateFlow(false)
    val disableArrowNavigation: StateFlow<Boolean> = _disableArrowNavigation.asStateFlow()

    private val _customAlbums = MutableStateFlow<List<CustomAlbumEntity>>(emptyList())
    val customAlbums: StateFlow<List<CustomAlbumEntity>> = _customAlbums.asStateFlow()

    private val _albumBackStack = mutableListOf<DateAlbum>()

    private val favoriteTimestamps = java.util.concurrent.ConcurrentHashMap<String, Long>()

    // Favorites & Custom Boards State
    private val _favoritePinKeys = MutableStateFlow<Set<String>>(emptySet())
    val favoritePinKeys: StateFlow<Set<String>> = _favoritePinKeys.asStateFlow()

    private val _individualFavoritePinKeys = MutableStateFlow<Set<String>>(emptySet())
    val individualFavoritePinKeys: StateFlow<Set<String>> = _individualFavoritePinKeys.asStateFlow()

    private val _favoriteAlbumIds = MutableStateFlow<Set<String>>(emptySet())
    val favoriteAlbumIds: StateFlow<Set<String>> = _favoriteAlbumIds.asStateFlow()

    private val _availableBoards = MutableStateFlow<List<PinterestBoard>>(listOf(DEFAULT_DUMP_BOARD, DEFAULT_MY_SAVE_BOARD, DEFAULT_FAVORITES_BOARD))
    val availableBoards: StateFlow<List<PinterestBoard>> = _availableBoards.asStateFlow()

    private val _deletedPinsUndo = MutableStateFlow<DeletedPinsUndoState?>(null)
    val deletedPinsUndo: StateFlow<DeletedPinsUndoState?> = _deletedPinsUndo.asStateFlow()

    private val _showDeleteFromAllConfirmation = MutableStateFlow<DeletedPinsUndoState?>(null)
    val showDeleteFromAllConfirmation: StateFlow<DeletedPinsUndoState?> = _showDeleteFromAllConfirmation.asStateFlow()

    private val _deletedBoardUndo = MutableStateFlow<DeletedBoardUndoState?>(null)
    val deletedBoardUndo: StateFlow<DeletedBoardUndoState?> = _deletedBoardUndo.asStateFlow()

    private var boardPinsObserverJob: kotlinx.coroutines.Job? = null
    private var currentLoadJob: kotlinx.coroutines.Job? = null

    var boardsListScrollIndex: Int = 0
        private set
    var boardsListScrollOffset: Int = 0
        private set

    fun saveBoardsListScrollPosition(index: Int, offset: Int) {
        boardsListScrollIndex = index
        boardsListScrollOffset = offset
    }

    val lastCrashLog: StateFlow<String?> = com.example.util.CrashMonitor.lastCrashState

    fun clearCrashLog() {
        appContext?.let { com.example.util.CrashMonitor.clearLastCrash(it) }
    }

    private val _forceBoardTypeOrder = MutableStateFlow(true)
    val forceBoardTypeOrder: StateFlow<Boolean> = _forceBoardTypeOrder.asStateFlow()

    fun saveReorderedBoards(reorderedList: List<BoardHistoryItem>, forceTypeOrder: Boolean) {
        _forceBoardTypeOrder.value = forceTypeOrder
        val ctx = appContext
        if (ctx != null) {
            val prefs = ctx.getSharedPreferences("pinterest_board_history", Context.MODE_PRIVATE)
            prefs.edit().putBoolean("force_board_type_order", forceTypeOrder).apply()
        }
        val validatedList = if (forceTypeOrder) {
            applyForcedBoardTypeOrder(reorderedList)
        } else {
            reorderedList
        }
        _boardHistory.value = validatedList
        saveHistoryToStorage()
    }

    private fun applyForcedBoardTypeOrder(list: List<BoardHistoryItem>): List<BoardHistoryItem> {
        val dump = list.firstOrNull { it.boardId == "board_dump" || it.url == "custom://dump" }
            ?: DEFAULT_SPECIAL_HISTORY[0]
        val mySave = list.firstOrNull { it.boardId == "board_my_save" || it.url == "custom://my_save" }
            ?: DEFAULT_SPECIAL_HISTORY[1]
        val fav = list.firstOrNull { it.boardId == "board_favorites" || it.url == "custom://favorites" }
            ?: DEFAULT_SPECIAL_HISTORY[2]

        val pinterestBoards = list.filter {
            !it.isCustom && it.boardId != "board_dump" && it.boardId != "board_my_save" && it.boardId != "board_favorites" &&
                    !it.url.startsWith("custom://")
        }
        val otherCustomBoards = list.filter {
            it.isCustom && it.boardId != "board_dump" && it.boardId != "board_my_save" && it.boardId != "board_favorites" &&
                    it.url != "custom://dump" && it.url != "custom://my_save" && it.url != "custom://favorites"
        }

        // Strict board type order: 1. Pinterest, 2. Permanent (Dump, My Save, Favorites), 3. Other custom
        return (pinterestBoards + listOf(dump, mySave, fav) + otherCustomBoards).distinctBy { it.url.trim().removeSuffix("/").lowercase() }
    }

    private fun ensureSpecialBoardsInHistory(list: List<BoardHistoryItem>): List<BoardHistoryItem> {
        val dump = list.firstOrNull { it.boardId == "board_dump" || it.url == "custom://dump" }
            ?: DEFAULT_SPECIAL_HISTORY[0]
        val mySave = list.firstOrNull { it.boardId == "board_my_save" || it.url == "custom://my_save" }
            ?: DEFAULT_SPECIAL_HISTORY[1]
        val fav = list.firstOrNull { it.boardId == "board_favorites" || it.url == "custom://favorites" }
            ?: DEFAULT_SPECIAL_HISTORY[2]

        val isForcedOrder = _forceBoardTypeOrder.value

        if (isForcedOrder) {
            return applyForcedBoardTypeOrder(list)
        } else {
            val existingUrls = list.map { it.url.trim().removeSuffix("/").lowercase() }.toSet()
            val missingSpecials = listOf(dump, mySave, fav).filter { !existingUrls.contains(it.url.trim().removeSuffix("/").lowercase()) }
            return (list + missingSpecials).distinctBy { it.url.trim().removeSuffix("/").lowercase() }
        }
    }

    private var allFilteredSortedPins: List<PinItem> = emptyList()
    private val _visibleLimit = MutableStateFlow(INITIAL_BATCH_SIZE)

    private val _totalAvailablePins = MutableStateFlow(0)
    val totalAvailablePins: StateFlow<Int> = _totalAvailablePins.asStateFlow()

    private val _displayedPins = MutableStateFlow<List<PinItem>>(emptyList())
    val displayedPins: StateFlow<List<PinItem>> = _displayedPins.asStateFlow()

    private fun updateDisplayedPins(resetLimit: Boolean = false) {
        val pins = _rawPins.value
        val query = _searchQuery.value
        val sort = _sortOption.value

        if (resetLimit) {
            _visibleLimit.value = INITIAL_BATCH_SIZE
        }

        val filtered = if (query.isBlank()) {
            pins
        } else {
            pins.filter {
                it.title.contains(query, ignoreCase = true) ||
                        it.description.contains(query, ignoreCase = true) ||
                        it.author.contains(query, ignoreCase = true)
            }
        }

        val isCustom = _currentBoard.value?.isCustom == true
        allFilteredSortedPins = when (sort) {
            SortOption.FAVORITED_NEWEST -> {
                filtered.sortedWith(
                    compareByDescending<PinItem> { favoriteTimestamps[it.id] ?: favoriteTimestamps[it.imageUrl] ?: it.dateAddedMillis }
                        .thenBy { it.boardPosition }
                )
            }
            SortOption.FAVORITED_OLDEST -> {
                filtered.sortedWith(
                    compareBy<PinItem> { favoriteTimestamps[it.id] ?: favoriteTimestamps[it.imageUrl] ?: it.dateAddedMillis }
                        .thenBy { it.boardPosition }
                )
            }
            SortOption.DATE_NEWEST -> {
                if (isCustom) {
                    // Newest first and older last (User requirement 1)
                    filtered.sortedWith(
                        compareByDescending<PinItem> { it.dateAddedMillis }
                            .thenBy { it.boardPosition }
                    )
                } else {
                    filtered.sortedWith(
                        compareBy<PinItem> { it.boardPosition }
                            .thenByDescending { it.dateAddedMillis }
                    )
                }
            }
            SortOption.FIRST_SEEN_NEWEST -> filtered.sortedWith(
                compareByDescending<PinItem> { it.firstSeenAtMillis }
                    .thenBy { it.boardPosition }
            )
            SortOption.DATE_PINTEREST_CREATED -> filtered.sortedWith(
                compareByDescending<PinItem> { it.dateAddedMillis }
                    .thenBy { it.boardPosition }
            )
            SortOption.DATE_OLDEST -> {
                if (isCustom) {
                    filtered.sortedWith(
                        compareBy<PinItem> { it.dateAddedMillis }
                            .thenBy { it.boardPosition }
                    )
                } else {
                    filtered.sortedWith(
                        compareByDescending<PinItem> { it.boardPosition }
                            .thenBy { it.dateAddedMillis }
                    )
                }
            }
            SortOption.ASPECT_TALL -> filtered.sortedBy { it.aspectRatio }
            SortOption.ASPECT_WIDE -> filtered.sortedByDescending { it.aspectRatio }
            SortOption.TITLE_AZ -> filtered.sortedBy { it.title.lowercase() }
            SortOption.TITLE_ZA -> filtered.sortedByDescending { it.title.lowercase() }
            SortOption.MOST_SAVED -> filtered.sortedByDescending { it.savesCount }
            SortOption.FEWEST_SAVED -> filtered.sortedBy { it.savesCount }
            SortOption.MOST_LIKED -> filtered.sortedByDescending { it.likesCount }
            SortOption.FEWEST_LIKED -> filtered.sortedBy { it.likesCount }
            SortOption.RESOLUTION_HIGH -> filtered.sortedByDescending { it.width * it.height }
            SortOption.RESOLUTION_LOW -> filtered.sortedBy { it.width * it.height }
            SortOption.FILE_SIZE_LARGE -> filtered.sortedByDescending { it.fileSizeKb }
            SortOption.FILE_SIZE_SMALL -> filtered.sortedBy { it.fileSizeKb }
            SortOption.AUTHOR_AZ -> filtered.sortedBy { it.author.lowercase() }
            SortOption.SHUFFLE_RANDOM -> filtered.shuffled()
        }

        _totalAvailablePins.value = allFilteredSortedPins.size
        val limit = _visibleLimit.value
        _displayedPins.value = allFilteredSortedPins.take(limit)
    }

    fun getAllSortedPins(): List<PinItem> = allFilteredSortedPins

    fun loadMorePins() {
        if (_displayedPins.value.size < allFilteredSortedPins.size) {
            _visibleLimit.value += BATCH_INCREMENT
            _displayedPins.value = allFilteredSortedPins.take(_visibleLimit.value)
        }
    }

    fun loadNextBatch() {
        loadMorePins()
    }

    fun ensureVisibleUpToIndex(targetIndex: Int) {
        val total = allFilteredSortedPins.size
        if (targetIndex >= _visibleLimit.value) {
            val needed = (targetIndex + BATCH_INCREMENT).coerceAtMost(total)
            _visibleLimit.value = needed
            _displayedPins.value = allFilteredSortedPins.take(needed)
        }
    }

    fun jumpToFraction(fraction: Float) {
        val total = allFilteredSortedPins.size
        if (total == 0) return
        val targetCount = (total * fraction.coerceIn(0f, 1f)).toInt().coerceAtLeast(INITIAL_BATCH_SIZE)
        if (targetCount > _visibleLimit.value) {
            _visibleLimit.value = targetCount
            _displayedPins.value = allFilteredSortedPins.take(targetCount)
        }
    }

    fun getEstimatedTimestampForFraction(fraction: Float): Long? {
        val total = allFilteredSortedPins.size
        if (total == 0) return null
        val targetIdx = (total * fraction.coerceIn(0f, 1f)).toInt().coerceIn(0, total - 1)
        return allFilteredSortedPins.getOrNull(targetIdx)?.dateAddedMillis
    }

    fun applyPins(pins: List<PinItem>) {
        _rawPins.value = pins
        updateDisplayedPins()
    }

    fun setContext(context: Context) {
        if (appContext == null) {
            appContext = context.applicationContext
            loadAppSettings()
            loadHistoryFromStorage()

            viewModelScope.launch {
                val ctx = appContext ?: return@launch
                val dao = AppDatabase.getDatabase(ctx).boardDao()
                ensureSpecialBoardsInDb(dao)
                loadOpenedBoardState()
            }

            com.example.util.ImageCacheManager.applyImageLoader(context)

            // Register receiver for isolated BrowserWorkerService in process :browser_worker
            val receiver = object : BroadcastReceiver() {
                override fun onReceive(c: Context?, intent: Intent?) {
                    when (intent?.action) {
                        BrowserWorkerService.ACTION_SCAN_STATUS -> {
                            val isScanning = intent.getBooleanExtra(BrowserWorkerService.EXTRA_IS_SCANNING, false)
                            val msg = intent.getStringExtra(BrowserWorkerService.EXTRA_STATUS_MESSAGE)
                            _isSyncing.value = isScanning
                            if (msg != null) {
                                _scannerState.value = _scannerState.value.copy(
                                    isScanning = isScanning,
                                    statusMessage = msg
                                )
                            }
                        }
                        BrowserWorkerService.ACTION_SCAN_FINISHED -> {
                            val count = intent.getIntExtra(BrowserWorkerService.EXTRA_NEW_PINS_COUNT, 0)
                            handleBackgroundScanFinished(count)
                        }
                    }
                }
            }
            scanBroadcastReceiver = receiver
            val filter = IntentFilter().apply {
                addAction(BrowserWorkerService.ACTION_SCAN_STATUS)
                addAction(BrowserWorkerService.ACTION_SCAN_FINISHED)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                context.applicationContext.registerReceiver(receiver, filter, Context.RECEIVER_NOT_EXPORTED)
            } else {
                context.applicationContext.registerReceiver(receiver, filter)
            }

            if (_browserWorker == null) {
                val worker = PinterestBrowserWorker(context.applicationContext, viewModelScope)
                worker.setOnPinDetectedListener { newPin ->
                    handleScannedPinDetected(newPin)
                }
                _browserWorker = worker

                var wasScanning = false
                viewModelScope.launch {
                    worker.state.collect { st ->
                        _scannerState.value = st
                        if (wasScanning && !st.isScanning) {
                            handleScanCompleted(st)
                        }
                        wasScanning = st.isScanning
                    }
                }
                viewModelScope.launch {
                    worker.diagnostics.collect { diag ->
                        _scannerDiagnostics.value = diag
                    }
                }
            }
        }
    }

    private suspend fun ensureSpecialBoardsInDb(dao: BoardDao) = withContext(Dispatchers.IO) {
        val dump = dao.getBoardById("board_dump")
        if (dump == null) {
            dao.insertBoard(
                BoardEntity(
                    id = "board_dump",
                    title = "Dump board",
                    slug = "dump",
                    ownerUsername = "you",
                    ownerDisplayName = "Dump board",
                    ownerAvatarUrl = "",
                    pinCount = 0,
                    followerCount = 0,
                    boardUrl = "custom://dump",
                    description = "Default dump board for quick saves and fallback",
                    isCustom = true,
                    customDomains = "",
                    isDefault = true,
                    isSpecialNonDeletable = true
                )
            )
            val mySaveExisting = dao.getBoardById("board_my_save")
            if (mySaveExisting != null && mySaveExisting.isDefault) {
                dao.insertBoard(mySaveExisting.copy(isDefault = false))
            }
        }

        val mySave = dao.getBoardById("board_my_save")
        if (mySave == null) {
            dao.insertBoard(
                BoardEntity(
                    id = "board_my_save",
                    title = "My Save",
                    slug = "my-save",
                    ownerUsername = "you",
                    ownerDisplayName = "My Save",
                    ownerAvatarUrl = "",
                    pinCount = 0,
                    followerCount = 0,
                    boardUrl = "custom://my_save",
                    description = "Custom board for saved items",
                    isCustom = true,
                    customDomains = "",
                    isDefault = false,
                    isSpecialNonDeletable = true
                )
            )
        }

        val favorites = dao.getBoardById("board_favorites")
        if (favorites == null) {
            dao.insertBoard(
                BoardEntity(
                    id = "board_favorites",
                    title = "Favorites",
                    slug = "favorites",
                    ownerUsername = "you",
                    ownerDisplayName = "Favorites",
                    ownerAvatarUrl = "",
                    pinCount = 0,
                    followerCount = 0,
                    boardUrl = "custom://favorites",
                    description = "Your favorite images",
                    isCustom = true,
                    customDomains = "",
                    isDefault = false,
                    isSpecialNonDeletable = true
                )
            )
        }

        val favIds = dao.getFavoritesPinIds("board_favorites")
        val favUrls = dao.getFavoritesImageUrls("board_favorites")
        _favoritePinKeys.value = (favIds + favUrls).toSet()

        val favPins = dao.getPinsForBoard("board_favorites")
        favPins.forEach { p ->
            favoriteTimestamps[p.id] = p.dateAddedMillis
            favoriteTimestamps[p.imageUrl] = p.dateAddedMillis
        }

        try {
            dao.trimEventsToMax50()
        } catch (_: Throwable) {}

        // Auto-match domain support for existing images across all boards (Requirement 1)
        val allCustom = dao.getCustomBoards()
        for (cb in allCustom) {
            val domains = cb.customDomains.split(",").map { it.trim() }.filter { it.isNotBlank() }
            if (domains.isNotEmpty()) {
                syncDomainMatchingWithAllExistingPins(cb.id, domains, dao)
            }
        }

        refreshAvailableBoardsFromDatabaseInternal(dao)
    }

    private suspend fun refreshAvailableBoardsFromDatabaseInternal(dao: BoardDao) {
        val entities = dao.getAllBoards()
        val boards = entities.map { entity ->
            val pins = dao.getPinsForBoard(entity.id).map { it.toPinItem() }
            entity.toPinterestBoard(pins)
        }

        val dump = boards.firstOrNull { it.id == "board_dump" } ?: DEFAULT_DUMP_BOARD
        val mySave = boards.firstOrNull { it.id == "board_my_save" } ?: DEFAULT_MY_SAVE_BOARD
        val fav = boards.firstOrNull { it.id == "board_favorites" } ?: DEFAULT_FAVORITES_BOARD
        val permanentIds = setOf("board_dump", "board_my_save", "board_favorites")
        val pinterestBoards = boards.filter { !it.isCustom && it.id !in permanentIds }
        val otherCustomBoards = boards.filter { it.isCustom && it.id !in permanentIds }

        val orderedBoards = (pinterestBoards + listOf(dump, mySave, fav) + otherCustomBoards).distinctBy { it.id }

        withContext(Dispatchers.Main) {
            _availableBoards.value = orderedBoards

            // Sync all boards into boardHistory so My Save, Favorites, and custom boards always exist on boards list (Requirement 3)
            val currentHistory = _boardHistory.value.toMutableList()
            for (b in boards) {
                val exists = currentHistory.any { it.boardId == b.id || it.url.equals(b.boardUrl, ignoreCase = true) }
                if (!exists) {
                    currentHistory.add(
                        BoardHistoryItem(
                            url = b.boardUrl,
                            title = b.title,
                            ownerName = b.ownerDisplayName,
                            ownerAvatarUrl = b.ownerAvatarUrl,
                            pinCount = b.pinCount,
                            isCustom = b.isCustom,
                            boardId = b.id
                        )
                    )
                }
            }

            _boardHistory.value = ensureSpecialBoardsInHistory(currentHistory)
            saveHistoryToStorage()
        }
    }

    fun refreshAvailableBoards() {
        val ctx = appContext ?: return
        viewModelScope.launch(Dispatchers.IO) {
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            refreshAvailableBoardsFromDatabaseInternal(dao)
        }
    }

    private fun handleScanCompleted(st: ScannerState) {
        if (isIncrementalScan) {
            _isSyncing.value = false
            isIncrementalScan = false

            val workerPins = _browserWorker?.getScannedPins() ?: emptyList()
            val detected = synchronized(incrementalNewPins) {
                (workerPins + incrementalNewPins).distinctBy { it.id }
            }
            incrementalNewPins.clear()

            val board = _currentBoard.value ?: return
            val currentPins = _rawPins.value
            val existingIds = currentPins.map { it.id }.toSet()
            val newPins = detected.filter { incoming -> !existingIds.contains(incoming.id) }

            if (newPins.isNotEmpty()) {
                val sortedNewPins = newPins.sortedWith(
                    compareBy<PinItem> { it.boardPosition }
                        .thenByDescending { it.id.toLongOrNull() ?: 0L }
                )

                val combined = sortedNewPins + currentPins
                val nowMillis = System.currentTimeMillis()
                val reordered = combined.mapIndexed { idx, pin ->
                    val artificialDate = (nowMillis - (idx * 60000L)).coerceAtLeast(0L)
                    pin.copy(
                        boardPosition = idx,
                        dateAddedMillis = artificialDate,
                        firstSeenAtMillis = if (sortedNewPins.any { it.id == pin.id }) nowMillis else pin.firstSeenAtMillis
                    )
                }

                _rawPins.value = reordered
                _sortOption.value = SortOption.DATE_NEWEST
                updateDisplayedPins(resetLimit = true)
                val updatedBoard = board.copy(pins = reordered, pinCount = reordered.size)
                _currentBoard.value = updatedBoard
                _snackbarMessage.value = "Refreshed! Added ${sortedNewPins.size} new image${if (sortedNewPins.size > 1) "s" else ""} to \"${updatedBoard.title}\""
                com.example.util.CrashMonitor.addBreadcrumb("Incremental browser scan success: added ${sortedNewPins.size} new pins ordered at top")

                viewModelScope.launch(Dispatchers.IO) {
                    val ctx = appContext ?: return@launch
                    try {
                        val dao = AppDatabase.getDatabase(ctx).boardDao()
                        val bEntity = BoardEntity.fromPinterestBoard(updatedBoard)
                        val pinEntities = reordered.mapIndexed { idx, p -> PinEntity.fromPinItem(p, updatedBoard.id, idx) }
                        dao.saveFullBoard(bEntity, pinEntities)
                        propagateDomainMatchingForPins(sortedNewPins, excludeBoardId = updatedBoard.id)
                    } catch (t: Throwable) {
                        android.util.Log.e("PinBoardViewModel", "Error saving refreshed board to Room", t)
                        com.example.util.CrashMonitor.recordException(t, "handleScanCompleted.saveFullBoard")
                    }
                }
            } else {
                _snackbarMessage.value = "Board is up to date (${currentPins.size} images)"
                com.example.util.CrashMonitor.addBreadcrumb("Incremental browser scan: board is up to date (${currentPins.size} pins)")
            }
        } else {
            val workerPins = _browserWorker?.getScannedPins() ?: emptyList()
            if (workerPins.isNotEmpty()) {
                val current = _rawPins.value
                val combined = (current + workerPins).distinctBy { it.id }
                _rawPins.value = combined
            }
            if (_rawPins.value.isNotEmpty()) {
                reorderPinsAfterScan()
            }
        }
    }

    private fun handleScannedPinDetected(newPin: PinItem) {
        val currentPins = _rawPins.value.toMutableList()
        val existingIndex = currentPins.indexOfFirst { it.id == newPin.id }
        if (existingIndex >= 0) {
            val existing = currentPins[existingIndex]
            val updated = existing.copy(
                thumbnailUrl = newPin.thumbnailUrl.ifBlank { existing.thumbnailUrl },
                imageUrl = newPin.imageUrl.ifBlank { existing.imageUrl },
                title = if (existing.title.isBlank() || existing.title.startsWith("Pin ")) newPin.title.ifBlank { existing.title } else existing.title,
                boardPosition = newPin.boardPosition
            )
            currentPins[existingIndex] = updated
        } else {
            currentPins.add(newPin)
        }
        _rawPins.value = currentPins
        val currentB = _currentBoard.value
        if (currentB != null && !currentB.isCustom) {
            _currentBoard.value = currentB.copy(pins = currentPins, pinCount = currentPins.size)
        }
        updateDisplayedPins()
    }

    fun reorderPinsAfterScan() {
        val currentPins = _rawPins.value
        if (currentPins.isEmpty()) return

        val ordered = currentPins.sortedWith(
            compareBy<PinItem> { it.boardPosition }
                .thenByDescending { it.id.toLongOrNull() ?: 0L }
        )

        val nowMillis = System.currentTimeMillis()
        val reindexed = ordered.mapIndexed { index, pin ->
            val artificialDate = (nowMillis - (index * 60000L)).coerceAtLeast(0L)
            pin.copy(
                boardPosition = index,
                dateAddedMillis = artificialDate
            )
        }

        _rawPins.value = reindexed
        _sortOption.value = SortOption.DATE_NEWEST
        updateDisplayedPins(resetLimit = true)

        val board = _currentBoard.value
        if (board != null) {
            val updatedBoard = board.copy(pins = reindexed, pinCount = reindexed.size)
            _currentBoard.value = updatedBoard
            viewModelScope.launch(Dispatchers.IO) {
                val ctx = appContext ?: return@launch
                try {
                    val dao = AppDatabase.getDatabase(ctx).boardDao()
                    val bEntity = BoardEntity.fromPinterestBoard(updatedBoard)
                    val pinEntities = reindexed.mapIndexed { idx, p -> PinEntity.fromPinItem(p, updatedBoard.id, idx) }
                    dao.saveFullBoard(bEntity, pinEntities)
                } catch (t: Throwable) {
                    android.util.Log.e("PinBoardViewModel", "Error saving reordered pins to Room", t)
                    com.example.util.CrashMonitor.recordException(t, "reorderPinsAfterScan")
                }
            }
        }
    }

    fun toggleBrowserTestingVisible() {
        _isBrowserTestingVisible.value = !_isBrowserTestingVisible.value
        saveAppSettings()
    }

    fun setBrowserTestingVisible(visible: Boolean) {
        _isBrowserTestingVisible.value = visible
        saveAppSettings()
    }

    fun startBrowserScan(
        url: String? = null,
        clearExistingPins: Boolean = false,
        stopOnKnownPinIds: Set<String> = emptySet()
    ) {
        val targetUrl = url ?: _currentBoard.value?.boardUrl ?: ""
        if (targetUrl.isBlank()) {
            _snackbarMessage.value = "Please enter or select a Pinterest board URL first"
            return
        }

        val isTargetCustom = targetUrl.startsWith("custom://") ||
                targetUrl == "board_dump" || targetUrl == "board_my_save" || targetUrl == "board_favorites" ||
                (url == null && _currentBoard.value?.isCustom == true)

        if (isTargetCustom) {
            _snackbarMessage.value = "Browser worker is only used for Pinterest boards."
            return
        }

        val cleanUrl = repository.parsePinterestUrl(targetUrl)?.let { (user, slug) ->
            "https://www.pinterest.com/$user/$slug/"
        } ?: targetUrl.substringBefore("?").trimEnd('/') + "/"

        // If currently viewing a different board or a custom/permanent board, switch to the Pinterest board
        val currentBoard = _currentBoard.value
        if (currentBoard == null || currentBoard.isCustom || currentBoard.boardUrl != targetUrl) {
            val parsed = repository.parsePinterestUrl(targetUrl)
            val user = parsed?.first ?: ""
            val slug = parsed?.second ?: ""
            val title = if (slug.isNotBlank()) {
                slug.replace("-", " ").replace("_", " ").replaceFirstChar { it.uppercase() }
            } else "Pinterest Board"
            val newBoard = PinterestBoard(
                id = if (user.isNotBlank() && slug.isNotBlank()) "$user-$slug" else targetUrl,
                title = title,
                slug = slug,
                ownerUsername = user,
                ownerDisplayName = if (user.isNotBlank()) user.replaceFirstChar { it.uppercase() } else "Pinterest",
                pinCount = 0,
                boardUrl = targetUrl,
                pins = emptyList(),
                isCustom = false
            )
            selectBoard(newBoard)
        }

        if (clearExistingPins) {
            _rawPins.value = emptyList()
            updateDisplayedPins(resetLimit = true)
        }
        _browserWorker?.startScan(cleanUrl, stopOnKnownPinIds, targetBoardId = _currentBoard.value?.id)
        _snackbarMessage.value = if (stopOnKnownPinIds.isNotEmpty()) {
            "Scanning board for unlisted new images..."
        } else {
            "Browser worker scanning $cleanUrl"
        }
    }

    fun stopBrowserScan() {
        _isSyncing.value = false
        isIncrementalScan = false
        _browserWorker?.stopScan()
        reorderPinsAfterScan()
    }

    fun toggleSeparateByDate() {
        _separateByDate.value = !_separateByDate.value
        saveAppSettings()
    }

    fun toggleGroupByAlbum() {
        _groupByAlbum.value = !_groupByAlbum.value
        saveAppSettings()
    }

    fun openAlbum(album: DateAlbum) {
        _albumBackStack.add(album)
        _activeAlbum.value = album
    }

    fun closeAlbum() {
        if (_albumBackStack.isNotEmpty()) {
            _albumBackStack.removeAt(_albumBackStack.lastIndex)
            _activeAlbum.value = _albumBackStack.lastOrNull()
        } else {
            _activeAlbum.value = null
        }
    }

    fun selectBoard(board: PinterestBoard) {
        try {
            com.example.util.CrashMonitor.addBreadcrumb("selectBoard: title='${board.title}', pins=${board.pins.size}, isCustom=${board.isCustom}")
            _albumBackStack.clear()
            _activeAlbum.value = null
            _currentBoard.value = board
            _rawPins.value = board.pins
            clearSelection()
            _searchQuery.value = ""

            val ctxInit = appContext
            if (ctxInit != null) {
                viewModelScope.launch(Dispatchers.IO) {
                    val dao = AppDatabase.getDatabase(ctxInit).boardDao()
                    val albums = dao.getAlbumsForBoard(board.id)
                    withContext(Dispatchers.Main) {
                        _customAlbums.value = albums
                    }
                }
            }

            if (_rememberPerBoardSettings.value) {
                val (savedCols, savedSort) = loadBoardSettings(board)
                if (savedCols != null && savedCols in 2..4) {
                    _columnCount.value = savedCols
                }
                if (savedSort != null) {
                    _sortOption.value = savedSort
                } else if (board.isCustom) {
                    _sortOption.value = SortOption.DATE_NEWEST
                }
            } else if (board.isCustom) {
                _sortOption.value = SortOption.DATE_NEWEST
            }

            updateDisplayedPins(resetLimit = true)
            addBoardToHistory(board)
            saveOpenedBoardState(board)

            // Observe ALL boards so share-to-default updates reflect immediately
            boardPinsObserverJob?.cancel()
            val ctx = appContext
            if (ctx != null) {
                boardPinsObserverJob = viewModelScope.launch(Dispatchers.IO) {
                    val dao = AppDatabase.getDatabase(ctx).boardDao()
                    launch {
                        dao.observeAlbumsForBoard(board.id).collect { albums ->
                            withContext(Dispatchers.Main) {
                                _customAlbums.value = albums
                            }
                        }
                    }
                    dao.observePinsForBoard(board.id).collect { entities ->
                        val dbPins = entities.map { it.toPinItem() }
                        val currentRaw = _rawPins.value
                        val currentRawIds = currentRaw.map { it.id }.toSet()
                        val hasNew = dbPins.any { !currentRawIds.contains(it.id) }
                        val countDiff = dbPins.size != currentRaw.size
                        if (hasNew || countDiff) {
                            withContext(Dispatchers.Main) {
                                _rawPins.value = dbPins
                                _currentBoard.value = _currentBoard.value?.copy(pins = dbPins, pinCount = dbPins.size)
                                updateDisplayedPins()
                            }
                        }
                    }
                }
            }
        } catch (t: Throwable) {
            if (t is kotlinx.coroutines.CancellationException || t.javaClass.name.contains("CancellationException")) {
                return
            }
            android.util.Log.e("PinBoardViewModel", "Error in selectBoard", t)
            com.example.util.CrashMonitor.recordException(t, "selectBoard: ${board.title}")
            _snackbarMessage.value = "Failed to render board: ${t.message ?: t.javaClass.simpleName}"
        }
    }

    fun loadBoardFromUrl(url: String, forceFullReload: Boolean = false) {
        val cleanUrl = url.trim()
        com.example.util.CrashMonitor.addBreadcrumb("loadBoardFromUrl called: url='$cleanUrl', force=$forceFullReload")
        currentLoadJob?.cancel()
        currentLoadJob = viewModelScope.launch {
            try {
                val ctx = appContext
                val dao = ctx?.let { AppDatabase.getDatabase(it).boardDao() }

                // Check custom scheme or internal board ID
                if (cleanUrl.startsWith("custom://") || cleanUrl == "board_dump" || cleanUrl == "board_my_save" || cleanUrl == "board_favorites") {
                    val boardId = cleanUrl.removePrefix("custom://").let {
                        when (it) {
                            "dump" -> "board_dump"
                            "my_save" -> "board_my_save"
                            "favorites" -> "board_favorites"
                            else -> it
                        }
                    }
                    val cachedCustom = withContext(Dispatchers.IO) {
                        dao?.getBoardByIdOrUrl(boardId, cleanUrl)
                    }
                    if (cachedCustom != null) {
                        val pinEntities = withContext(Dispatchers.IO) { dao?.getPinsForBoard(cachedCustom.id) ?: emptyList() }
                        val pins = pinEntities.map { it.toPinItem() }
                        val b = cachedCustom.toPinterestBoard(pins)
                        selectBoard(b)
                        // Do not show distracting toast on opening cached boards (User requirement 3)
                        return@launch
                    } else if (boardId == "board_dump") {
                        selectBoard(DEFAULT_DUMP_BOARD)
                        return@launch
                    } else if (boardId == "board_my_save") {
                        selectBoard(DEFAULT_MY_SAVE_BOARD)
                        return@launch
                    } else if (boardId == "board_favorites") {
                        selectBoard(DEFAULT_FAVORITES_BOARD)
                        return@launch
                    }
                }

                // Check standard cached board in Room
                if (!forceFullReload && dao != null) {
                    val parsed = repository.parsePinterestUrl(cleanUrl)
                    val slug = parsed?.second?.ifBlank { null }
                    val cachedBoardEntity = withContext(Dispatchers.IO) {
                        try {
                            if (slug != null) dao.getBoardByUrlOrSlug(cleanUrl, slug)
                            else dao.getBoardByIdOrUrl("", cleanUrl)
                        } catch (t: Throwable) {
                            com.example.util.CrashMonitor.recordException(t, "dao.getBoardByUrlOrSlug")
                            null
                        }
                    }

                    if (cachedBoardEntity != null) {
                        val cachedPinEntities = withContext(Dispatchers.IO) {
                            try {
                                dao.getPinsForBoard(cachedBoardEntity.id)
                            } catch (t: Throwable) {
                                com.example.util.CrashMonitor.recordException(t, "dao.getPinsForBoard")
                                emptyList()
                            }
                        }
                        val cachedPins = cachedPinEntities.map { it.toPinItem() }
                        val cachedBoard = cachedBoardEntity.toPinterestBoard(cachedPins)
                        selectBoard(cachedBoard)
                        if (cachedPinEntities.isNotEmpty() || cachedBoardEntity.isCustom) {
                            // Do not show distracting toast on opening cached boards (User requirement 3)
                            com.example.util.CrashMonitor.addBreadcrumb("Loaded from cache: ${cachedBoard.title} (${cachedPins.size} pins)")
                            return@launch
                        }
                    } else if (cleanUrl.contains("pinterest.", ignoreCase = true) || cleanUrl.contains("pin.it", ignoreCase = true)) {
                        val parsed = repository.parsePinterestUrl(cleanUrl)
                        val user = parsed?.first ?: ""
                        val slug = parsed?.second ?: ""
                        val title = if (slug.isNotBlank()) {
                            slug.replace("-", " ").replace("_", " ").replaceFirstChar { it.uppercase() }
                        } else "Pinterest Board"
                        val pBoard = PinterestBoard(
                            id = if (user.isNotBlank() && slug.isNotBlank()) "$user-$slug" else cleanUrl,
                            title = title,
                            slug = slug,
                            ownerUsername = user,
                            ownerDisplayName = if (user.isNotBlank()) user.replaceFirstChar { it.uppercase() } else "Pinterest",
                            pinCount = 0,
                            boardUrl = cleanUrl,
                            pins = emptyList(),
                            isCustom = false
                        )
                        selectBoard(pBoard)
                    }
                }

                // Fresh Fetch for Pinterest links
                _isLoading.value = true
                _loadingProgress.value = null
                _snackbarMessage.value = "Loading all images from board..."
                val result = repository.getBoardFromLink(
                    rawInput = cleanUrl,
                    onProgress = { current, total ->
                        _loadingProgress.value = current to total
                    }
                )
                result.fold(
                    onSuccess = { board ->
                        val prevCount = withContext(Dispatchers.IO) { dao?.getPinsForBoard(board.id)?.size ?: 0 }
                        selectBoard(board)
                        val newCount = (board.pins.size - prevCount).coerceAtLeast(0)
                        if (newCount > 0) {
                            _snackbarMessage.value = "Loaded ${newCount} new image${if (newCount > 1) "s" else ""} for \"${board.title}\""
                        }
                        com.example.util.CrashMonitor.addBreadcrumb("Board fetched successfully: ${board.title} (${board.pins.size} pins)")

                        if (dao != null) {
                            withContext(Dispatchers.IO) {
                                try {
                                    val bEntity = BoardEntity.fromPinterestBoard(board)
                                    val pinEntities = board.pins.mapIndexed { idx, p -> PinEntity.fromPinItem(p, board.id, idx) }
                                    dao.saveFullBoard(bEntity, pinEntities)
                                    propagateDomainMatchingForPins(board.pins, excludeBoardId = board.id)
                                    refreshAvailableBoardsFromDatabaseInternal(dao)
                                } catch (t: Throwable) {
                                    android.util.Log.e("PinBoardViewModel", "Error saving board to Room", t)
                                    com.example.util.CrashMonitor.recordException(t, "saveFullBoard")
                                }
                            }
                        }
                    },
                    onFailure = { err ->
                        val isPinterest = cleanUrl.contains("pinterest.", ignoreCase = true) || cleanUrl.contains("pin.it", ignoreCase = true)
                        if (isPinterest) {
                            if (_browserWorker != null) {
                                _snackbarMessage.value = "Launching browser worker to load pins..."
                                startBrowserScan(cleanUrl, clearExistingPins = false)
                                return@launch
                            }
                            _snackbarMessage.value = "Could not load Pinterest board: ${err.message}"
                            com.example.util.CrashMonitor.addBreadcrumb("getBoardFromLink Pinterest failure: ${err.message}")
                            return@launch
                        }

                        if (cleanUrl.startsWith("http://", ignoreCase = true) || cleanUrl.startsWith("https://", ignoreCase = true)) {
                            val targetBoard = _currentBoard.value ?: DEFAULT_DUMP_BOARD
                            addManualImages(cleanUrl, listOf(targetBoard.id))
                            return@launch
                        }
                        _snackbarMessage.value = "Could not load board: ${err.message}"
                        com.example.util.CrashMonitor.addBreadcrumb("getBoardFromLink failure: ${err.message}")
                    }
                )
            } catch (t: Throwable) {
                var isCancel = false
                var c: Throwable? = t
                while (c != null) {
                    if (c is kotlinx.coroutines.CancellationException ||
                        c is java.util.concurrent.CancellationException ||
                        c.javaClass.name.contains("CancellationException")
                    ) {
                        isCancel = true
                        break
                    }
                    c = c.cause
                }
                if (isCancel) {
                    return@launch
                }
                android.util.Log.e("PinBoardViewModel", "Error loading board from URL: $cleanUrl", t)
                com.example.util.CrashMonitor.recordException(t, "loadBoardFromUrl: $cleanUrl")
                _snackbarMessage.value = "Could not load board: ${t.message ?: t.javaClass.simpleName}"
            } finally {
                _isLoading.value = false
                _loadingProgress.value = null
            }
        }
    }

    // --- REFRESH BUTTON IMPLEMENTATION ---
    fun syncCurrentBoard() {
        val board = _currentBoard.value ?: return
        if (_isSyncing.value || _scannerState.value.isScanning) {
            _snackbarMessage.value = "Refresh already in progress..."
            return
        }

        // Requirement: "5. the refresh button now simply refresh images from links."
        if (board.isCustom) {
            refreshCustomBoardLinks(board)
            return
        }

        // Pinterest Board: Rescan through browser worker
        val currentPins = _rawPins.value
        val knownIds = currentPins.map { it.id }.toSet()

        _isSyncing.value = true
        isIncrementalScan = true
        synchronized(incrementalNewPins) { incrementalNewPins.clear() }
        _snackbarMessage.value = "Rescanning \"${board.title}\" through browser worker..."
        com.example.util.CrashMonitor.addBreadcrumb("syncCurrentBoard via browserWorker: '${board.title}' (${currentPins.size} current pins)")

        val cleanUrl = repository.parsePinterestUrl(board.boardUrl)?.let { (user, slug) ->
            "https://www.pinterest.com/$user/$slug/"
        } ?: board.boardUrl.substringBefore("?").trimEnd('/') + "/"

        if (_browserWorker == null && appContext != null) {
            setContext(appContext!!)
        }

        val worker = _browserWorker
        if (worker != null) {
            worker.startScan(cleanUrl, stopOnKnownPinIds = knownIds, targetBoardId = board.id)
        } else {
            viewModelScope.launch {
                try {
                    val result = withContext(Dispatchers.IO) {
                        repository.getBoardFromLink(cleanUrl)
                    }
                    result.fold(
                        onSuccess = { freshBoard ->
                            val incomingPins = freshBoard.pins
                            val newPins = incomingPins.filter { incoming ->
                                knownIds.none { it == incoming.id }
                            }
                            if (newPins.isNotEmpty()) {
                                handleRefreshedPinsMerged(board, freshBoard, newPins, currentPins)
                            } else {
                                _snackbarMessage.value = "Board is up to date (${currentPins.size} images)"
                            }
                        },
                        onFailure = { err ->
                            _snackbarMessage.value = "Could not refresh board: ${err.message ?: "Network error"}"
                        }
                    )
                } catch (t: Throwable) {
                    _snackbarMessage.value = "Could not refresh board: ${t.message ?: t.javaClass.simpleName}"
                } finally {
                    _isSyncing.value = false
                    isIncrementalScan = false
                }
            }
        }
    }

    private fun refreshCustomBoardLinks(board: PinterestBoard) {
        _isSyncing.value = true
        _snackbarMessage.value = "Refreshing unloaded & unlisted images for \"${board.title}\"..."

        viewModelScope.launch {
            try {
                val currentPins = _rawPins.value
                val visiblePinIds = _displayedPins.value.map { it.id }.toSet()

                // Target items according to Requirement 7:
                // 1) Yet unloaded images on the screen (viewport)
                // 2) Items that are not appeared or (unlisted in ui) yet on the boards
                val targetIndices = currentPins.indices.filter { idx ->
                    val pin = currentPins[idx]
                    val isVisibleOnScreen = visiblePinIds.contains(pin.id)
                    val isUnloadedOrBroken = pin.imageUrl.isBlank() ||
                            pin.thumbnailUrl.isBlank() ||
                            pin.isBrokenOrUnreachable ||
                            pin.fileSizeKb <= 0L
                    val isUnlistedInUi = !isVisibleOnScreen

                    (isVisibleOnScreen && isUnloadedOrBroken) || isUnlistedInUi
                }

                if (targetIndices.isEmpty()) {
                    _snackbarMessage.value = "Images on screen and board are already up to date!"
                    _isSyncing.value = false
                    return@launch
                }

                val updatedPins = withContext(Dispatchers.IO) {
                    val list = currentPins.toMutableList()
                    for (idx in targetIndices) {
                        val pin = list[idx]
                        val resolved = ImageLinkResolver.resolveLink(pin.sourceUrl.ifBlank { pin.imageUrl }, board.title)
                        list[idx] = pin.copy(
                            title = if (pin.title.startsWith("Image ") || pin.title.isBlank()) resolved.title else pin.title,
                            imageUrl = resolved.imageUrl,
                            thumbnailUrl = resolved.thumbnailUrl,
                            fileSizeKb = resolved.fileSizeKb,
                            mimeType = resolved.mimeType,
                            sourceDomain = resolved.sourceDomain,
                            isBrokenOrUnreachable = resolved.isBrokenOrUnreachable
                        )
                    }
                    list.toList()
                }

                val updatedBoard = board.copy(pins = updatedPins, pinCount = updatedPins.size)
                val ctx = appContext
                if (ctx != null) {
                    withContext(Dispatchers.IO) {
                        val dao = AppDatabase.getDatabase(ctx).boardDao()
                        val bEntity = BoardEntity.fromPinterestBoard(updatedBoard)
                        val pEntities = updatedPins.mapIndexed { idx, p -> PinEntity.fromPinItem(p, updatedBoard.id, idx) }
                        dao.saveFullBoard(bEntity, pEntities)
                    }
                }

                _rawPins.value = updatedPins
                _currentBoard.value = updatedBoard
                updateDisplayedPins(resetLimit = false)
                _snackbarMessage.value = "Refreshed ${targetIndices.size} unloaded & unlisted images for \"${board.title}\""
            } catch (t: Throwable) {
                _snackbarMessage.value = "Refresh failed: ${t.message}"
            } finally {
                _isSyncing.value = false
            }
        }
    }

    private fun handleRefreshedPinsMerged(
        board: PinterestBoard,
        freshBoard: PinterestBoard,
        newPins: List<PinItem>,
        currentPins: List<PinItem>
    ) {
        val sortedNewPins = newPins.sortedWith(
            compareBy<PinItem> { it.boardPosition }
                .thenByDescending { it.id.toLongOrNull() ?: 0L }
        )
        val combinedPins = (sortedNewPins + currentPins).distinctBy { it.id }
        val nowMillis = System.currentTimeMillis()

        val reorderedMerged = combinedPins.mapIndexed { index, pin ->
            val artificialDate = (nowMillis - (index * 60000L)).coerceAtLeast(0L)
            pin.copy(
                boardPosition = index,
                dateAddedMillis = artificialDate,
                firstSeenAtMillis = if (sortedNewPins.any { it.id == pin.id }) nowMillis else pin.firstSeenAtMillis
            )
        }

        val updatedBoard = board.copy(
            pins = reorderedMerged,
            pinCount = reorderedMerged.size,
            title = freshBoard.title.ifBlank { board.title },
            ownerDisplayName = freshBoard.ownerDisplayName.ifBlank { board.ownerDisplayName },
            ownerAvatarUrl = freshBoard.ownerAvatarUrl.ifBlank { board.ownerAvatarUrl }
        )

        val ctx = appContext
        val dao = ctx?.let { AppDatabase.getDatabase(it).boardDao() }
        if (dao != null) {
            viewModelScope.launch(Dispatchers.IO) {
                try {
                    val bEntity = BoardEntity.fromPinterestBoard(updatedBoard)
                    val pinEntities = reorderedMerged.mapIndexed { idx, p ->
                        PinEntity.fromPinItem(p, updatedBoard.id, idx)
                    }
                    dao.saveFullBoard(bEntity, pinEntities)
                    propagateDomainMatchingForPins(sortedNewPins, excludeBoardId = updatedBoard.id)
                } catch (t: Throwable) {
                    android.util.Log.e("PinBoardViewModel", "Error saving refreshed board to Room", t)
                    com.example.util.CrashMonitor.recordException(t, "syncCurrentBoard.saveFullBoard")
                }
            }
        }

        _rawPins.value = reorderedMerged
        _currentBoard.value = updatedBoard
        _sortOption.value = SortOption.DATE_NEWEST
        updateDisplayedPins(resetLimit = true)
        _snackbarMessage.value = "Refreshed! Added ${sortedNewPins.size} new image${if (sortedNewPins.size > 1) "s" else ""} to \"${updatedBoard.title}\""
    }

    private fun handleBackgroundScanFinished(newPinsCount: Int) {
        _isSyncing.value = false
        isIncrementalScan = false

        if (newPinsCount > 0) {
            _snackbarMessage.value = "Added $newPinsCount new image${if (newPinsCount > 1) "s" else ""} to board!"
            val board = _currentBoard.value
            val ctx = appContext
            if (board != null && ctx != null) {
                viewModelScope.launch(Dispatchers.IO) {
                    val dao = AppDatabase.getDatabase(ctx).boardDao()
                    val entities = dao.getPinsForBoard(board.id)
                    val pins = entities.map { it.toPinItem() }
                    withContext(Dispatchers.Main) {
                        _rawPins.value = pins
                        _currentBoard.value = board.copy(pins = pins, pinCount = pins.size)
                        updateDisplayedPins(resetLimit = true)
                    }
                }
            }
        } else {
            _snackbarMessage.value = "Board is up to date (no new images)"
        }
    }

    // --- CUSTOM BOARDS MANAGEMENT ---

    fun createCustomBoard(
        name: String,
        domains: List<String>,
        unstructuredLinksText: String,
        isDefault: Boolean
    ) {
        val ctx = appContext ?: return
        viewModelScope.launch {
            _isLoading.value = true
            _snackbarMessage.value = "Creating board \"$name\"..."

            val boardId = "custom_b_${System.currentTimeMillis()}"
            val boardUrl = "custom://$boardId"
            val dao = AppDatabase.getDatabase(ctx).boardDao()

            val links = LinkExtractor.extractLinks(unstructuredLinksText)
            val initialPins = mutableListOf<PinItem>()
            withContext(Dispatchers.IO) {
                links.forEachIndexed { idx, url ->
                    val resolved = ImageLinkResolver.resolveLink(url, name)
                    initialPins.add(resolved.copy(boardPosition = idx, dateAddedMillis = System.currentTimeMillis() - (idx * 1000L)))
                }
            }

            val uniqueInitialPins = initialPins.distinctBy { it.imageUrl }

            val newBoard = PinterestBoard(
                id = boardId,
                title = name,
                slug = name.lowercase().replace(" ", "-"),
                ownerUsername = "you",
                ownerDisplayName = "Custom",
                ownerAvatarUrl = "",
                pinCount = uniqueInitialPins.size,
                boardUrl = boardUrl,
                description = "",
                pins = uniqueInitialPins,
                isCustom = true,
                customDomains = domains,
                isDefault = isDefault,
                isSpecialNonDeletable = false
            )

            withContext(Dispatchers.IO) {
                if (isDefault) {
                    dao.updateBoardDefaultState(boardId)
                }
                val bEntity = BoardEntity.fromPinterestBoard(newBoard)
                val pEntities = uniqueInitialPins.mapIndexed { idx, p -> PinEntity.fromPinItem(p, boardId, idx) }
                dao.saveFullBoard(bEntity, pEntities)
                propagateDomainMatchingForPins(uniqueInitialPins, excludeBoardId = boardId)
                if (domains.isNotEmpty()) {
                    syncDomainMatchingWithAllExistingPins(boardId, domains, dao)
                }
                refreshAvailableBoardsFromDatabaseInternal(dao)
            }

            selectBoard(newBoard)
            _isLoading.value = false
            _snackbarMessage.value = "Created board \"$name\" with ${uniqueInitialPins.size} image${if (uniqueInitialPins.size != 1) "s" else ""}"
        }
    }

    fun editCustomBoard(
        boardId: String,
        newName: String,
        domains: List<String>,
        isDefault: Boolean
    ) {
        val ctx = appContext ?: return
        viewModelScope.launch(Dispatchers.IO) {
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            val existing = dao.getBoardById(boardId) ?: return@launch

            val cleanedDescription = if (existing.description.contains("auto-match", ignoreCase = true) || existing.description.contains("automatch", ignoreCase = true)) "" else existing.description
            val updated = existing.copy(
                title = newName,
                description = cleanedDescription,
                customDomains = domains.joinToString(", "),
                isDefault = isDefault
            )
            if (isDefault) {
                dao.updateBoardDefaultState(boardId)
            }
            dao.insertBoard(updated)
            if (domains.isNotEmpty()) {
                syncDomainMatchingWithAllExistingPins(boardId, domains, dao)
            }
            refreshAvailableBoardsFromDatabaseInternal(dao)

            withContext(Dispatchers.Main) {
                if (_currentBoard.value?.id == boardId) {
                    val cur = _currentBoard.value!!
                    _currentBoard.value = cur.copy(
                        title = newName,
                        description = cleanedDescription,
                        customDomains = domains,
                        isDefault = isDefault
                    )
                }
                _boardHistory.value = _boardHistory.value.map { item ->
                    if (item.boardId == boardId || item.url == existing.boardUrl) {
                        item.copy(title = newName)
                    } else item
                }
                saveHistoryToStorage()
                _snackbarMessage.value = "Updated \"$newName\""
            }
        }
    }

    fun getBoardForHistoryItem(item: BoardHistoryItem): PinterestBoard? {
        val direct = _availableBoards.value.firstOrNull {
            it.id == item.boardId || it.boardUrl == item.url ||
                    (item.url.startsWith("custom://") && it.boardUrl == item.url)
        }
        if (direct != null) return direct

        val cur = _currentBoard.value
        if (cur != null && (cur.id == item.boardId || cur.boardUrl == item.url)) {
            return cur
        }

        return if (item.isCustom) {
            PinterestBoard(
                id = item.boardId.ifBlank { item.url.removePrefix("custom://") },
                title = item.title,
                slug = item.title.lowercase().replace(" ", "-"),
                ownerUsername = "you",
                ownerDisplayName = "Custom",
                pinCount = item.pinCount,
                boardUrl = item.url,
                isCustom = true,
                isSpecialNonDeletable = (item.boardId == "board_dump" || item.boardId == "board_my_save" || item.boardId == "board_favorites" ||
                        item.url.contains("dump") || item.url.contains("my_save") || item.url.contains("favorites"))
            )
        } else null
    }

    fun deleteCustomBoard(board: PinterestBoard) {
        if (board.isSpecialNonDeletable) {
            _snackbarMessage.value = "System boards cannot be deleted."
            return
        }
        val ctx = appContext ?: return
        viewModelScope.launch {
            val dao = AppDatabase.getDatabase(ctx).boardDao()

            _deletedBoardUndo.value = DeletedBoardUndoState(board, _rawPins.value)

            withContext(Dispatchers.IO) {
                dao.deleteBoard(board.id)
                dao.deletePinsForBoard(board.id)

                // If default board was deleted, revert default to "Dump board" (Requirement 9)
                if (board.isDefault) {
                    dao.updateBoardDefaultState("board_dump")
                }
                refreshAvailableBoardsFromDatabaseInternal(dao)
            }

            _boardHistory.value = _boardHistory.value.filterNot { it.url == board.boardUrl || it.boardId == board.id }
            saveHistoryToStorage()

            if (_currentBoard.value?.id == board.id) {
                loadBoardFromUrl("custom://dump")
            }

            _snackbarMessage.value = "Deleted board \"${board.title}\""
        }
    }

    fun undoDeleteCustomBoard() {
        val undo = _deletedBoardUndo.value ?: return
        val ctx = appContext ?: return
        _deletedBoardUndo.value = null

        viewModelScope.launch {
            withContext(Dispatchers.IO) {
                val dao = AppDatabase.getDatabase(ctx).boardDao()
                val bEntity = BoardEntity.fromPinterestBoard(undo.board)
                val pEntities = undo.pins.mapIndexed { idx, p -> PinEntity.fromPinItem(p, undo.board.id, idx) }
                dao.saveFullBoard(bEntity, pEntities)
                refreshAvailableBoardsFromDatabaseInternal(dao)
            }
            selectBoard(undo.board)
            _snackbarMessage.value = "Restored board \"${undo.board.title}\""
        }
    }

    // --- MANUAL IMAGES ADDING & DOMAIN MATCHING ---

    fun addManualImages(
        unstructuredText: String,
        targetBoardIds: List<String>,
        extractMultipleImages: Boolean = false
    ) {
        // Implicit: if user is inside an album on the target board, add to that album
        val _activeAlbumId = _activeAlbum.value?.let { alb ->
            if (_currentBoard.value != null && targetBoardIds.contains(_currentBoard.value!!.id)) alb.id else null
        }
        val targetAlbumId: String? = _activeAlbumId
        val putIntoAlbum = false
        val ctx = appContext ?: return
        val links = LinkExtractor.extractLinks(unstructuredText)
        if (links.isEmpty()) {
            _snackbarMessage.value = "No valid links found in text"
            return
        }

        viewModelScope.launch {
            _isLoading.value = true
            _snackbarMessage.value = "Resolving ${links.size} link${if (links.size > 1) "s" else ""}..."

            val resolvedPins = withContext(Dispatchers.IO) {
                if (extractMultipleImages) {
                    links.flatMap { url -> ImageLinkResolver.resolveMultipleLinks(url) }
                } else {
                    links.map { url -> ImageLinkResolver.resolveLink(url) }
                }
            }

            val dao = AppDatabase.getDatabase(ctx).boardDao()
            val allBoards = withContext(Dispatchers.IO) { dao.getAllBoards() }
            val targetBoards = if (targetBoardIds.isNotEmpty()) {
                allBoards.filter { targetBoardIds.contains(it.id) }.toMutableList()
            } else if (targetAlbumId != null) {
                val album = withContext(Dispatchers.IO) { dao.getAlbumById(targetAlbumId) }
                if (album != null) {
                    allBoards.filter { it.id == album.boardId }.toMutableList()
                } else {
                    allBoards.filter { it.isDefault }.toMutableList()
                }
            } else {
                allBoards.filter { it.isDefault }.toMutableList()
            }

            // Also include custom boards whose customDomains match any of the links (only if not directly targeting an album)
            if (targetAlbumId == null) {
                val domainMatchedBoards = allBoards.filter { b ->
                    b.isCustom && resolvedPins.any { p ->
                        LinkExtractor.matchesAnyDomain(p.sourceUrl.ifBlank { p.imageUrl }, b.customDomains.split(","))
                    }
                }
                for (b in domainMatchedBoards) {
                    if (targetBoards.none { it.id == b.id }) {
                        targetBoards.add(b)
                    }
                }
            }

            var totalAdded = 0
            withContext(Dispatchers.IO) {
                for (boardEntity in targetBoards) {
                    var currentAlbumId = targetAlbumId

                    if (putIntoAlbum && resolvedPins.isNotEmpty()) {
                        val albumId = "album_${System.currentTimeMillis()}_${(1000..9999).random()}"
                        val albumTitle = resolvedPins.firstOrNull()?.title?.substringBefore(" (") ?: "Album"
                        val albumEntity = CustomAlbumEntity(
                            id = albumId,
                            boardId = boardEntity.id,
                            parentAlbumId = targetAlbumId,
                            title = albumTitle,
                            sourceUrl = links.firstOrNull() ?: "",
                            dateAddedMillis = System.currentTimeMillis()
                        )
                        dao.insertAlbum(albumEntity)
                        currentAlbumId = albumId
                    }

                    val existingIds = dao.getPinIdsForBoard(boardEntity.id).toSet()
                    val existingUrls = dao.getImageUrlsForBoard(boardEntity.id).toSet()

                    val pinsToInsert = mutableListOf<PinEntity>()
                    resolvedPins.forEachIndexed { idx, pin ->
                        if (!existingIds.contains(pin.id) && !existingUrls.contains(pin.imageUrl)) {
                            pinsToInsert.add(
                                PinEntity.fromPinItem(
                                    pin.copy(albumId = currentAlbumId),
                                    boardEntity.id,
                                    idx
                                )
                            )
                        }
                    }

                    if (pinsToInsert.isNotEmpty()) {
                        dao.insertPins(pinsToInsert)
                        totalAdded += pinsToInsert.size
                    }
                }
                refreshAvailableBoardsFromDatabaseInternal(dao)
            }

            val current = _currentBoard.value
            if (current != null && targetBoards.any { it.id == current.id }) {
                val updatedPins = withContext(Dispatchers.IO) {
                    dao.getPinsForBoard(current.id).map { it.toPinItem() }
                }
                val updatedAlbums = withContext(Dispatchers.IO) {
                    dao.getAlbumsForBoard(current.id)
                }
                _rawPins.value = updatedPins
                _customAlbums.value = updatedAlbums
                _currentBoard.value = current.copy(pins = updatedPins, pinCount = updatedPins.size)
                updateDisplayedPins(resetLimit = true)
            }

            _isLoading.value = false
            val actionDesc = if (putIntoAlbum) "Created album with $totalAdded image${if (totalAdded != 1) "s" else ""}" else "Added $totalAdded image${if (totalAdded != 1) "s" else ""}"
            _snackbarMessage.value = "$actionDesc to ${targetBoards.size} board${if (targetBoards.size != 1) "s" else ""}"
        }
    }

    fun movePinsToAlbum(pinIds: List<String>, targetAlbumId: String?) {
        val ctx = appContext ?: return
        viewModelScope.launch(Dispatchers.IO) {
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            dao.movePinsToAlbum(pinIds, targetAlbumId)
            val cur = _currentBoard.value
            if (cur != null) {
                val updatedPins = dao.getPinsForBoard(cur.id).map { it.toPinItem() }
                val updatedAlbums = dao.getAlbumsForBoard(cur.id)
                withContext(Dispatchers.Main) {
                    _rawPins.value = updatedPins
                    _customAlbums.value = updatedAlbums
                    _currentBoard.value = cur.copy(pins = updatedPins, pinCount = updatedPins.size)
                    updateDisplayedPins()
                }
            }
        }
    }

    fun moveAlbumToAlbum(albumId: String, targetParentAlbumId: String?) {
        val ctx = appContext ?: return
        viewModelScope.launch(Dispatchers.IO) {
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            dao.setAlbumParent(albumId, targetParentAlbumId)
            val cur = _currentBoard.value
            if (cur != null) {
                val albums = dao.getAlbumsForBoard(cur.id)
                withContext(Dispatchers.Main) {
                    _customAlbums.value = albums
                }
            }
        }
    }

    fun deleteCustomAlbum(albumId: String) {
        val ctx = appContext ?: return
        viewModelScope.launch(Dispatchers.IO) {
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            dao.deleteAlbumAndDetachPins(albumId)
            val cur = _currentBoard.value
            if (cur != null) {
                val albums = dao.getAlbumsForBoard(cur.id)
                val pins = dao.getPinsForBoard(cur.id).map { it.toPinItem() }
                withContext(Dispatchers.Main) {
                    _customAlbums.value = albums
                    _rawPins.value = pins
                    _currentBoard.value = cur.copy(pins = pins, pinCount = pins.size)
                    updateDisplayedPins()
                }
            }
        }
    }

    private suspend fun propagateDomainMatchingForPins(pins: List<PinItem>, excludeBoardId: String) {
        val ctx = appContext ?: return
        val dao = AppDatabase.getDatabase(ctx).boardDao()
        val allCustomBoards = dao.getCustomBoards().filter { it.id != excludeBoardId }

        for (boardEntity in allCustomBoards) {
            val domainList = boardEntity.customDomains.split(",").map { it.trim() }.filter { it.isNotBlank() }
            if (domainList.isEmpty()) continue

            val matchingPins = pins.filter { pin ->
                LinkExtractor.matchesAnyDomain(pin.sourceUrl.ifBlank { pin.imageUrl }, domainList)
            }
            if (matchingPins.isEmpty()) continue

            val existingIds = dao.getPinIdsForBoard(boardEntity.id).toSet()
            val existingUrls = dao.getImageUrlsForBoard(boardEntity.id).toSet()

            val pinsToAdd = matchingPins.filter {
                !existingIds.contains(it.id) && !existingUrls.contains(it.imageUrl)
            }

            if (pinsToAdd.isNotEmpty()) {
                val entities = pinsToAdd.mapIndexed { idx, p ->
                    PinEntity.fromPinItem(p, boardEntity.id, existingIds.size + idx)
                }
                dao.insertPins(entities)
            }
        }
    }

    private suspend fun syncDomainMatchingWithAllExistingPins(
        boardId: String,
        domains: List<String>,
        dao: BoardDao
    ) {
        if (domains.isEmpty()) return
        val allPins = dao.getAllPins()
        if (allPins.isEmpty()) return

        val matchingPins = allPins.filter { pin ->
            val testUrl = pin.sourceUrl.ifBlank { pin.imageUrl }
            LinkExtractor.matchesAnyDomain(testUrl, domains)
        }
        if (matchingPins.isEmpty()) return

        val existingIds = dao.getPinIdsForBoard(boardId).toSet()
        val existingUrls = dao.getImageUrlsForBoard(boardId).toSet()

        val pinsToAdd = matchingPins.filter { pin ->
            !existingIds.contains(pin.id) && !existingUrls.contains(pin.imageUrl)
        }.distinctBy { it.imageUrl }

        if (pinsToAdd.isNotEmpty()) {
            val entities = pinsToAdd.mapIndexed { idx, p ->
                p.copy(
                    boardId = boardId,
                    orderIndex = existingIds.size + idx,
                    boardPosition = existingIds.size + idx
                )
            }
            dao.insertPins(entities)

            val current = _currentBoard.value
            if (current != null && current.id == boardId) {
                withContext(Dispatchers.Main) {
                    val addedItems = entities.map { it.toPinItem() }
                    val combined = _rawPins.value + addedItems
                    _rawPins.value = combined
                    _currentBoard.value = current.copy(pins = combined, pinCount = combined.size)
                    updateDisplayedPins()
                }
            }
        }
    }

    // --- FAVORITES BOARD SYSTEM ---

    fun toggleFavorite(pin: PinItem) {
        val ctx = appContext ?: return
        viewModelScope.launch {
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            val currentlyFav = isFavorite(pin)

            if (currentlyFav) {
                withContext(Dispatchers.IO) {
                    dao.removePinFromFavorites("board_favorites", pin.id, pin.imageUrl)
                }
                _individualFavoritePinKeys.value = _individualFavoritePinKeys.value - pin.id - pin.imageUrl
                _favoritePinKeys.value = _favoritePinKeys.value - pin.id - pin.imageUrl
                saveAppSettings()

                // In favorites board: DO NOT instantly remove the image from the UI when user unfavorites it (User request 2)
                // The user may make mistakes. The image remains in place with its heart unfavorited.
                _snackbarMessage.value = "Removed from Favorites"
            } else {
                val now = System.currentTimeMillis()
                favoriteTimestamps[pin.id] = now
                favoriteTimestamps[pin.imageUrl] = now
                val order = withContext(Dispatchers.IO) { dao.getPinsForBoard("board_favorites").size }
                val favEntity = PinEntity.fromPinItem(pin, "board_favorites", order).copy(dateAddedMillis = now)
                withContext(Dispatchers.IO) {
                    dao.insertPins(listOf(favEntity))
                }
                _individualFavoritePinKeys.value = _individualFavoritePinKeys.value + pin.id + pin.imageUrl
                _favoritePinKeys.value = _favoritePinKeys.value + pin.id + pin.imageUrl
                saveAppSettings()

                if (_currentBoard.value?.id == "board_favorites") {
                    val currentList = _rawPins.value
                    val alreadyPresent = currentList.any { it.id == pin.id || it.imageUrl == pin.imageUrl }
                    if (!alreadyPresent) {
                        val updated = listOf(pin) + currentList
                        _rawPins.value = updated
                        _currentBoard.value = _currentBoard.value?.copy(pins = updated, pinCount = updated.size)
                        updateDisplayedPins()
                    }
                    // If already present (user re-favorited), keep the image's position exactly the same
                }
                _snackbarMessage.value = "Added to Favorites ♥"
            }
        }
    }

    fun isFavorite(pin: PinItem): Boolean {
        val keys = _favoritePinKeys.value
        return keys.contains(pin.id) || keys.contains(pin.imageUrl)
    }

    fun isAlbumFavorite(
        albumId: String,
        albumPins: List<PinItem>,
        favKeys: Set<String> = _favoritePinKeys.value,
        favAlbumIds: Set<String> = _favoriteAlbumIds.value
    ): Boolean {
        if (albumPins.isEmpty()) return false
        if (favAlbumIds.contains(albumId)) return true
        return albumPins.all { favKeys.contains(it.id) || favKeys.contains(it.imageUrl) }
    }

    fun isAlbumFavorite(albumPins: List<PinItem>): Boolean {
        if (albumPins.isEmpty()) return false
        val keys = _favoritePinKeys.value
        return albumPins.all { keys.contains(it.id) || keys.contains(it.imageUrl) }
    }

    fun toggleAlbumFavorites(albumId: String, albumTitle: String, pins: List<PinItem>) {
        val ctx = appContext ?: return
        if (pins.isEmpty()) return
        val currentlyFav = isAlbumFavorite(albumId, pins)

        if (currentlyFav) {
            // Unfavoriting the album
            _favoriteAlbumIds.value = _favoriteAlbumIds.value - albumId
            saveAppSettings()

            // Requirement 5: Keep individual favorites intact even when album is unfavorited!
            val individualKeys = _individualFavoritePinKeys.value
            val pinsToRemove = pins.filterNot { pin ->
                individualKeys.contains(pin.id) || individualKeys.contains(pin.imageUrl)
            }

            val removedKeys = pinsToRemove.flatMap { listOf(it.id, it.imageUrl) }.toSet()
            _favoritePinKeys.value = _favoritePinKeys.value - removedKeys

            val keptCount = pins.size - pinsToRemove.size
            if (keptCount > 0) {
                _snackbarMessage.value = "Removed \"$albumTitle\" from Favorites (kept $keptCount individually favorited images)"
            } else {
                _snackbarMessage.value = "Removed \"$albumTitle\" from Favorites"
            }

            viewModelScope.launch {
                val dao = AppDatabase.getDatabase(ctx).boardDao()
                withContext(Dispatchers.IO) {
                    pinsToRemove.forEach { pin ->
                        dao.removePinFromFavorites("board_favorites", pin.id, pin.imageUrl)
                    }
                    refreshAvailableBoardsFromDatabaseInternal(dao)
                }
                // In favorites board: DO NOT instantly remove the album/images from the UI when user unfavorites it (User request 3)
                // The user may make mistakes. The album and its images remain in place with heart unfavorited.
            }
        } else {
            // Favoriting the album
            _favoriteAlbumIds.value = _favoriteAlbumIds.value + albumId
            saveAppSettings()

            val toAdd = pins.filterNot { isFavorite(it) }
            val addedKeys = pins.flatMap { listOf(it.id, it.imageUrl) }.toSet()
            _favoritePinKeys.value = _favoritePinKeys.value + addedKeys
            _snackbarMessage.value = "Added \"$albumTitle\" (${pins.size} images) to Favorites ♥"

            val now = System.currentTimeMillis()
            pins.forEach { p ->
                favoriteTimestamps[p.id] = now
                favoriteTimestamps[p.imageUrl] = now
            }

            viewModelScope.launch {
                val dao = AppDatabase.getDatabase(ctx).boardDao()
                withContext(Dispatchers.IO) {
                    val currentFavCount = dao.getPinsForBoard("board_favorites").size
                    val entities = toAdd.mapIndexed { idx, pin ->
                        PinEntity.fromPinItem(pin, "board_favorites", currentFavCount + idx).copy(dateAddedMillis = now)
                    }
                    dao.insertPins(entities)
                    refreshAvailableBoardsFromDatabaseInternal(dao)
                }
                if (_currentBoard.value?.id == "board_favorites") {
                    val updatedPins = (toAdd + _rawPins.value).distinctBy { it.id }
                    _rawPins.value = updatedPins
                    _currentBoard.value = _currentBoard.value?.copy(pins = updatedPins, pinCount = updatedPins.size)
                    updateDisplayedPins()
                }
            }
        }
    }

    fun toggleAlbumFavorites(albumTitle: String, pins: List<PinItem>) {
        toggleAlbumFavorites("album_$albumTitle", albumTitle, pins)
    }

    // --- MOVE TO TOP FEATURE ---

    fun moveSelectedPinsToTop() {
        val board = _currentBoard.value ?: return
        val selectedIds = _selectedPinIds.value
        if (selectedIds.isEmpty()) return

        val currentPins = _rawPins.value
        val (selectedPins, remainingPins) = currentPins.partition { selectedIds.contains(it.id) }
        if (selectedPins.isEmpty()) return

        val nowMillis = System.currentTimeMillis()
        val reordered = (selectedPins + remainingPins).mapIndexed { idx, p ->
            p.copy(
                boardPosition = idx,
                dateAddedMillis = if (selectedIds.contains(p.id)) (nowMillis + (selectedPins.size - idx) * 1000L) else p.dateAddedMillis
            )
        }

        _rawPins.value = reordered
        _sortOption.value = SortOption.DATE_NEWEST
        _currentBoard.value = board.copy(pins = reordered)
        clearSelection()
        updateDisplayedPins(resetLimit = true)

        viewModelScope.launch(Dispatchers.IO) {
            val ctx = appContext ?: return@launch
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            val bEntity = BoardEntity.fromPinterestBoard(_currentBoard.value!!)
            val pEntities = reordered.mapIndexed { idx, p -> PinEntity.fromPinItem(p, board.id, idx) }
            dao.saveFullBoard(bEntity, pEntities)
        }

        _snackbarMessage.value = "Moved ${selectedPins.size} image${if (selectedPins.size > 1) "s" else ""} to the top"
    }

    fun movePinToTop(pin: PinItem) {
        val board = _currentBoard.value ?: return
        val currentPins = _rawPins.value
        val remaining = currentPins.filterNot { it.id == pin.id }
        val nowMillis = System.currentTimeMillis()
        val updatedPin = pin.copy(boardPosition = 0, dateAddedMillis = nowMillis + 60000L)
        val reordered = (listOf(updatedPin) + remaining).mapIndexed { idx, p -> p.copy(boardPosition = idx) }

        _rawPins.value = reordered
        _sortOption.value = SortOption.DATE_NEWEST
        _currentBoard.value = board.copy(pins = reordered)
        updateDisplayedPins(resetLimit = true)

        viewModelScope.launch(Dispatchers.IO) {
            val ctx = appContext ?: return@launch
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            val bEntity = BoardEntity.fromPinterestBoard(_currentBoard.value!!)
            val pEntities = reordered.mapIndexed { idx, p -> PinEntity.fromPinItem(p, board.id, idx) }
            dao.saveFullBoard(bEntity, pEntities)
        }

        _snackbarMessage.value = "Moved \"${pin.title}\" to top"
    }

    // --- COPY & MOVE TO OTHER BOARDS ---

    fun copySelectedPinsToBoards(targetBoardIds: List<String>, pinIds: Set<String>) {
        if (targetBoardIds.isEmpty() || pinIds.isEmpty()) return
        val ctx = appContext ?: return
        viewModelScope.launch {
            val pinsToCopy = _rawPins.value.filter { pinIds.contains(it.id) }
            if (pinsToCopy.isEmpty()) return@launch

            val dao = AppDatabase.getDatabase(ctx).boardDao()
            var totalCopied = 0
            withContext(Dispatchers.IO) {
                for (targetId in targetBoardIds) {
                    val existingIds = dao.getPinIdsForBoard(targetId).toSet()
                    val existingUrls = dao.getImageUrlsForBoard(targetId).toSet()
                    val newForTarget = pinsToCopy.filter {
                        !existingIds.contains(it.id) && !existingUrls.contains(it.imageUrl)
                    }
                    if (newForTarget.isNotEmpty()) {
                        val targetEntity = dao.getBoardById(targetId)
                        if (targetEntity != null) {
                            val existingPins = dao.getPinsForBoard(targetId).map { it.toPinItem() }
                            val combined = (newForTarget + existingPins).distinctBy { it.id }
                            val entities = combined.mapIndexed { idx, pin ->
                                PinEntity.fromPinItem(pin, targetId, idx)
                            }
                            dao.saveFullBoard(targetEntity, entities)
                        } else {
                            val entities = newForTarget.mapIndexed { idx, pin ->
                                PinEntity.fromPinItem(pin, targetId, existingIds.size + idx)
                            }
                            dao.insertPins(entities)
                        }
                        totalCopied += newForTarget.size
                    }
                }
                refreshAvailableBoardsFromDatabaseInternal(dao)
            }
            clearSelection()
            _snackbarMessage.value = "Copied ${pinsToCopy.size} image${if (pinsToCopy.size > 1) "s" else ""} to ${targetBoardIds.size} board${if (targetBoardIds.size > 1) "s" else ""}"
        }
    }

    fun moveSelectedPinsToBoards(targetBoardIds: List<String>, pinIds: Set<String>) {
        if (targetBoardIds.isEmpty() || pinIds.isEmpty()) return
        val ctx = appContext ?: return
        val sourceBoard = _currentBoard.value ?: return
        viewModelScope.launch {
            val pinsToMove = _rawPins.value.filter { pinIds.contains(it.id) }
            if (pinsToMove.isEmpty()) return@launch

            val dao = AppDatabase.getDatabase(ctx).boardDao()
            withContext(Dispatchers.IO) {
                // 1. Copy to target boards
                for (targetId in targetBoardIds) {
                    if (targetId == sourceBoard.id) continue
                    val existingIds = dao.getPinIdsForBoard(targetId).toSet()
                    val existingUrls = dao.getImageUrlsForBoard(targetId).toSet()
                    val newForTarget = pinsToMove.filter {
                        !existingIds.contains(it.id) && !existingUrls.contains(it.imageUrl)
                    }
                    if (newForTarget.isNotEmpty()) {
                        val targetEntity = dao.getBoardById(targetId)
                        if (targetEntity != null) {
                            val existingPins = dao.getPinsForBoard(targetId).map { it.toPinItem() }
                            val combined = (newForTarget + existingPins).distinctBy { it.id }
                            val entities = combined.mapIndexed { idx, pin ->
                                PinEntity.fromPinItem(pin, targetId, idx)
                            }
                            dao.saveFullBoard(targetEntity, entities)
                        } else {
                            val entities = newForTarget.mapIndexed { idx, pin ->
                                PinEntity.fromPinItem(pin, targetId, existingIds.size + idx)
                            }
                            dao.insertPins(entities)
                        }
                    }
                }
                // 2. Delete from source board in Room
                dao.deletePinsFromBoard(sourceBoard.id, pinIds.toList())
                refreshAvailableBoardsFromDatabaseInternal(dao)
            }

            // 3. Update current board in memory
            val remaining = _rawPins.value.filterNot { pinIds.contains(it.id) }
            _rawPins.value = remaining
            _currentBoard.value = sourceBoard.copy(pins = remaining, pinCount = remaining.size)
            updateDisplayedPins(resetLimit = false)
            clearSelection()
            _snackbarMessage.value = "Moved ${pinsToMove.size} image${if (pinsToMove.size > 1) "s" else ""} to ${targetBoardIds.size} board${if (targetBoardIds.size > 1) "s" else ""}"
        }
    }

    // --- DELETE PINS WITH UNDO & DELETE FROM ALL BOARDS ---

    fun deletePinsFromCurrentBoard(pinIds: Set<String>) {
        val board = _currentBoard.value ?: return
        if (pinIds.isEmpty()) return

        val currentPins = _rawPins.value
        val (toDelete, toKeep) = currentPins.partition { pinIds.contains(it.id) }
        if (toDelete.isEmpty()) return

        _deletedPinsUndo.value = DeletedPinsUndoState(
            boardId = board.id,
            pins = toDelete,
            imageUrls = toDelete.map { it.imageUrl }
        )

        _rawPins.value = toKeep
        _currentBoard.value = board.copy(pins = toKeep, pinCount = toKeep.size)
        clearSelection()
        updateDisplayedPins()

        viewModelScope.launch(Dispatchers.IO) {
            val ctx = appContext ?: return@launch
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            dao.deletePinsFromBoard(board.id, toDelete.map { it.id })
            refreshAvailableBoardsFromDatabaseInternal(dao)
        }
        // Requirement 4: Only show the floating banner with Undo/Delete From All buttons, do NOT show the duplicate generic snackbar
    }

    fun dismissUndoDeletePins() {
        _deletedPinsUndo.value = null
    }

    fun deleteSinglePin(pin: PinItem) {
        deletePinsFromCurrentBoard(setOf(pin.id))
    }

    fun undoDeletePins() {
        val undo = _deletedPinsUndo.value ?: return
        val board = _currentBoard.value ?: return
        _deletedPinsUndo.value = null

        val restored = (undo.pins + _rawPins.value).distinctBy { it.id }
        _rawPins.value = restored
        _currentBoard.value = board.copy(pins = restored, pinCount = restored.size)
        updateDisplayedPins()

        viewModelScope.launch(Dispatchers.IO) {
            val ctx = appContext ?: return@launch
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            val entities = undo.pins.mapIndexed { idx, p -> PinEntity.fromPinItem(p, undo.boardId, idx) }
            dao.insertPins(entities)
            refreshAvailableBoardsFromDatabaseInternal(dao)
        }

        _snackbarMessage.value = "Restored ${undo.pins.size} image${if (undo.pins.size > 1) "s" else ""}"
    }

    fun requestDeleteFromAllBoards() {
        val undo = _deletedPinsUndo.value ?: return
        _showDeleteFromAllConfirmation.value = undo
    }

    fun dismissDeleteFromAllConfirmation() {
        _showDeleteFromAllConfirmation.value = null
    }

    fun confirmDeleteFromAllBoards() {
        val undo = _showDeleteFromAllConfirmation.value ?: _deletedPinsUndo.value ?: return
        _showDeleteFromAllConfirmation.value = null
        _deletedPinsUndo.value = null

        val targetIds = undo.pins.map { it.id }
        val targetUrls = undo.imageUrls

        viewModelScope.launch(Dispatchers.IO) {
            val ctx = appContext ?: return@launch
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            dao.deletePinsFromAllBoards(targetIds, targetUrls)

            _favoritePinKeys.value = _favoritePinKeys.value.filterNot { targetIds.contains(it) || targetUrls.contains(it) }.toSet()
            refreshAvailableBoardsFromDatabaseInternal(dao)
        }

        val updated = _rawPins.value.filterNot { targetIds.contains(it.id) || targetUrls.contains(it.imageUrl) }
        _rawPins.value = updated
        _currentBoard.value = _currentBoard.value?.copy(pins = updated, pinCount = updated.size)
        updateDisplayedPins()

        _snackbarMessage.value = "Deleted image(s) from all boards"
    }

    // --- BOARD HISTORY & PERSISTENCE ---

    private fun addBoardToHistory(board: PinterestBoard) {
        val normUrl = board.boardUrl.trim().removeSuffix("/")
        val currentList = _boardHistory.value.toMutableList()
        val existingIndex = currentList.indexOfFirst {
            it.url.trim().removeSuffix("/").equals(normUrl, ignoreCase = true) ||
                    (it.title.equals(board.title, ignoreCase = true) && it.ownerName.equals(board.ownerDisplayName, ignoreCase = true))
        }
        val newItem = BoardHistoryItem(
            url = board.boardUrl,
            title = board.title,
            ownerName = board.ownerDisplayName,
            ownerAvatarUrl = board.ownerAvatarUrl,
            pinCount = board.pins.size,
            timestamp = System.currentTimeMillis(),
            isCustom = board.isCustom,
            boardId = board.id
        )
        if (existingIndex >= 0) {
            currentList[existingIndex] = newItem.copy(timestamp = currentList[existingIndex].timestamp)
        } else {
            currentList.add(newItem)
        }
        _boardHistory.value = ensureSpecialBoardsInHistory(currentList).take(30)
        saveHistoryToStorage()
    }

    fun removeHistoryItem(url: String) {
        if (url == "custom://my_save" || url == "custom://favorites") return
        val filtered = _boardHistory.value.filterNot { it.url == url }
        _boardHistory.value = ensureSpecialBoardsInHistory(filtered)
        saveHistoryToStorage()
    }

    fun clearHistory() {
        _boardHistory.value = DEFAULT_SPECIAL_HISTORY
        saveHistoryToStorage()
    }

    private fun getBoardKey(board: PinterestBoard): String {
        return if (board.id.isNotBlank()) "b_${board.id}"
        else "b_${board.boardUrl.hashCode()}"
    }

    private fun saveBoardSettings(board: PinterestBoard, cols: Int, sort: SortOption) {
        val ctx = appContext ?: return
        try {
            val prefs = ctx.getSharedPreferences("board_layout_prefs", Context.MODE_PRIVATE)
            prefs.edit()
                .putInt("${getBoardKey(board)}_columns", cols)
                .putString("${getBoardKey(board)}_sort", sort.name)
                .apply()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private fun loadBoardSettings(board: PinterestBoard): Pair<Int?, SortOption?> {
        val ctx = appContext ?: return Pair(null, null)
        try {
            val prefs = ctx.getSharedPreferences("board_layout_prefs", Context.MODE_PRIVATE)
            val key = getBoardKey(board)
            val savedCols = if (prefs.contains("${key}_columns")) {
                prefs.getInt("${key}_columns", 2)
            } else null

            val savedSortStr = prefs.getString("${key}_sort", null)
            val savedSort = if (savedSortStr != null) {
                try { SortOption.valueOf(savedSortStr) } catch (_: Exception) { null }
            } else null

            return Pair(savedCols, savedSort)
        } catch (e: Exception) {
            return Pair(null, null)
        }
    }

    fun setRememberPerBoardSettings(enabled: Boolean) {
        _rememberPerBoardSettings.value = enabled
        saveAppSettings()
        if (enabled) {
            _currentBoard.value?.let { board ->
                val (cols, sort) = loadBoardSettings(board)
                if (cols != null && cols in 2..4) {
                    _columnCount.value = cols
                }
                if (sort != null) {
                    _sortOption.value = sort
                    updateDisplayedPins(resetLimit = false)
                }
            }
        }
    }

    fun setHidePinTitlesAndAuthors(hide: Boolean) {
        _hidePinTitlesAndAuthors.value = hide
        saveAppSettings()
    }

    fun setPortraitAlbumCards(portrait: Boolean) {
        _portraitAlbumCards.value = portrait
        saveAppSettings()
    }

    fun setDisableArrowNavigation(disabled: Boolean) {
        _disableArrowNavigation.value = disabled
        saveAppSettings()
    }

    fun toggleDisableArrowNavigation(disabled: Boolean) {
        _disableArrowNavigation.value = disabled
        saveAppSettings()
    }

    private fun saveAppSettings() {
        val ctx = appContext ?: return
        try {
            val prefs = ctx.getSharedPreferences("app_settings", Context.MODE_PRIVATE)
            prefs.edit()
                .putInt("column_count", _columnCount.value)
                .putString("sort_option", _sortOption.value.name)
                .putBoolean("separate_by_date", _separateByDate.value)
                .putBoolean("group_by_album", _groupByAlbum.value)
                .putBoolean("remember_per_board_settings", _rememberPerBoardSettings.value)
                .putBoolean("hide_pin_titles_and_authors", _hidePinTitlesAndAuthors.value)
                .putBoolean("portrait_album_cards", _portraitAlbumCards.value)
                .putBoolean("disable_arrow_navigation", _disableArrowNavigation.value)
                .putBoolean("show_browser_testing", _isBrowserTestingVisible.value)
                .putStringSet("individual_favorite_pin_keys", _individualFavoritePinKeys.value)
                .putStringSet("favorite_album_ids", _favoriteAlbumIds.value)
                .apply()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private fun loadAppSettings() {
        val ctx = appContext ?: return
        try {
            val prefs = ctx.getSharedPreferences("app_settings", Context.MODE_PRIVATE)
            val savedCols = prefs.getInt("column_count", 2)
            if (savedCols in 2..4) {
                _columnCount.value = savedCols
            }
            val savedSortStr = prefs.getString("sort_option", null)
            if (savedSortStr != null) {
                try {
                    _sortOption.value = SortOption.valueOf(savedSortStr)
                    updateDisplayedPins()
                } catch (_: Exception) {}
            }
            _separateByDate.value = prefs.getBoolean("separate_by_date", false)
            _groupByAlbum.value = prefs.getBoolean("group_by_album", false)
            _rememberPerBoardSettings.value = prefs.getBoolean("remember_per_board_settings", true)
            _hidePinTitlesAndAuthors.value = prefs.getBoolean("hide_pin_titles_and_authors", false)
            _portraitAlbumCards.value = prefs.getBoolean("portrait_album_cards", false)
            _disableArrowNavigation.value = prefs.getBoolean("disable_arrow_navigation", false)
            _isBrowserTestingVisible.value = prefs.getBoolean("show_browser_testing", false)
            val savedIndiv = prefs.getStringSet("individual_favorite_pin_keys", null)
            if (savedIndiv != null) {
                _individualFavoritePinKeys.value = savedIndiv.toSet()
            }
            val savedAlbums = prefs.getStringSet("favorite_album_ids", null)
            if (savedAlbums != null) {
                _favoriteAlbumIds.value = savedAlbums.toSet()
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private fun saveOpenedBoardState(board: PinterestBoard) {
        val ctx = appContext ?: return
        try {
            val prefs = ctx.getSharedPreferences("app_settings", Context.MODE_PRIVATE)
            prefs.edit()
                .putString("last_opened_board_id", board.id)
                .putString("last_opened_board_url", board.boardUrl)
                .apply()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private fun loadOpenedBoardState() {
        val ctx = appContext ?: return
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val prefs = ctx.getSharedPreferences("app_settings", Context.MODE_PRIVATE)
                val lastBoardId = prefs.getString("last_opened_board_id", null)
                val lastBoardUrl = prefs.getString("last_opened_board_url", null)

                val dao = AppDatabase.getDatabase(ctx).boardDao()
                val targetBoard = if (!lastBoardId.isNullOrBlank() || !lastBoardUrl.isNullOrBlank()) {
                    dao.getBoardByIdOrUrl(lastBoardId ?: "", lastBoardUrl ?: "")
                } else {
                    dao.getDefaultBoard() ?: dao.getBoardById("board_dump") ?: dao.getBoardById("board_my_save") ?: dao.getAllBoards().firstOrNull()
                }

                val board = if (targetBoard != null) {
                    val pinEntities = dao.getPinsForBoard(targetBoard.id)
                    val pins = pinEntities.map { it.toPinItem() }
                    targetBoard.toPinterestBoard(pins)
                } else {
                    DEFAULT_DUMP_BOARD
                }

                withContext(Dispatchers.Main) {
                    if (_currentBoard.value == null) {
                        selectBoard(board)
                    }
                }
            } catch (t: Throwable) {
                t.printStackTrace()
            }
        }
    }

    private fun saveHistoryToStorage() {
        val ctx = appContext ?: return
        try {
            val prefs = ctx.getSharedPreferences("pinterest_board_history", Context.MODE_PRIVATE)
            val jsonArray = JSONArray()
            _boardHistory.value.forEach { item ->
                val obj = JSONObject().apply {
                    put("url", item.url)
                    put("title", item.title)
                    put("ownerName", item.ownerName)
                    put("ownerAvatarUrl", item.ownerAvatarUrl)
                    put("pinCount", item.pinCount)
                    put("timestamp", item.timestamp)
                    put("isCustom", item.isCustom)
                    put("boardId", item.boardId)
                }
                jsonArray.put(obj)
            }
            prefs.edit().putString("history_json", jsonArray.toString()).apply()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private fun loadHistoryFromStorage() {
        val ctx = appContext ?: return
        try {
            val prefs = ctx.getSharedPreferences("pinterest_board_history", Context.MODE_PRIVATE)
            val jsonStr = prefs.getString("history_json", null) ?: return
            val jsonArray = JSONArray(jsonStr)
            val list = mutableListOf<BoardHistoryItem>()
            for (i in 0 until jsonArray.length()) {
                val obj = jsonArray.getJSONObject(i)
                val url = obj.optString("url", "")
                if (url.isNotBlank()) {
                    list.add(
                        BoardHistoryItem(
                            url = url,
                            title = obj.optString("title", "Board"),
                            ownerName = obj.optString("ownerName", ""),
                            ownerAvatarUrl = obj.optString("ownerAvatarUrl", ""),
                            pinCount = obj.optInt("pinCount", 0),
                            timestamp = obj.optLong("timestamp", System.currentTimeMillis()),
                            isCustom = obj.optBoolean("isCustom", false),
                            boardId = obj.optString("boardId", "")
                        )
                    )
                }
            }
            _boardHistory.value = ensureSpecialBoardsInHistory(list.distinctBy { it.url.trim().removeSuffix("/").lowercase() })
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    fun setColumnCount(count: Int) {
        if (count in 2..4) {
            _columnCount.value = count
            saveAppSettings()
            if (_rememberPerBoardSettings.value) {
                _currentBoard.value?.let { board ->
                    saveBoardSettings(board, count, _sortOption.value)
                }
            }
        }
    }

    fun setSortOption(option: SortOption) {
        _sortOption.value = option
        updateDisplayedPins(resetLimit = true)
        saveAppSettings()
        if (_rememberPerBoardSettings.value) {
            _currentBoard.value?.let { board ->
                saveBoardSettings(board, _columnCount.value, option)
            }
        }
    }

    fun setSearchQuery(query: String) {
        _searchQuery.value = query
        updateDisplayedPins(resetLimit = true)
    }

    fun toggleSelection(pinId: String) {
        val current = _selectedPinIds.value
        val updated = if (current.contains(pinId)) {
            current - pinId
        } else {
            current + pinId
        }
        _selectedPinIds.value = updated
    }

    fun selectAll() {
        _selectedPinIds.value = allFilteredSortedPins.map { it.id }.toSet()
        _isSelectionMode.value = true
    }

    fun selectAllAlbums(albumIds: Set<String>) {
        _selectedAlbumIds.value = albumIds
    }

    fun deselectAll() {
        _selectedPinIds.value = emptySet()
    }

    fun clearSelection() {
        _selectedPinIds.value = emptySet()
        _selectedAlbumIds.value = emptySet()
        _isSelectionMode.value = false
    }

    fun toggleAlbumSelection(albumId: String) {
        val current = _selectedAlbumIds.value
        _selectedAlbumIds.value = if (current.contains(albumId)) current - albumId else current + albumId
    }

    fun enterSelectionMode(initialPinId: String? = null) {
        _isSelectionMode.value = true
        if (initialPinId != null) {
            _selectedPinIds.value = setOf(initialPinId)
        }
    }

    fun restoreFromBackup(
        backupFile: java.io.File,
        onComplete: (Result<com.example.util.BackupManager.RestoreSummary>) -> Unit
    ) {
        val ctx = appContext ?: return
        viewModelScope.launch {
            val result = com.example.util.BackupManager.restoreBackup(ctx, backupFile)
            if (result.isSuccess) {
                val dao = com.example.data.local.AppDatabase.getDatabase(ctx).boardDao()
                refreshAvailableBoardsFromDatabaseInternal(dao)
                loadAppSettings()
                loadHistoryFromStorage()
                _currentBoard.value?.let { curr ->
                    val updatedPins = withContext(Dispatchers.IO) { dao.getPinsForBoard(curr.id) }.map { it.toPinItem() }
                    _rawPins.value = updatedPins
                    _currentBoard.value = curr.copy(pins = updatedPins, pinCount = updatedPins.size)
                    updateDisplayedPins()
                }
            }
            onComplete(result)
        }
    }

    fun openFullscreen(index: Int) {
        if (!_isSelectionMode.value) {
            _fullscreenPinIndex.value = index
        }
    }

    fun closeFullscreen() {
        _fullscreenPinIndex.value = null
    }

    fun downloadSelected(context: Context) {
        val selectedIds = _selectedPinIds.value
        val pinsToDownload = displayedPins.value.filter { selectedIds.contains(it.id) }
        if (pinsToDownload.isEmpty()) {
            _snackbarMessage.value = "No images selected to download"
            return
        }

        viewModelScope.launch {
            _snackbarMessage.value = "Saving ${pinsToDownload.size} images to PinterestViewerDownloads..."
            val count = Downloader.downloadPins(context, pinsToDownload) { progress ->
                _downloadProgress.value = progress
            }
            _snackbarMessage.value = "Saved $count images to Downloads/${Downloader.FOLDER_NAME}!"
            clearSelection()
        }
    }

    fun downloadSingle(context: Context, pin: PinItem) {
        viewModelScope.launch {
            _snackbarMessage.value = "Saving image to PinterestViewerDownloads..."
            val success = Downloader.downloadSinglePin(context, pin)
            if (success) {
                _snackbarMessage.value = "Image saved to Downloads/${Downloader.FOLDER_NAME}!"
            } else {
                _snackbarMessage.value = "Failed to download image."
            }
        }
    }

    fun executeSnackbarAction() {
        _snackbarAction.value?.invoke()
    }

    fun dismissSnackbar() {
        _snackbarMessage.value = null
        _snackbarActionLabel.value = null
        _snackbarAction.value = null
    }

    fun showSnackbarWithAction(message: String, actionLabel: String, onAction: () -> Unit) {
        _snackbarActionLabel.value = actionLabel
        _snackbarAction.value = onAction
        _snackbarMessage.value = message
    }

    fun requestScrollToAlbum(albumId: String) { _scrollToAlbumId.value = albumId }
    fun consumeScrollRequest() { _scrollToAlbumId.value = null }
    fun openAlbumPositionDialog(albumId: String) { _repositioningAlbumId.value = albumId }
    fun closeAlbumPositionDialog() { _repositioningAlbumId.value = null }

    fun clearDownloadProgress() {
        _downloadProgress.value = null
    }

    fun deleteSelectedAlbums() {
        val ids = _selectedAlbumIds.value
        if (ids.isEmpty()) return
        val ctx = appContext ?: return
        viewModelScope.launch {
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            withContext(Dispatchers.IO) {
                ids.forEach { dao.deleteAlbumAndDetachPins(it) }
            }
            val cur = _currentBoard.value
            if (cur != null) {
                val pins = dao.getPinsForBoard(cur.id).map { it.toPinItem() }
                val albums = dao.getAlbumsForBoard(cur.id)
                withContext(Dispatchers.Main) {
                    _rawPins.value = pins
                    _customAlbums.value = albums
                    _currentBoard.value = cur.copy(pins = pins, pinCount = pins.size)
                    updateDisplayedPins()
                }
            }
            clearSelection()
            _snackbarMessage.value = "Deleted ${ids.size} album${if (ids.size > 1) "s" else ""}"
        }
    }

    private fun resolveInsertionMillis(position: AlbumPosition, pins: List<PinItem>, currentPins: List<PinItem>): Long {
        if (pins.isEmpty()) return System.currentTimeMillis()
        val sortedSel = pins.map { it.dateAddedMillis }.sorted()
        return when (position) {
            AlbumPosition.TOP_OF_BOARD -> (currentPins.maxOfOrNull { it.dateAddedMillis } ?: 0L) + 60_000L
            AlbumPosition.TOP_SELECTED -> sortedSel.last() + 60_000L
            AlbumPosition.MIDDLE_SELECTED -> sortedSel[sortedSel.size / 2]
            AlbumPosition.BOTTOM_SELECTED -> sortedSel.first() - 60_000L
        }
    }

    fun combineSelectedPinsToNewAlbum(position: AlbumPosition = AlbumPosition.TOP_SELECTED) {
        val selectedIds = _selectedPinIds.value
        if (selectedIds.size < 2) {
            _snackbarMessage.value = "Select at least 2 images to create an album"
            return
        }
        val board = _currentBoard.value ?: return
        val ctx = appContext ?: return
        val selectedPins = _rawPins.value.filter { selectedIds.contains(it.id) }
        viewModelScope.launch {
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            val albumId = "album_${System.currentTimeMillis()}_${(1000..9999).random()}"
            val albumDate = resolveInsertionMillis(position, selectedPins, _rawPins.value)
            val entity = CustomAlbumEntity(
                id = albumId, boardId = board.id, parentAlbumId = null,
                title = "Album (${selectedPins.size} images)",
                sourceUrl = "", dateAddedMillis = albumDate,
                orderIndex = 0, isFavorite = false
            )
            withContext(Dispatchers.IO) { dao.insertAlbum(entity) }
            val updatedPins = _rawPins.value.map { p ->
                if (selectedIds.contains(p.id)) p.copy(albumId = albumId) else p
            }
            withContext(Dispatchers.IO) {
                dao.upsertPinsSafely(updatedPins.mapIndexed { i, p -> PinEntity.fromPinItem(p, board.id, i) })
            }
            val albums = withContext(Dispatchers.IO) { dao.getAlbumsForBoard(board.id) }
            withContext(Dispatchers.Main) {
                _rawPins.value = updatedPins
                _customAlbums.value = albums
                _currentBoard.value = board.copy(pins = updatedPins, pinCount = updatedPins.size)
                clearSelection()
                updateDisplayedPins(resetLimit = true)
                requestScrollToAlbum(albumId)
                showSnackbarWithAction(
                    message = "Album created · ${selectedPins.size} images",
                    actionLabel = "Change position"
                ) { openAlbumPositionDialog(albumId) }
            }
        }
    }

    fun repositionAlbum(albumId: String, position: AlbumPosition) {
        val ctx = appContext ?: return
        viewModelScope.launch {
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            val albumPins = withContext(Dispatchers.IO) {
                dao.getPinsForAlbum(albumId).map { it.toPinItem() }
            }
            if (albumPins.isEmpty()) return@launch
            val date = resolveInsertionMillis(position, albumPins, _rawPins.value)
            withContext(Dispatchers.IO) { dao.updateAlbumDate(albumId, date) }
            val cur = _currentBoard.value
            if (cur != null) {
                val albums = withContext(Dispatchers.IO) { dao.getAlbumsForBoard(cur.id) }
                withContext(Dispatchers.Main) {
                    _customAlbums.value = albums
                    closeAlbumPositionDialog()
                    requestScrollToAlbum(albumId)
                }
            }
        }
    }

    fun beginAlbumTransfer(pinIds: Set<String>, mode: AlbumTransferMode) {
        if (pinIds.isEmpty()) return
        val board = _currentBoard.value ?: return
        _pendingAlbumTransfer.value = PendingAlbumTransfer(
            pinIds = pinIds, mode = mode, sourceBoardId = board.id,
            savedSelectionPinIds = _selectedPinIds.value,
            savedSelectionAlbumIds = _selectedAlbumIds.value
        )
    }

    fun cancelAlbumTransferAndRestore() {
        val transfer = _pendingAlbumTransfer.value ?: return
        _pendingAlbumTransfer.value = null
        _selectedPinIds.value = transfer.savedSelectionPinIds
        _selectedAlbumIds.value = transfer.savedSelectionAlbumIds
        _isSelectionMode.value = true
    }

    fun executeAlbumTransfer(targetAlbum: DateAlbum, targetBoardId: String) {
        val transfer = _pendingAlbumTransfer.value ?: return
        val ctx = appContext ?: return
        viewModelScope.launch {
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            val sourcePins = _rawPins.value.filter { transfer.pinIds.contains(it.id) }
            val existingUrls = withContext(Dispatchers.IO) { dao.getImageUrlsForBoard(targetBoardId).toSet() }
            val mode = transfer.mode
            val albumId = targetAlbum.id
            if (transfer.sourceBoardId == targetBoardId) {
                // Same board: just assign albumId
                val updatedPins = _rawPins.value.map { p ->
                    if (transfer.pinIds.contains(p.id)) p.copy(albumId = albumId) else p
                }
                withContext(Dispatchers.IO) {
                    dao.upsertPinsSafely(updatedPins.mapIndexed { i, p -> PinEntity.fromPinItem(p, targetBoardId, i) })
                }
                withContext(Dispatchers.Main) {
                    _rawPins.value = updatedPins
                    _currentBoard.value = _currentBoard.value?.copy(pins = updatedPins, pinCount = updatedPins.size)
                }
            } else {
                val toAdd = sourcePins.filter { !existingUrls.contains(it.imageUrl) }
                    .map { it.copy(albumId = albumId) }
                withContext(Dispatchers.IO) {
                    dao.insertPins(toAdd.mapIndexed { i, p -> PinEntity.fromPinItem(p, targetBoardId, i) })
                    if (mode == AlbumTransferMode.MOVE) {
                        dao.deletePinsFromBoard(transfer.sourceBoardId, transfer.pinIds.toList())
                    }
                }
                if (mode == AlbumTransferMode.MOVE) {
                    val remaining = _rawPins.value.filterNot { transfer.pinIds.contains(it.id) }
                    withContext(Dispatchers.Main) {
                        _rawPins.value = remaining
                        _currentBoard.value = _currentBoard.value?.copy(pins = remaining, pinCount = remaining.size)
                        updateDisplayedPins()
                    }
                }
            }
            _pendingAlbumTransfer.value = null
            withContext(Dispatchers.Main) {
                clearSelection()
                _snackbarMessage.value = "${if (mode == AlbumTransferMode.MOVE) "Moved" else "Copied"} ${sourcePins.size} image(s) to \"${targetAlbum.title}\""
            }
        }
    }

    override fun onCleared() {
        super.onCleared()
        _browserWorker?.destroy()
        scanBroadcastReceiver?.let {
            try {
                appContext?.unregisterReceiver(it)
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }
}
