package com.example.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.staggeredgrid.LazyVerticalStaggeredGrid
import androidx.compose.foundation.lazy.staggeredgrid.StaggeredGridCells
import androidx.compose.foundation.lazy.staggeredgrid.StaggeredGridItemSpan
import androidx.compose.foundation.lazy.staggeredgrid.items
import androidx.compose.foundation.lazy.staggeredgrid.itemsIndexed
import androidx.compose.foundation.lazy.staggeredgrid.rememberLazyStaggeredGridState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.CloudDownload
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.HourglassTop
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.Warning
import com.example.ui.dialogs.ReorderBoardsDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.nestedscroll.NestedScrollConnection
import androidx.compose.ui.input.nestedscroll.NestedScrollSource
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.model.PinItem
import com.example.ui.components.BoardHeader
import com.example.ui.components.BoardLinkDialog
import com.example.ui.components.DateSectionHeader
import com.example.model.PinterestBoard
import com.example.ui.components.FullscreenGalleryViewer
import com.example.ui.components.ModernGalleryFastScroller
import com.example.ui.components.BrowserWorkerTestingPanel
import com.example.ui.components.MultiSelectBottomBar
import com.example.ui.components.PinCard
import com.example.ui.components.PinterestTopBar
import com.example.ui.components.SettingsDialog
import com.example.ui.components.ErrorLogDialog
import com.example.ui.components.formatPinDateGroup
import com.example.ui.dialogs.CreateCustomBoardDialog
import com.example.ui.dialogs.EditCustomBoardDialog
import com.example.ui.dialogs.AddManualImagesDialog
import com.example.ui.dialogs.DeleteFromAllConfirmationDialog
import com.example.ui.dialogs.DeleteSelectionDialog
import com.example.ui.dialogs.CopyOrMoveImagesDialog
import com.example.ui.dialogs.BoardTransferMode
import androidx.activity.compose.BackHandler
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import com.example.model.DateAlbum
import com.example.ui.components.AlbumCard
import com.example.ui.components.AlbumPreviewOverlay
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary
import com.example.viewmodel.PinBoardViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

@Composable
fun PinBoardGalleryScreen(
    viewModel: PinBoardViewModel = viewModel(),
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }

    LaunchedEffect(Unit) {
        viewModel.setContext(context)
    }

    val currentBoard by viewModel.currentBoard.collectAsStateWithLifecycle()
    val displayedPins by viewModel.displayedPins.collectAsStateWithLifecycle()
    val totalAvailablePins by viewModel.totalAvailablePins.collectAsStateWithLifecycle()
    val rememberPerBoardSettings by viewModel.rememberPerBoardSettings.collectAsStateWithLifecycle()
    val hidePinTitlesAndAuthors by viewModel.hidePinTitlesAndAuthors.collectAsStateWithLifecycle()
    val columnCount by viewModel.columnCount.collectAsStateWithLifecycle()
    val sortOption by viewModel.sortOption.collectAsStateWithLifecycle()
    val separateByDate by viewModel.separateByDate.collectAsStateWithLifecycle()
    val groupByAlbum by viewModel.groupByAlbum.collectAsStateWithLifecycle()
    val activeAlbum by viewModel.activeAlbum.collectAsStateWithLifecycle()
    val portraitAlbumCards by viewModel.portraitAlbumCards.collectAsStateWithLifecycle()
    val disableArrowNavigation by viewModel.disableArrowNavigation.collectAsStateWithLifecycle()
    val customAlbums by viewModel.customAlbums.collectAsStateWithLifecycle()
    var previewAlbum by remember { mutableStateOf<DateAlbum?>(null) }
    val searchQuery by viewModel.searchQuery.collectAsStateWithLifecycle()
    val selectedPinIds by viewModel.selectedPinIds.collectAsStateWithLifecycle()
    val selectedAlbumIds by viewModel.selectedAlbumIds.collectAsStateWithLifecycle()
    val pendingAlbumTransfer by viewModel.pendingAlbumTransfer.collectAsStateWithLifecycle()
    val repositioningAlbumId by viewModel.repositioningAlbumId.collectAsStateWithLifecycle()
    val scrollToAlbumId by viewModel.scrollToAlbumId.collectAsStateWithLifecycle()
    val snackbarActionLabel by viewModel.snackbarActionLabel.collectAsStateWithLifecycle()
    val isSelectionMode by viewModel.isSelectionMode.collectAsStateWithLifecycle()
    val isLoading by viewModel.isLoading.collectAsStateWithLifecycle()
    val isSyncing by viewModel.isSyncing.collectAsStateWithLifecycle()
    val loadingProgress by viewModel.loadingProgress.collectAsStateWithLifecycle()
    val downloadProgress by viewModel.downloadProgress.collectAsStateWithLifecycle()
    val fullscreenPinIndex by viewModel.fullscreenPinIndex.collectAsStateWithLifecycle()
    val snackbarMessage by viewModel.snackbarMessage.collectAsStateWithLifecycle()
    val boardHistory by viewModel.boardHistory.collectAsStateWithLifecycle()

    val favoritePinKeys by viewModel.favoritePinKeys.collectAsStateWithLifecycle()
    val favoriteAlbumIds by viewModel.favoriteAlbumIds.collectAsStateWithLifecycle()
    val availableBoards by viewModel.availableBoards.collectAsStateWithLifecycle()
    val deletedPinsUndo by viewModel.deletedPinsUndo.collectAsStateWithLifecycle()
    val showDeleteFromAllConfirmation by viewModel.showDeleteFromAllConfirmation.collectAsStateWithLifecycle()
    val deletedBoardUndo by viewModel.deletedBoardUndo.collectAsStateWithLifecycle()

    val scannerState by viewModel.scannerState.collectAsStateWithLifecycle()
    val scannerDiagnostics by viewModel.scannerDiagnostics.collectAsStateWithLifecycle()
    val isBrowserTestingVisible by viewModel.isBrowserTestingVisible.collectAsStateWithLifecycle()
    val browserWorker = viewModel.browserWorker

    val lastCrashLog by viewModel.lastCrashLog.collectAsStateWithLifecycle()
    var isLinkDialogOpen by remember { mutableStateOf(false) }
    var isSettingsDialogOpen by remember { mutableStateOf(false) }
    var isCrashLogDialogOpen by remember { mutableStateOf(false) }
    var isCreateCustomBoardDialogOpen by remember { mutableStateOf(false) }
    var editingCustomBoard by remember { mutableStateOf<PinterestBoard?>(null) }
    var isAddManualImagesDialogOpen by remember { mutableStateOf(false) }
    var showCopyDialog by remember { mutableStateOf(false) }
    var showMoveDialog by remember { mutableStateOf(false) }
    var showDeleteSelectionDialog by remember { mutableStateOf(false) }
    var isReorderBoardsDialogOpen by remember { mutableStateOf(false) }
    val forceBoardTypeOrder by viewModel.forceBoardTypeOrder.collectAsStateWithLifecycle()

    val boardGridState = rememberLazyStaggeredGridState()
    val albumGridState = rememberLazyStaggeredGridState()
    val gridState = if (activeAlbum != null) albumGridState else boardGridState

    // Per-board/album scroll positions
    val boardScrollStates = remember { androidx.compose.runtime.mutableStateMapOf<String, Pair<Int, Int>>() }
    val albumScrollStates = remember { androidx.compose.runtime.mutableStateMapOf<String, Pair<Int, Int>>() }
    val boardsListScrollState = rememberSaveable(saver = androidx.compose.foundation.lazy.LazyListState.Saver) {
        androidx.compose.foundation.lazy.LazyListState(
            firstVisibleItemIndex = viewModel.boardsListScrollIndex,
            firstVisibleItemScrollOffset = viewModel.boardsListScrollOffset
        )
    }

    LaunchedEffect(boardsListScrollState.firstVisibleItemIndex, boardsListScrollState.firstVisibleItemScrollOffset) {
        viewModel.saveBoardsListScrollPosition(
            boardsListScrollState.firstVisibleItemIndex,
            boardsListScrollState.firstVisibleItemScrollOffset
        )
    }

    LaunchedEffect(activeAlbum) {
        if (viewModel.boardsListScrollIndex > 0 || viewModel.boardsListScrollOffset > 0) {
            boardsListScrollState.scrollToItem(
                viewModel.boardsListScrollIndex,
                viewModel.boardsListScrollOffset
            )
        }
    }

    // Handle back button navigation from opened Album
    BackHandler(enabled = activeAlbum != null) {
        viewModel.closeAlbum()
    }

    // Gradual loading: trigger next batch when scrolled near bottom
    LaunchedEffect(gridState.firstVisibleItemIndex, displayedPins.size, totalAvailablePins) {
        if (displayedPins.isNotEmpty() && displayedPins.size < totalAvailablePins) {
            if (gridState.firstVisibleItemIndex >= displayedPins.size - 16) {
                viewModel.loadNextBatch()
            }
        }
    }

    // Albums for custom albums & "Album (group by date)" layout
    val allPinsForAlbums = remember(displayedPins) {
        viewModel.getAllSortedPins().ifEmpty { displayedPins }
    }

    // Map custom album entities to DateAlbum items
    val customDateAlbums = remember(customAlbums, allPinsForAlbums, favoriteAlbumIds, favoritePinKeys) {
        customAlbums.map { entity ->
            val albumPins = allPinsForAlbums.filter { it.albumId == entity.id }
                .sortedByDescending { it.dateAddedMillis }
            DateAlbum(
                id = entity.id,
                title = entity.title,
                isMonthly = false,
                pins = albumPins,
                dateMillis = entity.dateAddedMillis,
                isFavorite = entity.isFavorite || favoriteAlbumIds.contains(entity.id),
                isCustomAlbum = true,
                parentAlbumId = entity.parentAlbumId
            )
        }
    }

    val topLevelCustomAlbums = remember(customDateAlbums) {
        customDateAlbums.filter { it.parentAlbumId == null }
    }

    val loosePins = remember(allPinsForAlbums) {
        allPinsForAlbums.filter { it.albumId == null }
    }

    // Merged gallery items (albums + loose pins) sorted by date
    data class GalleryItem(
        val album: DateAlbum? = null,
        val pin: PinItem? = null,
        val pinIndexInLoose: Int = -1,
        val dateAdded: Long
    )
    val galleryItems = remember(topLevelCustomAlbums, displayedPins) {
        val loosePinsForGallery = if (topLevelCustomAlbums.isNotEmpty()) displayedPins.filter { it.albumId == null } else displayedPins
        val items = mutableListOf<GalleryItem>()
        topLevelCustomAlbums.forEach { a -> items.add(GalleryItem(album = a, dateAdded = a.dateMillis)) }
        loosePinsForGallery.forEachIndexed { i, p -> items.add(GalleryItem(pin = p, pinIndexInLoose = i, dateAdded = p.dateAddedMillis)) }
        items.sortByDescending { it.dateAdded }
        items
    }
    val galleryItemsPlaceholder = galleryItems

    // Scroll to album when requested (after combine/creation)
    LaunchedEffect(scrollToAlbumId, galleryItemsPlaceholder) {
        val targetId = scrollToAlbumId ?: return@LaunchedEffect
        val idx = galleryItemsPlaceholder.indexOfFirst { it.album?.id == targetId }
        if (idx >= 0) {
            val hc = (if (browserWorker != null && isBrowserTestingVisible) 1 else 0) +
                     (if (currentBoard != null) 1 else 0) +
                     (if (isLoading) 1 else 0)
            boardGridState.animateScrollToItem(hc + idx)
            viewModel.consumeScrollRequest()
        }
    }

    // Date groups for "separate images by date" gallery layout
    val dateGroups = remember(displayedPins, separateByDate, topLevelCustomAlbums) {
        if (separateByDate) {
            val map = linkedMapOf<String, MutableList<PinItem>>()
            val pinsForDateGroups = if (topLevelCustomAlbums.isNotEmpty()) {
                displayedPins.filter { it.albumId == null }
            } else {
                displayedPins
            }
            for (pin in pinsForDateGroups) {
                val label = formatPinDateGroup(pin.dateAddedMillis)
                map.getOrPut(label) { mutableListOf() }.add(pin)
            }
            map.entries.map { it.key to it.value.toList() }
        } else {
            emptyList()
        }
    }

    val albums = remember(allPinsForAlbums, customDateAlbums, topLevelCustomAlbums, separateByDate, groupByAlbum, favoriteAlbumIds, favoritePinKeys) {
        if (!groupByAlbum) emptyList()
        else {
            val map = linkedMapOf<String, MutableList<PinItem>>()
            val labelMap = mutableMapOf<String, String>()
            val dateMap = mutableMapOf<String, Long>()

            if (separateByDate) {
                // Group by MONTH when both separateByDate and Album are checked
                val monthFormatter = SimpleDateFormat("yyyyMM", Locale.US)
                val monthLabelFormatter = SimpleDateFormat("MMMM yyyy", Locale.getDefault())
                for (pin in loosePins) {
                    val key = monthFormatter.format(Date(pin.dateAddedMillis))
                    if (!map.containsKey(key)) {
                        labelMap[key] = monthLabelFormatter.format(Date(pin.dateAddedMillis))
                        dateMap[key] = pin.dateAddedMillis
                    }
                    map.getOrPut(key) { mutableListOf() }.add(pin)
                }
                for (customAlb in topLevelCustomAlbums) {
                    val key = monthFormatter.format(Date(customAlb.dateMillis))
                    if (!map.containsKey(key)) {
                        labelMap[key] = monthLabelFormatter.format(Date(customAlb.dateMillis))
                        dateMap[key] = customAlb.dateMillis
                    }
                    if (!map.containsKey(key)) {
                        map[key] = mutableListOf()
                    }
                }
                map.entries.map { (key, pinsList) ->
                    val albumId = "month_$key"
                    val matchingCustomAlbums = topLevelCustomAlbums.filter { monthFormatter.format(Date(it.dateMillis)) == key }
                    DateAlbum(
                        id = albumId,
                        title = labelMap[key] ?: key,
                        isMonthly = true,
                        pins = pinsList.toList(),
                        dateMillis = dateMap[key] ?: 0L,
                        isFavorite = viewModel.isAlbumFavorite(albumId, pinsList, favoritePinKeys, favoriteAlbumIds),
                        subAlbums = matchingCustomAlbums
                    )
                }
            } else {
                // Group by DAY normally
                val dayFormatter = SimpleDateFormat("yyyyMMdd", Locale.US)
                val dayLabelFormatter = SimpleDateFormat("MMM d, yyyy", Locale.getDefault())
                for (pin in loosePins) {
                    val key = dayFormatter.format(Date(pin.dateAddedMillis))
                    if (!map.containsKey(key)) {
                        labelMap[key] = dayLabelFormatter.format(Date(pin.dateAddedMillis))
                        dateMap[key] = pin.dateAddedMillis
                    }
                    map.getOrPut(key) { mutableListOf() }.add(pin)
                }
                for (customAlb in topLevelCustomAlbums) {
                    val key = dayFormatter.format(Date(customAlb.dateMillis))
                    if (!map.containsKey(key)) {
                        labelMap[key] = dayLabelFormatter.format(Date(customAlb.dateMillis))
                        dateMap[key] = customAlb.dateMillis
                    }
                    if (!map.containsKey(key)) {
                        map[key] = mutableListOf()
                    }
                }
                map.entries.map { (key, pinsList) ->
                    val albumId = "day_$key"
                    val matchingCustomAlbums = topLevelCustomAlbums.filter { dayFormatter.format(Date(it.dateMillis)) == key }
                    DateAlbum(
                        id = albumId,
                        title = labelMap[key] ?: key,
                        isMonthly = false,
                        pins = pinsList.toList(),
                        dateMillis = dateMap[key] ?: 0L,
                        isFavorite = viewModel.isAlbumFavorite(albumId, pinsList, favoritePinKeys, favoriteAlbumIds),
                        subAlbums = matchingCustomAlbums
                    )
                }
            }
        }
    }

    val currentSubAlbums = remember(activeAlbum, customDateAlbums) {
        val active = activeAlbum
        if (active != null) {
            (customDateAlbums.filter { it.parentAlbumId == active.id } + active.subAlbums).distinctBy { it.id }
        } else {
            emptyList()
        }
    }

    // Auto-hide top menu bar on scroll down (Chrome browser mechanism)
    var topBarVisible by remember { mutableStateOf(true) }
    var topBarHeightPx by remember { mutableFloatStateOf(0f) }
    val density = LocalDensity.current
    val topBarHeightDp = with(density) { if (topBarHeightPx > 0f) topBarHeightPx.toDp() else 96.dp }

    val topBarOffsetProgress by animateFloatAsState(
        targetValue = if (topBarVisible && fullscreenPinIndex == null) 0f else -1f,
        animationSpec = spring(stiffness = Spring.StiffnessMediumLow),
        label = "top_bar_translation"
    )

    val nestedScrollConnection = remember {
        object : NestedScrollConnection {
            override fun onPreScroll(available: Offset, source: NestedScrollSource): Offset {
                val delta = available.y
                if (delta < -12f) {
                    topBarVisible = false
                } else if (delta > 12f) {
                    topBarVisible = true
                }
                return Offset.Zero
            }
        }
    }

    // Always restore top bar when at the very top of the board
    LaunchedEffect(gridState.firstVisibleItemIndex, gridState.firstVisibleItemScrollOffset) {
        if (gridState.firstVisibleItemIndex == 0 && gridState.firstVisibleItemScrollOffset < 15) {
            topBarVisible = true
        }
    }

    // Per-context (board or album) scroll save/restore
    val currentContext = activeAlbum?.id ?: currentBoard?.id ?: "none"
    LaunchedEffect(currentContext) {
        val key = currentContext
        val isAlbum = activeAlbum != null
        val targetState = if (isAlbum) albumGridState else boardGridState
        if (key != "none") {
            val saved = if (isAlbum) albumScrollStates[key] else boardScrollStates[key]
            if (saved != null) targetState.scrollToItem(saved.first, saved.second)
            else if (!isAlbum) targetState.scrollToItem(0)
        }
        try { kotlinx.coroutines.awaitCancellation() } finally {
            if (key != "none") {
                val idx = targetState.firstVisibleItemIndex
                val off = targetState.firstVisibleItemScrollOffset
                if (isAlbum) albumScrollStates[key] = idx to off
                else boardScrollStates[key] = idx to off
            }
        }
    }

    // Newest-pin change on the SAME board: scroll to top (not on board switch)
    var lastBoardId by remember { mutableStateOf<String?>(null) }
    var lastFirstPinId by remember { mutableStateOf<String?>(null) }
    val currentActiveAlbum by rememberUpdatedState(activeAlbum)
    LaunchedEffect(currentBoard?.id, currentBoard?.pins?.firstOrNull()?.id) {
        val bId = currentBoard?.id
        val pId = currentBoard?.pins?.firstOrNull()?.id
        val boardChanged = bId != lastBoardId
        val pinChanged = pId != null && pId != lastFirstPinId
        lastBoardId = bId
        lastFirstPinId = pId
        if (!boardChanged && pinChanged && currentActiveAlbum == null) {
            boardGridState.scrollToItem(0)
            topBarVisible = true
        }
    }

    // Regular backup check (User requirement 1)
    LaunchedEffect(Unit) {
        com.example.util.BackupManager.checkAndPerformScheduledBackup(context)
    }

    // Handle snackbar messages (with optional action)
    LaunchedEffect(snackbarMessage, snackbarActionLabel) {
        snackbarMessage?.let { msg ->
            val result = snackbarHostState.showSnackbar(
                message = msg,
                actionLabel = snackbarActionLabel,
                duration = if (snackbarActionLabel != null) androidx.compose.material3.SnackbarDuration.Long else androidx.compose.material3.SnackbarDuration.Short
            )
            if (result == androidx.compose.material3.SnackbarResult.ActionPerformed) {
                viewModel.executeSnackbarAction()
            }
            viewModel.dismissSnackbar()
        }
    }

    var fastScrollJob by remember { mutableStateOf<Job?>(null) }

    Scaffold(
        modifier = modifier
            .fillMaxSize()
            .nestedScroll(nestedScrollConnection),
        snackbarHost = { SnackbarHost(hostState = snackbarHostState) },
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        bottomBar = {
            if (fullscreenPinIndex == null && pendingAlbumTransfer == null) {
                MultiSelectBottomBar(
                    isVisible = isSelectionMode,
                    selectedPinCount = selectedPinIds.size,
                    selectedAlbumCount = selectedAlbumIds.size,
                    totalCount = displayedPins.size,
                    onSelectAll = { viewModel.selectAll() },
                    onDeselectAll = { viewModel.deselectAll() },
                    onClearSelection = { viewModel.clearSelection() },
                    onDownloadSelected = { viewModel.downloadSelected(context) },
                    onMoveToTop = { viewModel.moveSelectedPinsToTop() },
                    onDeleteSelected = {
                        if (selectedAlbumIds.isNotEmpty()) {
                            showDeleteSelectionDialog = true
                        } else if (selectedPinIds.isNotEmpty()) {
                            viewModel.deletePinsFromCurrentBoard(selectedPinIds)
                        }
                    },
                    onCopySelected = { showCopyDialog = true },
                    onMoveSelected = { showMoveDialog = true },
                    onCreateAlbum = { viewModel.combineSelectedPinsToNewAlbum() }
                )
            }
        }
    ) { _ ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.background)
        ) {
            // Pinterest-accurate Masonry Layout with Staggered Grid
            // Uses fixed top padding so top bar hide/show does not cause content to jump
            LazyVerticalStaggeredGrid(
                columns = StaggeredGridCells.Fixed(columnCount),
                state = gridState,
                contentPadding = PaddingValues(
                    top = topBarHeightDp,
                    start = 8.dp,
                    end = 8.dp,
                    bottom = 8.dp
                ),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalItemSpacing = 4.dp,
                modifier = Modifier
                    .fillMaxSize()
                    .testTag("pinterest_masonry_grid")
            ) {
                // Browser Worker Testing Panel (visible for testing purposes, Section 12-14)
                if (browserWorker != null && isBrowserTestingVisible) {
                    item(span = StaggeredGridItemSpan.FullLine, key = "browser_worker_testing_panel") {
                        BrowserWorkerTestingPanel(
                            scanner = browserWorker,
                            scannerState = scannerState,
                            diagnostics = scannerDiagnostics,
                            boardUrl = currentBoard?.boardUrl ?: scannerState.currentBoardUrl,
                            isCustomBoard = currentBoard?.isCustom == true,
                            onStartScan = {
                                val urlToScan = currentBoard?.boardUrl?.ifBlank { null }
                                    ?: scannerState.currentBoardUrl.ifBlank { null }
                                if (urlToScan != null) {
                                    viewModel.startBrowserScan(urlToScan, clearExistingPins = true)
                                } else {
                                    isLinkDialogOpen = true
                                }
                            },
                            onReorderPins = { viewModel.reorderPinsAfterScan() }
                        )
                    }
                }

                // Board Header as full-span item (always present so boards list keeps its position relative to screen)
                currentBoard?.let { board ->
                    item(span = StaggeredGridItemSpan.FullLine, key = "board_header") {
                        BoardHeader(
                            board = board,
                            boardHistory = boardHistory,
                            currentPinCount = if (activeAlbum != null) activeAlbum!!.pins.size else displayedPins.size,
                            boardsListScrollState = boardsListScrollState,
                            onHistoryItemSelected = { url -> viewModel.loadBoardFromUrl(url) },
                            onCustomBoardPillLongClick = { historyItem ->
                                viewModel.getBoardForHistoryItem(historyItem)?.let {
                                    editingCustomBoard = it
                                }
                            },
                            onOpenLinkDialog = { isLinkDialogOpen = true },
                            onOpenCreateCustomBoard = { isCreateCustomBoardDialogOpen = true },
                            onEditCurrentCustomBoard = {
                                if (board.isCustom) {
                                    editingCustomBoard = board
                                }
                            }
                        )
                    }
                }

                // Active Album Navigation Header (below the board header when viewing inside an opened album)
                activeAlbum?.let { album ->
                    item(span = StaggeredGridItemSpan.FullLine, key = "active_album_header") {
                        Surface(
                            shape = RoundedCornerShape(16.dp),
                            color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 4.dp, vertical = 6.dp)
                                .testTag("active_album_header")
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(horizontal = 8.dp, vertical = 8.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                IconButton(
                                    onClick = { viewModel.closeAlbum() },
                                    modifier = Modifier.testTag("album_back_button")
                                ) {
                                    Icon(
                                        imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                                        contentDescription = "Back to Albums",
                                        tint = PinterestRed
                                    )
                                }
                                Spacer(modifier = Modifier.width(4.dp))
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(
                                        text = album.title,
                                        style = MaterialTheme.typography.titleMedium.copy(
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 16.sp
                                        ),
                                        color = MaterialTheme.colorScheme.onSurface
                                    )
                                    Text(
                                        text = "${album.pins.size} image${if (album.pins.size > 1) "s" else ""} • Album",
                                        style = MaterialTheme.typography.bodySmall.copy(
                                            fontSize = 12.sp,
                                            color = PinterestTextSecondary
                                        )
                                    )
                                }
                                val isAlbumFav = viewModel.isAlbumFavorite(album.id, album.pins, favoritePinKeys, favoriteAlbumIds)
                                IconButton(
                                    onClick = {
                                        viewModel.toggleAlbumFavorites(album.id, album.title, album.pins)
                                    }
                                ) {
                                    Icon(
                                        imageVector = if (isAlbumFav) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                                        contentDescription = "Toggle Album Favorite",
                                        tint = if (isAlbumFav) PinterestRed else MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        }
                    }
                }

                // Empty State when board is empty by default
                if (currentBoard == null && displayedPins.isEmpty() && !isLoading) {
                    item(span = StaggeredGridItemSpan.FullLine) {
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 24.dp, vertical = 48.dp)
                                .testTag("empty_board_state"),
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.Center
                        ) {
                            Surface(
                                shape = RoundedCornerShape(24.dp),
                                color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f),
                                modifier = Modifier.size(72.dp)
                            ) {
                                Box(contentAlignment = Alignment.Center) {
                                    Icon(
                                        imageVector = Icons.Default.Add,
                                        contentDescription = null,
                                        tint = PinterestRed,
                                        modifier = Modifier.size(36.dp)
                                    )
                                }
                            }
                            Spacer(modifier = Modifier.height(16.dp))
                            Text(
                                text = "Your Board is Empty",
                                style = MaterialTheme.typography.titleMedium.copy(
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 18.sp
                                ),
                                color = MaterialTheme.colorScheme.onSurface
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                text = "Paste a Pinterest board URL to view its pins and download them.",
                                style = MaterialTheme.typography.bodyMedium.copy(
                                    fontSize = 13.sp,
                                    color = PinterestTextSecondary
                                ),
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                                modifier = Modifier.fillMaxWidth(0.85f)
                            )
                            Spacer(modifier = Modifier.height(20.dp))
                            Button(
                                onClick = { isLinkDialogOpen = true },
                                colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                                shape = RoundedCornerShape(24.dp),
                                modifier = Modifier.testTag("load_board_button")
                            ) {
                                Text(
                                    text = "Load Board Link",
                                    color = Color.White,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 14.sp
                                )
                            }

                            // Quick access to recent boards if available
                            if (boardHistory.isNotEmpty()) {
                                Spacer(modifier = Modifier.height(32.dp))
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    modifier = Modifier.padding(bottom = 12.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.History,
                                        contentDescription = null,
                                        tint = PinterestTextSecondary,
                                        modifier = Modifier.size(16.dp)
                                    )
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Text(
                                        text = "RECENT BOARD LINKS",
                                        style = MaterialTheme.typography.labelSmall.copy(
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 11.sp,
                                            letterSpacing = 0.5.sp,
                                            color = PinterestTextSecondary
                                        )
                                    )
                                }

                                Column(
                                    modifier = Modifier.fillMaxWidth(0.9f),
                                    verticalArrangement = Arrangement.spacedBy(8.dp)
                                ) {
                                    boardHistory.take(4).forEach { historyItem ->
                                        Surface(
                                            shape = RoundedCornerShape(12.dp),
                                            color = PinterestPillGray,
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .clickable { viewModel.loadBoardFromUrl(historyItem.url) }
                                                .testTag("recent_empty_board_${historyItem.url.hashCode()}")
                                        ) {
                                            Row(
                                                verticalAlignment = Alignment.CenterVertically,
                                                modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp)
                                            ) {
                                                Icon(
                                                    imageVector = Icons.Default.Link,
                                                    contentDescription = null,
                                                    tint = PinterestRed,
                                                    modifier = Modifier.size(16.dp)
                                                )
                                                Spacer(modifier = Modifier.width(10.dp))
                                                Column(modifier = Modifier.weight(1f)) {
                                                    Text(
                                                        text = historyItem.title,
                                                        fontSize = 13.sp,
                                                        fontWeight = FontWeight.Bold,
                                                        color = PinterestBlack,
                                                        maxLines = 1,
                                                        overflow = TextOverflow.Ellipsis
                                                    )
                                                    Text(
                                                        text = "${historyItem.ownerName} • ${historyItem.pinCount} pins",
                                                        fontSize = 11.sp,
                                                        color = PinterestTextSecondary
                                                    )
                                                }
                                                Text(
                                                    text = "Open",
                                                    fontSize = 12.sp,
                                                    fontWeight = FontWeight.Bold,
                                                    color = PinterestRed
                                                )
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // Loading State Indicator
                if (isLoading) {
                    item(span = StaggeredGridItemSpan.FullLine) {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 48.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                CircularProgressIndicator(
                                    color = PinterestRed,
                                    strokeWidth = 3.dp,
                                    modifier = Modifier.size(36.dp)
                                )
                                Spacer(modifier = Modifier.height(12.dp))
                                Text(
                                    text = "Loading pins from Pinterest...",
                                    style = MaterialTheme.typography.bodySmall.copy(
                                        color = PinterestTextSecondary,
                                        fontSize = 13.sp
                                    )
                                )
                            }
                        }
                    }
                }

                // Masonry Items: Albums, Opened Album Pins, Date-grouped Pins, or Standard Pins
                if (groupByAlbum && activeAlbum == null) {
                    // 1. Grouped by Album mode: display Album cards in masonry layout
                    items(
                        items = albums,
                        key = { album -> "${album.id}_${album.isFavorite}" }
                    ) { album ->
                        AlbumCard(
                            album = album,
                            columnCount = columnCount,
                            isFavorite = album.isFavorite,
                            isPortrait = portraitAlbumCards,
                            onClick = {
                                viewModel.openAlbum(album)
                            },
                            onLongClick = {
                                viewModel.toggleAlbumFavorites(album.id, album.title, album.pins)
                            },
                            onSwipePreview = {
                                previewAlbum = album
                            }
                        )
                    }
                } else if (activeAlbum != null) {
                    // 2. Opened Album mode: display sub-albums (if any) and collection of images for the selected album
                    if (currentSubAlbums.isNotEmpty()) {
                        items(
                            items = currentSubAlbums,
                            key = { alb -> "subalbum_${alb.id}_${alb.isFavorite}" }
                        ) { subAlb ->
                            AlbumCard(
                                album = subAlb,
                                columnCount = columnCount,
                                isFavorite = subAlb.isFavorite,
                                isPortrait = portraitAlbumCards,
                                onClick = {
                                    viewModel.openAlbum(subAlb)
                                },
                                onLongClick = {
                                    viewModel.toggleAlbumFavorites(subAlb.id, subAlb.title, subAlb.pins)
                                },
                                onSwipePreview = {
                                    previewAlbum = subAlb
                                }
                            )
                        }
                    }

                    val albumPins = activeAlbum!!.pins.sortedByDescending { it.dateAddedMillis }
                    itemsIndexed(
                        items = albumPins,
                        key = { index, pin -> "album_${activeAlbum!!.id}_${pin.id}_$index" }
                    ) { index, pin ->
                        val isSelected = selectedPinIds.contains(pin.id)
                        val isFav = favoritePinKeys.contains(pin.id) || favoritePinKeys.contains(pin.imageUrl)
                        PinCard(
                            pin = pin,
                            columnCount = columnCount,
                            isSelected = isSelected,
                            isSelectionMode = isSelectionMode,
                            isFavorite = isFav,
                            hideTitleAndAuthor = hidePinTitlesAndAuthors,
                            onClick = {
                                if (isSelectionMode) {
                                    viewModel.toggleSelection(pin.id)
                                } else {
                                    viewModel.openFullscreen(index)
                                }
                            },
                            onLongClick = {
                                if (isSelectionMode) {
                                    viewModel.toggleSelection(pin.id)
                                } else {
                                    viewModel.toggleFavorite(pin)
                                }
                            }
                        )
                    }
                } else if (separateByDate && dateGroups.isNotEmpty()) {
                    // Show custom albums on the board as AlbumCard
                    if (topLevelCustomAlbums.isNotEmpty()) {
                        items(
                            items = topLevelCustomAlbums,
                            key = { album -> "board_custom_album_${album.id}_${album.isFavorite}" }
                        ) { album ->
                            AlbumCard(
                                album = album,
                                columnCount = columnCount,
                                isFavorite = album.isFavorite,
                                isPortrait = portraitAlbumCards,
                                onClick = {
                                    viewModel.openAlbum(album)
                                },
                                onLongClick = {
                                    viewModel.toggleAlbumFavorites(album.id, album.title, album.pins)
                                },
                                onSwipePreview = {
                                    previewAlbum = album
                                }
                            )
                        }
                    }

                    // 3. Separate images by date headers
                    dateGroups.forEach { (dateLabel, groupPins) ->
                        item(
                            key = "date_header_$dateLabel",
                            span = StaggeredGridItemSpan.FullLine
                        ) {
                            DateSectionHeader(
                                dateLabel = dateLabel,
                                count = groupPins.size
                            )
                        }

                        itemsIndexed(
                            items = groupPins,
                            key = { grpIdx, pin -> "date_${dateLabel}_${pin.id}_$grpIdx" }
                        ) { _, pin ->
                            val index = displayedPins.indexOf(pin)
                            val isSelected = selectedPinIds.contains(pin.id)
                            val isFav = favoritePinKeys.contains(pin.id) || favoritePinKeys.contains(pin.imageUrl)
                            PinCard(
                                pin = pin,
                                columnCount = columnCount,
                                isSelected = isSelected,
                                isSelectionMode = isSelectionMode,
                                isFavorite = isFav,
                                hideTitleAndAuthor = hidePinTitlesAndAuthors,
                                onClick = {
                                    if (isSelectionMode) {
                                        viewModel.toggleSelection(pin.id)
                                    } else {
                                        viewModel.openFullscreen(if (index >= 0) index else 0)
                                    }
                                },
                                onLongClick = {
                                    if (isSelectionMode) {
                                        viewModel.toggleSelection(pin.id)
                                    } else {
                                        viewModel.toggleFavorite(pin)
                                    }
                                }
                            )
                        }
                    }
                } else {
                    // 4. Standard Masonry — merged albums + pins, sorted by date
                    items(
                        items = galleryItems,
                        key = { item ->
                            item.album?.let { "album_${it.id}" } ?: "pin_${item.pin?.id}"
                        }
                    ) { item ->
                        if (item.album != null) {
                            val album = item.album
                            val isSelectedAlbum = selectedAlbumIds.contains(album.id)
                            AlbumCard(
                                album = album,
                                columnCount = columnCount,
                                isFavorite = album.isFavorite,
                                isPortrait = portraitAlbumCards,
                                isSelected = isSelectedAlbum,
                                isSelectionMode = isSelectionMode,
                                onClick = {
                                    when {
                                        pendingAlbumTransfer != null -> viewModel.executeAlbumTransfer(album, currentBoard?.id ?: "")
                                        else -> viewModel.openAlbum(album)
                                    }
                                },
                                onLongClick = {
                                    viewModel.toggleAlbumFavorites(album.id, album.title, album.pins)
                                },
                                onSelectToggle = {
                                    viewModel.toggleAlbumSelection(album.id)
                                },
                                onSwipePreview = {
                                    previewAlbum = album
                                }
                            )
                        } else if (item.pin != null) {
                            val pin = item.pin
                            val isSelected = selectedPinIds.contains(pin.id)
                            val isFav = favoritePinKeys.contains(pin.id) || favoritePinKeys.contains(pin.imageUrl)
                            PinCard(
                                pin = pin,
                                columnCount = columnCount,
                                isSelected = isSelected,
                                isSelectionMode = isSelectionMode,
                                isFavorite = isFav,
                                hideTitleAndAuthor = hidePinTitlesAndAuthors,
                                onClick = {
                                    if (isSelectionMode) {
                                        viewModel.toggleSelection(pin.id)
                                    } else {
                                        viewModel.openFullscreen(item.pinIndexInLoose)
                                    }
                                },
                                onLongClick = {
                                    if (isSelectionMode) {
                                        viewModel.toggleSelection(pin.id)
                                    } else {
                                        viewModel.toggleFavorite(pin)
                                    }
                                }
                            )
                        }
                    }
                }

                // Gradual loading indicator for large boards (hidden in album mode, including inside album)
                if (!groupByAlbum && activeAlbum == null && displayedPins.isNotEmpty() && displayedPins.size < totalAvailablePins) {
                    item(span = StaggeredGridItemSpan.FullLine) {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 16.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.Center
                            ) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(16.dp),
                                    color = PinterestRed,
                                    strokeWidth = 2.dp
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    text = "Showing ${displayedPins.size} of $totalAvailablePins pins",
                                    fontSize = 12.sp,
                                    color = PinterestTextSecondary,
                                    fontWeight = FontWeight.Medium
                                )
                            }
                        }
                    }
                }

                // Extra padding at bottom for multi-select bar
                item(span = StaggeredGridItemSpan.FullLine) {
                    Spacer(modifier = Modifier.height(72.dp))
                }
            }

            // Seamless natural Chrome-like Auto-Hide Top Bar
            if (fullscreenPinIndex == null) {
                PinterestTopBar(
                    currentColumns = columnCount,
                    onColumnsChanged = { viewModel.setColumnCount(it) },
                    currentSort = sortOption,
                    onSortSelected = { viewModel.setSortOption(it) },
                    separateByDate = separateByDate,
                    onToggleSeparateByDate = { viewModel.toggleSeparateByDate() },
                    groupByAlbum = groupByAlbum,
                    onToggleGroupByAlbum = { viewModel.toggleGroupByAlbum() },
                    searchQuery = searchQuery,
                    onSearchQueryChanged = { viewModel.setSearchQuery(it) },
                    isSelectionMode = isSelectionMode,
                    onToggleSelectionMode = {
                        if (isSelectionMode) viewModel.clearSelection()
                        else viewModel.enterSelectionMode()
                    },
                    onOpenLinkDialog = { isLinkDialogOpen = true },
                    onOpenSettings = { isSettingsDialogOpen = true },
                    onOpenAddImages = { isAddManualImagesDialogOpen = true },
                    isSyncing = isSyncing,
                    onSyncClicked = { viewModel.syncCurrentBoard() },
                    isScanning = scannerState.isScanning,
                    currentBoard = currentBoard,
                    hasCrashLog = lastCrashLog != null,
                    onOpenCrashLogs = { isCrashLogDialogOpen = true },
                    modifier = Modifier
                        .align(Alignment.TopCenter)
                        .onGloballyPositioned { coords ->
                            if (coords.size.height > 0) {
                                topBarHeightPx = coords.size.height.toFloat()
                            }
                        }
                        .graphicsLayer {
                            translationY = topBarOffsetProgress * (size.height.takeIf { it > 0 } ?: 200f)
                            alpha = (1f + topBarOffsetProgress * 0.8f).coerceIn(0f, 1f)
                        }
                )
            }

            // Modern Gallery Interactive Fast Scroller on the right edge
            val currentGridPins = if (activeAlbum != null) activeAlbum!!.pins else displayedPins
            val totalScrollerItems = if (groupByAlbum && activeAlbum == null) {
                albums.size
            } else if (activeAlbum != null) {
                activeAlbum!!.pins.size
            } else {
                totalAvailablePins.coerceAtLeast(displayedPins.size)
            }
            ModernGalleryFastScroller(
                totalItems = totalScrollerItems,
                currentFirstVisibleIndex = if (currentBoard != null && activeAlbum == null) {
                    (gridState.firstVisibleItemIndex - 1).coerceAtLeast(0)
                } else {
                    gridState.firstVisibleItemIndex
                },
                currentScrollOffset = gridState.firstVisibleItemScrollOffset,
                canScrollForward = gridState.canScrollForward,
                canScrollBackward = gridState.canScrollBackward,
                displayedPins = currentGridPins,
                isScrolling = gridState.isScrollInProgress,
                onFastScrollTo = { targetIndex ->
                    viewModel.ensureVisibleUpToIndex(targetIndex)
                    fastScrollJob?.cancel()
                    fastScrollJob = scope.launch {
                        val maxDisplayIndex = (viewModel.displayedPins.value.size - 1).coerceAtLeast(0)
                        val safeTarget = targetIndex.coerceIn(0, maxDisplayIndex)
                        val targetGridIndex = if (currentBoard != null) {
                            if (safeTarget == 0) 0 else (safeTarget + 1).coerceAtMost(viewModel.displayedPins.value.size)
                        } else {
                            safeTarget
                        }
                        gridState.scrollToItem(targetGridIndex)
                    }
                },
                modifier = Modifier.align(Alignment.CenterEnd)
            )

            // Download Progress Floating Overlay
            downloadProgress?.let { progress ->
                if (!progress.isComplete) {
                    Surface(
                        modifier = Modifier
                            .align(Alignment.TopCenter)
                            .padding(top = 16.dp),
                        shape = RoundedCornerShape(20.dp),
                        color = PinterestBlack.copy(alpha = 0.9f),
                        shadowElevation = 8.dp
                    ) {
                        Column(
                            modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(
                                    imageVector = Icons.Default.CloudDownload,
                                    contentDescription = null,
                                    tint = PinterestRed,
                                    modifier = Modifier.size(16.dp)
                                )
                                Spacer(modifier = Modifier.width(6.dp))
                                Text(
                                    text = "Downloading ${progress.current} of ${progress.total}",
                                    fontWeight = FontWeight.Bold,
                                    color = Color.White,
                                    fontSize = 12.sp
                                )
                            }
                            Spacer(modifier = Modifier.height(6.dp))
                            LinearProgressIndicator(
                                progress = { progress.current.toFloat() / progress.total.coerceAtLeast(1) },
                                modifier = Modifier
                                    .width(160.dp)
                                    .height(4.dp),
                                color = PinterestRed,
                                trackColor = Color.DarkGray
                            )
                        }
                    }
                }
            }

            // Board Loading Indicator Banner (hidden in album mode, including inside album)
            if (!groupByAlbum && activeAlbum == null && isLoading && downloadProgress == null) {
                Surface(
                    shape = RoundedCornerShape(24.dp),
                    color = PinterestBlack.copy(alpha = 0.88f),
                    shadowElevation = 8.dp,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(bottom = 80.dp)
                        .testTag("board_loading_banner")
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.padding(horizontal = 18.dp, vertical = 10.dp)
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(16.dp),
                            color = PinterestRed,
                            strokeWidth = 2.dp
                        )
                        Spacer(modifier = Modifier.width(10.dp))
                        val progress = loadingProgress
                        val statusText = if (progress != null && progress.second > 0) {
                            "Loaded ${progress.first} of ${progress.second} images..."
                        } else if (progress != null && progress.first > 0) {
                            "Loaded ${progress.first} images..."
                        } else {
                            "Fetching board images..."
                        }
                        Text(
                            text = statusText,
                            fontWeight = FontWeight.SemiBold,
                            color = Color.White,
                            fontSize = 13.sp
                        )
                    }
                }
            }

            // Persistent Error / Crash Diagnostics Alert Banner (if error was recorded)
            if (lastCrashLog != null) {
                Surface(
                    shape = RoundedCornerShape(20.dp),
                    color = PinterestRed,
                    shadowElevation = 8.dp,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(bottom = if (isLoading) 130.dp else 74.dp, start = 16.dp, end = 16.dp)
                        .clickable { isCrashLogDialogOpen = true }
                        .testTag("crash_log_floating_banner")
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Warning,
                            contentDescription = "Crash report",
                            tint = Color.White,
                            modifier = Modifier.size(18.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "Error captured. Tap to view diagnostics",
                            color = Color.White,
                            fontWeight = FontWeight.Bold,
                            fontSize = 12.sp,
                            modifier = Modifier.weight(1f, fill = false)
                        )
                        Spacer(modifier = Modifier.width(12.dp))
                        Surface(
                            shape = CircleShape,
                            color = Color.White.copy(alpha = 0.2f),
                            modifier = Modifier.clickable { viewModel.clearCrashLog() }
                        ) {
                            Text(
                                text = "Dismiss",
                                color = Color.White,
                                fontWeight = FontWeight.Bold,
                                fontSize = 11.sp,
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                            )
                        }
                    }
                }
            }

            // Fullscreen Gallery Viewer Modal Overlay
            fullscreenPinIndex?.let { index ->
                val fullScreenPins = activeAlbum?.pins ?: (if (topLevelCustomAlbums.isNotEmpty()) viewModel.getAllSortedPins().filter { it.albumId == null } else viewModel.getAllSortedPins()).ifEmpty { displayedPins }
                FullscreenGalleryViewer(
                    pins = fullScreenPins,
                    initialIndex = index.coerceIn(0, (fullScreenPins.size - 1).coerceAtLeast(0)),
                    disableArrowNavigation = disableArrowNavigation,
                    isFavorite = { pin -> favoritePinKeys.contains(pin.id) || favoritePinKeys.contains(pin.imageUrl) },
                    onToggleFavorite = { pin -> viewModel.toggleFavorite(pin) },
                    onMoveToTop = { pin -> viewModel.movePinToTop(pin) },
                    onDeleteSingle = { pin -> viewModel.deleteSinglePin(pin) },
                    onClose = { viewModel.closeFullscreen() },
                    onDownloadSingle = { pin -> viewModel.downloadSingle(context, pin) }
                )
            }

            // Album Quick Preview Overlay (screen-fitting ~18 images preview on swipe)
            previewAlbum?.let { album ->
                AlbumPreviewOverlay(
                    album = album,
                    onDismiss = { previewAlbum = null }
                )
            }

            // Floating Undo & Delete From All Banner for deleted pins (Requirement 4)
            deletedPinsUndo?.let { undoState ->
                LaunchedEffect(undoState) {
                    kotlinx.coroutines.delay(6000L)
                    viewModel.dismissUndoDeletePins()
                }

                Surface(
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(bottom = if (isSelectionMode) 80.dp else 24.dp, start = 12.dp, end = 12.dp)
                        .fillMaxWidth()
                        .testTag("delete_undo_banner"),
                    shape = RoundedCornerShape(16.dp),
                    color = PinterestBlack.copy(alpha = 0.95f),
                    shadowElevation = 8.dp
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 14.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = run {
                                val pinCount = undoState.pins.size
                                val albumCount = undoState.albums.size
                                when {
                                    undoState.mode == com.example.viewmodel.DeleteSelectionMode.DISSOLVE && albumCount > 0 && pinCount > 0 ->
                                        "Deleted $pinCount image${if (pinCount > 1) "s" else ""}, dissolved $albumCount album${if (albumCount > 1) "s" else ""}"
                                    undoState.mode == com.example.viewmodel.DeleteSelectionMode.DISSOLVE && albumCount > 0 ->
                                        "Dissolved $albumCount album${if (albumCount > 1) "s" else ""}"
                                    undoState.mode == com.example.viewmodel.DeleteSelectionMode.DELETE_WITH_CONTENTS && albumCount > 0 ->
                                        "Deleted $pinCount image${if (pinCount > 1) "s" else ""} + $albumCount album${if (albumCount > 1) "s" else ""}"
                                    else ->
                                        "Deleted $pinCount image${if (pinCount > 1) "s" else ""}"
                                }
                            },
                            color = Color.White,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Medium,
                            modifier = Modifier.weight(1f)
                        )

                        Row(verticalAlignment = Alignment.CenterVertically) {
                            TextButton(
                                onClick = { viewModel.undoDeletePins() },
                                modifier = Modifier.testTag("undo_delete_pins_btn")
                            ) {
                                Text("Undo", color = Color(0xFF64B5F6), fontWeight = FontWeight.Bold, fontSize = 13.sp)
                            }

                            Spacer(modifier = Modifier.width(4.dp))

                            TextButton(
                                onClick = { viewModel.requestDeleteFromAllBoards() },
                                modifier = Modifier.testTag("delete_from_all_boards_btn")
                            ) {
                                Text("Delete from All", color = PinterestRed, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                            }

                            Spacer(modifier = Modifier.width(4.dp))

                            androidx.compose.material3.IconButton(
                                onClick = { viewModel.dismissUndoDeletePins() },
                                modifier = Modifier
                                    .size(28.dp)
                                    .testTag("exit_undo_delete_btn")
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Close,
                                    contentDescription = "Dismiss",
                                    tint = Color.White.copy(alpha = 0.7f),
                                    modifier = Modifier.size(16.dp)
                                )
                            }
                        }
                    }
                }
            }

            // Floating Undo Banner for deleted custom board (Requirement 3)
            deletedBoardUndo?.let { undoState ->
                Surface(
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(bottom = 24.dp, start = 12.dp, end = 12.dp)
                        .fillMaxWidth()
                        .testTag("delete_board_undo_banner"),
                    shape = RoundedCornerShape(16.dp),
                    color = PinterestBlack.copy(alpha = 0.95f),
                    shadowElevation = 8.dp
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 14.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "Deleted board \"${undoState.board.title}\"",
                            color = Color.White,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Medium,
                            modifier = Modifier.weight(1f)
                        )

                        TextButton(
                            onClick = { viewModel.undoDeleteCustomBoard() },
                            modifier = Modifier.testTag("undo_delete_board_btn")
                        ) {
                            Text("Undo", color = Color(0xFF64B5F6), fontWeight = FontWeight.Bold, fontSize = 13.sp)
                        }
                    }
                }
            }
        }
    }

    // Pending album transfer banner (wrapped in full-screen Box for .align)
    androidx.compose.foundation.layout.Box(modifier = Modifier.fillMaxSize()) {
        pendingAlbumTransfer?.let { transfer ->
        androidx.compose.material3.Surface(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 16.dp, start = 12.dp, end = 12.dp)
                .fillMaxWidth()
                .testTag("pending_album_transfer_banner"),
            shape = RoundedCornerShape(16.dp),
            color = PinterestBlack,
            shadowElevation = 8.dp
        ) {
            androidx.compose.foundation.layout.Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                androidx.compose.material3.IconButton(
                    onClick = { viewModel.cancelAlbumTransferAndRestore() },
                    modifier = Modifier.testTag("album_transfer_back_btn")
                ) {
                    androidx.compose.material3.Icon(
                        imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                        contentDescription = "Back to selection",
                        tint = Color.White
                    )
                }
                Text(
                    text = "Tap an album to ${if (transfer.mode == com.example.viewmodel.AlbumTransferMode.MOVE) "move" else "copy"} ${transfer.pinIds.size} image${if (transfer.pinIds.size > 1) "s" else ""}",
                    color = Color.White,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.weight(1f)
                )
                androidx.compose.material3.TextButton(
                    onClick = { viewModel.executeAlbumTransferToCurrentBoard() },
                    modifier = Modifier.testTag("album_transfer_here_btn")
                ) {
                    Text(
                        text = if (transfer.mode == com.example.viewmodel.AlbumTransferMode.MOVE) "Move here" else "Copy here",
                        color = Color(0xFF64B5F6),
                        fontWeight = FontWeight.Bold,
                        fontSize = 12.sp
                    )
                }
                androidx.compose.material3.TextButton(
                    onClick = { viewModel.executeAlbumTransferToCurrentBoard() },
                    modifier = Modifier.testTag("album_transfer_here_btn")
                ) {
                    Text(
                        text = if (transfer.mode == com.example.viewmodel.AlbumTransferMode.MOVE) "Move here" else "Copy here",
                        color = Color(0xFF64B5F6),
                        fontWeight = FontWeight.Bold,
                        fontSize = 12.sp
                    )
                }
            }
        }
        }
    }

    // Album position dialog
    repositioningAlbumId?.let { albumId ->
        val positions = listOf(
            com.example.viewmodel.AlbumPosition.TOP_OF_BOARD to "Top of board",
            com.example.viewmodel.AlbumPosition.TOP_SELECTED to "Top selected image",
            com.example.viewmodel.AlbumPosition.MIDDLE_SELECTED to "Middle selected image",
            com.example.viewmodel.AlbumPosition.BOTTOM_SELECTED to "Bottom selected image"
        )
        var picked by remember { mutableStateOf(com.example.viewmodel.AlbumPosition.TOP_SELECTED) }
        androidx.compose.material3.AlertDialog(
            onDismissRequest = { viewModel.closeAlbumPositionDialog() },
            title = { Text("Album position", fontWeight = FontWeight.Bold, fontSize = 16.sp) },
            text = {
                Column {
                    positions.forEach { (pos, label) ->
                        androidx.compose.foundation.layout.Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { picked = pos }
                                .padding(vertical = 6.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            androidx.compose.material3.RadioButton(
                                selected = picked == pos,
                                onClick = { picked = pos }
                            )
                            Text(label, fontSize = 13.sp)
                        }
                    }
                }
            },
            confirmButton = {
                androidx.compose.material3.Button(
                    onClick = {
                        viewModel.repositionAlbum(albumId, picked)
                        viewModel.closeAlbumPositionDialog()
                    },
                    colors = androidx.compose.material3.ButtonDefaults.buttonColors(containerColor = PinterestRed)
                ) { Text("Apply", color = Color.White) }
            },
            dismissButton = {
                androidx.compose.material3.TextButton(onClick = { viewModel.closeAlbumPositionDialog() }) {
                    Text("Cancel")
                }
            }
        )
    }

    // Board Link Dialog with History of Boards Links
    BoardLinkDialog(
        isOpen = isLinkDialogOpen,
        boardHistory = boardHistory,
        onDismiss = { isLinkDialogOpen = false },
        onLoadBoard = { url ->
            viewModel.loadBoardFromUrl(url)
        },
        onRemoveHistoryItem = { url -> viewModel.removeHistoryItem(url) },
        onClearHistory = { viewModel.clearHistory() }
    )

    // Image Cache & Layout Settings Dialog
    SettingsDialog(
        isOpen = isSettingsDialogOpen,
        rememberPerBoardSettings = rememberPerBoardSettings,
        onToggleRememberPerBoard = { viewModel.setRememberPerBoardSettings(it) },
        hidePinTitlesAndAuthors = hidePinTitlesAndAuthors,
        onToggleHidePinTitlesAndAuthors = { viewModel.setHidePinTitlesAndAuthors(it) },
        portraitAlbumCards = portraitAlbumCards,
        onTogglePortraitAlbumCards = { viewModel.setPortraitAlbumCards(it) },
        disableArrowNavigation = disableArrowNavigation,
        onToggleDisableArrowNavigation = { viewModel.setDisableArrowNavigation(it) },
        isBrowserTestingVisible = isBrowserTestingVisible,
        onToggleBrowserTesting = { viewModel.setBrowserTestingVisible(it) },
        onOpenCrashLogs = { isCrashLogDialogOpen = true },
        onRestoreBackup = { file, callback -> viewModel.restoreFromBackup(file, callback) },
        onDismiss = { isSettingsDialogOpen = false },
        onCacheSizeSaved = { newMb ->
            scope.launch {
                snackbarHostState.showSnackbar("Max image cache set to $newMb MB")
            }
        }
    )

    // Crash & Error Diagnostics Dialog
    ErrorLogDialog(
        isOpen = isCrashLogDialogOpen,
        errorLog = lastCrashLog,
        onDismiss = { isCrashLogDialogOpen = false },
        onClearLog = {
            viewModel.clearCrashLog()
            isCrashLogDialogOpen = false
        }
    )

    // Create Custom Board Dialog
    CreateCustomBoardDialog(
        isOpen = isCreateCustomBoardDialogOpen,
        onDismiss = { isCreateCustomBoardDialogOpen = false },
        onCreateBoard = { name, domains, links, isDef ->
            viewModel.createCustomBoard(name, domains, links, isDef)
        }
    )

    // Edit Custom Board Dialog
    EditCustomBoardDialog(
        isOpen = editingCustomBoard != null,
        board = editingCustomBoard,
        onDismiss = { editingCustomBoard = null },
        onOpenReorderBoards = {
            editingCustomBoard = null
            isReorderBoardsDialogOpen = true
        },
        onSaveBoard = { boardId, newName, domains, isDef ->
            viewModel.editCustomBoard(boardId, newName, domains, isDef)
        },
        onDeleteBoard = { b ->
            viewModel.deleteCustomBoard(b)
        }
    )

    // Reorder Boards Dialog (Requirement 6)
    ReorderBoardsDialog(
        isOpen = isReorderBoardsDialogOpen,
        boards = boardHistory,
        forceBoardTypeOrder = forceBoardTypeOrder,
        onDismiss = { isReorderBoardsDialogOpen = false },
        onSaveReorderedBoards = { reorderedList, forceTypeOrder ->
            viewModel.saveReorderedBoards(reorderedList, forceTypeOrder)
            isReorderBoardsDialogOpen = false
        }
    )

    // Add Manual Images Dialog
    AddManualImagesDialog(
        isOpen = isAddManualImagesDialogOpen,
        availableBoards = availableBoards,
        currentBoardId = currentBoard?.id,
        currentAlbumTitle = activeAlbum?.title,
        onDismiss = { isAddManualImagesDialogOpen = false },
        onAddImages = { text, targetBoards, extractMultiple ->
            viewModel.addManualImages(text, targetBoards, extractMultiple)
        }
    )

    // Delete From All Confirmation Dialog
    DeleteFromAllConfirmationDialog(
        isOpen = showDeleteFromAllConfirmation != null,
        itemCount = showDeleteFromAllConfirmation?.pins?.size ?: 0,
        onDismiss = { viewModel.dismissDeleteFromAllConfirmation() },
        onConfirmDeleteFromAll = { viewModel.confirmDeleteFromAllBoards() }
    )

    // Copy Images Dialog
    CopyOrMoveImagesDialog(
        isOpen = showCopyDialog,
        mode = BoardTransferMode.COPY,
        selectedPins = displayedPins.filter { selectedPinIds.contains(it.id) },
        selectedCount = selectedPinIds.size + selectedAlbumIds.size,
        availableBoards = availableBoards,
        currentBoardId = currentBoard?.id,
        onDismiss = { showCopyDialog = false },
        onTransferToAlbum = {
            showCopyDialog = false
            viewModel.beginAlbumTransfer(selectedPinIds, com.example.viewmodel.AlbumTransferMode.COPY)
        },
        onConfirm = { targetBoardIds ->
            viewModel.copySelectedPinsToBoards(targetBoardIds, selectedPinIds)
        }
    )

    // Move Images Dialog
    CopyOrMoveImagesDialog(
        isOpen = showMoveDialog,
        mode = BoardTransferMode.MOVE,
        selectedPins = displayedPins.filter { selectedPinIds.contains(it.id) },
        selectedCount = selectedPinIds.size + selectedAlbumIds.size,
        availableBoards = availableBoards,
        currentBoardId = currentBoard?.id,
        onDismiss = { showMoveDialog = false },
        onTransferToAlbum = {
            showMoveDialog = false
            viewModel.beginAlbumTransfer(selectedPinIds, com.example.viewmodel.AlbumTransferMode.MOVE)
        },
        onConfirm = { targetBoardIds ->
            viewModel.moveSelectedPinsToBoards(targetBoardIds, selectedPinIds)
        }
    )

    // Delete selection (albums involved) — ask how
    DeleteSelectionDialog(
        isOpen = showDeleteSelectionDialog,
        pinCount = selectedPinIds.size,
        albumCount = selectedAlbumIds.size,
        onDismiss = { showDeleteSelectionDialog = false },
        onDissolve = {
            viewModel.deleteSelectionAndAlbums(selectedPinIds, selectedAlbumIds, com.example.viewmodel.DeleteSelectionMode.DISSOLVE)
            showDeleteSelectionDialog = false
        },
        onDeleteAll = {
            viewModel.deleteSelectionAndAlbums(selectedPinIds, selectedAlbumIds, com.example.viewmodel.DeleteSelectionMode.DELETE_WITH_CONTENTS)
            showDeleteSelectionDialog = false
        }
    )
}
