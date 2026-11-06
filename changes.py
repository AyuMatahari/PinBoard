#!/usr/bin/env python3
"""
PinBoard Gallery — Sub-album selection, drill-in transfer, refresh, board picker
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
      GRADLE_OPTS: "-Djava.awt.headless=true"
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
          [ -f release.keystore ] || exit 1
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


def find_function_end(t, start_marker):
    idx = t.find(start_marker)
    if idx < 0: return -1
    open_brace = t.find("{", idx + len(start_marker) - 1)
    if open_brace < 0: return -1
    depth = 1
    i = open_brace + 1
    while i < len(t) and depth > 0:
        c = t[i]
        if c == '"':
            i += 1
            while i < len(t):
                if t[i] == "\\": i += 2; continue
                if t[i] == '"': break
                i += 1
        elif c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0: return i + 1
        i += 1
    return -1


# ============================================================
# PATCH 1 — ViewModel: refresh counters, nested combine, opened-album transfer
# ============================================================
def patch_viewmodel():
    log("\n=== PATCH: ViewModel ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # 1a. Add imageRefreshCounters state + refreshImage method
    if "_imageRefreshCounters" not in t:
        anchor = (
            "    private val _pendingAlbumTransfer = MutableStateFlow<PendingAlbumTransfer?>(null)\n"
            "    val pendingAlbumTransfer: StateFlow<PendingAlbumTransfer?> = _pendingAlbumTransfer.asStateFlow()\n"
        )
        add = (
            anchor +
            "\n"
            "    private val _imageRefreshCounters = MutableStateFlow<Map<String, Int>>(emptyMap())\n"
            "    val imageRefreshCounters: StateFlow<Map<String, Int>> = _imageRefreshCounters.asStateFlow()\n"
            "\n"
            "    fun refreshImage(pinId: String) {\n"
            "        val current = _imageRefreshCounters.value[pinId] ?: 0\n"
            "        _imageRefreshCounters.value = _imageRefreshCounters.value + (pinId to (current + 1))\n"
            "    }\n"
        )
        if anchor in t:
            t = t.replace(anchor, add, 1); changed = True
            log("  ✓ imageRefreshCounters + refreshImage")
        else:
            log("  ⚠ pendingAlbumTransfer anchor missing for refreshImage")

    # 1b. combineSelectedPinsToNewAlbum: nest under activeAlbum if inside one
    if "val parentAlbumId = _activeAlbum.value?.id" not in t:
        old_combine = (
            "            val entity = CustomAlbumEntity(\n"
            "                id = albumId, boardId = board.id, parentAlbumId = null,\n"
            "                title = \"Album (${selectedPins.size} images)\",\n"
            "                sourceUrl = \"\", dateAddedMillis = albumDate,\n"
            "                orderIndex = 0, isFavorite = false\n"
            "            )\n"
        )
        new_combine = (
            "            // If user is inside an album, nest the new one under it\n"
            "            val parentAlbumId = _activeAlbum.value?.id\n"
            "            val entity = CustomAlbumEntity(\n"
            "                id = albumId, boardId = board.id, parentAlbumId = parentAlbumId,\n"
            "                title = \"Album (${selectedPins.size} images)\",\n"
            "                sourceUrl = \"\", dateAddedMillis = albumDate,\n"
            "                orderIndex = 0, isFavorite = false\n"
            "            )\n"
        )
        if old_combine in t:
            t = t.replace(old_combine, new_combine, 1); changed = True
            log("  ✓ combine nests under active album")
        else:
            log("  ⚠ combine entity anchor missing")

    # 1c. executeAlbumTransferToCurrentBoard: use opened album as target
    marker = "    fun executeAlbumTransferToCurrentBoard() {"
    if "// New: opened-album-aware" not in t and marker in t:
        end_idx = find_function_end(t, marker)
        if end_idx > 0:
            idx = t.find(marker)
            new_fn = '''    // New: opened-album-aware executeAlbumTransferToCurrentBoard
    fun executeAlbumTransferToCurrentBoard() {
        val transfer = _pendingAlbumTransfer.value ?: return
        val currentBoard = _currentBoard.value ?: return
        val openedAlbum = _activeAlbum.value
        viewModelScope.launch {
            val ctx = appContext ?: return@launch
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            try {
                if (openedAlbum != null) {
                    // Transfer directly into opened album
                    val (pinCount, albumCount) = performTransfer(
                        dao = dao, sourceBoardId = transfer.sourceBoardId,
                        pinIds = transfer.pinIds, albumIds = transfer.albumIds,
                        targetBoardId = currentBoard.id, targetAlbumId = openedAlbum.id,
                        mode = transfer.mode
                    )
                    val verb = if (transfer.mode == AlbumTransferMode.MOVE) "Moved" else "Copied"
                    val pinPart = "$pinCount image${if (pinCount != 1) "s" else ""}"
                    val albumPart = if (albumCount > 0) " + $albumCount album${if (albumCount != 1) "s" else ""}" else ""
                    _snackbarMessage.value = "$verb $pinPart$albumPart into \\"${openedAlbum.title}\\""
                } else if (currentBoard.id == transfer.sourceBoardId) {
                    if (transfer.mode == AlbumTransferMode.MOVE) {
                        moveToTopInternal(transfer.sourceBoardId, transfer.pinIds, transfer.albumIds, dao)
                        _snackbarMessage.value = "Moved to top of board"
                    } else {
                        _snackbarMessage.value = "Already on this board"
                    }
                } else {
                    val (pinCount, albumCount) = performTransfer(
                        dao = dao, sourceBoardId = transfer.sourceBoardId,
                        pinIds = transfer.pinIds, albumIds = transfer.albumIds,
                        targetBoardId = currentBoard.id, targetAlbumId = null,
                        mode = transfer.mode
                    )
                    val verb = if (transfer.mode == AlbumTransferMode.MOVE) "Moved" else "Copied"
                    val pinPart = "$pinCount image${if (pinCount != 1) "s" else ""}"
                    val albumPart = if (albumCount > 0) " + $albumCount album${if (albumCount != 1) "s" else ""}" else ""
                    _snackbarMessage.value = "$verb $pinPart$albumPart to ${currentBoard.title}"
                }
                // Refresh current board view
                val refreshed = withContext(Dispatchers.IO) { dao.getPinsForBoard(currentBoard.id).map { it.toPinItem() } }
                val refreshedAlbums = withContext(Dispatchers.IO) { dao.getAlbumsForBoard(currentBoard.id) }
                withContext(Dispatchers.Main) {
                    _rawPins.value = refreshed
                    _customAlbums.value = refreshedAlbums
                    _currentBoard.value = currentBoard.copy(pins = refreshed, pinCount = refreshed.size)
                    updateDisplayedPins()
                }
            } catch (e: IllegalStateException) {
                _snackbarMessage.value = e.message ?: "Cannot transfer"
            } finally {
                _pendingAlbumTransfer.value = null
                withContext(Dispatchers.Main) { clearSelection() }
            }
        }
    }
'''
            t = t[:idx] + new_fn + t[end_idx:]
            changed = True
            log("  ✓ executeAlbumTransferToCurrentBoard — opened-album aware")
        else:
            log("  ⚠ could not find function end")

    if changed:
        f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 2 — PinCard: refresh counter support
# ============================================================
def patch_pin_card():
    log("\n=== PATCH: PinCard (refresh counter) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/PinCard.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "refreshCounter: Int = 0" in t:
        log("  ✓ already patched"); return

    old_sig = (
        "    hideTitleAndAuthor: Boolean = false,\n"
        "    isNew: Boolean = false,\n"
        "    onClick: () -> Unit,\n"
    )
    new_sig = (
        "    hideTitleAndAuthor: Boolean = false,\n"
        "    isNew: Boolean = false,\n"
        "    refreshCounter: Int = 0,\n"
        "    onClick: () -> Unit,\n"
    )
    if old_sig not in t:
        log("  ⚠ signature anchor missing"); return
    t = t.replace(old_sig, new_sig, 1)

    old_model = (
        "            AsyncImage(\n"
        "                model = ImageRequest.Builder(context)\n"
        "                    .data(pin.thumbnailUrl.ifBlank { pin.imageUrl })\n"
        "                    .crossfade(true)\n"
        "                    .build(),\n"
    )
    new_model = (
        "            AsyncImage(\n"
        "                model = ImageRequest.Builder(context)\n"
        "                    .data(pin.thumbnailUrl.ifBlank { pin.imageUrl })\n"
        "                    .apply {\n"
        "                        if (refreshCounter > 0) {\n"
        "                            memoryCacheKey(\"pin-thumb:${pin.id}:r$refreshCounter\")\n"
        "                            diskCacheKey(\"pin-thumb:${pin.id}:r$refreshCounter\")\n"
        "                        }\n"
        "                    }\n"
        "                    .crossfade(true)\n"
        "                    .build(),\n"
    )
    if old_model in t:
        t = t.replace(old_model, new_model, 1)
    else:
        log("  ⚠ AsyncImage model anchor missing (may still work if not refreshed)")

    f.write_text(t, encoding="utf-8")
    log("  ✓ PinCard patched")


# ============================================================
# PATCH 3 — FullscreenGalleryViewer: use ViewModel counter + callback
# ============================================================
def patch_fullscreen():
    log("\n=== PATCH: FullscreenGalleryViewer ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/FullscreenGalleryViewer.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # 3a. Add params
    old_sig = (
        "    onDownloadSingle: (PinItem) -> Unit,\n"
        "    disableArrowNavigation: Boolean = false,\n"
        "    modifier: Modifier = Modifier\n"
    )
    new_sig = (
        "    onDownloadSingle: (PinItem) -> Unit,\n"
        "    disableArrowNavigation: Boolean = false,\n"
        "    refreshCounters: Map<String, Int> = emptyMap(),\n"
        "    onRefreshImage: (PinItem) -> Unit = {},\n"
        "    modifier: Modifier = Modifier\n"
    )
    if old_sig in t:
        t = t.replace(old_sig, new_sig, 1); changed = True
        log("  ✓ new params")
    else:
        log("  ⚠ signature anchor missing")

    # 3b. Change button onClick
    old_btn = (
        "                        IconButton(\n"
        "                            onClick = {\n"
        "                                val key = currentPin.id\n"
        "                                imageRefreshKeys[key] = (imageRefreshKeys[key] ?: 0) + 1\n"
        "                                Toast.makeText(context, \"Refreshing image...\", Toast.LENGTH_SHORT).show()\n"
        "                            },\n"
    )
    new_btn = (
        "                        IconButton(\n"
        "                            onClick = {\n"
        "                                onRefreshImage(currentPin)\n"
        "                                Toast.makeText(context, \"Refreshing image...\", Toast.LENGTH_SHORT).show()\n"
        "                            },\n"
    )
    if old_btn in t:
        t = t.replace(old_btn, new_btn, 1); changed = True
        log("  ✓ button uses onRefreshImage")
    else:
        log("  ⚠ button anchor missing")

    # 3c. Change AsyncImage model to use passed map
    old_async = (
        "                val pageRefreshKey = imageRefreshKeys[pin.id] ?: 0\n"
        "                AsyncImage(\n"
        "                    model = ImageRequest.Builder(context)\n"
        "                        .data(pin.imageUrl)\n"
        "                        .apply {\n"
        "                            if (pageRefreshKey > 0) {\n"
        "                                memoryCacheKey(\"${pin.imageUrl}#refresh=$pageRefreshKey\")\n"
        "                                diskCacheKey(\"${pin.imageUrl}#refresh=$pageRefreshKey\")\n"
        "                            }\n"
        "                        }\n"
    )
    new_async = (
        "                val pageRefreshKey = refreshCounters[pin.id] ?: 0\n"
        "                AsyncImage(\n"
        "                    model = ImageRequest.Builder(context)\n"
        "                        .data(pin.imageUrl)\n"
        "                        .apply {\n"
        "                            if (pageRefreshKey > 0) {\n"
        "                                memoryCacheKey(\"pin-full:${pin.id}:r$pageRefreshKey\")\n"
        "                                diskCacheKey(\"pin-full:${pin.id}:r$pageRefreshKey\")\n"
        "                            }\n"
        "                        }\n"
    )
    if old_async in t:
        t = t.replace(old_async, new_async, 1); changed = True
        log("  ✓ AsyncImage uses passed map")
    else:
        log("  ⚠ AsyncImage anchor missing")

    # 3d. Remove local imageRefreshKeys if still present
    if "val imageRefreshKeys = remember { mutableStateMapOf<String, Int>() }" in t:
        t = t.replace(
            "    // Per-pin refresh counter; increment forces a fresh network fetch\n"
            "    val imageRefreshKeys = remember { mutableStateMapOf<String, Int>() }\n",
            "",
            1,
        )
        changed = True
        log("  ✓ removed local imageRefreshKeys")

    if changed:
        f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 4 — New BoardPickerDialog.kt
# ============================================================
def patch_board_picker_dialog():
    log("\n=== PATCH: BoardPickerDialog (new file) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/dialogs/BoardPickerDialog.kt"
    if f.exists():
        log("  ✓ already exists"); return

    content = r'''package com.example.ui.dialogs

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.model.BoardHistoryItem
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary


@OptIn(ExperimentalLayoutApi::class, ExperimentalFoundationApi::class)
@Composable
fun BoardPickerDialog(
    isOpen: Boolean,
    boards: List<BoardHistoryItem>,
    currentBoardUrl: String?,
    onDismiss: () -> Unit,
    onSelectBoard: (String) -> Unit
) {
    if (!isOpen) return

    var filter by remember { mutableStateOf("") }

    val filtered = remember(boards, filter) {
        if (filter.isBlank()) boards
        else boards.filter { it.title.contains(filter, ignoreCase = true) || it.ownerName.contains(filter, ignoreCase = true) }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text("Switch board", fontWeight = FontWeight.Bold, fontSize = 16.sp)
        },
        text = {
            androidx.compose.foundation.layout.Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 500.dp)
                    .verticalScroll(rememberScrollState())
            ) {
                FlowRow(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    filtered.forEach { item ->
                        val isCurrent = currentBoardUrl?.trimEnd('/')?.equals(item.url.trimEnd('/'), ignoreCase = true) == true
                        Surface(
                            shape = RoundedCornerShape(20.dp),
                            color = if (isCurrent) PinterestRed else PinterestPillGray,
                            modifier = Modifier
                                .clickable {
                                    onSelectBoard(item.url)
                                    onDismiss()
                                }
                                .testTag("board_picker_pill_${item.url.hashCode()}")
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp)
                            ) {
                                val isFav = item.boardId == "board_favorites" || item.url.contains("favorites")
                                val isMySave = item.boardId == "board_my_save" || item.url.contains("my_save")
                                val isDump = item.boardId == "board_dump" || item.url.contains("dump")

                                Icon(
                                    imageVector = when {
                                        isFav -> Icons.Default.Favorite
                                        isMySave -> Icons.Default.Bookmark
                                        isDump -> Icons.Default.Folder
                                        item.isCustom -> Icons.Default.Folder
                                        else -> Icons.Default.Link
                                    },
                                    contentDescription = null,
                                    tint = if (isCurrent) Color.White else PinterestRed,
                                    modifier = Modifier.size(13.dp)
                                )
                                Spacer(Modifier.width(6.dp))
                                Text(
                                    text = item.title.ifBlank { "Board" },
                                    fontSize = 13.sp,
                                    fontWeight = if (isCurrent) FontWeight.Bold else FontWeight.Medium,
                                    color = if (isCurrent) Color.White else PinterestBlack
                                )
                                if (item.isCustom && !isFav && !isMySave && !isDump) {
                                    Spacer(Modifier.width(4.dp))
                                    Text(
                                        text = "· Custom",
                                        fontSize = 10.sp,
                                        color = if (isCurrent) Color.White.copy(alpha = 0.7f) else PinterestTextSecondary
                                    )
                                }
                            }
                        }
                    }
                }

                if (filtered.isEmpty()) {
                    Spacer(Modifier.height(12.dp))
                    Text(
                        "No boards match.",
                        fontSize = 12.sp,
                        color = PinterestTextSecondary
                    )
                }
            }
        },
        confirmButton = {},
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Close", color = PinterestBlack) }
        },
        shape = RoundedCornerShape(20.dp)
    )
}
'''
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    log("  ✓ BoardPickerDialog.kt created")


# ============================================================
# PATCH 5 — BoardHeader: clickable title + "BOARDS" label
# ============================================================
def patch_board_header():
    log("\n=== PATCH: BoardHeader ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/BoardHeader.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # 5a. Add param
    old_sig = "    onEditCurrentCustomBoard: () -> Unit = {},\n"
    new_sig = (
        "    onEditCurrentCustomBoard: () -> Unit = {},\n"
        "    onOpenBoardPicker: () -> Unit = {},\n"
    )
    if old_sig in t and "onOpenBoardPicker" not in t:
        t = t.replace(old_sig, new_sig, 1); changed = True
        log("  ✓ onOpenBoardPicker param added")

    # 5b. Make big title clickable
    old_title = (
        "                Text(\n"
        "                    text = board.title,\n"
        "                    style = MaterialTheme.typography.headlineSmall.copy(\n"
        "                        fontWeight = FontWeight.ExtraBold,\n"
        "                        fontSize = 22.sp\n"
        "                    ),\n"
        "                    color = MaterialTheme.colorScheme.onSurface,\n"
        "                    maxLines = 2,\n"
        "                    overflow = TextOverflow.Ellipsis\n"
        "                )\n"
    )
    new_title = (
        "                Text(\n"
        "                    text = board.title,\n"
        "                    style = MaterialTheme.typography.headlineSmall.copy(\n"
        "                        fontWeight = FontWeight.ExtraBold,\n"
        "                        fontSize = 22.sp\n"
        "                    ),\n"
        "                    color = MaterialTheme.colorScheme.onSurface,\n"
        "                    maxLines = 2,\n"
        "                    overflow = TextOverflow.Ellipsis,\n"
        "                    modifier = Modifier\n"
        "                        .clickable { onOpenBoardPicker() }\n"
        "                        .testTag(\"board_title_open_picker\")\n"
        "                )\n"
    )
    if old_title in t:
        t = t.replace(old_title, new_title, 1); changed = True
        log("  ✓ title clickable")

    # 5c. Make "BOARDS (HOLD CUSTOM TO EDIT)" row clickable
    old_label = (
        "            Row(\n"
        "                verticalAlignment = Alignment.CenterVertically,\n"
        "                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)\n"
        "            ) {\n"
        "                Icon(\n"
        "                    imageVector = Icons.Default.History,\n"
        "                    contentDescription = null,\n"
        "                    tint = PinterestTextSecondary,\n"
        "                    modifier = Modifier.size(14.dp)\n"
        "                )\n"
        "                Spacer(modifier = Modifier.width(4.dp))\n"
        "                Text(\n"
        "                    text = \"BOARDS (HOLD CUSTOM TO EDIT)\",\n"
        "                    style = MaterialTheme.typography.labelSmall.copy(\n"
        "                        fontWeight = FontWeight.Bold,\n"
        "                        letterSpacing = 0.8.sp,\n"
        "                        fontSize = 10.sp,\n"
        "                        color = PinterestTextSecondary\n"
        "                    )\n"
        "                )\n"
        "            }\n"
    )
    new_label = (
        "            Row(\n"
        "                verticalAlignment = Alignment.CenterVertically,\n"
        "                modifier = Modifier\n"
        "                    .padding(horizontal = 16.dp, vertical = 4.dp)\n"
        "                    .clickable { onOpenBoardPicker() }\n"
        "                    .testTag(\"boards_label_open_picker\")\n"
        "            ) {\n"
        "                Icon(\n"
        "                    imageVector = Icons.Default.History,\n"
        "                    contentDescription = null,\n"
        "                    tint = PinterestTextSecondary,\n"
        "                    modifier = Modifier.size(14.dp)\n"
        "                )\n"
        "                Spacer(modifier = Modifier.width(4.dp))\n"
        "                Text(\n"
        "                    text = \"BOARDS (HOLD CUSTOM TO EDIT) — TAP TO SWITCH\",\n"
        "                    style = MaterialTheme.typography.labelSmall.copy(\n"
        "                        fontWeight = FontWeight.Bold,\n"
        "                        letterSpacing = 0.8.sp,\n"
        "                        fontSize = 10.sp,\n"
        "                        color = PinterestTextSecondary\n"
        "                    )\n"
        "                )\n"
        "            }\n"
        "        }\n"
    )
    if old_label in t:
        # Replace with new, but need to fix brace balance
        # old_label has closing "}\n" that also closes the containing if - too aggressive
        # Safer: replace just the Row body
        t = t.replace(
            "            Row(\n"
            "                verticalAlignment = Alignment.CenterVertically,\n"
            "                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)\n"
            "            ) {\n"
            "                Icon(\n"
            "                    imageVector = Icons.Default.History,\n"
            "                    contentDescription = null,\n"
            "                    tint = PinterestTextSecondary,\n"
            "                    modifier = Modifier.size(14.dp)\n"
            "                )\n"
            "                Spacer(modifier = Modifier.width(4.dp))\n"
            "                Text(\n"
            "                    text = \"BOARDS (HOLD CUSTOM TO EDIT)\",\n"
            "                    style = MaterialTheme.typography.labelSmall.copy(\n"
            "                        fontWeight = FontWeight.Bold,\n"
            "                        letterSpacing = 0.8.sp,\n"
            "                        fontSize = 10.sp,\n"
            "                        color = PinterestTextSecondary\n"
            "                    )\n"
            "                )\n"
            "            }\n",
            "            Row(\n"
            "                verticalAlignment = Alignment.CenterVertically,\n"
            "                modifier = Modifier\n"
            "                    .padding(horizontal = 16.dp, vertical = 4.dp)\n"
            "                    .clickable { onOpenBoardPicker() }\n"
            "                    .testTag(\"boards_label_open_picker\")\n"
            "            ) {\n"
            "                Icon(\n"
            "                    imageVector = Icons.Default.History,\n"
            "                    contentDescription = null,\n"
            "                    tint = PinterestTextSecondary,\n"
            "                    modifier = Modifier.size(14.dp)\n"
            "                )\n"
            "                Spacer(modifier = Modifier.width(4.dp))\n"
            "                Text(\n"
            "                    text = \"BOARDS (HOLD CUSTOM TO EDIT) — TAP TO SWITCH\",\n"
            "                    style = MaterialTheme.typography.labelSmall.copy(\n"
            "                        fontWeight = FontWeight.Bold,\n"
            "                        letterSpacing = 0.8.sp,\n"
            "                        fontSize = 10.sp,\n"
            "                        color = PinterestTextSecondary\n"
            "                    )\n"
            "                )\n"
            "            }\n",
            1,
        )
        changed = True
        log("  ✓ BOARDS label clickable")

    if changed:
        f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 6 — PinBoardGalleryScreen wiring
# ============================================================
def patch_gallery_screen():
    log("\n=== PATCH: PinBoardGalleryScreen ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # 6a. Collect imageRefreshCounters + add board-picker state
    if "val imageRefreshCounters by viewModel.imageRefreshCounters" not in t:
        anchor = "    val pendingAlbumTransfer by viewModel.pendingAlbumTransfer.collectAsStateWithLifecycle()\n"
        add = (
            anchor +
            "    val imageRefreshCounters by viewModel.imageRefreshCounters.collectAsStateWithLifecycle()\n"
        )
        if anchor in t:
            t = t.replace(anchor, add, 1); changed = True
            log("  ✓ imageRefreshCounters collected")

    if "var isBoardPickerOpen" not in t:
        anchor = "    var showDeleteSelectionDialog by remember { mutableStateOf(false) }\n"
        add = (
            anchor +
            "    var isBoardPickerOpen by remember { mutableStateOf(false) }\n"
        )
        if anchor in t:
            t = t.replace(anchor, add, 1); changed = True
            log("  ✓ isBoardPickerOpen state")

    # 6b. liveActiveAlbum (reactive) — insert after customDateAlbums declaration
    if "val liveActiveAlbum = remember(activeAlbum, customDateAlbums)" not in t:
        anchor = (
            "    val topLevelCustomAlbums = remember(customDateAlbums) {\n"
            "        customDateAlbums.filter { it.parentAlbumId == null }\n"
            "    }\n"
        )
        add = (
            anchor +
            "\n"
            "    // Reactive re-derivation of the currently opened album from live data.\n"
            "    val liveActiveAlbum = remember(activeAlbum, customDateAlbums) {\n"
            "        activeAlbum?.let { a -> customDateAlbums.firstOrNull { it.id == a.id } ?: a }\n"
            "    }\n"
        )
        if anchor in t:
            t = t.replace(anchor, add, 1); changed = True
            log("  ✓ liveActiveAlbum derived")
        else:
            log("  ⚠ topLevelCustomAlbums anchor missing")

    # 6c. currentSubAlbums — use liveActiveAlbum
    old_subs = (
        "    val currentSubAlbums = remember(activeAlbum, customDateAlbums) {\n"
        "        val active = activeAlbum\n"
        "        if (active != null) {\n"
        "            (customDateAlbums.filter { it.parentAlbumId == active.id } + active.subAlbums).distinctBy { it.id }\n"
        "        } else {\n"
        "            emptyList()\n"
        "        }\n"
        "    }\n"
    )
    new_subs = (
        "    val currentSubAlbums = remember(liveActiveAlbum, customDateAlbums) {\n"
        "        val active = liveActiveAlbum\n"
        "        if (active != null) {\n"
        "            (customDateAlbums.filter { it.parentAlbumId == active.id } + active.subAlbums).distinctBy { it.id }\n"
        "        } else {\n"
        "            emptyList()\n"
        "        }\n"
        "    }\n"
    )
    if old_subs in t:
        t = t.replace(old_subs, new_subs, 1); changed = True
        log("  ✓ currentSubAlbums uses liveActiveAlbum")

    # 6d. Opened-album sub-albums: add selection + pending transfer drill-in
    old_active_view = (
        "                } else if (activeAlbum != null) {\n"
        "                    // 2. Opened Album mode: display sub-albums (if any) and collection of images for the selected album\n"
        "                    if (currentSubAlbums.isNotEmpty()) {\n"
        "                        items(\n"
        "                            items = currentSubAlbums,\n"
        "                            key = { alb -> \"subalbum_${alb.id}_${alb.isFavorite}\" }\n"
        "                        ) { subAlb ->\n"
        "                            AlbumCard(\n"
        "                                album = subAlb,\n"
        "                                columnCount = columnCount,\n"
        "                                isFavorite = subAlb.isFavorite,\n"
        "                                isPortrait = portraitAlbumCards,\n"
        "                                onClick = {\n"
        "                                    viewModel.openAlbum(subAlb)\n"
        "                                },\n"
        "                                onLongClick = {\n"
        "                                    viewModel.toggleAlbumFavorites(subAlb.id, subAlb.title, subAlb.pins)\n"
        "                                },\n"
        "                                onSwipePreview = {\n"
        "                                    previewAlbum = subAlb\n"
        "                                }\n"
        "                            )\n"
        "                        }\n"
        "                    }\n"
        "\n"
        "                    val albumPins = activeAlbum!!.pins.sortedByDescending { it.dateAddedMillis }\n"
    )
    new_active_view = (
        "                } else if (liveActiveAlbum != null) {\n"
        "                    // 2. Opened Album mode: display sub-albums (if any) and collection of images for the selected album\n"
        "                    if (currentSubAlbums.isNotEmpty()) {\n"
        "                        items(\n"
        "                            items = currentSubAlbums,\n"
        "                            key = { alb -> \"subalbum_${alb.id}_${alb.isFavorite}\" }\n"
        "                        ) { subAlb ->\n"
        "                            val isSelectedAlb = selectedAlbumIds.contains(subAlb.id)\n"
        "                            AlbumCard(\n"
        "                                album = subAlb,\n"
        "                                columnCount = columnCount,\n"
        "                                isFavorite = subAlb.isFavorite,\n"
        "                                isPortrait = portraitAlbumCards,\n"
        "                                isSelected = isSelectedAlb,\n"
        "                                isSelectionMode = isSelectionMode,\n"
        "                                onClick = {\n"
        "                                    when {\n"
        "                                        pendingAlbumTransfer != null -> viewModel.executeAlbumTransfer(subAlb, currentBoard?.id ?: \"\")\n"
        "                                        else -> viewModel.openAlbum(subAlb)\n"
        "                                    }\n"
        "                                },\n"
        "                                onLongClick = {\n"
        "                                    when {\n"
        "                                        pendingAlbumTransfer != null -> viewModel.openAlbum(subAlb)\n"
        "                                        else -> viewModel.toggleAlbumFavorites(subAlb.id, subAlb.title, subAlb.pins)\n"
        "                                    }\n"
        "                                },\n"
        "                                onSelectToggle = { viewModel.toggleAlbumSelection(subAlb.id) },\n"
        "                                onSwipePreview = {\n"
        "                                    previewAlbum = subAlb\n"
        "                                }\n"
        "                            )\n"
        "                        }\n"
        "                    }\n"
        "\n"
        "                    val albumPins = allPinsForAlbums.filter { it.albumId == liveActiveAlbum!!.id }\n"
        "                        .sortedByDescending { it.dateAddedMillis }\n"
    )
    if old_active_view in t:
        t = t.replace(old_active_view, new_active_view, 1); changed = True
        log("  ✓ opened-album sub-albums — selection + drill-in + live pins")
    else:
        log("  ⚠ opened-album view anchor missing")

    # 6e. Update key/index use in opened-album itemsIndexed - need to handle liveActiveAlbum reference
    old_items_idx = (
        "                    itemsIndexed(\n"
        "                        items = albumPins,\n"
        "                        key = { index, pin -> \"album_${activeAlbum!!.id}_${pin.id}_$index\" }\n"
        "                    ) { index, pin ->\n"
    )
    new_items_idx = (
        "                    itemsIndexed(\n"
        "                        items = albumPins,\n"
        "                        key = { index, pin -> \"album_${liveActiveAlbum!!.id}_${pin.id}_$index\" }\n"
        "                    ) { index, pin ->\n"
    )
    if old_items_idx in t:
        t = t.replace(old_items_idx, new_items_idx, 1); changed = True

    # 6f. Opened-album pin cards: add refreshCounter
    old_open_pin = (
        "                        PinCard(\n"
        "                            pin = pin,\n"
        "                            columnCount = columnCount,\n"
        "                            isSelected = isSelected,\n"
        "                            isSelectionMode = isSelectionMode,\n"
        "                            isFavorite = isFav,\n"
        "                            hideTitleAndAuthor = hidePinTitlesAndAuthors,\n"
        "                            onClick = {\n"
        "                                if (isSelectionMode) {\n"
        "                                    viewModel.toggleSelection(pin.id)\n"
        "                                } else {\n"
        "                                    viewModel.openFullscreen(index)\n"
        "                                }\n"
        "                            },\n"
        "                            onLongClick = {\n"
        "                                if (isSelectionMode) {\n"
        "                                    viewModel.toggleSelection(pin.id)\n"
        "                                } else {\n"
        "                                    viewModel.toggleFavorite(pin)\n"
        "                                }\n"
        "                            }\n"
        "                        )\n"
    )
    new_open_pin = (
        "                        PinCard(\n"
        "                            pin = pin,\n"
        "                            columnCount = columnCount,\n"
        "                            isSelected = isSelected,\n"
        "                            isSelectionMode = isSelectionMode,\n"
        "                            isFavorite = isFav,\n"
        "                            hideTitleAndAuthor = hidePinTitlesAndAuthors,\n"
        "                            refreshCounter = imageRefreshCounters[pin.id] ?: 0,\n"
        "                            onClick = {\n"
        "                                if (isSelectionMode) {\n"
        "                                    viewModel.toggleSelection(pin.id)\n"
        "                                } else {\n"
        "                                    viewModel.openFullscreen(index)\n"
        "                                }\n"
        "                            },\n"
        "                            onLongClick = {\n"
        "                                if (isSelectionMode) {\n"
        "                                    viewModel.toggleSelection(pin.id)\n"
        "                                } else {\n"
        "                                    viewModel.toggleFavorite(pin)\n"
        "                                }\n"
        "                            }\n"
        "                        )\n"
    )
    if old_open_pin in t:
        t = t.replace(old_open_pin, new_open_pin, 1); changed = True
        log("  ✓ opened-album pins refreshCounter")

    # 6g. groupByAlbum top-level albums: add selection
    old_group_album = (
        "                    items(\n"
        "                        items = albums,\n"
        "                        key = { album -> \"${album.id}_${album.isFavorite}\" }\n"
        "                    ) { album ->\n"
        "                        AlbumCard(\n"
        "                            album = album,\n"
        "                            columnCount = columnCount,\n"
        "                            isFavorite = album.isFavorite,\n"
        "                            isPortrait = portraitAlbumCards,\n"
        "                            onClick = {\n"
        "                                viewModel.openAlbum(album)\n"
        "                            },\n"
        "                            onLongClick = {\n"
        "                                viewModel.toggleAlbumFavorites(album.id, album.title, album.pins)\n"
        "                            },\n"
        "                            onSwipePreview = {\n"
        "                                previewAlbum = album\n"
        "                            }\n"
        "                        )\n"
        "                    }\n"
    )
    new_group_album = (
        "                    items(\n"
        "                        items = albums,\n"
        "                        key = { album -> \"${album.id}_${album.isFavorite}\" }\n"
        "                    ) { album ->\n"
        "                        val isSelectedAlb = selectedAlbumIds.contains(album.id)\n"
        "                        AlbumCard(\n"
        "                            album = album,\n"
        "                            columnCount = columnCount,\n"
        "                            isFavorite = album.isFavorite,\n"
        "                            isPortrait = portraitAlbumCards,\n"
        "                            isSelected = isSelectedAlb,\n"
        "                            isSelectionMode = isSelectionMode,\n"
        "                            onClick = {\n"
        "                                when {\n"
        "                                    pendingAlbumTransfer != null -> viewModel.executeAlbumTransfer(album, currentBoard?.id ?: \"\")\n"
        "                                    else -> viewModel.openAlbum(album)\n"
        "                                }\n"
        "                            },\n"
        "                            onLongClick = {\n"
        "                                when {\n"
        "                                    pendingAlbumTransfer != null -> viewModel.openAlbum(album)\n"
        "                                    else -> viewModel.toggleAlbumFavorites(album.id, album.title, album.pins)\n"
        "                                }\n"
        "                            },\n"
        "                            onSelectToggle = { viewModel.toggleAlbumSelection(album.id) },\n"
        "                            onSwipePreview = {\n"
        "                                previewAlbum = album\n"
        "                            }\n"
        "                        )\n"
        "                    }\n"
    )
    if old_group_album in t:
        t = t.replace(old_group_album, new_group_album, 1); changed = True
        log("  ✓ groupByAlbum albums — selection + drill-in")

    # 6h. galleryItems path — onLongClick drills in during pending transfer
    old_gallery_long = (
        "                                onLongClick = {\n"
        "                                    viewModel.toggleAlbumFavorites(album.id, album.title, album.pins)\n"
        "                                },\n"
    )
    new_gallery_long = (
        "                                onLongClick = {\n"
        "                                    when {\n"
        "                                        pendingAlbumTransfer != null -> viewModel.openAlbum(album)\n"
        "                                        else -> viewModel.toggleAlbumFavorites(album.id, album.title, album.pins)\n"
        "                                    }\n"
        "                                },\n"
    )
    if old_gallery_long in t:
        t = t.replace(old_gallery_long, new_gallery_long, 1); changed = True
        log("  ✓ galleryItems — long-press drill-in during pending transfer")

    # 6i. galleryItems pin cards — refreshCounter
    old_gallery_pin = (
        "                            PinCard(\n"
        "                                pin = pin,\n"
        "                                columnCount = columnCount,\n"
        "                                isSelected = isSelected,\n"
        "                                isSelectionMode = isSelectionMode,\n"
        "                                isFavorite = isFav,\n"
        "                                hideTitleAndAuthor = hidePinTitlesAndAuthors,\n"
        "                                onClick = {\n"
        "                                    if (isSelectionMode) {\n"
        "                                        viewModel.toggleSelection(pin.id)\n"
        "                                    } else {\n"
        "                                        viewModel.openFullscreen(item.pinIndexInLoose)\n"
        "                                    }\n"
        "                                },\n"
        "                                onLongClick = {\n"
        "                                    if (isSelectionMode) {\n"
        "                                        viewModel.toggleSelection(pin.id)\n"
        "                                    } else {\n"
        "                                        viewModel.toggleFavorite(pin)\n"
        "                                    }\n"
        "                                }\n"
        "                            )\n"
    )
    new_gallery_pin = (
        "                            PinCard(\n"
        "                                pin = pin,\n"
        "                                columnCount = columnCount,\n"
        "                                isSelected = isSelected,\n"
        "                                isSelectionMode = isSelectionMode,\n"
        "                                isFavorite = isFav,\n"
        "                                hideTitleAndAuthor = hidePinTitlesAndAuthors,\n"
        "                                refreshCounter = imageRefreshCounters[pin.id] ?: 0,\n"
        "                                onClick = {\n"
        "                                    if (isSelectionMode) {\n"
        "                                        viewModel.toggleSelection(pin.id)\n"
        "                                    } else {\n"
        "                                        viewModel.openFullscreen(item.pinIndexInLoose)\n"
        "                                    }\n"
        "                                },\n"
        "                                onLongClick = {\n"
        "                                    if (isSelectionMode) {\n"
        "                                        viewModel.toggleSelection(pin.id)\n"
        "                                    } else {\n"
        "                                        viewModel.toggleFavorite(pin)\n"
        "                                    }\n"
        "                                }\n"
        "                            )\n"
    )
    if old_gallery_pin in t:
        t = t.replace(old_gallery_pin, new_gallery_pin, 1); changed = True
        log("  ✓ galleryItems pins refreshCounter")

    # 6j. date-group PinCard — refreshCounter (same shape as above but shorter)
    old_date_pin = (
        "                            PinCard(\n"
        "                                pin = pin,\n"
        "                                columnCount = columnCount,\n"
        "                                isSelected = isSelected,\n"
        "                                isSelectionMode = isSelectionMode,\n"
        "                                isFavorite = isFav,\n"
        "                                hideTitleAndAuthor = hidePinTitlesAndAuthors,\n"
    )
    new_date_pin = (
        "                            PinCard(\n"
        "                                pin = pin,\n"
        "                                columnCount = columnCount,\n"
        "                                isSelected = isSelected,\n"
        "                                isSelectionMode = isSelectionMode,\n"
        "                                isFavorite = isFav,\n"
        "                                hideTitleAndAuthor = hidePinTitlesAndAuthors,\n"
        "                                refreshCounter = imageRefreshCounters[pin.id] ?: 0,\n"
    )
    if old_date_pin in t and "refreshCounter = imageRefreshCounters[pin.id] ?: 0,\n                                onClick = {\n                                    if (isSelectionMode) {\n                                        viewModel.toggleSelection(pin.id)\n                                    } else {\n                                        viewModel.openFullscreen(if (index >= 0) index else 0)" not in t:
        # Only replace if this is the date-group one (no refreshCounter yet in this block)
        idx = t.find(old_date_pin)
        if idx >= 0:
            end_idx = t.find("                            )\n", idx)
            if end_idx > 0:
                block = t[idx:end_idx + len("                            )\n")]
                if "refreshCounter" not in block:
                    t = t[:idx] + new_date_pin + t[idx + len(old_date_pin):]
                    changed = True
                    log("  ✓ date-group pins refreshCounter")

    # 6k. FullscreenGalleryViewer — pass refreshCounters + onRefreshImage + liveActiveAlbum pins
    if "refreshCounters = imageRefreshCounters," not in t:
        old_fs = "                FullscreenGalleryViewer(\n"
        new_fs = (
            "                FullscreenGalleryViewer(\n"
            "                    refreshCounters = imageRefreshCounters,\n"
            "                    onRefreshImage = { p -> viewModel.refreshImage(p.id) },\n"
        )
        if old_fs in t:
            t = t.replace(old_fs, new_fs, 1); changed = True
            log("  ✓ FullscreenGalleryViewer refresh params")

    old_fs_pins = "                val fullScreenPins = activeAlbum?.pins ?: "
    new_fs_pins = "                val fullScreenPins = liveActiveAlbum?.pins ?: "
    if old_fs_pins in t:
        t = t.replace(old_fs_pins, new_fs_pins, 1); changed = True
        log("  ✓ fullScreenPins uses liveActiveAlbum")

    # 6l. BoardHeader — onOpenBoardPicker callback
    old_bh = (
        "                        BoardHeader(\n"
        "                            board = board,\n"
        "                            boardHistory = boardHistory,\n"
        "                            currentPinCount = if (activeAlbum != null) activeAlbum!!.pins.size else displayedPins.size,\n"
        "                            boardsListScrollState = boardsListScrollState,\n"
    )
    new_bh = (
        "                        BoardHeader(\n"
        "                            board = board,\n"
        "                            boardHistory = boardHistory,\n"
        "                            currentPinCount = if (liveActiveAlbum != null) liveActiveAlbum!!.pins.size else displayedPins.size,\n"
        "                            boardsListScrollState = boardsListScrollState,\n"
        "                            onOpenBoardPicker = { isBoardPickerOpen = true },\n"
    )
    if old_bh in t:
        t = t.replace(old_bh, new_bh, 1); changed = True
        log("  ✓ BoardHeader onOpenBoardPicker")

    # 6m. Add board picker dialog (near end of composable, before closing braces)
    if "BoardPickerDialog(" not in t:
        anchor = "    // Delete selection (albums involved) — ask how\n"
        add = (
            "    // Board picker (from title or BOARDS label tap)\n"
            "    com.example.ui.dialogs.BoardPickerDialog(\n"
            "        isOpen = isBoardPickerOpen,\n"
            "        boards = boardHistory,\n"
            "        currentBoardUrl = currentBoard?.boardUrl,\n"
            "        onDismiss = { isBoardPickerOpen = false },\n"
            "        onSelectBoard = { url ->\n"
            "            viewModel.loadBoardFromUrl(url)\n"
            "            isBoardPickerOpen = false\n"
            "        }\n"
            "    )\n"
            "\n"
            "    // Delete selection (albums involved) — ask how\n"
        )
        if anchor in t:
            t = t.replace(anchor, add, 1); changed = True
            log("  ✓ BoardPickerDialog rendered")

    # 6n. Horizontal board pill list auto-scroll on board change
    if "// Auto-scroll pill list to opened board" not in t:
        anchor = (
            "    LaunchedEffect(activeAlbum) {\n"
            "        if (viewModel.boardsListScrollIndex > 0 || viewModel.boardsListScrollOffset > 0) {\n"
            "            boardsListScrollState.scrollToItem(\n"
            "                viewModel.boardsListScrollIndex,\n"
            "                viewModel.boardsListScrollOffset\n"
            "            )\n"
            "        }\n"
            "    }\n"
        )
        add = (
            anchor +
            "\n"
            "    // Auto-scroll pill list to opened board\n"
            "    LaunchedEffect(currentBoard?.id, boardHistory.size) {\n"
            "        val cur = currentBoard ?: return@LaunchedEffect\n"
            "        val idx = boardHistory.indexOfFirst {\n"
            "            it.url.trimEnd('/').equals(cur.boardUrl.trimEnd('/'), ignoreCase = true) ||\n"
            "                (it.boardId.isNotBlank() && it.boardId == cur.id)\n"
            "        }\n"
            "        if (idx >= 0) {\n"
            "            boardsListScrollState.animateScrollToItem(idx)\n"
            "        }\n"
            "    }\n"
        )
        if anchor in t:
            t = t.replace(anchor, add, 1); changed = True
            log("  ✓ board pill list auto-scroll")

    if changed:
        f.write_text(t, encoding="utf-8")


# ============================================================
# Self-verify
# ============================================================
def verify_patches():
    log("\n=== Self-verify ===")
    checks = [
        ("app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt", [
            "val imageRefreshCounters: StateFlow<Map<String, Int>>",
            "fun refreshImage(pinId: String)",
            "val parentAlbumId = _activeAlbum.value?.id",
            "// New: opened-album-aware executeAlbumTransferToCurrentBoard",
        ]),
        ("app/src/main/java/com/example/ui/components/PinCard.kt", [
            "refreshCounter: Int = 0",
            "pin-thumb:${pin.id}:r$refreshCounter",
        ]),
        ("app/src/main/java/com/example/ui/components/FullscreenGalleryViewer.kt", [
            "refreshCounters: Map<String, Int> = emptyMap()",
            "onRefreshImage: (PinItem) -> Unit",
            "onRefreshImage(currentPin)",
            "refreshCounters[pin.id]",
        ]),
        ("app/src/main/java/com/example/ui/dialogs/BoardPickerDialog.kt", [
            "fun BoardPickerDialog(",
        ]),
        ("app/src/main/java/com/example/ui/components/BoardHeader.kt", [
            "onOpenBoardPicker: () -> Unit",
            "board_title_open_picker",
            "boards_label_open_picker",
        ]),
        ("app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt", [
            "val liveActiveAlbum = remember(activeAlbum, customDateAlbums)",
            "onSelectToggle = { viewModel.toggleAlbumSelection(subAlb.id) }",
            "onLongClick = {\n                                    when {\n                                        pendingAlbumTransfer != null -> viewModel.openAlbum(subAlb)",
            "refreshCounters = imageRefreshCounters,",
            "onRefreshImage = { p -> viewModel.refreshImage(p.id) }",
            "onOpenBoardPicker = { isBoardPickerOpen = true }",
            "com.example.ui.dialogs.BoardPickerDialog(",
            "// Auto-scroll pill list to opened board",
        ]),
    ]
    all_ok = True
    for rel, markers in checks:
        fp = PROJECT_ROOT / rel
        if not fp.exists():
            log(f"  ✗ {rel} missing"); all_ok = False; continue
        content = fp.read_text(encoding="utf-8")
        for m in markers:
            if m not in content:
                log(f"  ✗ MISSING in {rel.split('/')[-1]}: {m[:70]}")
                all_ok = False
        if all_ok:
            log(f"  ✓ {rel.split('/')[-1]}")
    if not all_ok:
        log("\n✗ VERIFICATION FAILED"); sys.exit(1)


# ============================================================
# Standard pipeline
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
        run(["git", "commit", "-m",
             "Sub-album selection, drill-in transfer, board picker, refresh counters"])


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
    log("PinBoard — sub-album select, drill-in, refresh, board picker")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    patch_viewmodel()
    patch_pin_card()
    patch_fullscreen()
    patch_board_picker_dialog()
    patch_board_header()
    patch_gallery_screen()
    verify_patches()

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