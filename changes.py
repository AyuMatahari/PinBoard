#!/usr/bin/env python3
"""
PinBoard Gallery — Select-mode fixes (round 2)
"""
import os, re, sys, json, time, shutil, datetime, subprocess, urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
REPO_NAME = "PinBoard"; APP_NAME = "PinBoard"; ARTIFACT = "app-release"
PACKAGE_ID = "com.aistudio.pinboardgallery.kzwvpt"
KEYSTORE_FILE = "release.keystore"; KEYSTORE_ALIAS = "upload"
KEYSTORE_PASS = "PinBoardRelease2025"
KEYSTORE_DNAME = "CN=PinBoard Gallery, OU=PinBoard, O=PinBoard, L=Unknown, ST=Unknown, C=US"
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
        with: { distribution: temurin, java-version: '17' }
      - uses: android-actions/setup-android@v3
        with: { packages: '' }
      - run: yes | sdkmanager --licenses >/dev/null 2>&1 || true
      - run: sdkmanager --install "platforms;android-36" "build-tools;36.0.0" >/dev/null 2>&1 || true
      - name: Verify keystore
        run: |
          [ -f release.keystore ] || { echo "no keystore"; exit 1; }
          keytool -list -keystore release.keystore -storepass PinBoardRelease2025 2>/dev/null | grep -q upload
      - uses: gradle/actions/setup-gradle@v3
        with: { gradle-version: wrapper }
      - run: chmod +x ./gradlew
      - run: ./gradlew :app:assembleRelease --stacktrace --no-daemon
      - name: Verify APK
        run: |
          APK=$(find app/build/outputs/apk/release -name "*.apk" | head -1)
          [ -n "$APK" ] || exit 1
          BT=$(ls -d $ANDROID_HOME/build-tools/* | sort -V | tail -1)
          "$BT/apksigner" verify --verbose --print-certs "$APK"
      - uses: actions/upload-artifact@v4
        with: { name: app-release, path: app/build/outputs/apk/release/*.apk, if-no-files-found: error }
"""


def log(m): print(m, flush=True)


def run(cmd, cwd=None, check=True, capture=False):
    log(f"> {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    try:
        return subprocess.run(cmd, cwd=str(cwd or PROJECT_ROOT), check=check,
                              capture_output=capture, text=True, shell=isinstance(cmd, str))
    except subprocess.CalledProcessError as e:
        if e.stdout: log(f"  out: {e.stdout}")
        if e.stderr: log(f"  err: {e.stderr}")
        if check: raise


def tool_available(name):
    try:
        subprocess.run([name, "--version"], capture_output=True, check=True, timeout=5)
        return True
    except Exception: return False


# ============================================================
# PATCH 1 — MultiSelectBottomBar
# ============================================================
def patch_multiselect_bar():
    log("\n=== PATCH: MultiSelectBottomBar (label + save icon) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/MultiSelectBottomBar.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # (a) Label format
    if 'if (selectedPinCount > 0 && selectedAlbumCount > 0)' not in t:
        old_label = (
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
        )
        new_label = (
            '                    Text(\n'
            '                        text = if (selectedPinCount > 0 && selectedAlbumCount > 0)\n'
            '                            "${selectedPinCount + selectedAlbumCount} itm"\n'
            '                        else if (selectedPinCount > 0) "$selectedPinCount img"\n'
            '                        else if (selectedAlbumCount > 0) "$selectedAlbumCount alb"\n'
            '                        else "0",\n'
        )
        if old_label in t:
            t = t.replace(old_label, new_label, 1); changed = True
            log("  ✓ combined-count label")
        else:
            log("  ⚠ label anchor missing")

    # (b) Save button → IconButton
    if 'testTag("download_selected_button")' in t and 'Button(\n                        onClick = onDownloadSelected,' in t:
        old_btn = (
            'Button(\n'
            '                        onClick = onDownloadSelected,\n'
            '                        enabled = selectedPinCount > 0,\n'
            '                        colors = ButtonDefaults.buttonColors(\n'
            '                            containerColor = PinterestRed,\n'
            '                            disabledContainerColor = PinterestPillGray\n'
            '                        ),\n'
            '                        shape = RoundedCornerShape(16.dp),\n'
            '                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),\n'
            '                        modifier = Modifier\n'
            '                            .height(34.dp)\n'
            '                            .testTag("download_selected_button")\n'
            '                    ) {\n'
            '                        Icon(\n'
            '                            imageVector = Icons.Default.Download,\n'
            '                            contentDescription = null,\n'
            '                            tint = if (selectedPinCount > 0) Color.White else Color.Gray,\n'
            '                            modifier = Modifier.size(14.dp)\n'
            '                        )\n'
            '                        Spacer(modifier = Modifier.width(4.dp))\n'
            '                        Text(\n'
            '                            text = "Save",\n'
            '                            fontSize = 12.sp,\n'
            '                            fontWeight = FontWeight.Bold,\n'
            '                            color = if (selectedPinCount > 0) Color.White else Color.Gray\n'
            '                        )\n'
            '                    }'
        )
        new_btn = (
            'IconButton(\n'
            '                        onClick = onDownloadSelected,\n'
            '                        enabled = selectedPinCount > 0,\n'
            '                        modifier = Modifier\n'
            '                            .size(32.dp)\n'
            '                            .testTag("download_selected_button")\n'
            '                    ) {\n'
            '                        Icon(\n'
            '                            imageVector = Icons.Default.Download,\n'
            '                            contentDescription = "Save selected",\n'
            '                            tint = if (selectedPinCount > 0) PinterestRed else Color.Gray,\n'
            '                            modifier = Modifier.size(18.dp)\n'
            '                        )\n'
            '                    }'
        )
        if old_btn in t:
            t = t.replace(old_btn, new_btn, 1); changed = True
            log("  ✓ save button → icon only")
        else:
            log("  ⚠ save button anchor missing (may already be icon-only)")

    if changed: f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 2 — CopyOrMoveImagesDialog: include current board
# ============================================================
def patch_copy_move_dialog():
    log("\n=== PATCH: CopyOrMoveImagesDialog (include current) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/dialogs/CopyOrMoveImagesDialog.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    old_filter = (
        '    val selectableBoards = remember(availableBoards, currentBoardId, mode) {\n'
        '        if (mode == BoardTransferMode.MOVE && !currentBoardId.isNullOrBlank()) {\n'
        '            availableBoards.filter { it.id != currentBoardId }\n'
        '        } else {\n'
        '            availableBoards\n'
        '        }\n'
        '    }\n'
    )
    new_filter = (
        '    // MOVE now includes the current board (moving to current board = reorder to top)\n'
        '    val selectableBoards = remember(availableBoards) { availableBoards }\n'
    )
    if old_filter in t:
        t = t.replace(old_filter, new_filter, 1); changed = True
        log("  ✓ include current board in MOVE list")

    # Add "(Current)" tag next to the board title when it matches currentBoardId
    if '(Current)' not in t:
        old_row = (
            '                                    Text(\n'
            '                                        text = board.title,\n'
            '                                        fontWeight = if (isChecked) FontWeight.Bold else FontWeight.Medium,\n'
            '                                        fontSize = 13.sp,\n'
            '                                        color = if (isChecked) PinterestRed else PinterestBlack\n'
            '                                    )\n'
        )
        new_row = (
            '                                    Text(\n'
            '                                        text = board.title,\n'
            '                                        fontWeight = if (isChecked) FontWeight.Bold else FontWeight.Medium,\n'
            '                                        fontSize = 13.sp,\n'
            '                                        color = if (isChecked) PinterestRed else PinterestBlack\n'
            '                                    )\n'
            '                                    if (board.id == currentBoardId) {\n'
            '                                        Spacer(modifier = Modifier.width(6.dp))\n'
            '                                        Text("(Current)", fontSize = 10.sp, color = PinterestTextSecondary)\n'
            '                                    }\n'
        )
        if old_row in t:
            t = t.replace(old_row, new_row, 1); changed = True
            log("  ✓ (Current) tag")

    if changed: f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 3 — AlbumCard: staleness + tap/hold inversion
# ============================================================
def patch_album_card():
    log("\n=== PATCH: AlbumCard gestures ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/AlbumCard.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # Import rememberUpdatedState
    if "import androidx.compose.runtime.rememberUpdatedState" not in t:
        t = t.replace(
            'import androidx.compose.runtime.remember\n',
            'import androidx.compose.runtime.remember\nimport androidx.compose.runtime.rememberUpdatedState\n',
            1,
        )
        changed = True

    # Wrap callbacks in rememberUpdatedState — insert just before the Box with pointerInput
    if "val currentOnSelectToggle by rememberUpdatedState(onSelectToggle)" not in t:
        anchor = (
            '    val context = LocalContext.current\n'
            '    val pins = album.pins\n'
        )
        add = (
            '    val context = LocalContext.current\n'
            '    val currentOnClick by rememberUpdatedState(onClick)\n'
            '    val currentOnLongClick by rememberUpdatedState(onLongClick)\n'
            '    val currentOnSelectToggle by rememberUpdatedState(onSelectToggle)\n'
            '    val currentOnSwipePreview by rememberUpdatedState(onSwipePreview)\n'
            '    val pins = album.pins\n'
        )
        if anchor in t:
            t = t.replace(anchor, add, 1); changed = True
            log("  ✓ rememberUpdatedState wrappers")

    # Change pointerInput key
    if "pointerInput(album.id, isSelectionMode)" not in t:
        t = t.replace(
            '.pointerInput(album.id) {',
            '.pointerInput(album.id, isSelectionMode) {',
            1,
        )
        changed = True
        log("  ✓ pointerInput key includes isSelectionMode")

    # Invert long-press branch: select mode → open album (onClick)
    old_long = (
        '                        down.consume()\n'
        '                        if (isSelectionMode) onSelectToggle() else onLongClick()\n'
    )
    new_long = (
        '                        down.consume()\n'
        '                        if (isSelectionMode) currentOnClick() else currentOnLongClick()\n'
    )
    if old_long in t:
        t = t.replace(old_long, new_long, 1); changed = True
        log("  ✓ long-press: select mode → open album")

    # Tap branch: select mode → toggle selection
    old_tap = (
        '                        if (isSelectionMode) onSelectToggle() else onClick()\n'
    )
    new_tap = (
        '                        if (isSelectionMode) currentOnSelectToggle() else currentOnClick()\n'
    )
    if old_tap in t:
        t = t.replace(old_tap, new_tap, 1); changed = True
        log("  ✓ tap: select mode → toggle selection")

    # Also update swipe → rememberUpdatedState lambda
    old_swipe = '                            onSwipePreview()\n'
    new_swipe = '                            currentOnSwipePreview()\n'
    if old_swipe in t and new_swipe not in t:
        t = t.replace(old_swipe, new_swipe, 1); changed = True

    if changed: f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 4 — ViewModel: delete-selection, move-to-top, banner
# ============================================================
def patch_viewmodel():
    log("\n=== PATCH: ViewModel (select-mode) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # (a) Extend enum + data class
    if "DeleteSelectionMode" not in t:
        anchor = "enum class AlbumTransferMode { COPY, MOVE }\n"
        add = (
            "enum class AlbumTransferMode { COPY, MOVE }\n"
            "\n"
            "enum class DeleteSelectionMode { DISSOLVE, DELETE_WITH_CONTENTS, PINS_ONLY }\n"
        )
        if anchor in t:
            t = t.replace(anchor, add, 1); changed = True
            log("  ✓ DeleteSelectionMode enum")

    if "dissolvedLinks" not in t and "data class DeletedPinsUndoState" in t:
        old_dc = (
            'data class DeletedPinsUndoState(\n'
            '    val boardId: String,\n'
            '    val pins: List<PinItem>,\n'
            '    val imageUrls: List<String> = pins.map { it.imageUrl }\n'
            ')\n'
        )
        new_dc = (
            'data class DeletedPinsUndoState(\n'
            '    val boardId: String,\n'
            '    val pins: List<PinItem>,\n'
            '    val imageUrls: List<String> = pins.map { it.imageUrl },\n'
            '    val albums: List<com.example.data.local.CustomAlbumEntity> = emptyList(),\n'
            '    val dissolvedLinks: Map<String, String> = emptyMap(),\n'
            '    val mode: DeleteSelectionMode = DeleteSelectionMode.PINS_ONLY\n'
            ')\n'
        )
        if old_dc in t:
            t = t.replace(old_dc, new_dc, 1); changed = True
            log("  ✓ DeletedPinsUndoState extended")

    # (b) New deleteSelectionAndAlbums method — insert before onCleared
    if "fun deleteSelectionAndAlbums(" not in t:
        anchor = '    override fun onCleared() {\n'
        new_methods = (
            '    fun deleteSelectionAndAlbums(pinIds: Set<String>, albumIds: Set<String>, mode: DeleteSelectionMode) {\n'
            '        val board = _currentBoard.value ?: return\n'
            '        if (pinIds.isEmpty() && albumIds.isEmpty()) return\n'
            '        viewModelScope.launch {\n'
            '            val ctx = appContext ?: return@launch\n'
            '            val dao = AppDatabase.getDatabase(ctx).boardDao()\n'
            '            val allPins = _rawPins.value\n'
            '            val albums = _customAlbums.value.filter { albumIds.contains(it.id) }\n'
            '            val albumPins = allPins.filter { it.albumId != null && albumIds.contains(it.albumId!!) }\n'
            '            val explicitPins = allPins.filter { pinIds.contains(it.id) }\n'
            '\n'
            '            val pinsToDelete: List<PinItem>\n'
            '            val dissolvedLinks = mutableMapOf<String, String>()\n'
            '\n'
            '            when (mode) {\n'
            '                DeleteSelectionMode.DELETE_WITH_CONTENTS -> {\n'
            '                    pinsToDelete = (explicitPins + albumPins).distinctBy { it.id }\n'
            '                }\n'
            '                DeleteSelectionMode.DISSOLVE -> {\n'
            '                    pinsToDelete = explicitPins\n'
            '                    albumPins.forEach { p -> p.albumId?.let { dissolvedLinks[p.id] = it } }\n'
            '                }\n'
            '                DeleteSelectionMode.PINS_ONLY -> {\n'
            '                    pinsToDelete = explicitPins\n'
            '                }\n'
            '            }\n'
            '\n'
            '            withContext(Dispatchers.IO) {\n'
            '                if (pinsToDelete.isNotEmpty()) {\n'
            '                    dao.deletePinsFromBoard(board.id, pinsToDelete.map { it.id })\n'
            '                }\n'
            '                albums.forEach { dao.deleteAlbum(it.id) }\n'
            '            }\n'
            '\n'
            '            val remaining = allPins\n'
            '                .filterNot { p -> pinsToDelete.any { pd -> pd.id == p.id } }\n'
            '                .map { p ->\n'
            '                    if (mode == DeleteSelectionMode.DISSOLVE &&\n'
            '                        p.albumId != null && albumIds.contains(p.albumId!!)) {\n'
            '                        p.copy(albumId = null)\n'
            '                    } else p\n'
            '                }\n'
            '            val remainingAlbums = _customAlbums.value.filterNot { albumIds.contains(it.id) }\n'
            '\n'
            '            _deletedPinsUndo.value = DeletedPinsUndoState(\n'
            '                boardId = board.id,\n'
            '                pins = pinsToDelete,\n'
            '                imageUrls = pinsToDelete.map { it.imageUrl },\n'
            '                albums = albums,\n'
            '                dissolvedLinks = dissolvedLinks,\n'
            '                mode = mode\n'
            '            )\n'
            '\n'
            '            withContext(Dispatchers.Main) {\n'
            '                _rawPins.value = remaining\n'
            '                _customAlbums.value = remainingAlbums\n'
            '                _currentBoard.value = board.copy(pins = remaining, pinCount = remaining.size)\n'
            '                updateDisplayedPins()\n'
            '                clearSelection()\n'
            '            }\n'
            '        }\n'
            '    }\n'
            '\n'
            '    // Move pins/albums to top of the board (also dissolves empty albums)\n'
            '    private suspend fun moveToTopInternal(pinIds: Set<String>, albumIds: Set<String>, dao: BoardDao) {\n'
            '        val board = _currentBoard.value ?: return\n'
            '        val allPins = _rawPins.value\n'
            '        val maxPinDate = allPins.maxOfOrNull { it.dateAddedMillis } ?: 0L\n'
            '        val maxAlbumDate = _customAlbums.value.maxOfOrNull { it.dateAddedMillis } ?: 0L\n'
            '        var nextDate = maxOf(maxPinDate, maxAlbumDate) + 60_000L\n'
            '\n'
            '        val affectedAlbumIds = mutableSetOf<String>()\n'
            '        val updatedPins = allPins.map { p ->\n'
            '            if (pinIds.contains(p.id)) {\n'
            '                p.albumId?.let { affectedAlbumIds.add(it) }\n'
            '                p.copy(albumId = null, dateAddedMillis = nextDate).also { nextDate += 1000L }\n'
            '            } else p\n'
            '        }\n'
            '\n'
            '        val updatedAlbums = _customAlbums.value.map { a ->\n'
            '            if (albumIds.contains(a.id)) {\n'
            '                a.copy(dateAddedMillis = nextDate).also { nextDate += 1000L }\n'
            '            } else a\n'
            '        }\n'
            '\n'
            '        val nonEmptyAlbumIds = updatedPins.mapNotNull { it.albumId }.toSet()\n'
            '        val dissolvedAlbumIds = affectedAlbumIds - nonEmptyAlbumIds\n'
            '        val finalAlbums = updatedAlbums.filterNot { it.id in dissolvedAlbumIds }\n'
            '\n'
            '        withContext(Dispatchers.IO) {\n'
            '            dao.upsertPinsSafely(updatedPins.mapIndexed { i, p -> PinEntity.fromPinItem(p, board.id, i) })\n'
            '            updatedAlbums.filter { it.id in albumIds }.forEach { dao.insertAlbum(it) }\n'
            '            dissolvedAlbumIds.forEach { dao.deleteAlbum(it) }\n'
            '        }\n'
            '\n'
            '        withContext(Dispatchers.Main) {\n'
            '            _rawPins.value = updatedPins\n'
            '            _customAlbums.value = finalAlbums\n'
            '            _currentBoard.value = board.copy(pins = updatedPins, pinCount = updatedPins.size)\n'
            '            updateDisplayedPins(resetLimit = true)\n'
            '        }\n'
            '    }\n'
            '\n'
            '    fun executeAlbumTransferToCurrentBoard() {\n'
            '        val transfer = _pendingAlbumTransfer.value ?: return\n'
            '        val currentBoard = _currentBoard.value ?: return\n'
            '        val sourceBoardId = transfer.sourceBoardId\n'
            '        viewModelScope.launch {\n'
            '            val ctx = appContext ?: return@launch\n'
            '            val dao = AppDatabase.getDatabase(ctx).boardDao()\n'
            '            if (currentBoard.id == sourceBoardId) {\n'
            '                if (transfer.mode == AlbumTransferMode.MOVE) {\n'
            '                    moveToTopInternal(transfer.pinIds, emptySet(), dao)\n'
            '                    _snackbarMessage.value = "Moved ${transfer.pinIds.size} to top of board"\n'
            '                } else {\n'
            '                    _snackbarMessage.value = "Already on this board"\n'
            '                }\n'
            '            } else {\n'
            '                val pins = _rawPins.value.filter { transfer.pinIds.contains(it.id) }\n'
            '                val existingUrls = withContext(Dispatchers.IO) { dao.getImageUrlsForBoard(currentBoard.id).toSet() }\n'
            '                val baseDate = System.currentTimeMillis()\n'
            '                val toAdd = pins.filter { !existingUrls.contains(it.imageUrl) }\n'
            '                    .mapIndexed { i, p -> p.copy(albumId = null, dateAddedMillis = baseDate + i * 1000L) }\n'
            '                withContext(Dispatchers.IO) {\n'
            '                    dao.insertPins(toAdd.mapIndexed { i, p -> PinEntity.fromPinItem(p, currentBoard.id, i) })\n'
            '                    if (transfer.mode == AlbumTransferMode.MOVE) {\n'
            '                        dao.deletePinsFromBoard(sourceBoardId, transfer.pinIds.toList())\n'
            '                    }\n'
            '                }\n'
            '                if (transfer.mode == AlbumTransferMode.MOVE) {\n'
            '                    val remaining = _rawPins.value.filterNot { transfer.pinIds.contains(it.id) }\n'
            '                    withContext(Dispatchers.Main) {\n'
            '                        _rawPins.value = remaining\n'
            '                        _currentBoard.value = currentBoard.copy(pins = remaining, pinCount = remaining.size)\n'
            '                        updateDisplayedPins()\n'
            '                    }\n'
            '                }\n'
            '                _snackbarMessage.value = "${if (transfer.mode == AlbumTransferMode.MOVE) "Moved" else "Copied"} ${toAdd.size} to ${currentBoard.title}"\n'
            '            }\n'
            '            _pendingAlbumTransfer.value = null\n'
            '            withContext(Dispatchers.Main) { clearSelection() }\n'
            '        }\n'
            '    }\n'
            '\n'
        )
        if anchor in t:
            t = t.replace(anchor, new_methods + anchor, 1); changed = True
            log("  ✓ deleteSelectionAndAlbums + moveToTopInternal + executeAlbumTransferToCurrentBoard")

    # (c) beginAlbumTransfer exits select mode
    old_begin = (
        '        _pendingAlbumTransfer.value = PendingAlbumTransfer(\n'
        '            pinIds = pinIds, mode = mode, sourceBoardId = board.id,\n'
        '            savedSelectionPinIds = _selectedPinIds.value,\n'
        '            savedSelectionAlbumIds = _selectedAlbumIds.value\n'
        '        )\n'
        '    }\n'
    )
    new_begin = (
        '        _pendingAlbumTransfer.value = PendingAlbumTransfer(\n'
        '            pinIds = pinIds, mode = mode, sourceBoardId = board.id,\n'
        '            savedSelectionPinIds = _selectedPinIds.value,\n'
        '            savedSelectionAlbumIds = _selectedAlbumIds.value\n'
        '        )\n'
        '        _isSelectionMode.value = false\n'
        '    }\n'
    )
    if old_begin in t:
        t = t.replace(old_begin, new_begin, 1); changed = True
        log("  ✓ beginAlbumTransfer exits select mode")

    # (d) Update undoDeletePins to restore albums + dissolved links
    old_undo = (
        '    fun undoDeletePins() {\n'
        '        val undo = _deletedPinsUndo.value ?: return\n'
        '        val board = _currentBoard.value ?: return\n'
        '        _deletedPinsUndo.value = null\n'
        '\n'
        '        val restored = (undo.pins + _rawPins.value).distinctBy { it.id }\n'
        '        _rawPins.value = restored\n'
        '        _currentBoard.value = board.copy(pins = restored, pinCount = restored.size)\n'
        '        updateDisplayedPins()\n'
        '\n'
        '        viewModelScope.launch(Dispatchers.IO) {\n'
        '            val ctx = appContext ?: return@launch\n'
        '            val dao = AppDatabase.getDatabase(ctx).boardDao()\n'
        '            val entities = undo.pins.mapIndexed { idx, p -> PinEntity.fromPinItem(p, undo.boardId, idx) }\n'
        '            dao.insertPins(entities)\n'
        '            refreshAvailableBoardsFromDatabaseInternal(dao)\n'
        '        }\n'
        '\n'
        '        _snackbarMessage.value = "Restored ${undo.pins.size} image${if (undo.pins.size > 1) "s" else ""}"\n'
        '    }\n'
    )
    new_undo = (
        '    fun undoDeletePins() {\n'
        '        val undo = _deletedPinsUndo.value ?: return\n'
        '        val board = _currentBoard.value ?: return\n'
        '        _deletedPinsUndo.value = null\n'
        '\n'
        '        val restored = (undo.pins + _rawPins.value).distinctBy { it.id }\n'
        '        _rawPins.value = restored\n'
        '        _currentBoard.value = board.copy(pins = restored, pinCount = restored.size)\n'
        '        updateDisplayedPins()\n'
        '\n'
        '        viewModelScope.launch(Dispatchers.IO) {\n'
        '            val ctx = appContext ?: return@launch\n'
        '            val dao = AppDatabase.getDatabase(ctx).boardDao()\n'
        '            if (undo.albums.isNotEmpty()) {\n'
        '                dao.insertAlbums(undo.albums)\n'
        '            }\n'
        '            val entities = undo.pins.mapIndexed { idx, p -> PinEntity.fromPinItem(p, undo.boardId, idx) }\n'
        '            if (entities.isNotEmpty()) dao.insertPins(entities)\n'
        '            undo.dissolvedLinks.forEach { (pinId, albumId) ->\n'
        '                try { dao.movePinsToAlbum(listOf(pinId), albumId) } catch (_: Throwable) {}\n'
        '            }\n'
        '            refreshAvailableBoardsFromDatabaseInternal(dao)\n'
        '        }\n'
        '\n'
        '        val albumMsg = if (undo.albums.isNotEmpty()) " + ${undo.albums.size} album${if (undo.albums.size > 1) "s" else ""}" else ""\n'
        '        _snackbarMessage.value = "Restored ${undo.pins.size} image${if (undo.pins.size > 1) "s" else ""}$albumMsg"\n'
        '    }\n'
    )
    if old_undo in t:
        t = t.replace(old_undo, new_undo, 1); changed = True
        log("  ✓ undoDeletePins restores albums + dissolved links")

    if changed: f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 5 — New DeleteSelectionDialog.kt
# ============================================================
def patch_new_delete_dialog():
    log("\n=== PATCH: DeleteSelectionDialog.kt (new file) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/dialogs/DeleteSelectionDialog.kt"
    if f.exists(): log("  ✓ already exists"); return

    content = r'''package com.example.ui.dialogs

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.FolderOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary


@Composable
fun DeleteSelectionDialog(
    isOpen: Boolean,
    pinCount: Int,
    albumCount: Int,
    onDismiss: () -> Unit,
    onDissolve: () -> Unit,
    onDeleteAll: () -> Unit
) {
    if (!isOpen) return

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(
                text = "Choose how to delete selected albums:",
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp
            )
        },
        text = {
            Column(Modifier.fillMaxWidth()) {
                Text(
                    text = if (pinCount > 0)
                        "$albumCount album(s) + $pinCount image(s) selected"
                    else
                        "$albumCount album(s) selected",
                    fontSize = 12.sp,
                    color = PinterestTextSecondary
                )
                Spacer(Modifier.height(12.dp))

                // Option A: Dissolve
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = PinterestPillGray,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onDissolve() }
                        .testTag("delete_option_dissolve")
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Box(
                            modifier = Modifier
                                .size(32.dp)
                                .clip(CircleShape)
                                .background(Color(0xFFE3F2FD)),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = Icons.Default.FolderOff,
                                contentDescription = null,
                                tint = Color(0xFF1976D2),
                                modifier = Modifier.size(18.dp)
                            )
                        }
                        Spacer(Modifier.width(10.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                "Dissolve album, keep inside images",
                                fontWeight = FontWeight.SemiBold,
                                fontSize = 13.sp,
                                color = PinterestBlack
                            )
                            Text(
                                "Images stay on the board as loose pins.",
                                fontSize = 11.sp,
                                color = PinterestTextSecondary
                            )
                        }
                    }
                }

                Spacer(Modifier.height(8.dp))

                // Option B: Delete album + contents
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = PinterestPillGray,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onDeleteAll() }
                        .testTag("delete_option_with_contents")
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Box(
                            modifier = Modifier
                                .size(32.dp)
                                .clip(CircleShape)
                                .background(PinterestRed.copy(alpha = 0.15f)),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = Icons.Default.DeleteOutline,
                                contentDescription = null,
                                tint = PinterestRed,
                                modifier = Modifier.size(18.dp)
                            )
                        }
                        Spacer(Modifier.width(10.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                "Delete album + images inside",
                                fontWeight = FontWeight.SemiBold,
                                fontSize = 13.sp,
                                color = PinterestBlack
                            )
                            Text(
                                "Images are permanently removed. Undo is available.",
                                fontSize = 11.sp,
                                color = PinterestTextSecondary
                            )
                        }
                    }
                }

                if (pinCount > 0) {
                    Spacer(Modifier.height(10.dp))
                    Text(
                        "Explicitly selected images are deleted regardless of choice above.",
                        fontSize = 11.sp,
                        color = PinterestTextSecondary
                    )
                }
            }
        },
        confirmButton = {},
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel", color = PinterestBlack)
            }
        },
        shape = RoundedCornerShape(20.dp)
    )
}
'''
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    log("  ✓ created")


# ============================================================
# PATCH 6 — Gallery screen
# ============================================================
def patch_gallery_screen():
    log("\n=== PATCH: PinBoardGalleryScreen ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # (a) Album pins sort by dateAddedMillis (both board-level and opened-album)
    old_sort1 = (
        '            val albumPins = allPinsForAlbums.filter { it.albumId == entity.id }\n'
        '                .sortedBy { it.boardPosition }\n'
    )
    new_sort1 = (
        '            val albumPins = allPinsForAlbums.filter { it.albumId == entity.id }\n'
        '                .sortedByDescending { it.dateAddedMillis }\n'
    )
    if old_sort1 in t:
        t = t.replace(old_sort1, new_sort1, 1); changed = True
        log("  ✓ album pins sorted by dateAddedMillis")

    # Also the opened-album pins get re-sorted at render
    old_open = '                    val albumPins = activeAlbum!!.pins\n'
    new_open = '                    val albumPins = activeAlbum!!.pins.sortedByDescending { it.dateAddedMillis }\n'
    if old_open in t:
        t = t.replace(old_open, new_open, 1); changed = True
        log("  ✓ opened album pins sorted")

    # (b) Collect new state
    if "val deletedSelectionUndo" not in t and "val deletedPinsUndo by viewModel.deletedPinsUndo" in t:
        anchor = '    val deletedPinsUndo by viewModel.deletedPinsUndo.collectAsStateWithLifecycle()\n'
        add = (
            anchor +
            '    // (deletedPinsUndo now includes album info for mixed deletes)\n'
        )
        # No new state needed — we extended DeletedPinsUndoState
        pass  # existing collection covers it

    # (c) Delete button routing + dialog state
    if "showDeleteSelectionDialog" not in t:
        anchor = '    var showMoveDialog by remember { mutableStateOf(false) }\n'
        add = (
            '    var showMoveDialog by remember { mutableStateOf(false) }\n'
            '    var showDeleteSelectionDialog by remember { mutableStateOf(false) }\n'
        )
        if anchor in t:
            t = t.replace(anchor, add, 1); changed = True
            log("  ✓ showDeleteSelectionDialog state")

    # (d) Update MultiSelectBottomBar onDeleteSelected
    old_del = (
        '                    onDeleteSelected = {\n'
        '                        if (selectedPinIds.isNotEmpty()) viewModel.deletePinsFromCurrentBoard(selectedPinIds)\n'
        '                        if (selectedAlbumIds.isNotEmpty()) viewModel.deleteSelectedAlbums()\n'
        '                    },\n'
    )
    new_del = (
        '                    onDeleteSelected = {\n'
        '                        if (selectedAlbumIds.isNotEmpty()) {\n'
        '                            showDeleteSelectionDialog = true\n'
        '                        } else if (selectedPinIds.isNotEmpty()) {\n'
        '                            viewModel.deletePinsFromCurrentBoard(selectedPinIds)\n'
        '                        }\n'
        '                    },\n'
    )
    if old_del in t:
        t = t.replace(old_del, new_del, 1); changed = True
        log("  ✓ delete button routes to dialog when albums present")

    # (e) Render DeleteSelectionDialog — insert after the Copy/Move dialogs, before the end of the composable
    if "DeleteSelectionDialog(" not in t:
        anchor = '    CopyOrMoveImagesDialog(\n        isOpen = showMoveDialog,\n'
        # find the closing of Move dialog call; insert after it
        idx = t.find(anchor)
        if idx >= 0:
            # find the closing "    )\n" of Move dialog
            close_idx = t.find("    )\n", idx)
            if close_idx >= 0:
                insert_at = close_idx + len("    )\n")
                dialog_block = (
                    '\n'
                    '    // Delete selection (albums involved) — ask how\n'
                    '    DeleteSelectionDialog(\n'
                    '        isOpen = showDeleteSelectionDialog,\n'
                    '        pinCount = selectedPinIds.size,\n'
                    '        albumCount = selectedAlbumIds.size,\n'
                    '        onDismiss = { showDeleteSelectionDialog = false },\n'
                    '        onDissolve = {\n'
                    '            viewModel.deleteSelectionAndAlbums(selectedPinIds, selectedAlbumIds, com.example.viewmodel.DeleteSelectionMode.DISSOLVE)\n'
                    '            showDeleteSelectionDialog = false\n'
                    '        },\n'
                    '        onDeleteAll = {\n'
                    '            viewModel.deleteSelectionAndAlbums(selectedPinIds, selectedAlbumIds, com.example.viewmodel.DeleteSelectionMode.DELETE_WITH_CONTENTS)\n'
                    '            showDeleteSelectionDialog = false\n'
                    '        }\n'
                    '    )\n'
                )
                t = t[:insert_at] + dialog_block + t[insert_at:]
                changed = True
                log("  ✓ DeleteSelectionDialog rendered")

    # Import DeleteSelectionDialog
    if "import com.example.ui.dialogs.DeleteSelectionDialog" not in t:
        t = t.replace(
            'import com.example.ui.dialogs.DeleteFromAllConfirmationDialog\n',
            'import com.example.ui.dialogs.DeleteFromAllConfirmationDialog\n'
            'import com.example.ui.dialogs.DeleteSelectionDialog\n',
            1,
        )
        changed = True

    # (f) Banner button "Move here"/"Copy here"
    old_banner_row = (
        '                Text(\n'
        '                    text = "Tap an album to ${if (transfer.mode == com.example.viewmodel.AlbumTransferMode.MOVE) "move" else "copy"} ${transfer.pinIds.size} image${if (transfer.pinIds.size > 1) "s" else ""}",\n'
        '                    color = Color.White,\n'
        '                    fontSize = 13.sp,\n'
        '                    fontWeight = FontWeight.Medium,\n'
        '                    modifier = Modifier.weight(1f)\n'
        '                )\n'
    )
    new_banner_row = (
        '                Text(\n'
        '                    text = "Tap an album to ${if (transfer.mode == com.example.viewmodel.AlbumTransferMode.MOVE) "move" else "copy"} ${transfer.pinIds.size} image${if (transfer.pinIds.size > 1) "s" else ""}",\n'
        '                    color = Color.White,\n'
        '                    fontSize = 13.sp,\n'
        '                    fontWeight = FontWeight.Medium,\n'
        '                    modifier = Modifier.weight(1f)\n'
        '                )\n'
        '                androidx.compose.material3.TextButton(\n'
        '                    onClick = { viewModel.executeAlbumTransferToCurrentBoard() },\n'
        '                    modifier = Modifier.testTag("album_transfer_here_btn")\n'
        '                ) {\n'
        '                    Text(\n'
        '                        text = if (transfer.mode == com.example.viewmodel.AlbumTransferMode.MOVE) "Move here" else "Copy here",\n'
        '                        color = Color(0xFF64B5F6),\n'
        '                        fontWeight = FontWeight.Bold,\n'
        '                        fontSize = 12.sp\n'
        '                    )\n'
        '                }\n'
    )
    if old_banner_row in t:
        t = t.replace(old_banner_row, new_banner_row, 1); changed = True
        log("  ✓ banner Move here / Copy here button")

    # (g) Unified banner display for DeletedPinsUndoState (albums + pins)
    old_banner_text = (
        '                        Text(\n'
        '                            text = "Deleted ${undoState.pins.size} image${if (undoState.pins.size > 1) "s" else ""}",\n'
    )
    new_banner_text = (
        '                        Text(\n'
        '                            text = run {\n'
        '                                val pinCount = undoState.pins.size\n'
        '                                val albumCount = undoState.albums.size\n'
        '                                when {\n'
        '                                    undoState.mode == com.example.viewmodel.DeleteSelectionMode.DISSOLVE && albumCount > 0 && pinCount > 0 ->\n'
        '                                        "Deleted $pinCount image${if (pinCount > 1) "s" else ""}, dissolved $albumCount album${if (albumCount > 1) "s" else ""}"\n'
        '                                    undoState.mode == com.example.viewmodel.DeleteSelectionMode.DISSOLVE && albumCount > 0 ->\n'
        '                                        "Dissolved $albumCount album${if (albumCount > 1) "s" else ""}"\n'
        '                                    undoState.mode == com.example.viewmodel.DeleteSelectionMode.DELETE_WITH_CONTENTS && albumCount > 0 ->\n'
        '                                        "Deleted $pinCount image${if (pinCount > 1) "s" else ""} + $albumCount album${if (albumCount > 1) "s" else ""}"\n'
        '                                    else ->\n'
        '                                        "Deleted $pinCount image${if (pinCount > 1) "s" else ""}"\n'
        '                                }\n'
        '                            },\n'
    )
    if old_banner_text in t:
        t = t.replace(old_banner_text, new_banner_text, 1); changed = True
        log("  ✓ undo banner label (albums + pins)")

    if changed: f.write_text(t, encoding="utf-8")


# ============================================================
# Standard pipeline (unchanged from prior turns)
# ============================================================
def read_app_version():
    p = PROJECT_ROOT / "app/build.gradle.kts"
    if not p.exists(): return ("unknown", "0")
    x = p.read_text(encoding="utf-8")
    vn = re.search(r'versionName\s*=\s*"([^"]+)"', x)
    vc = re.search(r"versionCode\s*=\s*(\d+)", x)
    return (vn.group(1) if vn else "unknown", vc.group(1) if vc else "0")


def ensure_release_keystore():
    log("\n=== release.keystore ===")
    ks = PROJECT_ROOT / KEYSTORE_FILE
    if ks.exists() and ks.stat().st_size > 0:
        r = subprocess.run(["keytool", "-list", "-keystore", str(ks), "-storepass", KEYSTORE_PASS],
                           capture_output=True, text=True)
        if r.returncode == 0 and KEYSTORE_ALIAS in r.stdout:
            log("  ✓ OK"); return
        sys.exit(1)
    r = subprocess.run(["keytool", "-genkeypair", "-v", "-keystore", str(ks),
                        "-alias", KEYSTORE_ALIAS, "-keyalg", "RSA", "-keysize", "2048",
                        "-validity", KEYSTORE_VALIDITY, "-storepass", KEYSTORE_PASS,
                        "-keypass", KEYSTORE_PASS, "-dname", KEYSTORE_DNAME],
                       capture_output=True, text=True)
    if r.returncode != 0: sys.exit(1)


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
    log("\n=== build.gradle.kts ===")
    p = PROJECT_ROOT / "app/build.gradle.kts"
    if not p.exists(): sys.exit(1)
    x = p.read_text(encoding="utf-8"); orig = x
    idx = x.find('create("release")')
    if idx == -1: sys.exit(1)
    span = find_braced(x, idx)
    if not span: sys.exit(1)
    ob, cb = span
    if f'storeFile = file("${{rootDir}}/{KEYSTORE_FILE}")' not in x[ob:cb]:
        nc = (f'\n      storeFile = file("${{rootDir}}/{KEYSTORE_FILE}")\n'
              f'      storePassword = "{KEYSTORE_PASS}"\n'
              f'      keyAlias = "{KEYSTORE_ALIAS}"\n'
              f'      keyPassword = "{KEYSTORE_PASS}"\n    ')
        x = x[:ob+1] + nc + x[cb:]
    if x != orig: p.write_text(x, encoding="utf-8")


def latest_gradle_version():
    try:
        req = urllib.request.Request("https://api.github.com/repos/gradle/gradle/releases/latest",
                                     headers={"User-Agent": "pinboard"})
        with urllib.request.urlopen(req, timeout=30) as r:
            tag = json.load(r).get("tag_name", "").lstrip("v")
            if tag: return tag
    except Exception: pass
    pr = PROJECT_ROOT / "gradle/wrapper/gradle-wrapper.properties"
    if pr.exists():
        m = re.search(r"gradle-([\d.]+)-bin\.zip", pr.read_text(encoding="utf-8"))
        if m: return m.group(1)
    return "9.3.1"


def ensure_gradle_wrapper():
    log("\n=== gradle wrapper ===")
    gw = PROJECT_ROOT / "gradlew"; gwb = PROJECT_ROOT / "gradlew.bat"
    jar = PROJECT_ROOT / "gradle/wrapper/gradle-wrapper.jar"
    if gw.exists() and gwb.exists() and jar.exists(): log("  ✓"); return
    ver = latest_gradle_version(); base = f"https://raw.githubusercontent.com/gradle/gradle/v{ver}"
    for url, dest in [(f"{base}/gradlew", gw), (f"{base}/gradlew.bat", gwb),
                      (f"{base}/gradle/wrapper/gradle-wrapper.jar", jar)]:
        if dest.exists() and dest.stat().st_size > 0: continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try: urllib.request.urlretrieve(url, dest)
        except Exception as e: log(e); sys.exit(1)
    try: os.chmod(gw, 0o755)
    except: pass


def write_workflow():
    log("\n=== workflow ===")
    wf = PROJECT_ROOT / ".github/workflows"; wf.mkdir(parents=True, exist_ok=True)
    (wf / "build.yml").write_text(WORKFLOW_YAML, encoding="utf-8")


def setup_git():
    log("\n=== git ===")
    if not (PROJECT_ROOT / ".git").exists():
        run(["git", "init"]); run(["git", "branch", "-M", "main"])
    if not subprocess.run(["git", "config", "--global", "user.name"], capture_output=True, text=True).stdout.strip():
        run(["git", "config", "--global", "user.name", "PinBoard Build"])
    if not subprocess.run(["git", "config", "--global", "user.email"], capture_output=True, text=True).stdout.strip():
        run(["git", "config", "--global", "user.email", "pinboard@build.local"])
    gi = PROJECT_ROOT / ".gitignore"
    req = ["build/", "*/build/", ".gradle/", "local.properties", "*.iml", ".idea/", ".cxx/",
           ".DS_Store", ".kotlin/", ".env", "_downloads/", "*.jks", "*.keystore",
           "!debug.keystore", "!release.keystore"]
    ex = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    merged = list(ex)
    for l in req:
        if l not in merged: merged.append(l)
    gi.write_text("\n".join(merged) + "\n", encoding="utf-8")
    run(["git", "add", "-A"])
    for n in (KEYSTORE_FILE, "debug.keystore"):
        if (PROJECT_ROOT / n).exists(): run(["git", "add", "-f", n], check=False)
    if subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip():
        run(["git", "commit", "-m", "Select-mode round 2: label, save icon, album delete dialog, gestures, banner"])


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
    subprocess.run(["gh", "run", "download", str(run_id), "--repo", repo_full,
                    "--name", ARTIFACT, "--dir", str(dl)], check=True)
    return dl


def move_apk(dl):
    log("\n=== Move APK ===")
    apks = list(dl.glob("*.apk"))
    if not apks: sys.exit(1)
    apk = apks[0]; vn, vc = read_app_version()
    log(f"  App: {vn} ({vc})")
    tf = PROJECT_ROOT / "Apk Directory.txt"
    target = Path(tf.read_text(encoding="utf-8").strip()) if tf.exists() else Path.home() / "Downloads"
    target.mkdir(parents=True, exist_ok=True)
    dest = target / f"{APP_NAME}-v{vn}-{vc}{apk.suffix}"
    if dest.exists():
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = target / f"{APP_NAME}-v{vn}-{vc}_{ts}{apk.suffix}"
    shutil.copy2(apk, dest)
    log(f"  ✓ {dest}")
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


def verify_apk(apk):
    log("\n=== Verify APK ===")
    s = find_apksigner()
    if not s: log("  skip"); return
    r = subprocess.run([s, "verify", "--verbose", "--print-certs", str(apk)], capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    log("\n".join(f"  {l}" for l in out.splitlines()[:8]))
    if r.returncode != 0 or "Verifies" not in out: log("  ✗"); sys.exit(1)
    log("  ✓")


def find_adb():
    if tool_available("adb"): return "adb"
    for c in [Path(os.environ.get("LOCALAPPDATA", "")) / "Android/Sdk/platform-tools/adb.exe",
              Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe",
              Path.home() / "Library/Android/sdk/platform-tools/adb", Path("/usr/local/bin/adb")]:
        if c.exists(): return str(c)
    return None


def adb_device(adb):
    try:
        r = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=5)
        if r.returncode != 0: return False
        return any("\tdevice" in l or " device" in l for l in r.stdout.strip().splitlines()[1:])
    except: return False


def device_install(apk):
    log("\n=== Device install ===")
    adb = find_adb()
    if not adb or not adb_device(adb):
        log(f"  no device: adb uninstall {PACKAGE_ID}; adb install \"{apk}\"")
        return
    subprocess.run([adb, "uninstall", PACKAGE_ID], capture_output=True, timeout=60)
    r = subprocess.run([adb, "install", str(apk)], capture_output=True, text=True, timeout=300)
    out = (r.stdout + r.stderr).strip()
    log(f"  {out}")
    if "Success" in out: log("  ✓ Installed")


def main():
    log("=" * 70)
    log("PinBoard — select-mode fixes round 2")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    patch_multiselect_bar()
    patch_copy_move_dialog()
    patch_album_card()
    patch_new_delete_dialog()
    patch_viewmodel()
    patch_gallery_screen()

    ensure_release_keystore()
    patch_build_gradle()
    ensure_gradle_wrapper()
    write_workflow()
    setup_git()
    verify_keystore_tracked()
    repo = ensure_github_repo()
    dl = trigger_and_download(repo)
    apk = move_apk(dl)
    verify_apk(apk)
    device_install(apk)
    log("\n" + "=" * 70)
    log(f"DONE -> {apk}")
    log("=" * 70)


if __name__ == "__main__":
    main()