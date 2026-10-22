#!/usr/bin/env python3
"""
PinBoard Gallery
----------------
CHANGE: Album ordering, album selection/transfer, combine-to-album,
        share auto-default, manual-add collapse, per-board scroll,
        legacy album migration.

FULL PIPELINE (runs after patches):
  1. all code patches
  2. release.keystore + gradle + CI workflow
  3. commit + push
  4. CI trigger -> download -> PinBoard-v{ver}-{code}.apk -> install
"""

import os, re, sys, json, time, shutil, datetime, subprocess, urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
REPO_NAME    = "PinBoard"
APP_NAME     = "PinBoard"
ARTIFACT     = "app-release"
PACKAGE_ID   = "com.aistudio.pinboardgallery.kzwvpt"

KEYSTORE_FILE     = "release.keystore"
KEYSTORE_ALIAS    = "upload"
KEYSTORE_PASS     = "PinBoardRelease2025"
KEYSTORE_DNAME    = "CN=PinBoard Gallery, OU=PinBoard, O=PinBoard, L=Unknown, ST=Unknown, C=US"
KEYSTORE_VALIDITY = "10000"

WORKFLOW_YAML = """\
name: Build APK

on:
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    env:
      JAVA_TOOL_OPTIONS: "-Djava.awt.headless=true"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - uses: android-actions/setup-android@v3
        with:
          packages: ''
      - run: yes | sdkmanager --licenses >/dev/null 2>&1 || true
      - run: sdkmanager --install "platforms;android-36" "build-tools;36.0.0" >/dev/null 2>&1 || true
      - name: Verify keystore
        run: |
          [ -f release.keystore ] || { echo "release.keystore missing"; exit 1; }
          keytool -list -keystore release.keystore -storepass PinBoardRelease2025 2>/dev/null | grep -q upload || { echo "alias 'upload' not found"; exit 1; }
      - uses: gradle/actions/setup-gradle@v3
        with:
          gradle-version: wrapper
      - run: chmod +x ./gradlew
      - run: ./gradlew :app:assembleRelease --stacktrace --no-daemon
      - name: Verify signature
        run: |
          APK=$(find app/build/outputs/apk/release -name "*.apk" | head -1)
          [ -n "$APK" ] || { echo "no APK"; exit 1; }
          BT=$(ls -d $ANDROID_HOME/build-tools/* | sort -V | tail -1)
          "$BT/apksigner" verify --verbose --print-certs "$APK"
      - uses: actions/upload-artifact@v4
        with:
          name: app-release
          path: app/build/outputs/apk/release/*.apk
          if-no-files-found: error
"""


def log(m): print(m, flush=True)


def run(cmd, cwd=None, check=True, capture=False):
    log(f"> {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    try:
        return subprocess.run(cmd, cwd=str(cwd or PROJECT_ROOT),
                              check=check, capture_output=capture, text=True,
                              shell=isinstance(cmd, str))
    except subprocess.CalledProcessError as e:
        log(f"  rc={e.returncode}")
        if e.stdout: log(f"  out: {e.stdout}")
        if e.stderr: log(f"  err: {e.stderr}")
        if check: raise


def tool_available(name):
    try:
        subprocess.run([name, "--version"], capture_output=True, check=True, timeout=5)
        return True
    except Exception:
        return False


# ============================================================
# PATCH 1 — DAO additions
# ============================================================
def patch_dao():
    log("\n=== PATCH: DAO additions ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/data/local/BoardDao.kt"
    if not f.exists(): log(f"  ✗ {f}"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    if "suspend fun detachPinsFromAlbum" not in t:
        anchor = (
            '    @Query("DELETE FROM custom_albums WHERE id = :albumId")\n'
            '    suspend fun deleteAlbum(albumId: String)\n'
        )
        add = (
            anchor +
            '\n'
            '    @Query("UPDATE pins SET albumId = NULL WHERE albumId = :albumId")\n'
            '    suspend fun detachPinsFromAlbum(albumId: String)\n'
            '\n'
            '    @Transaction\n'
            '    suspend fun deleteAlbumAndDetachPins(albumId: String) {\n'
            '        detachPinsFromAlbum(albumId)\n'
            '        deleteAlbum(albumId)\n'
            '    }\n'
            '\n'
            '    @Query("UPDATE custom_albums SET dateAddedMillis = :date WHERE id = :albumId")\n'
            '    suspend fun updateAlbumDate(albumId: String, date: Long)\n'
        )
        if anchor in t:
            t = t.replace(anchor, add, 1); changed = True
            log("  ✓ detachPinsFromAlbum + deleteAlbumAndDetachPins + updateAlbumDate")

    if changed:
        f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 2 — ViewModel
# ============================================================
def patch_viewmodel():
    log("\n=== PATCH: ViewModel ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt"
    if not f.exists(): log(f"  ✗ {f}"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # ---- 2a. Data classes at top of file (after imports) ----
    if "enum class AlbumPosition" not in t:
        anchor = "data class DeletedBoardUndoState(\n"
        if anchor in t:
            dc = (
                "enum class AlbumPosition { TOP_OF_BOARD, TOP_SELECTED, MIDDLE_SELECTED, BOTTOM_SELECTED }\n"
                "\n"
                "enum class AlbumTransferMode { COPY, MOVE }\n"
                "\n"
                "data class PendingAlbumTransfer(\n"
                "    val pinIds: Set<String>,\n"
                "    val mode: AlbumTransferMode,\n"
                "    val sourceBoardId: String,\n"
                "    val savedSelectionPinIds: Set<String>,\n"
                "    val savedSelectionAlbumIds: Set<String>\n"
                ")\n"
                "\n"
            )
            t = t.replace(anchor, dc + anchor, 1); changed = True
            log("  ✓ data classes")

    # ---- 2b. New state fields after _selectedPinIds ----
    if "_selectedAlbumIds" not in t:
        anchor = (
            '    private val _selectedPinIds = MutableStateFlow<Set<String>>(emptySet())\n'
            '    val selectedPinIds: StateFlow<Set<String>> = _selectedPinIds.asStateFlow()\n'
        )
        add = (
            anchor +
            '\n'
            '    private val _selectedAlbumIds = MutableStateFlow<Set<String>>(emptySet())\n'
            '    val selectedAlbumIds: StateFlow<Set<String>> = _selectedAlbumIds.asStateFlow()\n'
            '\n'
            '    private val _snackbarActionLabel = MutableStateFlow<String?>(null)\n'
            '    val snackbarActionLabel: StateFlow<String?> = _snackbarActionLabel.asStateFlow()\n'
            '\n'
            '    private val _snackbarAction = MutableStateFlow<(() -> Unit)?>(null)\n'
            '\n'
            '    private val _pendingAlbumTransfer = MutableStateFlow<PendingAlbumTransfer?>(null)\n'
            '    val pendingAlbumTransfer: StateFlow<PendingAlbumTransfer?> = _pendingAlbumTransfer.asStateFlow()\n'
            '\n'
            '    private val _repositioningAlbumId = MutableStateFlow<String?>(null)\n'
            '    val repositioningAlbumId: StateFlow<String?> = _repositioningAlbumId.asStateFlow()\n'
            '\n'
            '    private val _scrollToAlbumId = MutableStateFlow<String?>(null)\n'
            '    val scrollToAlbumId: StateFlow<String?> = _scrollToAlbumId.asStateFlow()\n'
        )
        if anchor in t:
            t = t.replace(anchor, add, 1); changed = True
            log("  ✓ new state fields")

    # ---- 2c. Update dismissSnackbar ----
    old_ds = (
        '    fun dismissSnackbar() {\n'
        '        _snackbarMessage.value = null\n'
        '    }\n'
    )
    new_ds = (
        '    fun dismissSnackbar() {\n'
        '        _snackbarMessage.value = null\n'
        '        _snackbarActionLabel.value = null\n'
        '        _snackbarAction.value = null\n'
        '    }\n'
        '\n'
        '    fun showSnackbarWithAction(message: String, actionLabel: String, onAction: () -> Unit) {\n'
        '        _snackbarActionLabel.value = actionLabel\n'
        '        _snackbarAction.value = onAction\n'
        '        _snackbarMessage.value = message\n'
        '    }\n'
        '\n'
        '    fun requestScrollToAlbum(albumId: String) { _scrollToAlbumId.value = albumId }\n'
        '    fun consumeScrollRequest() { _scrollToAlbumId.value = null }\n'
        '    fun openAlbumPositionDialog(albumId: String) { _repositioningAlbumId.value = albumId }\n'
        '    fun closeAlbumPositionDialog() { _repositioningAlbumId.value = null }\n'
    )
    if old_ds in t:
        t = t.replace(old_ds, new_ds, 1); changed = True
        log("  ✓ snackbar action helpers")

    # ---- 2d. Update clearSelection + selectAll ----
    old_cs = (
        '    fun clearSelection() {\n'
        '        _selectedPinIds.value = emptySet()\n'
        '        _isSelectionMode.value = false\n'
        '    }\n'
    )
    new_cs = (
        '    fun clearSelection() {\n'
        '        _selectedPinIds.value = emptySet()\n'
        '        _selectedAlbumIds.value = emptySet()\n'
        '        _isSelectionMode.value = false\n'
        '    }\n'
        '\n'
        '    fun toggleAlbumSelection(albumId: String) {\n'
        '        val current = _selectedAlbumIds.value\n'
        '        _selectedAlbumIds.value = if (current.contains(albumId)) current - albumId else current + albumId\n'
        '    }\n'
    )
    if old_cs in t:
        t = t.replace(old_cs, new_cs, 1); changed = True
        log("  ✓ clearSelection + toggleAlbumSelection")

    old_sa = (
        '    fun selectAll() {\n'
        '        _selectedPinIds.value = allFilteredSortedPins.map { it.id }.toSet()\n'
        '        _isSelectionMode.value = true\n'
        '    }\n'
    )
    new_sa = (
        '    fun selectAll() {\n'
        '        _selectedPinIds.value = allFilteredSortedPins.map { it.id }.toSet()\n'
        '        _isSelectionMode.value = true\n'
        '    }\n'
        '\n'
        '    fun selectAllAlbums(albumIds: Set<String>) {\n'
        '        _selectedAlbumIds.value = albumIds\n'
        '    }\n'
    )
    if old_sa in t:
        t = t.replace(old_sa, new_sa, 1); changed = True

    # ---- 2e. New methods before `override fun onCleared()` ----
    if "fun deleteSelectedAlbums()" not in t:
        anchor = '    override fun onCleared() {\n'
        new_methods = (
            '    fun deleteSelectedAlbums() {\n'
            '        val ids = _selectedAlbumIds.value\n'
            '        if (ids.isEmpty()) return\n'
            '        val ctx = appContext ?: return\n'
            '        viewModelScope.launch {\n'
            '            val dao = AppDatabase.getDatabase(ctx).boardDao()\n'
            '            withContext(Dispatchers.IO) {\n'
            '                ids.forEach { dao.deleteAlbumAndDetachPins(it) }\n'
            '            }\n'
            '            val cur = _currentBoard.value\n'
            '            if (cur != null) {\n'
            '                val pins = dao.getPinsForBoard(cur.id).map { it.toPinItem() }\n'
            '                val albums = dao.getAlbumsForBoard(cur.id)\n'
            '                withContext(Dispatchers.Main) {\n'
            '                    _rawPins.value = pins\n'
            '                    _customAlbums.value = albums\n'
            '                    _currentBoard.value = cur.copy(pins = pins, pinCount = pins.size)\n'
            '                    updateDisplayedPins()\n'
            '                }\n'
            '            }\n'
            '            clearSelection()\n'
            '            _snackbarMessage.value = "Deleted ${ids.size} album${if (ids.size > 1) "s" else ""}"\n'
            '        }\n'
            '    }\n'
            '\n'
            '    private fun resolveInsertionMillis(position: AlbumPosition, pins: List<PinItem>, currentPins: List<PinItem>): Long {\n'
            '        if (pins.isEmpty()) return System.currentTimeMillis()\n'
            '        val sortedSel = pins.map { it.dateAddedMillis }.sorted()\n'
            '        return when (position) {\n'
            '            AlbumPosition.TOP_OF_BOARD -> (currentPins.maxOfOrNull { it.dateAddedMillis } ?: 0L) + 60_000L\n'
            '            AlbumPosition.TOP_SELECTED -> sortedSel.last() + 60_000L\n'
            '            AlbumPosition.MIDDLE_SELECTED -> sortedSel[sortedSel.size / 2]\n'
            '            AlbumPosition.BOTTOM_SELECTED -> sortedSel.first() - 60_000L\n'
            '        }\n'
            '    }\n'
            '\n'
            '    fun combineSelectedPinsToNewAlbum(position: AlbumPosition = AlbumPosition.TOP_SELECTED) {\n'
            '        val selectedIds = _selectedPinIds.value\n'
            '        if (selectedIds.size < 2) {\n'
            '            _snackbarMessage.value = "Select at least 2 images to create an album"\n'
            '            return\n'
            '        }\n'
            '        val board = _currentBoard.value ?: return\n'
            '        val ctx = appContext ?: return\n'
            '        val selectedPins = _rawPins.value.filter { selectedIds.contains(it.id) }\n'
            '        viewModelScope.launch {\n'
            '            val dao = AppDatabase.getDatabase(ctx).boardDao()\n'
            '            val albumId = "album_${System.currentTimeMillis()}_${(1000..9999).random()}"\n'
            '            val albumDate = resolveInsertionMillis(position, selectedPins, _rawPins.value)\n'
            '            val entity = CustomAlbumEntity(\n'
            '                id = albumId, boardId = board.id, parentAlbumId = null,\n'
            '                title = "Album (${selectedPins.size} images)",\n'
            '                sourceUrl = "", dateAddedMillis = albumDate,\n'
            '                orderIndex = 0, isFavorite = false\n'
            '            )\n'
            '            withContext(Dispatchers.IO) { dao.insertAlbum(entity) }\n'
            '            val updatedPins = _rawPins.value.map { p ->\n'
            '                if (selectedIds.contains(p.id)) p.copy(albumId = albumId) else p\n'
            '            }\n'
            '            withContext(Dispatchers.IO) {\n'
            '                dao.upsertPinsSafely(updatedPins.mapIndexed { i, p -> PinEntity.fromPinItem(p, board.id, i) })\n'
            '            }\n'
            '            val albums = withContext(Dispatchers.IO) { dao.getAlbumsForBoard(board.id) }\n'
            '            withContext(Dispatchers.Main) {\n'
            '                _rawPins.value = updatedPins\n'
            '                _customAlbums.value = albums\n'
            '                _currentBoard.value = board.copy(pins = updatedPins, pinCount = updatedPins.size)\n'
            '                clearSelection()\n'
            '                updateDisplayedPins(resetLimit = true)\n'
            '                requestScrollToAlbum(albumId)\n'
            '                showSnackbarWithAction(\n'
            '                    message = "Album created · ${selectedPins.size} images",\n'
            '                    actionLabel = "Change position"\n'
            '                ) { openAlbumPositionDialog(albumId) }\n'
            '            }\n'
            '        }\n'
            '    }\n'
            '\n'
            '    fun repositionAlbum(albumId: String, position: AlbumPosition) {\n'
            '        val ctx = appContext ?: return\n'
            '        viewModelScope.launch {\n'
            '            val dao = AppDatabase.getDatabase(ctx).boardDao()\n'
            '            val albumPins = withContext(Dispatchers.IO) {\n'
            '                dao.getPinsForAlbum(albumId).map { it.toPinItem() }\n'
            '            }\n'
            '            if (albumPins.isEmpty()) return@launch\n'
            '            val date = resolveInsertionMillis(position, albumPins, _rawPins.value)\n'
            '            withContext(Dispatchers.IO) { dao.updateAlbumDate(albumId, date) }\n'
            '            val cur = _currentBoard.value\n'
            '            if (cur != null) {\n'
            '                val albums = withContext(Dispatchers.IO) { dao.getAlbumsForBoard(cur.id) }\n'
            '                withContext(Dispatchers.Main) {\n'
            '                    _customAlbums.value = albums\n'
            '                    closeAlbumPositionDialog()\n'
            '                    requestScrollToAlbum(albumId)\n'
            '                }\n'
            '            }\n'
            '        }\n'
            '    }\n'
            '\n'
            '    fun beginAlbumTransfer(pinIds: Set<String>, mode: AlbumTransferMode) {\n'
            '        if (pinIds.isEmpty()) return\n'
            '        val board = _currentBoard.value ?: return\n'
            '        _pendingAlbumTransfer.value = PendingAlbumTransfer(\n'
            '            pinIds = pinIds, mode = mode, sourceBoardId = board.id,\n'
            '            savedSelectionPinIds = _selectedPinIds.value,\n'
            '            savedSelectionAlbumIds = _selectedAlbumIds.value\n'
            '        )\n'
            '    }\n'
            '\n'
            '    fun cancelAlbumTransferAndRestore() {\n'
            '        val transfer = _pendingAlbumTransfer.value ?: return\n'
            '        _pendingAlbumTransfer.value = null\n'
            '        _selectedPinIds.value = transfer.savedSelectionPinIds\n'
            '        _selectedAlbumIds.value = transfer.savedSelectionAlbumIds\n'
            '        _isSelectionMode.value = true\n'
            '    }\n'
            '\n'
            '    fun executeAlbumTransfer(targetAlbum: DateAlbum, targetBoardId: String) {\n'
            '        val transfer = _pendingAlbumTransfer.value ?: return\n'
            '        val ctx = appContext ?: return\n'
            '        viewModelScope.launch {\n'
            '            val dao = AppDatabase.getDatabase(ctx).boardDao()\n'
            '            val sourcePins = _rawPins.value.filter { transfer.pinIds.contains(it.id) }\n'
            '            val existingUrls = withContext(Dispatchers.IO) { dao.getImageUrlsForBoard(targetBoardId).toSet() }\n'
            '            val mode = transfer.mode\n'
            '            val albumId = targetAlbum.id\n'
            '            if (transfer.sourceBoardId == targetBoardId) {\n'
            '                // Same board: just assign albumId\n'
            '                val updatedPins = _rawPins.value.map { p ->\n'
            '                    if (transfer.pinIds.contains(p.id)) p.copy(albumId = albumId) else p\n'
            '                }\n'
            '                withContext(Dispatchers.IO) {\n'
            '                    dao.upsertPinsSafely(updatedPins.mapIndexed { i, p -> PinEntity.fromPinItem(p, targetBoardId, i) })\n'
            '                }\n'
            '                withContext(Dispatchers.Main) {\n'
            '                    _rawPins.value = updatedPins\n'
            '                    _currentBoard.value = _currentBoard.value?.copy(pins = updatedPins, pinCount = updatedPins.size)\n'
            '                }\n'
            '            } else {\n'
            '                val toAdd = sourcePins.filter { !existingUrls.contains(it.imageUrl) }\n'
            '                    .map { it.copy(albumId = albumId) }\n'
            '                withContext(Dispatchers.IO) {\n'
            '                    dao.insertPins(toAdd.mapIndexed { i, p -> PinEntity.fromPinItem(p, targetBoardId, i) })\n'
            '                    if (mode == AlbumTransferMode.MOVE) {\n'
            '                        dao.deletePinsFromBoard(transfer.sourceBoardId, transfer.pinIds.toList())\n'
            '                    }\n'
            '                }\n'
            '                if (mode == AlbumTransferMode.MOVE) {\n'
            '                    val remaining = _rawPins.value.filterNot { transfer.pinIds.contains(it.id) }\n'
            '                    withContext(Dispatchers.Main) {\n'
            '                        _rawPins.value = remaining\n'
            '                        _currentBoard.value = _currentBoard.value?.copy(pins = remaining, pinCount = remaining.size)\n'
            '                        updateDisplayedPins()\n'
            '                    }\n'
            '                }\n'
            '            }\n'
            '            _pendingAlbumTransfer.value = null\n'
            '            withContext(Dispatchers.Main) {\n'
            '                clearSelection()\n'
            '                _snackbarMessage.value = "${if (mode == AlbumTransferMode.MOVE) "Moved" else "Copied"} ${sourcePins.size} image(s) to \\"${targetAlbum.title}\\""\n'
            '            }\n'
            '        }\n'
            '    }\n'
            '\n'
        )
        if anchor in t:
            t = t.replace(anchor, new_methods + anchor, 1); changed = True
            log("  ✓ new methods (delete/combine/reposition/transfer)")

    # ---- 2f. Update deleteCustomAlbum to detach pins ----
    if "dao.deleteAlbumAndDetachPins(albumId)" not in t:
        old_da = (
            '    fun deleteCustomAlbum(albumId: String) {\n'
            '        val ctx = appContext ?: return\n'
            '        viewModelScope.launch(Dispatchers.IO) {\n'
            '            val dao = AppDatabase.getDatabase(ctx).boardDao()\n'
            '            dao.deleteAlbum(albumId)\n'
        )
        new_da = old_da.replace("dao.deleteAlbum(albumId)", "dao.deleteAlbumAndDetachPins(albumId)")
        if old_da in t:
            t = t.replace(old_da, new_da, 1); changed = True
            log("  ✓ deleteCustomAlbum uses deleteAlbumAndDetachPins")

    # ---- 2g. AddManualImages signature change ----
    if "fun addManualImages(\n        unstructuredText: String,\n        targetBoardIds: List<String>,\n        extractMultipleImages: Boolean = false\n    )" not in t:
        # Replace old signature
        old_sig = (
            '    fun addManualImages(\n'
            '        unstructuredText: String,\n'
            '        targetBoardIds: List<String>,\n'
            '        extractMultipleImages: Boolean = false,\n'
            '        putIntoAlbum: Boolean = false,\n'
            '        targetAlbumId: String? = null\n'
            '    ) {\n'
        )
        new_sig = (
            '    fun addManualImages(\n'
            '        unstructuredText: String,\n'
            '        targetBoardIds: List<String>,\n'
            '        extractMultipleImages: Boolean = false\n'
            '    ) {\n'
            '        // Implicit: if user is inside an album on the target board, add to that album\n'
            '        val _activeAlbumId = _activeAlbum.value?.let { alb ->\n'
            '            if (_currentBoard.value != null && targetBoardIds.contains(_currentBoard.value!!.id)) alb.id else null\n'
            '        }\n'
            '        val targetAlbumId: String? = _activeAlbumId\n'
            '        val putIntoAlbum = false\n'
        )
        if old_sig in t:
            t = t.replace(old_sig, new_sig, 1); changed = True
            log("  ✓ addManualImages signature updated")

    # ---- 2h. Observer for ALL boards (not just custom) ----
    old_obs = (
        '            // Auto-load new images only applied to custom boards, not Pinterest boards (User request 1)\n'
        '            boardPinsObserverJob?.cancel()\n'
        '            val ctx = appContext\n'
        '            if (ctx != null && board.isCustom && board.id != "board_favorites") {\n'
    )
    new_obs = (
        '            // Observe ALL boards so share-to-default updates reflect immediately\n'
        '            boardPinsObserverJob?.cancel()\n'
        '            val ctx = appContext\n'
        '            if (ctx != null) {\n'
    )
    if old_obs in t:
        t = t.replace(old_obs, new_obs, 1); changed = True
        log("  ✓ observer for all boards")

    if changed:
        f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 3 — AlbumCard selection
# ============================================================
def patch_album_card():
    log("\n=== PATCH: AlbumCard selection ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/AlbumCard.kt"
    if not f.exists(): log(f"  ✗ {f}"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # Add new params to signature
    old_sig = (
        'fun AlbumCard(\n'
        '    album: DateAlbum,\n'
        '    columnCount: Int,\n'
        '    isFavorite: Boolean,\n'
        '    isPortrait: Boolean = false,\n'
        '    onClick: () -> Unit,\n'
        '    onLongClick: () -> Unit,\n'
        '    onSwipePreview: () -> Unit,\n'
        '    modifier: Modifier = Modifier\n'
        ') {\n'
    )
    new_sig = (
        'fun AlbumCard(\n'
        '    album: DateAlbum,\n'
        '    columnCount: Int,\n'
        '    isFavorite: Boolean,\n'
        '    isPortrait: Boolean = false,\n'
        '    isSelected: Boolean = false,\n'
        '    isSelectionMode: Boolean = false,\n'
        '    onClick: () -> Unit,\n'
        '    onLongClick: () -> Unit,\n'
        '    onSelectToggle: () -> Unit = {},\n'
        '    onSwipePreview: () -> Unit,\n'
        '    modifier: Modifier = Modifier\n'
        ') {\n'
    )
    if old_sig in t:
        t = t.replace(old_sig, new_sig, 1); changed = True
        log("  ✓ signature with isSelected/isSelectionMode/onSelectToggle")

    # In select mode, tap and long-press toggle selection instead of default behavior
    if "if (isSelectionMode) onSelectToggle() else onClick()" not in t:
        old_tap = (
            '                    } else if (timeoutResult == false && !longPressed) {\n'
            '                        onClick()\n'
            '                    }\n'
        )
        new_tap = (
            '                    } else if (timeoutResult == false && !longPressed) {\n'
            '                        if (isSelectionMode) onSelectToggle() else onClick()\n'
            '                    }\n'
        )
        if old_tap in t:
            t = t.replace(old_tap, new_tap, 1); changed = True

        old_long = (
            '                    if (timeoutResult == null && !isHorizontalSwipe) {\n'
            '                        longPressed = true\n'
            '                        down.consume()\n'
            '                        onLongClick()\n'
        )
        new_long = (
            '                    if (timeoutResult == null && !isHorizontalSwipe) {\n'
            '                        longPressed = true\n'
            '                        down.consume()\n'
            '                        if (isSelectionMode) onSelectToggle() else onLongClick()\n'
        )
        if old_long in t:
            t = t.replace(old_long, new_long, 1); changed = True

    # Selection overlay on the top card
    if 'isSelectionMode' in t and "Album Selected" not in t:
        old_badge = (
            '                            // Heart Badge if favorited\n'
            '                            if (isFavorite) {\n'
        )
        new_badge = (
            '                            // Selection overlay\n'
            '                            if (isSelectionMode) {\n'
            '                                Box(\n'
            '                                    modifier = Modifier\n'
            '                                        .matchParentSize()\n'
            '                                        .background(\n'
            '                                            if (isSelected) PinterestRed.copy(alpha = 0.28f)\n'
            '                                            else Color.Black.copy(alpha = 0.10f)\n'
            '                                        )\n'
            '                                )\n'
            '                                Box(\n'
            '                                    modifier = Modifier\n'
            '                                        .align(Alignment.TopEnd)\n'
            '                                        .padding(8.dp)\n'
            '                                        .size(28.dp)\n'
            '                                        .clip(CircleShape)\n'
            '                                        .background(if (isSelected) PinterestRed else Color.Black.copy(alpha = 0.45f))\n'
            '                                        .border(2.dp, Color.White, CircleShape),\n'
            '                                    contentAlignment = Alignment.Center\n'
            '                                ) {\n'
            '                                    if (isSelected) {\n'
            '                                        Icon(\n'
            '                                            imageVector = Icons.Default.Check,\n'
            '                                            contentDescription = "Album Selected",\n'
            '                                            tint = Color.White,\n'
            '                                            modifier = Modifier.size(18.dp)\n'
            '                                        )\n'
            '                                    }\n'
            '                                }\n'
            '                            }\n'
            '\n'
            '                            // Heart Badge if favorited\n'
            '                            if (isFavorite && !isSelectionMode) {\n'
        )
        if old_badge in t:
            t = t.replace(old_badge, new_badge, 1); changed = True
            log("  ✓ selection overlay")

    # Ensure necessary imports
    if "import androidx.compose.material.icons.filled.Check" not in t:
        t = t.replace(
            'import androidx.compose.material.icons.filled.Favorite\n',
            'import androidx.compose.material.icons.filled.Check\nimport androidx.compose.material.icons.filled.Favorite\n',
            1,
        )
        changed = True
    if "import androidx.compose.foundation.border" not in t:
        t = t.replace(
            'import androidx.compose.foundation.background\n',
            'import androidx.compose.foundation.background\nimport androidx.compose.foundation.border\n',
            1,
        )
        changed = True

    if changed:
        f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 4 — MultiSelectBottomBar
# ============================================================
def patch_multiselect_bottom_bar():
    log("\n=== PATCH: MultiSelectBottomBar ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/MultiSelectBottomBar.kt"
    if not f.exists(): log(f"  ✗ {f}"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "selectedAlbumCount: Int" in t:
        log("  ✓ already patched"); return

    # Add new params
    t = t.replace(
        '    selectedCount: Int,\n'
        '    totalCount: Int,\n'
        '    onSelectAll: () -> Unit,\n'
        '    onDeselectAll: () -> Unit = {},\n'
        '    onClearSelection: () -> Unit,\n'
        '    onDownloadSelected: () -> Unit,\n'
        '    onMoveToTop: () -> Unit = {},\n'
        '    onDeleteSelected: () -> Unit = {},\n'
        '    onCopySelected: () -> Unit = {},\n'
        '    onMoveSelected: () -> Unit = {},\n'
        '    modifier: Modifier = Modifier\n',
        '    selectedPinCount: Int = 0,\n'
        '    selectedAlbumCount: Int = 0,\n'
        '    totalCount: Int,\n'
        '    onSelectAll: () -> Unit,\n'
        '    onDeselectAll: () -> Unit = {},\n'
        '    onClearSelection: () -> Unit,\n'
        '    onDownloadSelected: () -> Unit,\n'
        '    onMoveToTop: () -> Unit = {},\n'
        '    onDeleteSelected: () -> Unit = {},\n'
        '    onCopySelected: () -> Unit = {},\n'
        '    onMoveSelected: () -> Unit = {},\n'
        '    onCreateAlbum: () -> Unit = {},\n'
        '    modifier: Modifier = Modifier\n',
        1,
    )

    # Replace internal references to selectedCount
    t = t.replace('selectedCount', '(selectedPinCount + selectedAlbumCount)')
    # But keep the count display readable: use a summary Text
    t = t.replace(
        '                    Text(\n'
        '                        text = "$(selectedPinCount + selectedAlbumCount)",\n'
        '                        style = MaterialTheme.typography.titleSmall.copy(\n'
        '                            fontWeight = FontWeight.Bold,\n'
        '                            fontSize = 13.sp\n'
        '                        ),\n'
        '                        color = MaterialTheme.colorScheme.onSurface\n'
        '                    )\n',
        '                    Text(\n'
        '                        text = buildString {\n'
        '                            append(selectedPinCount)\n'
        '                            append(" img")\n'
        '                            if (selectedAlbumCount > 0) {\n'
        '                                append(" · ")\n'
        '                                append(selectedAlbumCount)\n'
        '                                append(" alb")\n'
        '                            }\n'
        '                        },\n'
        '                        style = MaterialTheme.typography.titleSmall.copy(\n'
        '                            fontWeight = FontWeight.Bold,\n'
        '                            fontSize = 12.sp\n'
        '                        ),\n'
        '                        color = MaterialTheme.colorScheme.onSurface\n'
        '                    )\n',
        1,
    )

    # Fix enable checks: download/movetop pin-only, delete both, create album >=2 pins
    t = t.replace('IconButton(\n                        onClick = onMoveToTop,\n                        enabled = (selectedPinCount + selectedAlbumCount) > 0,',
                  'IconButton(\n                        onClick = onMoveToTop,\n                        enabled = selectedPinCount > 0,')
    t = t.replace('IconButton(\n                        onClick = onDeleteSelected,\n                        enabled = (selectedPinCount + selectedAlbumCount) > 0,',
                  'IconButton(\n                        onClick = onDeleteSelected,\n                        enabled = (selectedPinCount + selectedAlbumCount) > 0,')
    t = t.replace('enabled = (selectedPinCount + selectedAlbumCount) > 0,\n                        colors = ButtonDefaults.buttonColors(',
                  'enabled = selectedPinCount > 0,\n                        colors = ButtonDefaults.buttonColors(')

    # Insert "Create Album" button before download button
    if "onCreateAlbum" in t and "Icons.Default.CollectionsBookmark" not in t:
        anchor = (
            '                    // Download Button\n'
            '                    Button(\n'
        )
        add = (
            '                    // Create Album button (pins only, >=2)\n'
            '                    if (selectedPinCount >= 2) {\n'
            '                        IconButton(\n'
            '                            onClick = onCreateAlbum,\n'
            '                            modifier = Modifier\n'
            '                                .size(32.dp)\n'
            '                                .testTag("multi_select_create_album_btn")\n'
            '                        ) {\n'
            '                            Icon(\n'
            '                                imageVector = Icons.Default.CreateNewFolder,\n'
            '                                contentDescription = "Create album from selected images",\n'
            '                                tint = PinterestRed,\n'
            '                                modifier = Modifier.size(18.dp)\n'
            '                            )\n'
            '                        }\n'
            '                    }\n'
            '\n'
            '                    // Download Button\n'
            '                    Button(\n'
        )
        if anchor in t:
            t = t.replace(anchor, add, 1)
            # add import
            t = t.replace(
                'import androidx.compose.material.icons.filled.ContentCopy\n',
                'import androidx.compose.material.icons.filled.ContentCopy\nimport androidx.compose.material.icons.filled.CreateNewFolder\n',
                1,
            )

    f.write_text(t, encoding="utf-8")
    log("  ✓ MultiSelectBottomBar updated")


# ============================================================
# PATCH 5 — AddManualImagesDialog (collapse boards, no album)
# ============================================================
def patch_add_manual_dialog():
    log("\n=== PATCH: AddManualImagesDialog ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/dialogs/AddManualImagesDialog.kt"
    if not f.exists(): log(f"  ✗ {f}"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # Remove album params
    old_sig = (
        'fun AddManualImagesDialog(\n'
        '    isOpen: Boolean,\n'
        '    availableBoards: List<PinterestBoard>,\n'
        '    currentBoardId: String?,\n'
        '    availableAlbums: List<DateAlbum> = emptyList(),\n'
        '    currentAlbumId: String? = null,\n'
        '    onDismiss: () -> Unit,\n'
        '    onAddImages: (rawText: String, targetBoardIds: List<String>, extractMultipleImages: Boolean, putIntoAlbum: Boolean, targetAlbumId: String?) -> Unit\n'
        ') {\n'
    )
    new_sig = (
        'fun AddManualImagesDialog(\n'
        '    isOpen: Boolean,\n'
        '    availableBoards: List<PinterestBoard>,\n'
        '    currentBoardId: String?,\n'
        '    currentAlbumTitle: String? = null,\n'
        '    onDismiss: () -> Unit,\n'
        '    onAddImages: (rawText: String, targetBoardIds: List<String>, extractMultipleImages: Boolean) -> Unit\n'
        ') {\n'
    )
    if old_sig in t:
        t = t.replace(old_sig, new_sig, 1); changed = True
        log("  ✓ signature simplified")

    # Remove putIntoAlbum/targetAlbumId/selectedAlbumId state
    t = t.replace(
        '    var extractMultipleImages by remember { mutableStateOf(false) }\n'
        '    var putIntoAlbum by remember { mutableStateOf(false) }\n'
        '    var selectedAlbumId by remember(currentAlbumId) { mutableStateOf(currentAlbumId) }\n',
        '    var extractMultipleImages by remember { mutableStateOf(false) }\n'
        '    var boardsExpanded by remember { mutableStateOf(false) }\n',
        1,
    )

    # Remove the "put into album" checkbox section
    old_checkbox = (
        '                // Checklist 2: Shown only when user checks extractMultipleImages\n'
        '                if (extractMultipleImages) {\n'
    )
    # find full block
    idx = t.find(old_checkbox)
    if idx >= 0:
        # find the matching close — just find the next `}` matching the outer if
        # Use a simple brace count starting after `if (extractMultipleImages) {`
        start = t.find('{', idx + len('                // Checklist 2: Shown only when user checks extractMultipleImages\n                if (extractMultipleImages) '))
        if start >= 0:
            depth = 1
            i = start + 1
            while i < len(t) and depth > 0:
                if t[i] == '{': depth += 1
                elif t[i] == '}': depth -= 1
                i += 1
            # Remove the block including trailing newline
            t = t[:idx] + t[i:].lstrip('\n')
            changed = True
            log("  ✓ removed put-into-album checkbox")

    # Remove album selection section
    old_album = '                // If non-sort custom albums exist, user can add directly to an album\n'
    idx = t.find(old_album)
    if idx >= 0:
        # find next `}\n\n                Spacer(modifier = Modifier.height(8.dp))`
        end_marker = '                Spacer(modifier = Modifier.height(8.dp))\n                Text(\n                    text = "Tip: Any other custom boards with matching domains will also receive the images automatically.",'
        end_idx = t.find(end_marker, idx)
        if end_idx >= 0:
            t = t[:idx] + t[end_idx:]
            changed = True
            log("  ✓ removed album picker")

    # Wrap board selector in expandable summary
    if "boardsExpanded" in t and "SELECT BOARDS TO INCLUDE" in t:
        old_sel_hdr = (
            '                Text(\n'
            '                    text = "SELECT BOARDS TO INCLUDE",\n'
            '                    style = MaterialTheme.typography.labelSmall.copy(\n'
            '                        fontWeight = FontWeight.Bold,\n'
            '                        letterSpacing = 0.8.sp,\n'
            '                        fontSize = 11.sp,\n'
            '                        color = PinterestTextSecondary\n'
            '                    )\n'
            '                )\n'
            '                Spacer(modifier = Modifier.height(6.dp))\n'
        )
        new_sel_hdr = (
            '                Row(\n'
            '                    modifier = Modifier\n'
            '                        .fillMaxWidth()\n'
            '                        .clickable { boardsExpanded = !boardsExpanded }\n'
            '                        .padding(vertical = 6.dp),\n'
            '                    verticalAlignment = Alignment.CenterVertically\n'
            '                ) {\n'
            '                    Text(\n'
            '                        text = "Adding to: ${selectedBoardIds.size} board${if (selectedBoardIds.size != 1) "s" else ""}",\n'
            '                        fontSize = 12.sp,\n'
            '                        fontWeight = FontWeight.SemiBold,\n'
            '                        color = PinterestTextSecondary,\n'
            '                        modifier = Modifier.weight(1f)\n'
            '                    )\n'
            '                    Text(\n'
            '                        text = if (boardsExpanded) "▲" else "▼",\n'
            '                        fontSize = 11.sp,\n'
            '                        color = PinterestRed\n'
            '                    )\n'
            '                }\n'
            '                androidx.compose.animation.AnimatedVisibility(visible = boardsExpanded) {\n'
            '                    Column {\n'
            '                        Spacer(modifier = Modifier.height(6.dp))\n'
        )
        if old_sel_hdr in t:
            t = t.replace(old_sel_hdr, new_sel_hdr, 1)
            # Close the animated visibility after FlowRow's closing brace
            # Find the FlowRow block that contains board items
            flow_anchor = (
                '                        availableBoards.forEach { board ->\n'
                '                            val isChecked = selectedBoardIds.contains(board.id)\n'
                '                            Surface(\n'
                '                                shape = RoundedCornerShape(16.dp),\n'
                '                                color = if (isChecked) PinterestBlack else PinterestPillGray,\n'
                '                                modifier = Modifier\n'
                '                                    .clickable {\n'
                '                                        if (isChecked) selectedBoardIds.remove(board.id)\n'
                '                                        else selectedBoardIds.add(board.id)\n'
                '                                    }\n'
                '                                    .testTag("select_target_board_${board.id}")\n'
                '                            ) {\n'
                '                                Row(\n'
                '                                    verticalAlignment = Alignment.CenterVertically,\n'
                '                                    modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp)\n'
                '                                ) {\n'
                '                                    if (isChecked) {\n'
                '                                        Icon(\n'
                '                                            imageVector = Icons.Default.Check,\n'
                '                                            contentDescription = null,\n'
                '                                            tint = Color.White,\n'
                '                                            modifier = Modifier.size(14.dp)\n'
                '                                        )\n'
                '                                        Spacer(modifier = Modifier.width(4.dp))\n'
                '                                    }\n'
                '                                    Text(\n'
                '                                        text = board.title,\n'
                '                                        fontSize = 12.sp,\n'
                '                                        fontWeight = if (isChecked) FontWeight.Bold else FontWeight.Medium,\n'
                '                                        color = if (isChecked) Color.White else PinterestBlack\n'
                '                                    )\n'
                '                                }\n'
                '                            }\n'
                '                        }\n'
                '                    }\n'
                '                }\n'
            )
            # Add closing after the FlowRow
            # Actually the FlowRow ends with `}` then the forEach loop was inside.
            # Simpler: add closing braces after the last `}\n                    }\n                }\n` matching forEach's end + FlowRow end
            # We appended `Column {` and `AnimatedVisibility {` so need to add `}` twice after FlowRow.
            # Find the current position of the closing after forEach+FlowRow (look for the "Tip:" text after)
            tip_marker = '                Spacer(modifier = Modifier.height(8.dp))\n                Text(\n                    text = "Tip:'
            tip_idx = t.find(tip_marker)
            if tip_idx >= 0:
                close = '                    }\n                }\n'
                t = t[:tip_idx] + close + t[tip_idx:]
                changed = True
                log("  ✓ board selector collapsed by default")

    # Update onAddImages call at bottom
    old_confirm = (
        '                    if (extractedLinks.isNotEmpty() && (selectedBoardIds.isNotEmpty() || selectedAlbumId != null)) {\n'
        '                        onAddImages(\n'
        '                            textInput.trim(),\n'
        '                            selectedBoardIds.toList(),\n'
        '                            extractMultipleImages,\n'
        '                            putIntoAlbum,\n'
        '                            selectedAlbumId\n'
        '                        )\n'
        '                        onDismiss()\n'
        '                    }\n'
    )
    new_confirm = (
        '                    if (extractedLinks.isNotEmpty() && selectedBoardIds.isNotEmpty()) {\n'
        '                        onAddImages(\n'
        '                            textInput.trim(),\n'
        '                            selectedBoardIds.toList(),\n'
        '                            extractMultipleImages\n'
        '                        )\n'
        '                        onDismiss()\n'
        '                    }\n'
    )
    if old_confirm in t:
        t = t.replace(old_confirm, new_confirm, 1); changed = True
        log("  ✓ onAddImages call updated")

    t = t.replace(
        '                enabled = extractedLinks.isNotEmpty() && (selectedBoardIds.isNotEmpty() || selectedAlbumId != null),',
        '                enabled = extractedLinks.isNotEmpty() && selectedBoardIds.isNotEmpty(),',
    )
    t = t.replace(
        '                    text = if (putIntoAlbum) "Create Album (${extractedLinks.size} URL${if (extractedLinks.size > 1) "s" else ""})"\n'
        '                    else "Add ${extractedLinks.size} Link${if (extractedLinks.size > 1) "s" else ""}",',
        '                    text = "Add ${extractedLinks.size} Link${if (extractedLinks.size > 1) "s" else ""}",',
    )

    if changed:
        f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 6 — CopyOrMoveImagesDialog (To Album button)
# ============================================================
def patch_copy_move_dialog():
    log("\n=== PATCH: CopyOrMoveImagesDialog ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/dialogs/CopyOrMoveImagesDialog.kt"
    if not f.exists(): log(f"  ✗ {f}"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # Add new params
    old_sig = (
        '    currentBoardId: String?,\n'
        '    onDismiss: () -> Unit,\n'
        '    onConfirm: (targetBoardIds: List<String>) -> Unit\n'
        ') {\n'
    )
    new_sig = (
        '    currentBoardId: String?,\n'
        '    onDismiss: () -> Unit,\n'
        '    onTransferToAlbum: (() -> Unit)? = null,\n'
        '    onConfirm: (targetBoardIds: List<String>) -> Unit\n'
        ') {\n'
    )
    if old_sig in t:
        t = t.replace(old_sig, new_sig, 1); changed = True

    # Add "To Album" button at top of text block
    if "onTransferToAlbum != null" not in t:
        anchor = '                Text(\n                    text = if (isMove) {\n'
        add = (
            '                // Transfer to album button (new feature)\n'
            '                if (onTransferToAlbum != null) {\n'
            '                    Surface(\n'
            '                        shape = RoundedCornerShape(12.dp),\n'
            '                        color = if (isMove) Color(0xFFFFF3E0) else Color(0xFFE3F2FD),\n'
            '                        border = androidx.compose.foundation.BorderStroke(\n'
            '                            1.dp,\n'
            '                            if (isMove) Color(0xFFFF9800) else Color(0xFF2196F3)\n'
            '                        ),\n'
            '                        modifier = Modifier\n'
            '                            .fillMaxWidth()\n'
            '                            .padding(vertical = 3.dp)\n'
            '                            .clickable { onTransferToAlbum() }\n'
            '                            .testTag("action_transfer_to_album")\n'
            '                    ) {\n'
            '                        Row(\n'
            '                            modifier = Modifier\n'
            '                                .fillMaxWidth()\n'
            '                                .padding(horizontal = 12.dp, vertical = 10.dp),\n'
            '                            verticalAlignment = Alignment.CenterVertically\n'
            '                        ) {\n'
            '                            Icon(\n'
            '                                imageVector = Icons.Default.Folder,\n'
            '                                contentDescription = null,\n'
            '                                tint = if (isMove) Color(0xFFFF9800) else Color(0xFF2196F3),\n'
            '                                modifier = Modifier.size(18.dp)\n'
            '                            )\n'
            '                            Spacer(modifier = Modifier.width(10.dp))\n'
            '                            Text(\n'
            '                                text = "${if (isMove) "Move" else "Copy"} to Album",\n'
            '                                fontWeight = FontWeight.Bold,\n'
            '                                fontSize = 13.sp,\n'
            '                                color = PinterestBlack\n'
            '                            )\n'
            '                        }\n'
            '                    }\n'
            '                    Spacer(modifier = Modifier.height(8.dp))\n'
            '                }\n'
            '\n'
            '                Text(\n'
            '                    text = if (isMove) {\n'
        )
        if anchor in t:
            t = t.replace(anchor, add, 1); changed = True
            if "import androidx.compose.material.icons.filled.Folder" not in t:
                t = t.replace(
                    'import androidx.compose.material.icons.filled.Image\n',
                    'import androidx.compose.material.icons.filled.Folder\nimport androidx.compose.material.icons.filled.Image\n',
                    1,
                )
            log("  ✓ To Album button")

    if changed:
        f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 7 — ShareTargetActivity (auto-default, no album, no scrim)
# ============================================================
def patch_share_activity():
    log("\n=== PATCH: ShareTargetActivity ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/ShareTargetActivity.kt"
    if not f.exists(): log(f"  ✗ {f}"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # 7a. Remove outer clickable scrim
    old_scrim = (
        '        modifier = Modifier\n'
        '            .fillMaxSize()\n'
        '            .background(Color.Black.copy(alpha = 0.55f))\n'
        '            .clickable { onDismissAndSaveDefault() },\n'
        '        contentAlignment = Alignment.Center\n'
    )
    new_scrim = (
        '        modifier = Modifier\n'
        '            .fillMaxSize()\n'
        '            .background(Color.Black.copy(alpha = 0.55f)),\n'
        '        contentAlignment = Alignment.Center\n'
    )
    if old_scrim in t:
        t = t.replace(old_scrim, new_scrim, 1); changed = True
        log("  ✓ removed outer clickable scrim")

    # 7b. Rename onDismissAndSaveDefault -> onClose (semantic: item already auto-saved)
    t = t.replace("onDismissAndSaveDefault", "onClose")

    # 7c. Remove album params from dialog + auto-save to default on create
    # This is complex. Replace the whole saveAndFinish + onCreate wrapper.
    # Simpler: patch the onSaveToBoards handler to not take album params

    old_save_handler = (
        '                    onSaveToBoards = { targetBoardIds, extractMultiple, putAlbum, targetAlbumId ->\n'
        '                        saveAndFinish(\n'
        '                            targetBoardIds = targetBoardIds,\n'
        '                            links = sharedLinks,\n'
        '                            imageUris = sharedImageUris,\n'
        '                            extractMultipleImages = extractMultiple,\n'
        '                            putIntoAlbum = putAlbum,\n'
        '                            targetAlbumId = targetAlbumId\n'
        '                        )\n'
        '                    }\n'
    )
    new_save_handler = (
        '                    onSaveToBoards = { targetBoardIds, extractMultiple ->\n'
        '                        saveAndFinish(\n'
        '                            targetBoardIds = targetBoardIds,\n'
        '                            links = sharedLinks,\n'
        '                            imageUris = sharedImageUris,\n'
        '                            extractMultipleImages = extractMultiple\n'
        '                        )\n'
        '                    }\n'
    )
    if old_save_handler in t:
        t = t.replace(old_save_handler, new_save_handler, 1); changed = True

    # 7d. Update saveAndFinish signature + remove album logic
    old_saf_sig = (
        '    private fun saveAndFinish(\n'
        '        targetBoardIds: List<String>,\n'
        '        links: List<String>,\n'
        '        imageUris: List<Uri>,\n'
        '        extractMultipleImages: Boolean = false,\n'
        '        putIntoAlbum: Boolean = false,\n'
        '        targetAlbumId: String? = null\n'
        '    ) {\n'
    )
    new_saf_sig = (
        '    private fun saveAndFinish(\n'
        '        targetBoardIds: List<String>,\n'
        '        links: List<String>,\n'
        '        imageUris: List<Uri>,\n'
        '        extractMultipleImages: Boolean = false\n'
        '    ) {\n'
    )
    if old_saf_sig in t:
        t = t.replace(old_saf_sig, new_saf_sig, 1); changed = True

    # 7e. Dialog signature: remove album params, add defaultBoardId
    old_dialog_sig = (
        'private fun FloatingShareDialog(\n'
        '    sharedLinks: List<String>,\n'
        '    sharedImageUris: List<Uri>,\n'
        '    onClose: () -> Unit,\n'
        '    onSaveToBoards: (targetBoardIds: List<String>, extractMultiple: Boolean, putAlbum: Boolean, targetAlbumId: String?) -> Unit\n'
        ') {\n'
    )
    new_dialog_sig = (
        'private fun FloatingShareDialog(\n'
        '    sharedLinks: List<String>,\n'
        '    sharedImageUris: List<Uri>,\n'
        '    onClose: () -> Unit,\n'
        '    onSaveToBoards: (targetBoardIds: List<String>, extractMultiple: Boolean) -> Unit\n'
        ') {\n'
    )
    if old_dialog_sig in t:
        t = t.replace(old_dialog_sig, new_dialog_sig, 1); changed = True

    # 7f. Remove album params/state from dialog
    for old, new in [
        ('    var putIntoAlbum by remember { mutableStateOf(false) }\n', ''),
        ('    var selectedAlbumId by remember { mutableStateOf<String?>(null) }\n', ''),
        ('    var albums by remember { mutableStateOf<List<CustomAlbumEntity>>(emptyList()) }\n', ''),
    ]:
        if old in t:
            t = t.replace(old, new, 1); changed = True

    # 7g. Remove album loading line
    t = t.replace(
        '            albums = dao.getAllAlbums()\n',
        '',
        1,
    )

    # 7h. Simplify putIntoAlbum branches (extractMultiple stays)
    old_extract_block = (
        '                        if (extractMultipleImages) {\n'
        '                            putIntoAlbum = false\n'
        '                        }\n'
    )
    if old_extract_block in t:
        t = t.replace(old_extract_block, '', 1)
    old_extract_2 = '                                if (!it) putIntoAlbum = false\n'
    if old_extract_2 in t:
        t = t.replace(old_extract_2, '', 1)

    # 7i. Simplify album picker section — remove entire block from "// Also allow selecting existing non-sort albums"
    idx = t.find('                        // Also allow selecting existing non-sort albums\n')
    if idx >= 0:
        end_marker = '                    }\n                }\n\n                Spacer(modifier = Modifier.height(16.dp))'
        end_idx = t.find(end_marker, idx)
        if end_idx >= 0:
            t = t[:idx] + t[end_idx:]
            changed = True
            log("  ✓ removed album picker from share")

    # 7j. Simplify save button click
    old_btn = (
        '                        onClick = {\n'
        '                            if (selectedAlbumId != null) {\n'
        '                                onSaveToBoards(emptyList(), extractMultipleImages, putIntoAlbum, selectedAlbumId)\n'
        '                            } else if (selectedBoardIds.isNotEmpty()) {\n'
        '                                onSaveToBoards(selectedBoardIds.toList(), extractMultipleImages, putIntoAlbum, null)\n'
        '                            } else {\n'
        '                                onClose()\n'
        '                            }\n'
        '                        },\n'
    )
    new_btn = (
        '                        onClick = {\n'
        '                            if (selectedBoardIds.isNotEmpty()) {\n'
        '                                onSaveToBoards(selectedBoardIds.toList(), extractMultipleImages)\n'
        '                            } else {\n'
        '                                onClose()\n'
        '                            }\n'
        '                        },\n'
    )
    if old_btn in t:
        t = t.replace(old_btn, new_btn, 1); changed = True

    # 7k. Simplify button text
    old_btn_text = (
        '                        Text(\n'
        '                            text = if (putIntoAlbum) "Save as Album"\n'
        '                            else if (selectedAlbumId != null) "Add to Album"\n'
        '                            else if (selectedBoardIds.size > 1) "Save to ${selectedBoardIds.size} Boards"\n'
        '                            else "Save",\n'
        '                            color = Color.White,\n'
        '                            fontWeight = FontWeight.Bold\n'
        '                        )\n'
    )
    new_btn_text = (
        '                        Text(\n'
        '                            text = if (selectedBoardIds.size > 1) "Save to ${selectedBoardIds.size} Boards"\n'
        '                            else "Save",\n'
        '                            color = Color.White,\n'
        '                            fontWeight = FontWeight.Bold\n'
        '                        )\n'
    )
    if old_btn_text in t:
        t = t.replace(old_btn_text, new_btn_text, 1); changed = True

    # 7l. Wrap onCreate to auto-save + toast before showing dialog
    old_oncreate = (
        '        setContent {\n'
        '            MyApplicationTheme {\n'
        '                FloatingShareDialog(\n'
        '                    sharedLinks = sharedLinks,\n'
        '                    sharedImageUris = sharedImageUris,\n'
        '                    onClose = {\n'
    )
    new_oncreate = (
        '        setContent {\n'
        '            MyApplicationTheme {\n'
        '                FloatingShareDialog(\n'
        '                    sharedLinks = sharedLinks,\n'
        '                    sharedImageUris = sharedImageUris,\n'
        '                    onClose = {\n'
    )
    # Note: we keep the same call site (onClose already renamed from onDismissAndSaveDefault)
    # The auto-save is added separately below via a new helper.

    if changed:
        f.write_text(t, encoding="utf-8")
        log("  ✓ share dialog simplified")

    # 7m. Add auto-save call in onCreate — insert before setContent
    if "autoSaveToDefaultBoard(" not in t:
        anchor = (
            '        setContent {\n'
            '            MyApplicationTheme {\n'
            '                FloatingShareDialog(\n'
        )
        add = (
            '        // Auto-save to default board immediately\n'
            '        autoSaveToDefaultBoard(sharedLinks, sharedImageUris)\n'
            '\n'
            '        setContent {\n'
            '            MyApplicationTheme {\n'
            '                FloatingShareDialog(\n'
        )
        if anchor in t:
            t = t.replace(anchor, add, 1)
            f.write_text(t, encoding="utf-8")
            log("  ✓ auto-save call inserted")

    # 7n. Add autoSaveToDefaultBoard helper method before saveAndFinish
    if "private fun autoSaveToDefaultBoard(" not in t:
        anchor = '    private fun saveAndFinish(\n'
        helper = (
            '    private fun autoSaveToDefaultBoard(links: List<String>, imageUris: List<Uri>) {\n'
            '        val appCtx = applicationContext\n'
            '        kotlinx.coroutines.CoroutineScope(Dispatchers.IO).launch {\n'
            '            try {\n'
            '                val dao = AppDatabase.getDatabase(appCtx).boardDao()\n'
            '                ensureDefaultBoardsExist(dao)\n'
            '                val allBoards = dao.getAllBoards()\n'
            '                val defaultBoard = allBoards.firstOrNull { it.isDefault }\n'
            '                    ?: allBoards.firstOrNull { it.id == "board_dump" }\n'
            '                    ?: allBoards.firstOrNull() ?: return@launch\n'
            '                val resolvedPins = mutableListOf<PinItem>()\n'
            '                for (link in links) {\n'
            '                    resolvedPins.add(ImageLinkResolver.resolveLink(link, defaultBoard.title))\n'
            '                }\n'
            '                for (uri in imageUris) {\n'
            '                    val uriStr = uri.toString()\n'
            '                    resolvedPins.add(PinItem(\n'
            '                        id = ImageLinkResolver.generateDeterministicPinId(uriStr),\n'
            '                        title = "Shared Photo",\n'
            '                        imageUrl = uriStr,\n'
            '                        thumbnailUrl = uriStr,\n'
            '                        author = "Shared from device",\n'
            '                        sourceUrl = uriStr,\n'
            '                        dateAddedMillis = System.currentTimeMillis()\n'
            '                    ))\n'
            '                }\n'
            '                val existingIds = dao.getPinIdsForBoard(defaultBoard.id).toSet()\n'
            '                val existingUrls = dao.getImageUrlsForBoard(defaultBoard.id).toSet()\n'
            '                val toInsert = resolvedPins.filter { !existingIds.contains(it.id) && !existingUrls.contains(it.imageUrl) }\n'
            '                if (toInsert.isNotEmpty()) {\n'
            '                    dao.insertPins(toInsert.mapIndexed { i, p -> PinEntity.fromPinItem(p, defaultBoard.id, i) })\n'
            '                }\n'
            '                withContext(Dispatchers.Main) {\n'
            '                    Toast.makeText(\n'
            '                        this@ShareTargetActivity,\n'
            '                        "Saved to ${defaultBoard.title}",\n'
            '                        Toast.LENGTH_SHORT\n'
            '                    ).show()\n'
            '                }\n'
            '            } catch (t: Throwable) {\n'
            '                t.printStackTrace()\n'
            '            }\n'
            '        }\n'
            '    }\n'
            '\n'
        )
        if anchor in t:
            t = t.replace(anchor, helper + anchor, 1)
            f.write_text(t, encoding="utf-8")
            log("  ✓ autoSaveToDefaultBoard helper")

    # 7o. Add necessary imports
    for imp in [
        'import kotlinx.coroutines.Dispatchers\n',
        'import kotlinx.coroutines.launch\n',
        'import kotlinx.coroutines.withContext\n',
    ]:
        if imp not in t:
            t = t.replace('import kotlinx.coroutines.', imp + 'import kotlinx.coroutines.', 1) if 'import kotlinx.coroutines.' in t else t
    # ensure the 3 imports exist
    if 'import kotlinx.coroutines.Dispatchers' not in t:
        t = t.replace(
            'import com.example.util.LinkExtractor\n',
            'import com.example.util.LinkExtractor\nimport kotlinx.coroutines.Dispatchers\nimport kotlinx.coroutines.launch\nimport kotlinx.coroutines.withContext\n',
            1,
        )
    # ImageLinkResolver already imported
    f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 8 — Gallery screen (big)
# ============================================================
def patch_gallery_screen():
    log("\n=== PATCH: PinBoardGalleryScreen ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not f.exists(): log(f"  ✗ {f}"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # ---- 8a. Split grid state + context scroll ----
    old_state = '    val gridState = rememberLazyStaggeredGridState()\n'
    new_state = (
        '    val boardGridState = rememberLazyStaggeredGridState()\n'
        '    val albumGridState = rememberLazyStaggeredGridState()\n'
        '    val gridState = if (activeAlbum != null) albumGridState else boardGridState\n'
        '\n'
        '    // Per-board/album scroll positions\n'
        '    val boardScrollStates = remember { androidx.compose.runtime.mutableStateMapOf<String, Pair<Int, Int>>() }\n'
        '    val albumScrollStates = remember { androidx.compose.runtime.mutableStateMapOf<String, Pair<Int, Int>>() }\n'
    )
    if old_state in t:
        t = t.replace(old_state, new_state, 1); changed = True
        log("  ✓ split gridState")

    # ---- 8b. Replace the reset-on-board-change effect ----
    old_reset = (
        '    // Reset scroll to top when board changes or newest pin changes so images refresh cleanly at top\n'
        '    LaunchedEffect(currentBoard?.id, currentBoard?.pins?.firstOrNull()?.id) {\n'
        '        gridState.scrollToItem(0)\n'
        '        topBarVisible = true\n'
        '    }\n'
    )
    new_reset = (
        '    // Per-context (board or album) scroll save/restore\n'
        '    val currentContext = activeAlbum?.id ?: currentBoard?.id ?: "none"\n'
        '    LaunchedEffect(currentContext) {\n'
        '        val key = currentContext\n'
        '        val isAlbum = activeAlbum != null\n'
        '        val targetState = if (isAlbum) albumGridState else boardGridState\n'
        '        if (key != "none") {\n'
        '            val saved = if (isAlbum) albumScrollStates[key] else boardScrollStates[key]\n'
        '            if (saved != null) targetState.scrollToItem(saved.first, saved.second)\n'
        '            else if (!isAlbum) targetState.scrollToItem(0)\n'
        '        }\n'
        '        try { kotlinx.coroutines.awaitCancellation() } finally {\n'
        '            if (key != "none") {\n'
        '                val idx = targetState.firstVisibleItemIndex\n'
        '                val off = targetState.firstVisibleItemScrollOffset\n'
        '                if (isAlbum) albumScrollStates[key] = idx to off\n'
        '                else boardScrollStates[key] = idx to off\n'
        '            }\n'
        '        }\n'
        '    }\n'
        '\n'
        '    // Newest-pin change on the SAME board: scroll to top (not on board switch)\n'
        '    var lastBoardId by remember { mutableStateOf<String?>(null) }\n'
        '    var lastFirstPinId by remember { mutableStateOf<String?>(null) }\n'
        '    val currentActiveAlbum by rememberUpdatedState(activeAlbum)\n'
        '    LaunchedEffect(currentBoard?.id, currentBoard?.pins?.firstOrNull()?.id) {\n'
        '        val bId = currentBoard?.id\n'
        '        val pId = currentBoard?.pins?.firstOrNull()?.id\n'
        '        val boardChanged = bId != lastBoardId\n'
        '        val pinChanged = pId != null && pId != lastFirstPinId\n'
        '        lastBoardId = bId\n'
        '        lastFirstPinId = pId\n'
        '        if (!boardChanged && pinChanged && currentActiveAlbum == null) {\n'
        '            boardGridState.scrollToItem(0)\n'
        '            topBarVisible = true\n'
        '        }\n'
        '    }\n'
    )
    if old_reset in t:
        t = t.replace(old_reset, new_reset, 1); changed = True
        log("  ✓ per-context scroll restore")

    # ensure rememberUpdatedState import
    if "import androidx.compose.runtime.rememberUpdatedState" not in t:
        t = t.replace(
            'import androidx.compose.runtime.rememberSaveable\n',
            'import androidx.compose.runtime.rememberSaveable\nimport androidx.compose.runtime.rememberUpdatedState\n',
            1,
        )
        changed = True

    # ---- 8c. Scroll-to-album effect (add after LaunchedEffect(activeAlbum) block) ----
    anchor = (
        '    // Handle back button navigation from opened Album\n'
    )
    scroll_to_album = (
        '    // Scroll to album when requested (after combine/creation)\n'
        '    LaunchedEffect(scrollToAlbumId, galleryItemsPlaceholder) {\n'
        '        val targetId = scrollToAlbumId ?: return@LaunchedEffect\n'
        '        val idx = galleryItemsPlaceholder.indexOfFirst { it.album?.id == targetId }\n'
        '        if (idx >= 0) {\n'
        '            val hc = (if (browserWorker != null && isBrowserTestingVisible) 1 else 0) +\n'
        '                     (if (currentBoard != null) 1 else 0) +\n'
        '                     (if (isLoading) 1 else 0)\n'
        '            boardGridState.animateScrollToItem(hc + idx)\n'
        '            viewModel.consumeScrollRequest()\n'
        '        }\n'
        '    }\n'
        '\n'
        '    // Handle back button navigation from opened Album\n'
    )
    # We'll insert this AFTER galleryItems is defined. Skip here, place later.
    # Add a placeholder: mark position; we'll inject below.

    # ---- 8d. Collect new state flows ----
    if "val selectedAlbumIds by viewModel.selectedAlbumIds" not in t:
        anchor_collect = '    val selectedPinIds by viewModel.selectedPinIds.collectAsStateWithLifecycle()\n'
        add = (
            anchor_collect +
            '    val selectedAlbumIds by viewModel.selectedAlbumIds.collectAsStateWithLifecycle()\n'
            '    val pendingAlbumTransfer by viewModel.pendingAlbumTransfer.collectAsStateWithLifecycle()\n'
            '    val repositioningAlbumId by viewModel.repositioningAlbumId.collectAsStateWithLifecycle()\n'
            '    val scrollToAlbumId by viewModel.scrollToAlbumId.collectAsStateWithLifecycle()\n'
            '    val snackbarActionLabel by viewModel.snackbarActionLabel.collectAsStateWithLifecycle()\n'
        )
        if anchor_collect in t:
            t = t.replace(anchor_collect, add, 1); changed = True
            log("  ✓ state flows collected")

    # ---- 8e. Add merged gallery items after customDateAlbums / topLevelCustomAlbums ----
    anchor_gallery = (
        '    val loosePins = remember(allPinsForAlbums) {\n'
        '        allPinsForAlbums.filter { it.albumId == null }\n'
        '    }\n'
    )
    gallery_items = (
        anchor_gallery +
        '\n'
        '    // Merged gallery items (albums + loose pins) sorted by date\n'
        '    data class GalleryItem(\n'
        '        val album: DateAlbum? = null,\n'
        '        val pin: PinItem? = null,\n'
        '        val pinIndexInLoose: Int = -1,\n'
        '        val dateAdded: Long\n'
        '    )\n'
        '    val galleryItems = remember(topLevelCustomAlbums, displayedPins) {\n'
        '        val loosePinsForGallery = if (topLevelCustomAlbums.isNotEmpty()) displayedPins.filter { it.albumId == null } else displayedPins\n'
        '        val items = mutableListOf<GalleryItem>()\n'
        '        topLevelCustomAlbums.forEach { a -> items.add(GalleryItem(album = a, dateAdded = a.dateMillis)) }\n'
        '        loosePinsForGallery.forEachIndexed { i, p -> items.add(GalleryItem(pin = p, pinIndexInLoose = i, dateAdded = p.dateAddedMillis)) }\n'
        '        items.sortByDescending { it.dateAdded }\n'
        '        items\n'
        '    }\n'
        '    val galleryItemsPlaceholder = galleryItems\n'
    )
    if anchor_gallery in t and "galleryItems = remember(topLevelCustomAlbums" not in t:
        t = t.replace(anchor_gallery, gallery_items, 1); changed = True
        log("  ✓ merged gallery items")

    # Now insert the scroll-to-album effect
    if "LaunchedEffect(scrollToAlbumId, galleryItemsPlaceholder)" not in t and "galleryItemsPlaceholder" in t:
        anchor_back = '    // Handle back button navigation from opened Album\n'
        add_effect = (
            '    // Scroll to album when requested (after combine/creation)\n'
            '    LaunchedEffect(scrollToAlbumId, galleryItemsPlaceholder) {\n'
            '        val targetId = scrollToAlbumId ?: return@LaunchedEffect\n'
            '        val idx = galleryItemsPlaceholder.indexOfFirst { it.album?.id == targetId }\n'
            '        if (idx >= 0) {\n'
            '            val hc = (if (browserWorker != null && isBrowserTestingVisible) 1 else 0) +\n'
            '                     (if (currentBoard != null) 1 else 0) +\n'
            '                     (if (isLoading) 1 else 0)\n'
            '            boardGridState.animateScrollToItem(hc + idx)\n'
            '            viewModel.consumeScrollRequest()\n'
            '        }\n'
            '    }\n'
            '\n'
            '    // Handle back button navigation from opened Album\n'
        )
        t = t.replace(anchor_back, add_effect, 1); changed = True
        log("  ✓ scroll-to-album effect")

    # ---- 8f. Replace standard masonry else block with merged items ----
    old_std_block = (
        '                } else {\n'
        '                    // 4. Standard Masonry Pin Items with Top-Level Custom Albums\n'
        '                    if (topLevelCustomAlbums.isNotEmpty()) {\n'
        '                        items(\n'
        '                            items = topLevelCustomAlbums,\n'
        '                            key = { album -> "board_custom_album_${album.id}_${album.isFavorite}" }\n'
        '                        ) { album ->\n'
        '                            AlbumCard(\n'
        '                                album = album,\n'
        '                                columnCount = columnCount,\n'
        '                                isFavorite = album.isFavorite,\n'
        '                                isPortrait = portraitAlbumCards,\n'
        '                                onClick = {\n'
        '                                    viewModel.openAlbum(album)\n'
        '                                },\n'
        '                                onLongClick = {\n'
        '                                    viewModel.toggleAlbumFavorites(album.id, album.title, album.pins)\n'
        '                                },\n'
        '                                onSwipePreview = {\n'
        '                                    previewAlbum = album\n'
        '                                }\n'
        '                            )\n'
        '                        }\n'
        '                    }\n'
        '\n'
        '                    val pinsToShow = if (topLevelCustomAlbums.isNotEmpty()) {\n'
        '                        displayedPins.filter { it.albumId == null }\n'
        '                    } else {\n'
        '                        displayedPins\n'
        '                    }\n'
        '\n'
        '                    itemsIndexed(\n'
        '                        items = pinsToShow,\n'
        '                        key = { index, pin -> "${pin.id}_$index" }\n'
        '                    ) { index, pin ->\n'
        '                        val isSelected = selectedPinIds.contains(pin.id)\n'
        '                        val isFav = favoritePinKeys.contains(pin.id) || favoritePinKeys.contains(pin.imageUrl)\n'
        '                        PinCard(\n'
        '                            pin = pin,\n'
        '                            columnCount = columnCount,\n'
        '                            isSelected = isSelected,\n'
        '                            isSelectionMode = isSelectionMode,\n'
        '                            isFavorite = isFav,\n'
        '                            hideTitleAndAuthor = hidePinTitlesAndAuthors,\n'
        '                            onClick = {\n'
        '                                if (isSelectionMode) {\n'
        '                                    viewModel.toggleSelection(pin.id)\n'
        '                                } else {\n'
        '                                    viewModel.openFullscreen(index)\n'
        '                                }\n'
        '                            },\n'
        '                            onLongClick = {\n'
        '                                if (isSelectionMode) {\n'
        '                                    viewModel.toggleSelection(pin.id)\n'
        '                                } else {\n'
        '                                    viewModel.toggleFavorite(pin)\n'
        '                                }\n'
        '                            }\n'
        '                        )\n'
        '                    }\n'
        '                }\n'
    )
    new_std_block = (
        '                } else {\n'
        '                    // 4. Standard Masonry — merged albums + pins, sorted by date\n'
        '                    items(\n'
        '                        items = galleryItems,\n'
        '                        key = { item ->\n'
        '                            item.album?.let { "album_${it.id}" } ?: "pin_${item.pin?.id}"\n'
        '                        }\n'
        '                    ) { item ->\n'
        '                        if (item.album != null) {\n'
        '                            val album = item.album\n'
        '                            val isSelectedAlbum = selectedAlbumIds.contains(album.id)\n'
        '                            AlbumCard(\n'
        '                                album = album,\n'
        '                                columnCount = columnCount,\n'
        '                                isFavorite = album.isFavorite,\n'
        '                                isPortrait = portraitAlbumCards,\n'
        '                                isSelected = isSelectedAlbum,\n'
        '                                isSelectionMode = isSelectionMode,\n'
        '                                onClick = {\n'
        '                                    when {\n'
        '                                        pendingAlbumTransfer != null -> viewModel.executeAlbumTransfer(album, currentBoard?.id ?: "")\n'
        '                                        else -> viewModel.openAlbum(album)\n'
        '                                    }\n'
        '                                },\n'
        '                                onLongClick = {\n'
        '                                    viewModel.toggleAlbumFavorites(album.id, album.title, album.pins)\n'
        '                                },\n'
        '                                onSelectToggle = {\n'
        '                                    viewModel.toggleAlbumSelection(album.id)\n'
        '                                },\n'
        '                                onSwipePreview = {\n'
        '                                    previewAlbum = album\n'
        '                                }\n'
        '                            )\n'
        '                        } else if (item.pin != null) {\n'
        '                            val pin = item.pin\n'
        '                            val isSelected = selectedPinIds.contains(pin.id)\n'
        '                            val isFav = favoritePinKeys.contains(pin.id) || favoritePinKeys.contains(pin.imageUrl)\n'
        '                            PinCard(\n'
        '                                pin = pin,\n'
        '                                columnCount = columnCount,\n'
        '                                isSelected = isSelected,\n'
        '                                isSelectionMode = isSelectionMode,\n'
        '                                isFavorite = isFav,\n'
        '                                hideTitleAndAuthor = hidePinTitlesAndAuthors,\n'
        '                                onClick = {\n'
        '                                    if (isSelectionMode) {\n'
        '                                        viewModel.toggleSelection(pin.id)\n'
        '                                    } else {\n'
        '                                        viewModel.openFullscreen(item.pinIndexInLoose)\n'
        '                                    }\n'
        '                                },\n'
        '                                onLongClick = {\n'
        '                                    if (isSelectionMode) {\n'
        '                                        viewModel.toggleSelection(pin.id)\n'
        '                                    } else {\n'
        '                                        viewModel.toggleFavorite(pin)\n'
        '                                    }\n'
        '                                }\n'
        '                            )\n'
        '                        }\n'
        '                    }\n'
        '                }\n'
    )
    if old_std_block in t:
        t = t.replace(old_std_block, new_std_block, 1); changed = True
        log("  ✓ merged masonry rendering")

    # ---- 8g. MultiSelectBottomBar call update ----
    old_bottombar = (
        '            if (fullscreenPinIndex == null) {\n'
        '                MultiSelectBottomBar(\n'
        '                    isVisible = isSelectionMode,\n'
        '                    selectedCount = selectedPinIds.size,\n'
        '                    totalCount = displayedPins.size,\n'
        '                    onSelectAll = { viewModel.selectAll() },\n'
        '                    onDeselectAll = { viewModel.deselectAll() },\n'
        '                    onClearSelection = { viewModel.clearSelection() },\n'
        '                    onDownloadSelected = { viewModel.downloadSelected(context) },\n'
        '                    onMoveToTop = { viewModel.moveSelectedPinsToTop() },\n'
        '                    onDeleteSelected = { viewModel.deletePinsFromCurrentBoard(selectedPinIds) },\n'
        '                    onCopySelected = { showCopyDialog = true },\n'
        '                    onMoveSelected = { showMoveDialog = true }\n'
        '                )\n'
        '            }\n'
    )
    new_bottombar = (
        '            if (fullscreenPinIndex == null && pendingAlbumTransfer == null) {\n'
        '                MultiSelectBottomBar(\n'
        '                    isVisible = isSelectionMode,\n'
        '                    selectedPinCount = selectedPinIds.size,\n'
        '                    selectedAlbumCount = selectedAlbumIds.size,\n'
        '                    totalCount = displayedPins.size,\n'
        '                    onSelectAll = { viewModel.selectAll() },\n'
        '                    onDeselectAll = { viewModel.deselectAll() },\n'
        '                    onClearSelection = { viewModel.clearSelection() },\n'
        '                    onDownloadSelected = { viewModel.downloadSelected(context) },\n'
        '                    onMoveToTop = { viewModel.moveSelectedPinsToTop() },\n'
        '                    onDeleteSelected = {\n'
        '                        if (selectedPinIds.isNotEmpty()) viewModel.deletePinsFromCurrentBoard(selectedPinIds)\n'
        '                        if (selectedAlbumIds.isNotEmpty()) viewModel.deleteSelectedAlbums()\n'
        '                    },\n'
        '                    onCopySelected = { showCopyDialog = true },\n'
        '                    onMoveSelected = { showMoveDialog = true },\n'
        '                    onCreateAlbum = { viewModel.combineSelectedPinsToNewAlbum() }\n'
        '                )\n'
        '            }\n'
    )
    if old_bottombar in t:
        t = t.replace(old_bottombar, new_bottombar, 1); changed = True
        log("  ✓ bottom bar updated")

    # ---- 8h. Snackbar handling with action ----
    old_snack = (
        '    // Handle snackbar messages\n'
        '    LaunchedEffect(snackbarMessage) {\n'
        '        snackbarMessage?.let {\n'
        '            snackbarHostState.showSnackbar(it)\n'
        '            viewModel.dismissSnackbar()\n'
        '        }\n'
        '    }\n'
    )
    new_snack = (
        '    // Handle snackbar messages (with optional action)\n'
        '    LaunchedEffect(snackbarMessage, snackbarActionLabel) {\n'
        '        snackbarMessage?.let { msg ->\n'
        '            val result = snackbarHostState.showSnackbar(\n'
        '                message = msg,\n'
        '                actionLabel = snackbarActionLabel,\n'
        '                duration = if (snackbarActionLabel != null) androidx.compose.material3.SnackbarDuration.Long else androidx.compose.material3.SnackbarDuration.Short\n'
        '            )\n'
        '            if (result == androidx.compose.material3.SnackbarResult.ActionPerformed) {\n'
        '                viewModel.pendingAlbumTransfer.value?.let { }\n'
        '            }\n'
        '            viewModel.dismissSnackbar()\n'
        '        }\n'
        '    }\n'
    )
    # We can't easily access the onAction callback from UI, so use a companion method.
    # Actually we stored the action in ViewModel. Let's expose a method:
    if old_snack in t:
        new_snack_fixed = (
            '    // Handle snackbar messages (with optional action)\n'
            '    LaunchedEffect(snackbarMessage, snackbarActionLabel) {\n'
            '        snackbarMessage?.let { msg ->\n'
            '            val result = snackbarHostState.showSnackbar(\n'
            '                message = msg,\n'
            '                actionLabel = snackbarActionLabel,\n'
            '                duration = if (snackbarActionLabel != null) androidx.compose.material3.SnackbarDuration.Long else androidx.compose.material3.SnackbarDuration.Short\n'
            '            )\n'
            '            if (result == androidx.compose.material3.SnackbarResult.ActionPerformed) {\n'
            '                viewModel.executeSnackbarAction()\n'
            '            }\n'
            '            viewModel.dismissSnackbar()\n'
            '        }\n'
            '    }\n'
        )
        t = t.replace(old_snack, new_snack_fixed, 1); changed = True
        log("  ✓ snackbar action handler")

    # Add executeSnackbarAction method to ViewModel — actually we need to add it there.
    # We'll do that in patch_viewmodel — need to add there. Actually skip, we'll add a call via
    # a different mechanism (see ViewModel patch).

    # ---- 8i. Album position dialog + pending banner ----
    # Insert before BoardLinkDialog call at the end
    anchor_dialogs = (
        '\n'
        '    // Board Link Dialog with History of Boards Links\n'
        '    BoardLinkDialog(\n'
    )
    new_dialogs = (
        '\n'
        '    // Pending album transfer banner (bottom, hides select bar)\n'
        '    pendingAlbumTransfer?.let { transfer ->\n'
        '        androidx.compose.material3.Surface(\n'
        '            modifier = Modifier\n'
        '                .align(Alignment.BottomCenter)\n'
        '                .padding(bottom = 16.dp, start = 12.dp, end = 12.dp)\n'
        '                .fillMaxWidth()\n'
        '                .testTag("pending_album_transfer_banner"),\n'
        '            shape = RoundedCornerShape(16.dp),\n'
        '            color = PinterestBlack,\n'
        '            shadowElevation = 8.dp\n'
        '        ) {\n'
        '            androidx.compose.foundation.layout.Row(\n'
        '                modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 6.dp),\n'
        '                verticalAlignment = Alignment.CenterVertically\n'
        '            ) {\n'
        '                androidx.compose.material3.IconButton(\n'
        '                    onClick = { viewModel.cancelAlbumTransferAndRestore() },\n'
        '                    modifier = Modifier.testTag("album_transfer_back_btn")\n'
        '                ) {\n'
        '                    androidx.compose.material3.Icon(\n'
        '                        imageVector = Icons.AutoMirrored.Filled.ArrowBack,\n'
        '                        contentDescription = "Back to selection",\n'
        '                        tint = Color.White\n'
        '                    )\n'
        '                }\n'
        '                Text(\n'
        '                    text = "Tap an album to ${if (transfer.mode == com.example.viewmodel.AlbumTransferMode.MOVE) "move" else "copy"} ${transfer.pinIds.size} image${if (transfer.pinIds.size > 1) "s" else ""}",\n'
        '                    color = Color.White,\n'
        '                    fontSize = 13.sp,\n'
        '                    fontWeight = FontWeight.Medium,\n'
        '                    modifier = Modifier.weight(1f)\n'
        '                )\n'
        '            }\n'
        '        }\n'
        '    }\n'
        '\n'
        '    // Album position dialog\n'
        '    repositioningAlbumId?.let { albumId ->\n'
        '        val positions = listOf(\n'
        '            com.example.viewmodel.AlbumPosition.TOP_OF_BOARD to "Top of board",\n'
        '            com.example.viewmodel.AlbumPosition.TOP_SELECTED to "Top selected image",\n'
        '            com.example.viewmodel.AlbumPosition.MIDDLE_SELECTED to "Middle selected image",\n'
        '            com.example.viewmodel.AlbumPosition.BOTTOM_SELECTED to "Bottom selected image"\n'
        '        )\n'
        '        var picked by remember { mutableStateOf(com.example.viewmodel.AlbumPosition.TOP_SELECTED) }\n'
        '        androidx.compose.material3.AlertDialog(\n'
        '            onDismissRequest = { viewModel.closeAlbumPositionDialog() },\n'
        '            title = { Text("Album position", fontWeight = FontWeight.Bold, fontSize = 16.sp) },\n'
        '            text = {\n'
        '                Column {\n'
        '                    positions.forEach { (pos, label) ->\n'
        '                        androidx.compose.foundation.layout.Row(\n'
        '                            modifier = Modifier\n'
        '                                .fillMaxWidth()\n'
        '                                .androidx.compose.foundation.clickable { picked = pos }\n'
        '                                .padding(vertical = 6.dp),\n'
        '                            verticalAlignment = Alignment.CenterVertically\n'
        '                        ) {\n'
        '                            androidx.compose.material3.RadioButton(\n'
        '                                selected = picked == pos,\n'
        '                                onClick = { picked = pos }\n'
        '                            )\n'
        '                            Text(label, fontSize = 13.sp)\n'
        '                        }\n'
        '                    }\n'
        '                }\n'
        '            },\n'
        '            confirmButton = {\n'
        '                androidx.compose.material3.Button(\n'
        '                    onClick = {\n'
        '                        viewModel.repositionAlbum(albumId, picked)\n'
        '                        viewModel.closeAlbumPositionDialog()\n'
        '                    },\n'
        '                    colors = androidx.compose.material3.ButtonDefaults.buttonColors(containerColor = PinterestRed)\n'
        '                ) { Text("Apply", color = Color.White) }\n'
        '            },\n'
        '            dismissButton = {\n'
        '                androidx.compose.material3.TextButton(onClick = { viewModel.closeAlbumPositionDialog() }) {\n'
        '                    Text("Cancel")\n'
        '                }\n'
        '            }\n'
        '        )\n'
        '    }\n'
        '\n'
        '    // Board Link Dialog with History of Boards Links\n'
        '    BoardLinkDialog(\n'
    )
    if anchor_dialogs in t and "pending_album_transfer_banner" not in t:
        # Fix the syntax error in the clickable line
        new_dialogs = new_dialogs.replace(
            '.androidx.compose.foundation.clickable { picked = pos }',
            '.clickable { picked = pos }'
        )
        t = t.replace(anchor_dialogs, new_dialogs, 1); changed = True
        log("  ✓ banner + reposition dialog")

    # ---- 8j. Update AddManualImagesDialog call ----
    old_manual_call = (
        '    AddManualImagesDialog(\n'
        '        isOpen = isAddManualImagesDialogOpen,\n'
        '        availableBoards = availableBoards,\n'
        '        currentBoardId = currentBoard?.id,\n'
        '        availableAlbums = customDateAlbums,\n'
        '        currentAlbumId = activeAlbum?.id,\n'
        '        onDismiss = { isAddManualImagesDialogOpen = false },\n'
        '        onAddImages = { text, targetBoards, extractMultiple, putIntoAlbum, targetAlbumId ->\n'
        '            viewModel.addManualImages(text, targetBoards, extractMultiple, putIntoAlbum, targetAlbumId)\n'
        '        }\n'
        '    )\n'
    )
    new_manual_call = (
        '    AddManualImagesDialog(\n'
        '        isOpen = isAddManualImagesDialogOpen,\n'
        '        availableBoards = availableBoards,\n'
        '        currentBoardId = currentBoard?.id,\n'
        '        currentAlbumTitle = activeAlbum?.title,\n'
        '        onDismiss = { isAddManualImagesDialogOpen = false },\n'
        '        onAddImages = { text, targetBoards, extractMultiple ->\n'
        '            viewModel.addManualImages(text, targetBoards, extractMultiple)\n'
        '        }\n'
        '    )\n'
    )
    if old_manual_call in t:
        t = t.replace(old_manual_call, new_manual_call, 1); changed = True
        log("  ✓ AddManual dialog call updated")

    # ---- 8k. Copy/Move dialog: pass albums + transfer-to-album callback ----
    old_copy_call = (
        '    CopyOrMoveImagesDialog(\n'
        '        isOpen = showCopyDialog,\n'
        '        mode = BoardTransferMode.COPY,\n'
        '        selectedPins = displayedPins.filter { selectedPinIds.contains(it.id) },\n'
        '        selectedCount = selectedPinIds.size,\n'
        '        availableBoards = availableBoards,\n'
        '        currentBoardId = currentBoard?.id,\n'
        '        onDismiss = { showCopyDialog = false },\n'
        '        onConfirm = { targetBoardIds ->\n'
        '            viewModel.copySelectedPinsToBoards(targetBoardIds, selectedPinIds)\n'
        '        }\n'
        '    )\n'
    )
    new_copy_call = (
        '    CopyOrMoveImagesDialog(\n'
        '        isOpen = showCopyDialog,\n'
        '        mode = BoardTransferMode.COPY,\n'
        '        selectedPins = displayedPins.filter { selectedPinIds.contains(it.id) },\n'
        '        selectedCount = selectedPinIds.size + selectedAlbumIds.size,\n'
        '        availableBoards = availableBoards,\n'
        '        currentBoardId = currentBoard?.id,\n'
        '        onDismiss = { showCopyDialog = false },\n'
        '        onTransferToAlbum = {\n'
        '            showCopyDialog = false\n'
        '            viewModel.beginAlbumTransfer(selectedPinIds, com.example.viewmodel.AlbumTransferMode.COPY)\n'
        '        },\n'
        '        onConfirm = { targetBoardIds ->\n'
        '            viewModel.copySelectedPinsToBoards(targetBoardIds, selectedPinIds)\n'
        '        }\n'
        '    )\n'
    )
    if old_copy_call in t:
        t = t.replace(old_copy_call, new_copy_call, 1); changed = True
        log("  ✓ Copy dialog updated")

    old_move_call = (
        '    CopyOrMoveImagesDialog(\n'
        '        isOpen = showMoveDialog,\n'
        '        mode = BoardTransferMode.MOVE,\n'
        '        selectedPins = displayedPins.filter { selectedPinIds.contains(it.id) },\n'
        '        selectedCount = selectedPinIds.size,\n'
        '        availableBoards = availableBoards,\n'
        '        currentBoardId = currentBoard?.id,\n'
        '        onDismiss = { showMoveDialog = false },\n'
        '        onConfirm = { targetBoardIds ->\n'
        '            viewModel.moveSelectedPinsToBoards(targetBoardIds, selectedPinIds)\n'
        '        }\n'
        '    )\n'
    )
    new_move_call = (
        '    CopyOrMoveImagesDialog(\n'
        '        isOpen = showMoveDialog,\n'
        '        mode = BoardTransferMode.MOVE,\n'
        '        selectedPins = displayedPins.filter { selectedPinIds.contains(it.id) },\n'
        '        selectedCount = selectedPinIds.size + selectedAlbumIds.size,\n'
        '        availableBoards = availableBoards,\n'
        '        currentBoardId = currentBoard?.id,\n'
        '        onDismiss = { showMoveDialog = false },\n'
        '        onTransferToAlbum = {\n'
        '            showMoveDialog = false\n'
        '            viewModel.beginAlbumTransfer(selectedPinIds, com.example.viewmodel.AlbumTransferMode.MOVE)\n'
        '        },\n'
        '        onConfirm = { targetBoardIds ->\n'
        '            viewModel.moveSelectedPinsToBoards(targetBoardIds, selectedPinIds)\n'
        '        }\n'
        '    )\n'
    )
    if old_move_call in t:
        t = t.replace(old_move_call, new_move_call, 1); changed = True
        log("  ✓ Move dialog updated")

    if changed:
        f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 9 — Backup migration + album ordering version
# ============================================================
def patch_backup_migration():
    log("\n=== PATCH: Backup album migration ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/BackupManager.kt"
    if not f.exists(): log(f"  ✗ {f}"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # Add album_ordering_version = 2 to backup
    if '"album_ordering_version"' not in t:
        anchor = '            rootJson.put("custom_albums", albumsArray)\n'
        if anchor in t:
            t = t.replace(anchor, anchor + '            rootJson.put("album_ordering_version", 2)\n', 1)
            changed = True
            log("  ✓ backup writes album_ordering_version=2")

    # Add migration on restore — after album restore block
    if "// Legacy album migration" not in t:
        anchor = (
            '                if (albumEntities.isNotEmpty()) {\n'
            '                    dao.insertAlbums(albumEntities)\n'
            '                }\n'
            '            }\n'
        )
        add = (
            anchor +
            '\n'
            '            // Legacy album migration: if backup is v1 (no album_ordering_version),\n'
            '            // reposition each album to the median of its pins\' dateAddedMillis\n'
            '            // so they intersperse naturally with pins instead of stacking on top.\n'
            '            val albumOrderVer = rootJson.optInt("album_ordering_version", 1)\n'
            '            if (albumOrderVer < 2) {\n'
            '                try {\n'
            '                    val allAlbums = dao.getAllAlbums()\n'
            '                    for (album in allAlbums) {\n'
            '                        val albumPins = dao.getPinsForAlbum(album.id)\n'
            '                        if (albumPins.size > 1) {\n'
            '                            val dates = albumPins.map { it.dateAddedMillis }.sorted()\n'
            '                            val median = dates[dates.size / 2]\n'
            '                            dao.updateAlbumDate(album.id, median)\n'
            '                        }\n'
            '                    }\n'
            '                } catch (_: Throwable) {}\n'
            '            }\n'
        )
        if anchor in t:
            t = t.replace(anchor, add, 1); changed = True
            log("  ✓ legacy album migration on restore")

    if changed:
        f.write_text(t, encoding="utf-8")


# ============================================================
# Helper additions to ViewModel (post-patch, avoid conflicts)
# ============================================================
def patch_viewmodel_execute_action():
    log("\n=== PATCH: ViewModel executeSnackbarAction ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt"
    if not f.exists(): return
    t = f.read_text(encoding="utf-8")
    if "fun executeSnackbarAction()" in t:
        log("  ✓ already present"); return
    anchor = '    fun dismissSnackbar() {\n'
    add = (
        '    fun executeSnackbarAction() {\n'
        '        _snackbarAction.value?.invoke()\n'
        '    }\n'
        '\n'
        '    fun dismissSnackbar() {\n'
    )
    if anchor in t:
        t = t.replace(anchor, add, 1)
        f.write_text(t, encoding="utf-8")
        log("  ✓ executeSnackbarAction added")


# ============================================================
# Build pipeline
# ============================================================
def read_app_version():
    p = PROJECT_ROOT / "app/build.gradle.kts"
    if not p.exists(): return ("unknown", "0")
    text = p.read_text(encoding="utf-8")
    vn = re.search(r'versionName\s*=\s*"([^"]+)"', text)
    vc = re.search(r'versionCode\s*=\s*(\d+)', text)
    return (vn.group(1) if vn else "unknown", vc.group(1) if vc else "0")


def ensure_release_keystore():
    log("\n=== Ensuring release.keystore ===")
    ks = PROJECT_ROOT / KEYSTORE_FILE
    if ks.exists() and ks.stat().st_size > 0:
        r = subprocess.run(["keytool", "-list", "-keystore", str(ks), "-storepass", KEYSTORE_PASS],
                           capture_output=True, text=True)
        if r.returncode == 0 and KEYSTORE_ALIAS in r.stdout:
            log(f"  ✓ OK"); return
        sys.exit(1)
    r = subprocess.run(["keytool", "-genkeypair", "-v", "-keystore", str(ks),
                        "-alias", KEYSTORE_ALIAS, "-keyalg", "RSA", "-keysize", "2048",
                        "-validity", KEYSTORE_VALIDITY, "-storepass", KEYSTORE_PASS,
                        "-keypass", KEYSTORE_PASS, "-dname", KEYSTORE_DNAME],
                       capture_output=True, text=True)
    if r.returncode != 0: log(r.stderr); sys.exit(1)
    log("  ✓ Generated")


def find_braced(text, start):
    o = text.find("{", start)
    if o == -1: return None
    d, i = 1, o + 1
    while i < len(text) and d > 0:
        c = text[i]
        if c == '"':
            i += 1
            while i < len(text):
                if text[i] == "\\": i += 2; continue
                if text[i] == '"': break
                i += 1
        elif c == "{": d += 1
        elif c == "}":
            d -= 1
            if d == 0: return (o, i)
        i += 1
    return None


def patch_build_gradle():
    log("\n=== Patching app/build.gradle.kts ===")
    p = PROJECT_ROOT / "app/build.gradle.kts"
    if not p.exists(): sys.exit(1)
    text = p.read_text(encoding="utf-8"); orig = text
    idx = text.find('create("release")')
    if idx == -1: sys.exit(1)
    span = find_braced(text, idx)
    if not span: sys.exit(1)
    ob, cb = span
    if f'storeFile = file("${{rootDir}}/{KEYSTORE_FILE}")' not in text[ob:cb]:
        nc = (f'\n      storeFile = file("${{rootDir}}/{KEYSTORE_FILE}")\n'
              f'      storePassword = "{KEYSTORE_PASS}"\n'
              f'      keyAlias = "{KEYSTORE_ALIAS}"\n'
              f'      keyPassword = "{KEYSTORE_PASS}"\n    ')
        text = text[:ob+1] + nc + text[cb:]
        log("  ✓ storeFile updated")
    bt = text.find("buildTypes {")
    if bt != -1:
        rel = text.find("release {", bt)
        if rel != -1:
            rspan = find_braced(text, rel)
            if rspan:
                ro, rc = rspan
                block = text[ro+1:rc]
                if "isDebuggable = true" in block:
                    text = text[:ro+1] + block.replace("isDebuggable = true", "isDebuggable = false") + text[rc:]
                elif "isDebuggable" not in block:
                    nb = block.replace("isMinifyEnabled = false", "isMinifyEnabled = false\n      isDebuggable = false", 1)
                    if nb != block: text = text[:ro+1] + nb + text[rc:]
    if text != orig: p.write_text(text, encoding="utf-8")


def latest_gradle_version():
    try:
        req = urllib.request.Request("https://api.github.com/repos/gradle/gradle/releases/latest",
                                     headers={"User-Agent": "pinboard"})
        with urllib.request.urlopen(req, timeout=30) as r:
            tag = json.load(r).get("tag_name", "").lstrip("v")
            if tag: return tag
    except Exception: pass
    props = PROJECT_ROOT / "gradle/wrapper/gradle-wrapper.properties"
    if props.exists():
        m = re.search(r"gradle-([\d.]+)-bin\.zip", props.read_text(encoding="utf-8"))
        if m: return m.group(1)
    return "9.3.1"


def ensure_gradle_wrapper():
    log("\n=== Ensuring gradle wrapper ===")
    for name, url in [
        ("gradlew", None), ("gradlew.bat", None),
        ("gradle/wrapper/gradle-wrapper.jar", None),
    ]: pass
    gw = PROJECT_ROOT / "gradlew"
    gwb = PROJECT_ROOT / "gradlew.bat"
    jar = PROJECT_ROOT / "gradle/wrapper/gradle-wrapper.jar"
    if gw.exists() and gwb.exists() and jar.exists():
        log("  ✓ Present"); return
    ver = latest_gradle_version()
    base = f"https://raw.githubusercontent.com/gradle/gradle/v{ver}"
    for url, dest in [(f"{base}/gradlew", gw), (f"{base}/gradlew.bat", gwb),
                      (f"{base}/gradle/wrapper/gradle-wrapper.jar", jar)]:
        if dest.exists() and dest.stat().st_size > 0: continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try: urllib.request.urlretrieve(url, dest)
        except Exception as e: log(e); sys.exit(1)
    try: os.chmod(gw, 0o755)
    except Exception: pass


def write_workflow():
    log("\n=== Writing workflow ===")
    wf = PROJECT_ROOT / ".github/workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "build.yml").write_text(WORKFLOW_YAML, encoding="utf-8")
    log("  ✓ Written")


def setup_git():
    log("\n=== Git setup ===")
    if not (PROJECT_ROOT / ".git").exists():
        run(["git", "init"]); run(["git", "branch", "-M", "main"])
    if not subprocess.run(["git", "config", "--global", "user.name"], capture_output=True, text=True).stdout.strip():
        run(["git", "config", "--global", "user.name", "PinBoard Build"])
    if not subprocess.run(["git", "config", "--global", "user.email"], capture_output=True, text=True).stdout.strip():
        run(["git", "config", "--global", "user.email", "pinboard@build.local"])
    gi = PROJECT_ROOT / ".gitignore"
    req = ["build/", "*/build/", ".gradle/", "local.properties", "*.iml", ".idea/", ".cxx/", ".DS_Store",
           ".kotlin/", ".env", "_downloads/", "*.jks", "*.keystore", "!debug.keystore", "!release.keystore"]
    existing = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    merged = list(existing)
    for l in req:
        if l not in merged: merged.append(l)
    gi.write_text("\n".join(merged) + "\n", encoding="utf-8")
    run(["git", "add", "-A"])
    for n in (KEYSTORE_FILE, "debug.keystore"):
        if (PROJECT_ROOT / n).exists():
            run(["git", "add", "-f", n], check=False)
    if subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip():
        run(["git", "commit", "-m", "Albums: ordering + selection + transfer + share default + scroll"])
        log("  ✓ Committed")


def verify_keystore_tracked():
    r = subprocess.run(["git", "ls-files", "--error-unmatch", KEYSTORE_FILE],
                       capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    if r.returncode != 0:
        run(["git", "add", "-f", KEYSTORE_FILE])
        run(["git", "commit", "-m", "Add keystore"])


def gh_user():
    r = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip(): sys.exit(1)
    return r.stdout.strip()


def ensure_github_repo():
    log("\n=== GitHub repo ===")
    user = gh_user(); full = f"{user}/{REPO_NAME}"
    if subprocess.run(["gh", "repo", "view", full], capture_output=True).returncode != 0:
        subprocess.run(["gh", "repo", "create", REPO_NAME, "--public", "--source", ".",
                        "--remote", "origin", "--push"], capture_output=True, text=True)
    if subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True).returncode != 0:
        run(["git", "remote", "add", "origin", f"https://github.com/{full}.git"])
    r = subprocess.run(["git", "push", "-u", "origin", "main"], capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(["git", "push", "-u", "origin", "main", "--force"], capture_output=True, text=True)
    return full


def trigger_and_download(repo_full):
    log("\n=== CI ===")
    for _ in range(6):
        r = subprocess.run(["gh", "workflow", "run", "build.yml", "--ref", "main", "--repo", repo_full],
                           capture_output=True, text=True)
        if r.returncode == 0: break
        time.sleep(10)
    else: sys.exit(1)
    time.sleep(10)
    run_id = None
    for _ in range(20):
        r = subprocess.run(["gh", "run", "list", "--repo", repo_full, "--workflow", "build.yml",
                            "--limit", "1", "--json", "databaseId"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            try:
                runs = json.loads(r.stdout)
                if runs: run_id = runs[0]["databaseId"]; break
            except json.JSONDecodeError: pass
        time.sleep(5)
    if run_id is None: sys.exit(1)
    while True:
        r = subprocess.run(["gh", "run", "view", str(run_id), "--repo", repo_full,
                            "--json", "status,conclusion"], capture_output=True, text=True)
        if r.returncode != 0: time.sleep(15); continue
        try: info = json.loads(r.stdout)
        except: time.sleep(15); continue
        st, cc = info.get("status"), info.get("conclusion")
        log(f"  status={st} conclusion={cc}")
        if st == "completed":
            if cc != "success":
                subprocess.run(["gh", "run", "view", str(run_id), "--repo", repo_full, "--log-failed"])
                sys.exit(1)
            break
        time.sleep(20)
    dl = PROJECT_ROOT / "_downloads"
    if dl.exists(): shutil.rmtree(dl)
    dl.mkdir()
    r = subprocess.run(["gh", "run", "download", str(run_id), "--repo", repo_full,
                        "--name", ARTIFACT, "--dir", str(dl)], capture_output=True, text=True)
    if r.returncode != 0: sys.exit(1)
    return dl


def move_apk(dl):
    log("\n=== Moving APK ===")
    apks = list(dl.glob("*.apk"))
    if not apks: sys.exit(1)
    apk = apks[0]
    vn, vc = read_app_version()
    log(f"  App: {vn} ({vc})")
    tf = PROJECT_ROOT / "Apk Directory.txt"
    target_dir = (Path(tf.read_text(encoding="utf-8").strip()) if tf.exists() else Path.home() / "Downloads")
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / f"{APP_NAME}-v{vn}-{vc}{apk.suffix}"
    if dest.exists():
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = target_dir / f"{APP_NAME}-v{vn}-{vc}_{ts}{apk.suffix}"
    shutil.copy2(apk, dest)
    log(f"  ✓ APK -> {dest}")
    return dest


def find_apksigner():
    for sdk in [Path(os.environ.get("ANDROID_HOME", "")), Path(os.environ.get("ANDROID_SDK_ROOT", "")),
                Path(os.environ.get("LOCALAPPDATA", "")) / "Android/Sdk",
                Path.home() / "AppData/Local/Android/Sdk",
                Path.home() / "Library/Android/sdk", Path("/usr/local/lib/android/sdk")]:
        if not str(sdk).strip() or not sdk.exists(): continue
        bt = sdk / "build-tools"
        if not bt.exists(): continue
        for v in sorted([d for d in bt.iterdir() if d.is_dir()], key=lambda d: d.name, reverse=True):
            for n in ("apksigner.bat", "apksigner"):
                e = v / n
                if e.exists(): return str(e)
    return None


def verify_apk_signature(apk):
    log("\n=== Verify APK signature ===")
    s = find_apksigner()
    if not s: log("  skip (no apksigner)"); return
    r = subprocess.run([s, "verify", "--verbose", "--print-certs", str(apk)], capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    log("\n".join(f"  {l}" for l in out.splitlines()[:15]))
    if r.returncode != 0 or "Verifies" not in out:
        log("  ✗ FAILED"); sys.exit(1)
    log("  ✓ verified")


def find_adb():
    if tool_available("adb"): return "adb"
    for c in [Path(os.environ.get("LOCALAPPDATA", "")) / "Android/Sdk/platform-tools/adb.exe",
              Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe",
              Path.home() / "Library/Android/sdk/platform-tools/adb", Path("/usr/local/bin/adb")]:
        if c.exists(): return str(c)
    return None


def adb_device_connected(adb):
    try:
        r = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=5)
        if r.returncode != 0: return False
        return any("\tdevice" in l or " device" in l for l in r.stdout.strip().splitlines()[1:])
    except: return False


def device_install(apk):
    log("\n=== Device install ===")
    adb = find_adb()
    if not adb or not adb_device_connected(adb):
        log("  no device — manual install:")
        log(f"    adb uninstall {PACKAGE_ID}")
        log(f'    adb install "{apk}"')
        return
    subprocess.run([adb, "uninstall", PACKAGE_ID], capture_output=True, text=True, timeout=60)
    r = subprocess.run([adb, "install", str(apk)], capture_output=True, text=True, timeout=300)
    out = (r.stdout + r.stderr).strip()
    log(f"  {out}")
    if "Success" in out: log("  ✓ Installed")


# ============================================================
# main
# ============================================================
def main():
    log("=" * 70)
    log("PinBoard — Albums overhaul")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    patch_dao()
    patch_viewmodel()
    patch_viewmodel_execute_action()
    patch_album_card()
    patch_multiselect_bottom_bar()
    patch_add_manual_dialog()
    patch_copy_move_dialog()
    patch_share_activity()
    patch_gallery_screen()
    patch_backup_migration()

    ensure_release_keystore()
    patch_build_gradle()
    ensure_gradle_wrapper()
    write_workflow()

    setup_git()
    verify_keystore_tracked()
    repo = ensure_github_repo()
    dl = trigger_and_download(repo)
    apk = move_apk(dl)
    verify_apk_signature(apk)
    device_install(apk)

    log("\n" + "=" * 70)
    log(f"DONE -> {apk}")
    log("=" * 70)


if __name__ == "__main__":
    main()