#!/usr/bin/env python3
"""
PinBoard Gallery — Album/Board transfer for pins + albums + mixed
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


def patch_transfer_albums():
    log("\n=== PATCH: Transfer albums + mixed selection ===")
    vm_f = PROJECT_ROOT / "app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt"
    ps_f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not vm_f.exists(): log("  ✗ VM missing"); sys.exit(1)
    if not ps_f.exists(): log("  ✗ Screen missing"); sys.exit(1)

    t = vm_f.read_text(encoding="utf-8")
    changed = False

    # ---------- 1. PendingAlbumTransfer: add albumIds ----------
    old_dc = (
        'data class PendingAlbumTransfer(\n'
        '    val pinIds: Set<String>,\n'
        '    val mode: AlbumTransferMode,\n'
        '    val sourceBoardId: String,\n'
        '    val savedSelectionPinIds: Set<String>,\n'
        '    val savedSelectionAlbumIds: Set<String>\n'
        ')\n'
    )
    new_dc = (
        'data class PendingAlbumTransfer(\n'
        '    val pinIds: Set<String>,\n'
        '    val albumIds: Set<String>,\n'
        '    val mode: AlbumTransferMode,\n'
        '    val sourceBoardId: String,\n'
        '    val savedSelectionPinIds: Set<String>,\n'
        '    val savedSelectionAlbumIds: Set<String>\n'
        ')\n'
    )
    if old_dc in t:
        t = t.replace(old_dc, new_dc, 1); changed = True
        log("  ✓ PendingAlbumTransfer.albumIds added")
    elif 'val albumIds: Set<String>,\n    val mode: AlbumTransferMode' in t:
        log("  ✓ PendingAlbumTransfer already has albumIds")

    # ---------- 2. beginAlbumTransfer new signature ----------
    old_bm = "    fun beginAlbumTransfer(pinIds: Set<String>, mode: AlbumTransferMode) {"
    new_bm = "    fun beginAlbumTransfer(pinIds: Set<String>, albumIds: Set<String>, mode: AlbumTransferMode) {"
    if new_bm in t:
        log("  ✓ beginAlbumTransfer already 3-arg")
    elif old_bm in t:
        end_idx = find_function_end(t, old_bm)
        if end_idx > 0:
            idx = t.find(old_bm)
            new_fn = """    fun beginAlbumTransfer(pinIds: Set<String>, albumIds: Set<String>, mode: AlbumTransferMode) {
        if (pinIds.isEmpty() && albumIds.isEmpty()) return
        val board = _currentBoard.value ?: return
        _pendingAlbumTransfer.value = PendingAlbumTransfer(
            pinIds = pinIds, albumIds = albumIds, mode = mode, sourceBoardId = board.id,
            savedSelectionPinIds = _selectedPinIds.value,
            savedSelectionAlbumIds = _selectedAlbumIds.value
        )
        _isSelectionMode.value = false
    }
"""
            t = t[:idx] + new_fn + t[end_idx:]
            changed = True
            log("  ✓ beginAlbumTransfer updated")

    # ---------- 3. performTransfer helper ----------
    if "private suspend fun performTransfer(" not in t:
        anchor = "    fun executeAlbumTransfer(targetAlbum: DateAlbum, targetBoardId: String) {"
        idx = t.find(anchor)
        if idx < 0:
            log("  ✗ executeAlbumTransfer anchor not found (for helper insert)")
        else:
            helper = '''    private suspend fun performTransfer(
        dao: BoardDao,
        sourceBoardId: String,
        pinIds: Set<String>,
        albumIds: Set<String>,
        targetBoardId: String,
        targetAlbumId: String?,
        mode: AlbumTransferMode
    ): Pair<Int, Int> {
        val sourcePins = dao.getPinsForBoard(sourceBoardId).map { it.toPinItem() }
        val sourceAlbums = dao.getAlbumsForBoard(sourceBoardId)
        val selectedAlbums = sourceAlbums.filter { albumIds.contains(it.id) }
        if (selectedAlbums.isEmpty() && pinIds.isEmpty()) return 0 to 0
        val selectedAlbumIdSet = selectedAlbums.map { it.id }.toSet()

        // Full album tree (selected + all descendants)
        val albumIdsInTransfer = mutableSetOf<String>()
        val toVisit = selectedAlbums.map { it.id }.toMutableList()
        while (toVisit.isNotEmpty()) {
            val id = toVisit.removeAt(0)
            if (!albumIdsInTransfer.add(id)) continue
            sourceAlbums.filter { it.parentAlbumId == id }.forEach { toVisit.add(it.id) }
        }

        // Cycle prevention
        if (targetAlbumId != null && albumIdsInTransfer.contains(targetAlbumId)) {
            throw IllegalStateException("Cannot transfer an album into itself or its descendants")
        }

        // Pins traveling with albums
        val pinsInAlbums = sourcePins.filter { it.albumId != null && albumIdsInTransfer.contains(it.albumId) }
        // Standalone pins (explicitly selected, not in transferred albums)
        val standalonePins = sourcePins.filter { pinIds.contains(it.id) && (it.albumId == null || !albumIdsInTransfer.contains(it.albumId)) }

        val targetPinDates = dao.getPinsForBoard(targetBoardId).map { it.dateAddedMillis }
        val targetAlbumDates = dao.getAlbumsForBoard(targetBoardId).map { it.dateAddedMillis }
        var nextDate = maxOf(targetPinDates.maxOrNull() ?: 0L, targetAlbumDates.maxOrNull() ?: 0L) + 60_000L
        val crossingBoard = sourceBoardId != targetBoardId

        fun isRootOfTransfer(album: com.example.data.local.CustomAlbumEntity): Boolean {
            var p = album.parentAlbumId
            while (p != null) {
                if (selectedAlbumIdSet.contains(p)) return false
                p = sourceAlbums.firstOrNull { it.id == p }?.parentAlbumId
            }
            return true
        }

        when (mode) {
            AlbumTransferMode.COPY -> {
                val albumIdMap = mutableMapOf<String, String>()
                val albumsToCopy = sourceAlbums.filter { albumIdsInTransfer.contains(it.id) }
                val roots = selectedAlbums.filter { isRootOfTransfer(it) }
                val ordered = mutableListOf<com.example.data.local.CustomAlbumEntity>()
                val visited = mutableSetOf<String>()
                fun visit(album: com.example.data.local.CustomAlbumEntity) {
                    if (!visited.add(album.id)) return
                    ordered.add(album)
                    albumsToCopy.filter { it.parentAlbumId == album.id }.forEach { visit(it) }
                }
                roots.forEach { visit(it) }
                albumsToCopy.forEach { if (it.id !in visited) visit(it) }

                var pinCounter = 0
                val newPins = mutableListOf<PinEntity>()
                ordered.forEach { album ->
                    val newId = "album_copy_${System.currentTimeMillis()}_${(1000..9999).random()}"
                    albumIdMap[album.id] = newId
                    val newParent = if (isRootOfTransfer(album)) targetAlbumId else albumIdMap[album.parentAlbumId]
                    val thisDate = nextDate; nextDate += 1000L
                    dao.insertAlbum(album.copy(
                        id = newId, boardId = targetBoardId,
                        parentAlbumId = newParent, dateAddedMillis = thisDate
                    ))
                    pinsInAlbums.filter { it.albumId == album.id }.forEach { pin ->
                        val thisPinDate = nextDate; nextDate += 100L
                        newPins.add(PinEntity.fromPinItem(
                            pin.copy(
                                id = "pin_copy_${System.currentTimeMillis()}_${pinCounter}_${(1000..9999).random()}",
                                albumId = newId, dateAddedMillis = thisPinDate
                            ),
                            targetBoardId, pinCounter++
                        ))
                    }
                }
                standalonePins.forEach { pin ->
                    val thisPinDate = nextDate; nextDate += 100L
                    newPins.add(PinEntity.fromPinItem(
                        pin.copy(
                            id = "pin_copy_${System.currentTimeMillis()}_${pinCounter}_${(1000..9999).random()}",
                            albumId = targetAlbumId, dateAddedMillis = thisPinDate
                        ),
                        targetBoardId, pinCounter++
                    ))
                }
                if (newPins.isNotEmpty()) dao.upsertPinsSafely(newPins)
                return newPins.size to ordered.size
            }
            AlbumTransferMode.MOVE -> {
                val albumsToMove = sourceAlbums.filter { albumIdsInTransfer.contains(it.id) }
                albumsToMove.forEach { album ->
                    val newParent = if (isRootOfTransfer(album)) targetAlbumId else album.parentAlbumId
                    val newDate = if (isRootOfTransfer(album)) { val d = nextDate; nextDate += 1000L; d } else album.dateAddedMillis
                    dao.insertAlbum(album.copy(
                        boardId = targetBoardId, parentAlbumId = newParent, dateAddedMillis = newDate
                    ))
                }
                if (crossingBoard) {
                    val movedPins = pinsInAlbums.map { pin ->
                        PinEntity.fromPinItem(pin, targetBoardId, pin.boardPosition)
                    }
                    if (movedPins.isNotEmpty()) {
                        dao.upsertPinsSafely(movedPins)
                        dao.deletePinsFromBoard(sourceBoardId, pinsInAlbums.map { it.id })
                    }
                }
                val standaloneEntities = standalonePins.mapIndexed { i, pin ->
                    PinEntity.fromPinItem(
                        pin.copy(albumId = targetAlbumId, dateAddedMillis = nextDate + i * 100L),
                        targetBoardId, i
                    )
                }
                if (standaloneEntities.isNotEmpty()) {
                    dao.upsertPinsSafely(standaloneEntities)
                    if (crossingBoard) {
                        dao.deletePinsFromBoard(sourceBoardId, standalonePins.map { it.id })
                    }
                }
                return standalonePins.size + pinsInAlbums.size to albumsToMove.size
            }
        }
    }

'''
            t = t[:idx] + helper + t[idx:]
            changed = True
            log("  ✓ performTransfer helper added")

    # ---------- 4. executeAlbumTransfer replaced ----------
    marker = "    fun executeAlbumTransfer(targetAlbum: DateAlbum, targetBoardId: String) {"
    if "// Comprehensive executeAlbumTransfer" not in t and marker in t:
        end_idx = find_function_end(t, marker)
        if end_idx > 0:
            idx = t.find(marker)
            new_fn = '''    // Comprehensive executeAlbumTransfer — handles pins + albums
    fun executeAlbumTransfer(targetAlbum: DateAlbum, targetBoardId: String) {
        val transfer = _pendingAlbumTransfer.value ?: return
        val ctx = appContext ?: return
        viewModelScope.launch {
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            try {
                val (pinCount, albumCount) = performTransfer(
                    dao = dao, sourceBoardId = transfer.sourceBoardId,
                    pinIds = transfer.pinIds, albumIds = transfer.albumIds,
                    targetBoardId = targetBoardId, targetAlbumId = targetAlbum.id,
                    mode = transfer.mode
                )
                val curr = _currentBoard.value
                if (curr != null) {
                    val refreshed = withContext(Dispatchers.IO) { dao.getPinsForBoard(curr.id).map { it.toPinItem() } }
                    val refreshedAlbums = withContext(Dispatchers.IO) { dao.getAlbumsForBoard(curr.id) }
                    withContext(Dispatchers.Main) {
                        _rawPins.value = refreshed
                        _customAlbums.value = refreshedAlbums
                        _currentBoard.value = curr.copy(pins = refreshed, pinCount = refreshed.size)
                        updateDisplayedPins()
                    }
                }
                _pendingAlbumTransfer.value = null
                withContext(Dispatchers.Main) {
                    clearSelection()
                    val verb = if (transfer.mode == AlbumTransferMode.MOVE) "Moved" else "Copied"
                    val pinPart = "$pinCount image${if (pinCount != 1) "s" else ""}"
                    val albumPart = if (albumCount > 0) " + $albumCount album${if (albumCount != 1) "s" else ""}" else ""
                    _snackbarMessage.value = "$verb $pinPart$albumPart to \\"${targetAlbum.title}\\""
                }
            } catch (e: IllegalStateException) {
                _pendingAlbumTransfer.value = null
                withContext(Dispatchers.Main) { _snackbarMessage.value = e.message ?: "Cannot transfer" }
            }
        }
    }
'''
            t = t[:idx] + new_fn + t[end_idx:]
            changed = True
            log("  ✓ executeAlbumTransfer replaced (handles albums)")

    # ---------- 5. executeAlbumTransferToCurrentBoard replaced ----------
    marker2 = "    fun executeAlbumTransferToCurrentBoard() {"
    if "// Comprehensive executeAlbumTransferToCurrentBoard" not in t and marker2 in t:
        end_idx = find_function_end(t, marker2)
        if end_idx > 0:
            idx = t.find(marker2)
            new_fn = '''    // Comprehensive executeAlbumTransferToCurrentBoard — handles pins + albums
    fun executeAlbumTransferToCurrentBoard() {
        val transfer = _pendingAlbumTransfer.value ?: return
        val currentBoard = _currentBoard.value ?: return
        viewModelScope.launch {
            val ctx = appContext ?: return@launch
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            try {
                if (currentBoard.id == transfer.sourceBoardId) {
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
                    val refreshed = withContext(Dispatchers.IO) { dao.getPinsForBoard(currentBoard.id).map { it.toPinItem() } }
                    val refreshedAlbums = withContext(Dispatchers.IO) { dao.getAlbumsForBoard(currentBoard.id) }
                    withContext(Dispatchers.Main) {
                        _rawPins.value = refreshed
                        _customAlbums.value = refreshedAlbums
                        _currentBoard.value = currentBoard.copy(pins = refreshed, pinCount = refreshed.size)
                        updateDisplayedPins()
                    }
                    val verb = if (transfer.mode == AlbumTransferMode.MOVE) "Moved" else "Copied"
                    val pinPart = "$pinCount image${if (pinCount != 1) "s" else ""}"
                    val albumPart = if (albumCount > 0) " + $albumCount album${if (albumCount != 1) "s" else ""}" else ""
                    _snackbarMessage.value = "$verb $pinPart$albumPart to ${currentBoard.title}"
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
            log("  ✓ executeAlbumTransferToCurrentBoard replaced (handles albums)")

    # ---------- 6. moveToTopInternal extended ----------
    old_marker = "    private suspend fun moveToTopInternal(sourceBoardId: String, pinIds: Set<String>, albumIds: Set<String>, dao: BoardDao) {"
    if "// Extended: dissolve parent albums that become empty" not in t and old_marker in t:
        end_idx = find_function_end(t, old_marker)
        if end_idx > 0:
            idx = t.find(old_marker)
            new_fn = '''    // Extended: dissolve parent albums that become empty
    private suspend fun moveToTopInternal(sourceBoardId: String, pinIds: Set<String>, albumIds: Set<String>, dao: BoardDao) {
        val allPins = withContext(Dispatchers.IO) { dao.getPinsForBoard(sourceBoardId).map { it.toPinItem() } }
        val allAlbums = withContext(Dispatchers.IO) { dao.getAlbumsForBoard(sourceBoardId) }
        val maxPinDate = allPins.maxOfOrNull { it.dateAddedMillis } ?: 0L
        val maxAlbumDate = allAlbums.maxOfOrNull { it.dateAddedMillis } ?: 0L
        var nextDate = maxOf(maxPinDate, maxAlbumDate) + 60_000L

        val affectedAlbumIds = mutableSetOf<String>()
        val updatedPins = allPins.map { p ->
            if (pinIds.contains(p.id)) {
                p.albumId?.let { affectedAlbumIds.add(it) }
                p.copy(albumId = null, dateAddedMillis = nextDate).also { nextDate += 1000L }
            } else p
        }
        albumIds.forEach { movedId ->
            val parent = allAlbums.firstOrNull { it.id == movedId }?.parentAlbumId
            if (parent != null) affectedAlbumIds.add(parent)
        }
        val updatedAlbums = allAlbums.map { a ->
            if (albumIds.contains(a.id)) {
                a.copy(parentAlbumId = null, dateAddedMillis = nextDate).also { nextDate += 1000L }
            } else a
        }
        val pinsByAlbum = updatedPins.filter { it.albumId != null }.groupBy { it.albumId!! }
        val childrenByAlbum = updatedAlbums.filter { it.parentAlbumId != null }.groupBy { it.parentAlbumId!! }
        val nonEmptyAlbumIds = pinsByAlbum.keys + childrenByAlbum.keys
        val dissolvedAlbumIds = affectedAlbumIds - nonEmptyAlbumIds
        val finalAlbums = updatedAlbums.filterNot { it.id in dissolvedAlbumIds }

        withContext(Dispatchers.IO) {
            dao.upsertPinsSafely(updatedPins.mapIndexed { i, p -> PinEntity.fromPinItem(p, sourceBoardId, i) })
            updatedAlbums.filter { it.id in albumIds }.forEach { dao.insertAlbum(it) }
            dissolvedAlbumIds.forEach { dao.deleteAlbum(it) }
        }

        val curr = _currentBoard.value
        if (curr != null && curr.id == sourceBoardId) {
            withContext(Dispatchers.Main) {
                _rawPins.value = updatedPins
                _customAlbums.value = finalAlbums
                _currentBoard.value = curr.copy(pins = updatedPins, pinCount = updatedPins.size)
                updateDisplayedPins(resetLimit = true)
            }
        }
    }
'''
            t = t[:idx] + new_fn + t[end_idx:]
            changed = True
            log("  ✓ moveToTopInternal extended (parent dissolution)")

    if changed:
        vm_f.write_text(t, encoding="utf-8")

    # ---------- PinBoardGalleryScreen ----------
    ps_t = ps_f.read_text(encoding="utf-8")
    ps_changed = False

    if "viewModel.beginAlbumTransfer(selectedPinIds, com.example.viewmodel.AlbumTransferMode.COPY)" in ps_t:
        ps_t = ps_t.replace(
            "viewModel.beginAlbumTransfer(selectedPinIds, com.example.viewmodel.AlbumTransferMode.COPY)",
            "viewModel.beginAlbumTransfer(selectedPinIds, selectedAlbumIds, com.example.viewmodel.AlbumTransferMode.COPY)",
            1
        )
        ps_changed = True
        log("  ✓ COPY call passes albums")

    if "viewModel.beginAlbumTransfer(selectedPinIds, com.example.viewmodel.AlbumTransferMode.MOVE)" in ps_t:
        ps_t = ps_t.replace(
            "viewModel.beginAlbumTransfer(selectedPinIds, com.example.viewmodel.AlbumTransferMode.MOVE)",
            "viewModel.beginAlbumTransfer(selectedPinIds, selectedAlbumIds, com.example.viewmodel.AlbumTransferMode.MOVE)",
            1
        )
        ps_changed = True
        log("  ✓ MOVE call passes albums")

    old_banner = '"Tap an album to ${if (transfer.mode == com.example.viewmodel.AlbumTransferMode.MOVE) "move" else "copy"} ${transfer.pinIds.size} image${if (transfer.pinIds.size > 1) "s" else ""}"'
    new_banner = '"Tap an album to ${if (transfer.mode == com.example.viewmodel.AlbumTransferMode.MOVE) "move" else "copy"} ${transfer.pinIds.size + transfer.albumIds.size} item${if ((transfer.pinIds.size + transfer.albumIds.size) != 1) "s" else ""}"'
    if old_banner in ps_t:
        ps_t = ps_t.replace(old_banner, new_banner, 1)
        ps_changed = True
        log("  ✓ banner combined count")
    elif new_banner in ps_t:
        log("  ✓ banner already updated")

    if ps_changed:
        ps_f.write_text(ps_t, encoding="utf-8")

    # ---------- Self-verify ----------
    log("\n=== Self-verify ===")
    t_v = vm_f.read_text(encoding="utf-8")
    t_p = ps_f.read_text(encoding="utf-8")
    checks = [
        ("PendingAlbumTransfer.albumIds", "val albumIds: Set<String>," in t_v),
        ("beginAlbumTransfer 3-arg", "fun beginAlbumTransfer(pinIds: Set<String>, albumIds: Set<String>, mode: AlbumTransferMode)" in t_v),
        ("performTransfer helper", "private suspend fun performTransfer(" in t_v),
        ("executeAlbumTransfer replaced", "// Comprehensive executeAlbumTransfer" in t_v),
        ("executeAlbumTransferToCurrentBoard replaced", "// Comprehensive executeAlbumTransferToCurrentBoard" in t_v),
        ("moveToTopInternal extended", "// Extended: dissolve parent albums that become empty" in t_v),
        ("cycle prevention", "Cannot transfer an album into itself" in t_v),
        ("copy call has albums", "viewModel.beginAlbumTransfer(selectedPinIds, selectedAlbumIds" in t_p),
        ("banner combined count", "transfer.pinIds.size + transfer.albumIds.size" in t_p),
    ]
    all_ok = True
    for label, ok in checks:
        log(f"  {'✓' if ok else '✗'} {label}")
        if not ok: all_ok = False
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
        run(["git", "commit", "-m", "Move/Copy albums + mixed selection (nested album support)"])


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
    log("PinBoard — Move/Copy albums + mixed selection")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    patch_transfer_albums()

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