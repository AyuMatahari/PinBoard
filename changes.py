#!/usr/bin/env python3
"""
PinBoard Gallery — fix dateGroups forward reference (re-run) + ID fullscreen + drag picker
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


def find_matching_brace(text, open_idx):
    depth = 0
    i = open_idx
    while i < len(text):
        c = text[i]
        if c == '"':
            i += 1
            while i < len(text):
                if text[i] == "\\":
                    i += 2; continue
                if text[i] == '"':
                    break
                i += 1
        elif c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0: return i
        i += 1
    return -1


# ============================================================
# PATCH 0 — CRITICAL: fix isStandardMasonryActive forward reference
# ============================================================
def patch_forward_reference():
    log("\n=== PATCH: isStandardMasonryActive forward reference (CRITICAL) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    date_groups_idx = t.find("val dateGroups = remember(")
    is_std_idx = t.find("val isStandardMasonryActive")
    albums_idx = t.find("val albums = remember(allPinsForAlbums")

    if date_groups_idx < 0:
        log("  ✗ dateGroups declaration not found"); sys.exit(1)
    if albums_idx < 0:
        log("  ✗ albums declaration not found"); sys.exit(1)

    if is_std_idx >= 0 and is_std_idx > date_groups_idx:
        log("  ✓ already correctly placed (after dateGroups)"); return

    # Remove all existing occurrences (however many, wherever they are)
    removed = 0
    while True:
        idx = t.find("val isStandardMasonryActive")
        if idx < 0:
            break
        line_start = t.rfind("\n", 0, idx) + 1
        # Find the closing `dateGroups.isNotEmpty())` — end of the declaration
        end_marker = "dateGroups.isNotEmpty())"
        end_idx = t.find(end_marker, idx)
        if end_idx < 0:
            # Fallback: end at the next newline
            end_idx = t.find("\n", idx)
            if end_idx < 0:
                break
            end_idx += 1
        else:
            end_idx += len(end_marker)
            # Consume trailing newline(s)
            while end_idx < len(t) and t[end_idx] == "\n":
                end_idx += 1
        t = t[:line_start] + t[end_idx:]
        removed += 1
        # Re-scan since positions shifted
        is_std_idx = t.find("val isStandardMasonryActive")
        if is_std_idx < 0:
            break

    if removed > 0:
        log(f"  ✓ removed {removed} misplaced declaration(s)")

    # Re-insert correctly — before `albums = remember(allPinsForAlbums`
    # (`albums` is declared AFTER `dateGroups` in the original file)
    block = (
        "    val isStandardMasonryActive = !groupByAlbum && liveActiveAlbum == null &&\n"
        "        !(separateByDate && dateGroups.isNotEmpty())\n"
        "\n"
    )
    if "    val albums = remember(allPinsForAlbums" in t:
        t = t.replace(
            "    val albums = remember(allPinsForAlbums",
            block + "    val albums = remember(allPinsForAlbums",
            1,
        )
        log("  ✓ reinserted after dateGroups, before albums")
    else:
        log("  ✗ could not find albums anchor for reinsertion"); sys.exit(1)

    f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 1 — ViewModel fullscreenPinId
# ============================================================
def patch_vm_fullscreen_pin_id():
    log("\n=== PATCH: ViewModel fullscreenPinId ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "_fullscreenPinId" in t and "openFullscreenByPinId" in t:
        log("  ✓ already patched"); return

    changed = False
    if "private val _fullscreenPinId" not in t:
        anchor = (
            "    private val _fullscreenPinIndex = MutableStateFlow<Int?>(null)\n"
            "    val fullscreenPinIndex: StateFlow<Int?> = _fullscreenPinIndex.asStateFlow()\n"
        )
        add = (
            anchor +
            "\n"
            "    private val _fullscreenPinId = MutableStateFlow<String?>(null)\n"
            "    val fullscreenPinId: StateFlow<String?> = _fullscreenPinId.asStateFlow()\n"
        )
        if anchor in t:
            t = t.replace(anchor, add, 1); changed = True
            log("  ✓ fullscreenPinId state")

    if "fun openFullscreenByPinId" not in t:
        old_open = (
            "    fun openFullscreen(index: Int) {\n"
            "        if (!_isSelectionMode.value) {\n"
            "            _fullscreenPinIndex.value = index\n"
            "        }\n"
            "    }\n"
            "\n"
            "    fun closeFullscreen() {\n"
            "        _fullscreenPinIndex.value = null\n"
            "    }\n"
        )
        new_open = (
            "    fun openFullscreen(index: Int) {\n"
            "        if (!_isSelectionMode.value) {\n"
            "            _fullscreenPinIndex.value = index\n"
            "            _fullscreenPinId.value = null\n"
            "        }\n"
            "    }\n"
            "\n"
            "    fun openFullscreenByPinId(pinId: String) {\n"
            "        if (!_isSelectionMode.value) {\n"
            "            _fullscreenPinId.value = pinId\n"
            "            _fullscreenPinIndex.value = null\n"
            "        }\n"
            "    }\n"
            "\n"
            "    fun closeFullscreen() {\n"
            "        _fullscreenPinIndex.value = null\n"
            "        _fullscreenPinId.value = null\n"
            "    }\n"
        )
        if old_open in t:
            t = t.replace(old_open, new_open, 1); changed = True
            log("  ✓ openFullscreenByPinId")

    if changed: f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 2 — Screen state + ID clicks
# ============================================================
def patch_screen_state_and_clicks():
    log("\n=== PATCH: Screen state + ID clicks ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    if "val fullscreenPinId by viewModel.fullscreenPinId" not in t:
        old_collect = "    val fullscreenPinIndex by viewModel.fullscreenPinIndex.collectAsStateWithLifecycle()\n"
        new_collect = (
            "    val fullscreenPinIndex by viewModel.fullscreenPinIndex.collectAsStateWithLifecycle()\n"
            "    val fullscreenPinId by viewModel.fullscreenPinId.collectAsStateWithLifecycle()\n"
            "    val isFullscreenActive = fullscreenPinId != null || fullscreenPinIndex != null\n"
        )
        if old_collect in t:
            t = t.replace(old_collect, new_collect, 1); changed = True
            log("  ✓ collect state + isFullscreenActive")

    n = t.count("fullscreenPinIndex == null")
    if n > 0:
        t = t.replace("fullscreenPinIndex == null", "!isFullscreenActive")
        changed = True
        log(f"  ✓ {n} 'fullscreenPinIndex == null' → '!isFullscreenActive'")

    t = t.replace("fullscreenPinIndex != null", "isFullscreenActive")

    # Gallery click
    old_click_g = (
        "                                        val visualIdx = galleryPinsForFullscreen.indexOfFirst { it.id == pin.id }\n"
        "                                            .coerceAtLeast(0)\n"
        "                                        viewModel.openFullscreen(visualIdx)\n"
    )
    if old_click_g in t:
        t = t.replace(old_click_g, "                                        viewModel.openFullscreenByPinId(pin.id)\n", 1)
        changed = True
        log("  ✓ galleryItems click → ID")

    # Album view click
    old_click_a = (
        "                                } else {\n"
        "                                    viewModel.openFullscreen(index)\n"
        "                                }\n"
    )
    if old_click_a in t:
        idx = t.find(old_click_a)
        if idx > 0:
            t = t[:idx] + (
                "                                } else {\n"
                "                                    viewModel.openFullscreenByPinId(pin.id)\n"
                "                                }\n"
            ) + t[idx + len(old_click_a):]
            changed = True
            log("  ✓ album view click → ID")

    # Date-group click
    old_click_d = (
        "                                } else {\n"
        "                                    viewModel.openFullscreen(if (index >= 0) index else 0)\n"
        "                                }\n"
    )
    if old_click_d in t:
        t = t.replace(old_click_d, (
            "                                } else {\n"
            "                                    viewModel.openFullscreenByPinId(pin.id)\n"
            "                                }\n"
        ), 1)
        changed = True
        log("  ✓ date-group click → ID")

    if changed: f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 3 — Fullscreen render block (brace-balanced)
# ============================================================
def patch_screen_fullscreen_render():
    log("\n=== PATCH: Fullscreen render (brace-balanced) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if ("if (isFullscreenActive) {" in t
            and "fullscreenPinId != null -> fullScreenPins.indexOfFirst { it.id == fullscreenPinId }" in t):
        log("  ✓ already patched"); return

    marker = "fullscreenPinIndex?.let {"
    idx = t.find(marker)
    if idx < 0:
        log("  ✗ marker not found"); sys.exit(1)

    open_brace = idx + len(marker) - 1
    close_brace = find_matching_brace(t, open_brace)
    if close_brace < 0:
        log("  ✗ matching brace not found"); sys.exit(1)

    line_start = t.rfind("\n", 0, idx) + 1
    ind = t[line_start:idx]
    inner = ind + "    "
    inner2 = inner + "    "

    new_block = (
        f"{ind}if (isFullscreenActive) {{\n"
        f"{inner}val fullScreenPins = when {{\n"
        f"{inner2}liveActiveAlbum != null -> liveActiveAlbum!!.pins\n"
        f"{inner2}galleryPinsForFullscreen.isNotEmpty() -> galleryPinsForFullscreen\n"
        f"{inner2}else -> viewModel.getAllSortedPins().ifEmpty {{ displayedPins }}\n"
        f"{inner}}}\n"
        f"{inner}val initialIndex = when {{\n"
        f"{inner2}fullscreenPinId != null -> fullScreenPins.indexOfFirst {{ it.id == fullscreenPinId }}.coerceAtLeast(0)\n"
        f"{inner2}fullscreenPinIndex != null -> fullscreenPinIndex!!.coerceIn(0, (fullScreenPins.size - 1).coerceAtLeast(0))\n"
        f"{inner2}else -> 0\n"
        f"{inner}}}\n"
        f"{inner}FullscreenGalleryViewer(\n"
        f"{inner2}refreshCounters = imageRefreshCounters,\n"
        f"{inner2}onRefreshImage = {{ p -> viewModel.refreshImage(p.id) }},\n"
        f"{inner2}pins = fullScreenPins,\n"
        f"{inner2}initialIndex = initialIndex,\n"
        f"{inner2}disableArrowNavigation = disableArrowNavigation,\n"
        f"{inner2}isFavorite = {{ pin -> favoritePinKeys.contains(pin.id) || favoritePinKeys.contains(pin.imageUrl) }},\n"
        f"{inner2}onToggleFavorite = {{ pin -> viewModel.toggleFavorite(pin) }},\n"
        f"{inner2}onMoveToTop = {{ pin -> viewModel.movePinToTop(pin) }},\n"
        f"{inner2}onDeleteSingle = {{ pin -> viewModel.deleteSinglePin(pin) }},\n"
        f"{inner2}onClose = {{ viewModel.closeFullscreen() }},\n"
        f"{inner2}onDownloadSingle = {{ pin -> viewModel.downloadSingle(context, pin) }}\n"
        f"{inner}}}\n"
        f"{ind}}}"
    )

    t = t[:idx] + new_block + t[close_brace + 1:]
    f.write_text(t, encoding="utf-8")
    log(f"  ✓ fullscreen block replaced ({close_brace - idx} chars → {len(new_block)} chars)")


# ============================================================
# PATCH 4 — BoardPickerDialog with drag-reorder
# ============================================================
NEW_BOARD_PICKER = r'''package com.example.ui.dialogs

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.material.icons.filled.DragHandle
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Link
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.zIndex
import com.example.model.BoardHistoryItem
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary
import kotlin.math.roundToInt


@Composable
fun BoardPickerDialog(
    isOpen: Boolean,
    boards: List<BoardHistoryItem>,
    currentBoardUrl: String?,
    onDismiss: () -> Unit,
    onSelectBoard: (String) -> Unit,
    onReorderBoards: (List<BoardHistoryItem>) -> Unit = {}
) {
    if (!isOpen) return

    var localBoards by remember(boards) { mutableStateOf(boards) }
    var draggedIndex by remember { mutableStateOf<Int?>(null) }
    var accumulatedDrag by remember { mutableFloatStateOf(0f) }

    val density = LocalDensity.current
    val itemHeightDp = 56.dp
    val itemHeightPx = with(density) { itemHeightDp.toPx() }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Column {
                Text("Switch board", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                Spacer(Modifier.height(4.dp))
                Text(
                    "Tap to open · Hold to drag reorder",
                    fontSize = 11.sp,
                    color = PinterestTextSecondary
                )
            }
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 500.dp)
                    .verticalScroll(rememberScrollState())
            ) {
                localBoards.forEachIndexed { index, item ->
                    val isCurrent = currentBoardUrl?.trimEnd('/')
                        ?.equals(item.url.trimEnd('/'), ignoreCase = true) == true
                    val isDragged = draggedIndex == index

                    val isFav = item.boardId == "board_favorites" || item.url.contains("favorites")
                    val isMySave = item.boardId == "board_my_save" || item.url.contains("my_save")
                    val isDump = item.boardId == "board_dump" || item.url.contains("dump")

                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(itemHeightDp)
                            .padding(vertical = 2.dp)
                            .graphicsLayer {
                                if (isDragged) {
                                    translationY = accumulatedDrag
                                    shadowElevation = 12.dp.toPx()
                                    alpha = 0.95f
                                    scaleX = 1.02f
                                    scaleY = 1.02f
                                }
                            }
                            .zIndex(if (isDragged) 1f else 0f)
                            .pointerInput(item.url, localBoards.size) {
                                detectDragGesturesAfterLongPress(
                                    onDragStart = {
                                        draggedIndex = index
                                        accumulatedDrag = 0f
                                    },
                                    onDrag = { change, drag ->
                                        change.consume()
                                        accumulatedDrag += drag.dy
                                    },
                                    onDragEnd = {
                                        val offset = (accumulatedDrag / itemHeightPx).roundToInt()
                                        val targetIdx = (index + offset)
                                            .coerceIn(0, localBoards.size - 1)
                                        if (targetIdx != index) {
                                            val newList = localBoards.toMutableList()
                                            val moved = newList.removeAt(index)
                                            newList.add(targetIdx, moved)
                                            localBoards = newList
                                            onReorderBoards(newList)
                                        }
                                        draggedIndex = null
                                        accumulatedDrag = 0f
                                    },
                                    onDragCancel = {
                                        draggedIndex = null
                                        accumulatedDrag = 0f
                                    }
                                )
                            }
                    ) {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    if (draggedIndex == null) {
                                        onSelectBoard(item.url)
                                        onDismiss()
                                    }
                                }
                                .testTag("board_picker_pill_${item.url.hashCode()}")
                                .background(
                                    color = if (isCurrent) PinterestRed else PinterestPillGray,
                                    shape = RoundedCornerShape(24.dp)
                                )
                                .padding(horizontal = 14.dp, vertical = 12.dp),
                            contentAlignment = Alignment.CenterStart
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.Start
                            ) {
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
                                    modifier = Modifier.size(14.dp)
                                )
                                Spacer(Modifier.width(8.dp))
                                Text(
                                    text = item.title.ifBlank { "Board" },
                                    fontSize = 13.sp,
                                    fontWeight = if (isCurrent) FontWeight.Bold else FontWeight.Medium,
                                    color = if (isCurrent) Color.White else PinterestBlack,
                                    modifier = Modifier.weight(1f)
                                )
                                if (item.isCustom && !isFav && !isMySave && !isDump) {
                                    Text(
                                        text = "· Custom",
                                        fontSize = 10.sp,
                                        color = if (isCurrent) Color.White.copy(alpha = 0.7f) else PinterestTextSecondary
                                    )
                                    Spacer(Modifier.width(6.dp))
                                }
                                Icon(
                                    imageVector = Icons.Default.DragHandle,
                                    contentDescription = "Drag to reorder",
                                    tint = if (isCurrent) Color.White.copy(alpha = 0.7f) else PinterestTextSecondary,
                                    modifier = Modifier.size(16.dp)
                                )
                            }
                        }
                    }
                }

                if (localBoards.isEmpty()) {
                    Spacer(Modifier.height(12.dp))
                    Text("No boards available.", fontSize = 12.sp, color = PinterestTextSecondary)
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


def patch_board_picker_dialog():
    log("\n=== PATCH: BoardPickerDialog ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/dialogs/BoardPickerDialog.kt"
    if f.exists():
        t = f.read_text(encoding="utf-8")
        if "detectDragGesturesAfterLongPress" in t and "onReorderBoards(newList)" in t:
            log("  ✓ already patched"); return
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(NEW_BOARD_PICKER, encoding="utf-8")
    log("  ✓ rewritten with drag-reorder")


# ============================================================
# PATCH 5 — Wire onReorderBoards
# ============================================================
def patch_wire_reorder():
    log("\n=== PATCH: Wire onReorderBoards ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "onReorderBoards = { list -> viewModel.saveReorderedBoards(list, false) }" in t:
        log("  ✓ already wired"); return

    old_call = (
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
    )
    new_call = (
        "    com.example.ui.dialogs.BoardPickerDialog(\n"
        "        isOpen = isBoardPickerOpen,\n"
        "        boards = boardHistory,\n"
        "        currentBoardUrl = currentBoard?.boardUrl,\n"
        "        onDismiss = { isBoardPickerOpen = false },\n"
        "        onSelectBoard = { url ->\n"
        "            viewModel.loadBoardFromUrl(url)\n"
        "            isBoardPickerOpen = false\n"
        "        },\n"
        "        onReorderBoards = { list -> viewModel.saveReorderedBoards(list, false) }\n"
        "    )\n"
    )
    if old_call in t:
        t = t.replace(old_call, new_call, 1)
        f.write_text(t, encoding="utf-8")
        log("  ✓ wired")
    else:
        # Fallback: balance-paren insertion
        idx = t.find("com.example.ui.dialogs.BoardPickerDialog(")
        if idx < 0:
            log("  ✗ call not found"); sys.exit(1)
        paren_idx = t.find("(", idx)
        depth = 0
        i = paren_idx
        while i < len(t):
            if t[i] == "(": depth += 1
            elif t[i] == ")":
                depth -= 1
                if depth == 0:
                    t = t[:i] + ",\n        onReorderBoards = { list -> viewModel.saveReorderedBoards(list, false) }\n    " + t[i:]
                    f.write_text(t, encoding="utf-8")
                    log("  ✓ wired (fallback)")
                    return
            i += 1


# ============================================================
# Verify
# ============================================================
def verify_all():
    log("\n=== VERIFY ===")

    # CRITICAL: forward reference
    fp = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not fp.exists():
        log("  ✗ PinBoardGalleryScreen.kt missing"); sys.exit(1)
    content = fp.read_text(encoding="utf-8")

    date_groups_idx = content.find("val dateGroups = remember(")
    is_std_idx = content.find("val isStandardMasonryActive")
    is_std_count = content.count("val isStandardMasonryActive")

    if date_groups_idx < 0:
        log("  ✗ dateGroups declaration not found"); sys.exit(1)
    if is_std_idx < 0:
        log("  ✗ isStandardMasonryActive declaration not found"); sys.exit(1)
    if is_std_idx < date_groups_idx:
        log(f"  ✗ isStandardMasonryActive BEFORE dateGroups (will fail to compile!)")
        log(f"    isStandardMasonryActive idx={is_std_idx}, dateGroups idx={date_groups_idx}")
        sys.exit(1)
    if is_std_count != 1:
        log(f"  ✗ expected 1 isStandardMasonryActive declaration, found {is_std_count}"); sys.exit(1)
    log("  ✓ isStandardMasonryActive after dateGroups, single declaration")

    # Other markers
    checks = [
        ("app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt", [
            "private val _fullscreenPinId",
            "fun openFullscreenByPinId(pinId: String)",
        ]),
        ("app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt", [
            "val fullscreenPinId by viewModel.fullscreenPinId",
            "val isFullscreenActive = ",
            "fullscreenPinId != null -> fullScreenPins.indexOfFirst { it.id == fullscreenPinId }",
            "onReorderBoards = { list -> viewModel.saveReorderedBoards(list, false) }",
        ]),
        ("app/src/main/java/com/example/ui/dialogs/BoardPickerDialog.kt", [
            "detectDragGesturesAfterLongPress",
            "onReorderBoards(newList)",
        ]),
    ]
    for rel, markers in checks:
        fp2 = PROJECT_ROOT / rel
        if not fp2.exists():
            log(f"  ✗ {rel} missing"); sys.exit(1)
        c = fp2.read_text(encoding="utf-8")
        ok = True
        for m in markers:
            if m not in c:
                log(f"  ✗ MISSING in {rel.split('/')[-1]}: {m[:60]}")
                ok = False
        if ok:
            log(f"  ✓ {rel.split('/')[-1]}")
        else:
            sys.exit(1)


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
             "Fix dateGroups forward reference (re-apply); keep ID fullscreen + drag picker"])


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
    log("PinBoard — fix dateGroups forward ref + ID fullscreen + drag picker")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    # CRITICAL: fix forward reference FIRST
    patch_forward_reference()

    # Then other patches (all idempotent)
    patch_vm_fullscreen_pin_id()
    patch_screen_state_and_clicks()
    patch_screen_fullscreen_render()
    patch_board_picker_dialog()
    patch_wire_reorder()

    # Verify everything BEFORE CI
    verify_all()

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