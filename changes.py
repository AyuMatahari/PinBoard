#!/usr/bin/env python3
"""
PinBoard Gallery — BoardPicker v3: pill FlowRow + drag-drop (visual preserved)
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
# NEW BOARD PICKER (v3 — pills + drag-drop)
# ============================================================
NEW_BOARD_PICKER = r'''package com.example.ui.dialogs

// v3-pill-drag
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Link
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.PointerInputChange
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onGloballyPositioned
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


@OptIn(ExperimentalLayoutApi::class, ExperimentalFoundationApi::class)
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
    var draggedUrl by remember { mutableStateOf<String?>(null) }
    var dragOffset by remember { mutableStateOf(Offset.Zero) }
    var suppressClickUntil by remember { mutableStateOf(0L) }
    val itemBounds = remember { mutableMapOf<String, Rect>() }

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
                FlowRow(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    localBoards.forEach { item ->
                        val isCurrent = currentBoardUrl?.trimEnd('/')
                            ?.equals(item.url.trimEnd('/'), ignoreCase = true) == true
                        val isDragged = draggedUrl == item.url

                        val isFav = item.boardId == "board_favorites" || item.url.contains("favorites")
                        val isMySave = item.boardId == "board_my_save" || item.url.contains("my_save")
                        val isDump = item.boardId == "board_dump" || item.url.contains("dump")

                        Surface(
                            shape = RoundedCornerShape(20.dp),
                            color = if (isCurrent) PinterestRed else PinterestPillGray,
                            modifier = Modifier
                                .onGloballyPositioned { coords ->
                                    itemBounds[item.url] = coords.boundsInRoot()
                                }
                                .graphicsLayer {
                                    if (isDragged) {
                                        translationX = dragOffset.x
                                        translationY = dragOffset.y
                                        shadowElevation = 12.dp.toPx()
                                        scaleX = 1.06f
                                        scaleY = 1.06f
                                        alpha = 0.95f
                                    }
                                }
                                .zIndex(if (isDragged) 1f else 0f)
                                .pointerInput(item.url, localBoards.size) {
                                    detectDragGesturesAfterLongPress(
                                        onDragStart = {
                                            draggedUrl = item.url
                                            dragOffset = Offset.Zero
                                        },
                                        onDrag = { change: PointerInputChange, amount: Offset ->
                                            change.consume()
                                            dragOffset += amount
                                        },
                                        onDragEnd = {
                                            val current = draggedUrl
                                            draggedUrl = null
                                            suppressClickUntil = System.currentTimeMillis() + 250
                                            if (current != null) {
                                                val draggedBounds = itemBounds[current]
                                                if (draggedBounds != null && dragOffset.getDistance() > 8f) {
                                                    val finalCenter = draggedBounds.center + dragOffset
                                                    val target = itemBounds.entries
                                                        .filter { it.key != current }
                                                        .minByOrNull { (it.value.center - finalCenter).getDistance() }
                                                    if (target != null) {
                                                        val fromIdx = localBoards.indexOfFirst { it.url == current }
                                                        val toIdx = localBoards.indexOfFirst { it.url == target.key }
                                                        if (fromIdx >= 0 && toIdx >= 0 && fromIdx != toIdx) {
                                                            val newList = localBoards.toMutableList()
                                                            val moved = newList.removeAt(fromIdx)
                                                            newList.add(toIdx, moved)
                                                            localBoards = newList
                                                            onReorderBoards(newList)
                                                        }
                                                    }
                                                }
                                            }
                                            dragOffset = Offset.Zero
                                        },
                                        onDragCancel = {
                                            draggedUrl = null
                                            dragOffset = Offset.Zero
                                            suppressClickUntil = System.currentTimeMillis() + 250
                                        }
                                    )
                                }
                                .clickable {
                                    if (System.currentTimeMillis() > suppressClickUntil) {
                                        onSelectBoard(item.url)
                                        onDismiss()
                                    }
                                }
                                .testTag("board_picker_pill_${item.url.hashCode()}")
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp)
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


def patch_board_picker_v3():
    log("\n=== PATCH: BoardPicker v3 (pills + drag) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/dialogs/BoardPickerDialog.kt"
    if f.exists():
        t = f.read_text(encoding="utf-8")
        if "// v3-pill-drag" in t and "FlowRow" in t and "dragOffset += amount" in t:
            log("  ✓ already v3"); return
        log("  → forcing v3 rewrite")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(NEW_BOARD_PICKER, encoding="utf-8")
    log("  ✓ v3 written (FlowRow pills + drop-based drag)")


# ============================================================
# Declaration order fix (idempotent)
# ============================================================
def patch_declaration_order():
    log("\n=== PATCH: declaration order (fullscreenPinId before isFullscreenActive) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    orig = t

    # Remove fullscreenPinId collection lines
    removed_pinid = 0
    while True:
        m = re.search(r'\n[ \t]*val fullscreenPinId by viewModel\.fullscreenPinId\.collectAsStateWithLifecycle\(\)', t)
        if not m: break
        line_end = t.find("\n", m.start() + 1)
        if line_end < 0: line_end = len(t)
        t = t[:m.start()] + t[line_end:]
        removed_pinid += 1
        if removed_pinid > 20: break

    # Remove isFullscreenActive lines
    removed_std = 0
    while True:
        m = re.search(r'\n[ \t]*val isFullscreenActive = [^\n]*', t)
        if not m: break
        line_end = t.find("\n", m.end())
        if line_end < 0: line_end = len(t)
        t = t[:m.start()] + t[line_end:]
        removed_std += 1
        if removed_std > 20: break

    if removed_pinid == 0 and removed_std == 0:
        # Check if already correct
        pi = t.find("val fullscreenPinId by viewModel.fullscreenPinId.collectAsStateWithLifecycle()")
        si = t.find("val isFullscreenActive = ")
        if pi >= 0 and si >= 0 and pi < si:
            log("  ✓ already correct"); return

    log(f"  → removed {removed_pinid} fullscreenPinId, {removed_std} isFullscreenActive")

    anchors = [
        r'\n([ \t]*)val fullscreenPinIndex by viewModel\.fullscreenPinIndex\.collectAsStateWithLifecycle\(\)',
        r'\n([ \t]*)val currentBoard by viewModel\.currentBoard\.collectAsStateWithLifecycle\(\)',
    ]
    matched = None
    for pat in anchors:
        m = re.search(pat, t)
        if m: matched = m; break
    if not matched:
        log("  ✗ no anchor found"); sys.exit(1)

    indent = matched.group(1)
    insert_at = matched.end()
    new_lines = (
        f"\n{indent}val fullscreenPinId by viewModel.fullscreenPinId.collectAsStateWithLifecycle()"
        f"\n{indent}val isFullscreenActive = fullscreenPinId != null || fullscreenPinIndex != null"
    )
    t = t[:insert_at] + new_lines + t[insert_at:]

    f.write_text(t, encoding="utf-8")
    log("  ✓ declarations reordered")

    pinid_idx = t.find("val fullscreenPinId by viewModel.fullscreenPinId.collectAsStateWithLifecycle()")
    std_idx = t.find("val isFullscreenActive = ")
    if pinid_idx > std_idx:
        log("  ✗ order still wrong"); sys.exit(1)
    log("  ✓ order confirmed")


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
            log("  ⚠ openFullscreen anchor missing")

    if changed: f.write_text(t, encoding="utf-8")
    else: log("  ✓ already patched")


def patch_wire_reorder():
    log("\n=== PATCH: Wire onReorderBoards ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    t = f.read_text(encoding="utf-8")
    if "onReorderBoards = { list -> viewModel.saveReorderedBoards(list, false) }" in t:
        log("  ✓ already wired"); return

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
                log("  ✓ wired")
                return
        i += 1
    log("  ✗ paren failed"); sys.exit(1)


# ============================================================
# Verify
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

    checks = []

    # Declaration order (from prior fix)
    pinid_idx = pts.find("val fullscreenPinId by viewModel.fullscreenPinId.collectAsStateWithLifecycle()")
    std_idx = pts.find("val isFullscreenActive = ")
    checks.append(("fullscreenPinId declared", pinid_idx >= 0))
    checks.append(("isFullscreenActive declared", std_idx >= 0))
    checks.append(("fullscreenPinId BEFORE isFullscreenActive",
                   pinid_idx >= 0 and std_idx >= 0 and pinid_idx < std_idx))
    checks.append(("fullscreenPinId single declaration",
                   pts.count("val fullscreenPinId by viewModel.fullscreenPinId.collectAsStateWithLifecycle()") == 1))
    checks.append(("isFullscreenActive single declaration",
                   pts.count("val isFullscreenActive = ") == 1))

    # VM
    checks.append(("VM fullscreenPinId state", "private val _fullscreenPinId" in vmt))
    checks.append(("VM openFullscreenByPinId", "fun openFullscreenByPinId(pinId: String)" in vmt))

    # BoardPicker v3: pill + drag
    checks.append(("BoardPicker v3 marker", "// v3-pill-drag" in bpt))
    checks.append(("BoardPicker uses FlowRow (pill layout)", "FlowRow(" in bpt))
    checks.append(("BoardPicker pill shape RoundedCornerShape(20.dp)", "RoundedCornerShape(20.dp)" in bpt))
    checks.append(("BoardPicker pill padding 12/7", "horizontal = 12.dp, vertical = 7.dp" in bpt))
    checks.append(("BoardPicker drag detection", "detectDragGesturesAfterLongPress" in bpt))
    checks.append(("BoardPicker dragOffset accumulation", "dragOffset += amount" in bpt))
    checks.append(("BoardPicker reorder callback", "onReorderBoards(newList)" in bpt))
    checks.append(("BoardPicker NOT a full-width Column of rows (no full-width pill modifier)",
                   "modifier = Modifier\n                                .fillMaxWidth()\n                                .height(itemHeightDp)" not in bpt))

    # Wiring
    checks.append(("onReorderBoards wired",
                   "onReorderBoards = { list -> viewModel.saveReorderedBoards(list, false) }" in pts))

    # Bracket balance on screen
    def strip(text):
        out, i = [], 0
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

    stripped_ps = strip(pts)
    po, pc = stripped_ps.count("("), stripped_ps.count(")")
    bo, bc = stripped_ps.count("{"), stripped_ps.count("}")
    checks.append((f"Screen paren balance ({po}/{pc})", po == pc))
    checks.append((f"Screen brace balance ({bo}/{bc})", bo == bc))

    stripped_bp = strip(bpt)
    bpo, bpc = stripped_bp.count("("), stripped_bp.count(")")
    bbo, bbc = stripped_bp.count("{"), stripped_bp.count("}")
    checks.append((f"BoardPicker paren balance ({bpo}/{bpc})", bpo == bpc))
    checks.append((f"BoardPicker brace balance ({bbo}/{bbc})", bbo == bbc))

    all_ok = True
    for name, ok in checks:
        log(f"  {'✓' if ok else '✗'} {name}")
        if not ok: all_ok = False

    if not all_ok:
        log("\n✗ VERIFICATION FAILED"); sys.exit(1)


# ============================================================
# Pipeline helpers (unchanged)
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
        run(["git", "commit", "-m", "BoardPicker v3: pill FlowRow layout preserved + drag-drop reorder"])


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
    log("PinBoard — BoardPicker v3 (pills + drag)")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    patch_board_picker_v3()
    patch_declaration_order()
    patch_vm_fullscreen_pin_id()
    patch_wire_reorder()
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