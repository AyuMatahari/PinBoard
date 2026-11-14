#!/usr/bin/env python3
"""
PinBoard Gallery — force-fix isFullscreenActive + BoardPickerDialog dy
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


# ============================================================
# NEW BOARD PICKER (v2 — dragAmount.y, version marker)
# ============================================================
NEW_BOARD_PICKER = r'''package com.example.ui.dialogs

// v2-drag-reorder
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.PointerInputChange
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
                                    onDrag = { change: PointerInputChange, dragAmount: Offset ->
                                        change.consume()
                                        accumulatedDrag += dragAmount.y
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


# ============================================================
# PATCH — Force-rewrite BoardPickerDialog
# ============================================================
def patch_board_picker_force():
    log("\n=== PATCH: BoardPickerDialog (force v2) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/dialogs/BoardPickerDialog.kt"
    if f.exists():
        t = f.read_text(encoding="utf-8")
        if "// v2-drag-reorder" in t and "drag.dy" not in t and "dragAmount.y" in t:
            log("  ✓ already at v2"); return
        log("  → forcing rewrite (existing file broken or old)")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(NEW_BOARD_PICKER, encoding="utf-8")
    log("  ✓ v2 written (dragAmount.y, explicit types)")


# ============================================================
# PATCH — Force-ensure isFullscreenActive declaration
# ============================================================
def patch_is_fullscreen_active_force():
    log("\n=== PATCH: isFullscreenActive (force) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    # 1) Remove ALL existing `val isFullscreenActive = ...` declarations
    removed = 0
    while True:
        idx = t.find("val isFullscreenActive")
        if idx < 0: break
        line_start = t.rfind("\n", 0, idx) + 1
        # Find end of the val statement (next newline after closing expression)
        line_end = t.find("\n", idx)
        if line_end < 0:
            line_end = len(t)
        # Remove the full line
        t = t[:line_start] + t[line_end + 1:]
        removed += 1
        if removed > 20: break  # safety
    if removed > 0:
        log(f"  ✓ removed {removed} existing isFullscreenActive declaration(s)")

    # 2) Find an insertion anchor — `val fullscreenPinIndex by ...` line
    anchors = [
        r'(\n([ \t]+)val fullscreenPinIndex by viewModel\.fullscreenPinIndex\.collectAsStateWithLifecycle\(\))',
        r'(\n([ \t]+)val fullscreenPinId by viewModel\.fullscreenPinId\.collectAsStateWithLifecycle\(\))',
        r'(\n([ \t]+)val currentBoard by viewModel\.currentBoard\.collectAsStateWithLifecycle\(\))',
    ]
    matched = None
    for pat in anchors:
        m = re.search(pat, t)
        if m:
            matched = m
            break

    if not matched:
        log("  ✗ no insertion anchor matched"); sys.exit(1)

    indent = matched.group(2)
    insert_at = matched.end(1)
    decl = f"\n{indent}val isFullscreenActive = fullscreenPinId != null || fullscreenPinIndex != null"
    t = t[:insert_at] + decl + t[insert_at:]
    log(f"  ✓ single isFullscreenActive declaration inserted (indent='{indent}')")

    f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH — ViewModel fullscreenPinId (idempotent)
# ============================================================
def patch_vm_fullscreen_pin_id():
    log("\n=== PATCH: ViewModel fullscreenPinId ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    if "private val _fullscreenPinId" not in t:
        anchor = (
            "    private val _fullscreenPinIndex = MutableStateFlow<Int?>(null)\n"
            "    val fullscreenPinIndex: StateFlow<Int?> = _fullscreenPinIndex.asStateFlow()\n"
        )
        if anchor in t:
            t = t.replace(anchor, anchor + (
                "\n"
                "    private val _fullscreenPinId = MutableStateFlow<String?>(null)\n"
                "    val fullscreenPinId: StateFlow<String?> = _fullscreenPinId.asStateFlow()\n"
            ), 1)
            changed = True
            log("  ✓ fullscreenPinId state")
        else:
            log("  ⚠ fullscreenPinIndex anchor missing")

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
            t = t.replace(old_open, new_open, 1)
            changed = True
            log("  ✓ openFullscreenByPinId")
        else:
            log("  ⚠ openFullscreen/closeFullscreen anchor missing")

    if changed: f.write_text(t, encoding="utf-8")
    else: log("  ✓ already patched")


# ============================================================
# PATCH — fullscreenPinId collection (idempotent)
# ============================================================
def patch_fullscreen_pin_id_collection():
    log("\n=== PATCH: fullscreenPinId collection ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    t = f.read_text(encoding="utf-8")

    if "val fullscreenPinId by viewModel.fullscreenPinId" in t:
        log("  ✓ already present"); return

    old_anchor = "    val fullscreenPinIndex by viewModel.fullscreenPinIndex.collectAsStateWithLifecycle()\n"
    if old_anchor in t:
        t = t.replace(old_anchor, old_anchor + "    val fullscreenPinId by viewModel.fullscreenPinId.collectAsStateWithLifecycle()\n", 1)
        f.write_text(t, encoding="utf-8")
        log("  ✓ added")
        return

    m = re.search(r'(\n([ \t]+)val fullscreenPinIndex by viewModel\.fullscreenPinIndex\.collectAsStateWithLifecycle\(\))', t)
    if m:
        indent = m.group(2)
        insert_at = m.end(1)
        t = t[:insert_at] + f"\n{indent}val fullscreenPinId by viewModel.fullscreenPinId.collectAsStateWithLifecycle()" + t[insert_at:]
        f.write_text(t, encoding="utf-8")
        log("  ✓ added (regex)")
    else:
        log("  ✗ fullscreenPinIndex collection not found"); sys.exit(1)


# ============================================================
# PATCH — Wire onReorderBoards (idempotent)
# ============================================================
def patch_wire_reorder():
    log("\n=== PATCH: Wire onReorderBoards ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    t = f.read_text(encoding="utf-8")

    if "onReorderBoards = { list -> viewModel.saveReorderedBoards(list, false) }" in t:
        log("  ✓ already wired"); return

    # Paren-balanced insertion
    idx = t.find("com.example.ui.dialogs.BoardPickerDialog(")
    if idx < 0:
        log("  ✗ call not found"); sys.exit(1)
    paren_idx = t.find("(", idx)
    depth = 0
    i = paren_idx
    while i < len(t):
        if t[i] == "(":
            depth += 1
        elif t[i] == ")":
            depth -= 1
            if depth == 0:
                t = t[:i] + ",\n        onReorderBoards = { list -> viewModel.saveReorderedBoards(list, false) }\n    " + t[i:]
                f.write_text(t, encoding="utf-8")
                log("  ✓ wired")
                return
        i += 1
    log("  ✗ call paren balance failed"); sys.exit(1)


# ============================================================
# Verification
# ============================================================
def verify_all():
    log("\n=== VERIFY ===")
    ps = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    vm = PROJECT_ROOT / "app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt"
    bp = PROJECT_ROOT / "app/src/main/java/com/example/ui/dialogs/BoardPickerDialog.kt"

    for p in (ps, vm, bp):
        if not p.exists():
            log(f"  ✗ missing: {p}"); sys.exit(1)

    pts = ps.read_text(encoding="utf-8")
    vmt = vm.read_text(encoding="utf-8")
    bpt = bp.read_text(encoding="utf-8")

    # Fatal checks
    checks = []

    # 1. isFullscreenActive declared EXACTLY once, before first use
    decl_count = pts.count("val isFullscreenActive =")
    checks.append(("isFullscreenActive declared exactly once", decl_count == 1))
    if decl_count == 1:
        decl_idx = pts.find("val isFullscreenActive =")
        # Find first USE that isn't the declaration itself (search after decl)
        after_decl = pts[decl_idx + 30:]
        has_use = ("isFullscreenActive" in after_decl)
        checks.append(("isFullscreenActive used after declaration", has_use))
    else:
        checks.append(("isFullscreenActive used after declaration", False))

    # 2. fullscreenPinId collection present
    checks.append(("fullscreenPinId collection",
                   "val fullscreenPinId by viewModel.fullscreenPinId.collectAsStateWithLifecycle()" in pts))

    # 3. BoardPickerDialog uses dragAmount.y (not drag.dy)
    checks.append(("BoardPicker uses dragAmount.y", "dragAmount.y" in bpt))
    checks.append(("BoardPicker has no drag.dy", "drag.dy" not in bpt))
    checks.append(("BoardPicker v2 marker", "// v2-drag-reorder" in bpt))
    checks.append(("BoardPicker has detectDragGesturesAfterLongPress",
                   "detectDragGesturesAfterLongPress" in bpt))
    checks.append(("BoardPicker has onReorderBoards call",
                   "onReorderBoards(newList)" in bpt))

    # 4. VM has fullscreenPinId
    checks.append(("VM fullscreenPinId", "private val _fullscreenPinId" in vmt))
    checks.append(("VM openFullscreenByPinId", "fun openFullscreenByPinId(pinId: String)" in vmt))

    # 5. onReorderBoards wired in screen
    checks.append(("onReorderBoards wired",
                   "onReorderBoards = { list -> viewModel.saveReorderedBoards(list, false) }" in pts))

    # 6. Bracket balance on PinBoardGalleryScreen.kt
    def strip_strings_comments(text):
        out = []
        i = 0
        while i < len(text):
            c = text[i]
            if c == '"':
                i += 1
                while i < len(text):
                    if text[i] == "\\": i += 2; continue
                    if text[i] == '"': i += 1; break
                    i += 1
            elif c == "'":
                i += 1
                while i < len(text):
                    if text[i] == "\\": i += 2; continue
                    if text[i] == "'": i += 1; break
                    i += 1
            elif c == "/" and i+1 < len(text) and text[i+1] == "/":
                while i < len(text) and text[i] != "\n": i += 1
            elif c == "/" and i+1 < len(text) and text[i+1] == "*":
                i += 2
                while i+1 < len(text):
                    if text[i] == "*" and text[i+1] == "/":
                        i += 2; break
                    i += 1
            else:
                out.append(c); i += 1
        return "".join(out)

    stripped = strip_strings_comments(pts)
    po, pc = stripped.count("("), stripped.count(")")
    bo, bc = stripped.count("{"), stripped.count("}")
    checks.append((f"Screen paren balance ({po}/{pc})", po == pc))
    checks.append((f"Screen brace balance ({bo}/{bc})", bo == bc))

    all_ok = True
    for name, ok in checks:
        log(f"  {'✓' if ok else '✗'} {name}")
        if not ok: all_ok = False

    if not all_ok:
        log("\n✗ VERIFICATION FAILED"); sys.exit(1)


# ============================================================
# Pipeline helpers
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
             "Force-fix isFullscreenActive declaration + BoardPicker v2 (dragAmount.y)"])


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
    log("PinBoard — force-fix isFullscreenActive + BoardPicker v2")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    # 1) Force-rewrite BoardPickerDialog (idempotent via version marker)
    patch_board_picker_force()

    # 2) ViewModel fullscreenPinId (idempotent)
    patch_vm_fullscreen_pin_id()

    # 3) Screen: fullscreenPinId collection (must come BEFORE isFullscreenActive insertion)
    patch_fullscreen_pin_id_collection()

    # 4) Screen: FORCE-cleanup + insert isFullscreenActive declaration
    patch_is_fullscreen_active_force()

    # 5) Wire onReorderBoards (idempotent)
    patch_wire_reorder()

    # 6) Verify before CI
    verify_all()

    # 7) Build pipeline
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