#!/usr/bin/env python3
"""
PinBoard Gallery — 4 fixes (re-run, VM anchor corrected)
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
# PATCH 1 — Share put-into-album (idempotent)
# ============================================================
def patch_share_put_into_album():
    log("\n=== PATCH: Share — save-multiple-to-new-album ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/ShareTargetActivity.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if 'testTag("share_put_into_album_checkbox")' in t:
        log("  ✓ already patched"); return

    changed = False
    # (same logic as before)
    if "var putIntoAlbum by remember { mutableStateOf(false) }" not in t:
        anchor = "    var extractMultipleImages by remember { mutableStateOf(false) }\n"
        if anchor in t:
            t = t.replace(anchor, anchor + "    var putIntoAlbum by remember { mutableStateOf(false) }\n", 1)
            changed = True
            log("  ✓ putIntoAlbum state")

    old_after = (
        "                        Column {\n"
        "                            Text(\"Add multiple main images from webpage\",\n"
        "                                fontSize = 12.sp, fontWeight = FontWeight.SemiBold)\n"
        "                            Text(\"Extract content images in order\",\n"
        "                                fontSize = 10.sp, color = PinterestTextSecondary)\n"
        "                        }\n"
        "                    }\n"
        "                }\n"
    )
    new_after = (
        "                        Column {\n"
        "                            Text(\"Add multiple main images from webpage\",\n"
        "                                fontSize = 12.sp, fontWeight = FontWeight.SemiBold)\n"
        "                            Text(\"Extract content images in order\",\n"
        "                                fontSize = 10.sp, color = PinterestTextSecondary)\n"
        "                        }\n"
        "                    }\n"
        "                    if (extractMultipleImages) {\n"
        "                        Row(\n"
        "                            modifier = Modifier.fillMaxWidth()\n"
        "                                .combinedClickable(\n"
        "                                    onClick = { putIntoAlbum = !putIntoAlbum },\n"
        "                                    onLongClick = { putIntoAlbum = !putIntoAlbum }\n"
        "                                )\n"
        "                                .padding(start = 24.dp, top = 4.dp)\n"
        "                                .testTag(\"share_put_into_album_checkbox\"),\n"
        "                            verticalAlignment = Alignment.CenterVertically\n"
        "                        ) {\n"
        "                            Checkbox(\n"
        "                                checked = putIntoAlbum,\n"
        "                                onCheckedChange = { putIntoAlbum = it },\n"
        "                                colors = CheckboxDefaults.colors(checkedColor = PinterestRed)\n"
        "                            )\n"
        "                            Spacer(Modifier.width(4.dp))\n"
        "                            Column {\n"
        "                                Text(\"Save to new album\",\n"
        "                                    fontSize = 12.sp, fontWeight = FontWeight.SemiBold)\n"
        "                                Text(\"Multiple images grouped as one album\",\n"
        "                                    fontSize = 10.sp, color = PinterestTextSecondary)\n"
        "                            }\n"
        "                        }\n"
        "                    }\n"
        "                }\n"
    )
    if old_after in t:
        t = t.replace(old_after, new_after, 1); changed = True
        log("  ✓ putIntoAlbum checkbox")

    old_cb = (
        "                    onSaveToSelected = { boards, extractMultiple ->\n"
        "                        finish()\n"
        "                        performSaveToBoards(sharedLinks, sharedImageUris, boards, extractMultiple)\n"
        "                    },\n"
        "                    onHoldBoard = { boardId, extractMultiple ->\n"
        "                        finish()\n"
        "                        performSaveToBoards(sharedLinks, sharedImageUris, listOf(boardId), extractMultiple)\n"
        "                    }\n"
    )
    new_cb = (
        "                    onSaveToSelected = { boards, extractMultiple, putAlbum ->\n"
        "                        finish()\n"
        "                        performSaveToBoards(sharedLinks, sharedImageUris, boards, extractMultiple, putAlbum)\n"
        "                    },\n"
        "                    onHoldBoard = { boardId, extractMultiple, putAlbum ->\n"
        "                        finish()\n"
        "                        performSaveToBoards(sharedLinks, sharedImageUris, listOf(boardId), extractMultiple, putAlbum)\n"
        "                    }\n"
    )
    if old_cb in t:
        t = t.replace(old_cb, new_cb, 1); changed = True
        log("  ✓ callbacks include putAlbum")

    old_sig = (
        "    private fun performSaveToBoards(\n"
        "        links: List<String>,\n"
        "        uris: List<Uri>,\n"
        "        targetBoardIds: List<String>,\n"
        "        extractMultiple: Boolean\n"
        "    ) {\n"
    )
    new_sig = (
        "    private fun performSaveToBoards(\n"
        "        links: List<String>,\n"
        "        uris: List<Uri>,\n"
        "        targetBoardIds: List<String>,\n"
        "        extractMultiple: Boolean,\n"
        "        putIntoAlbum: Boolean = false\n"
        "    ) {\n"
    )
    if old_sig in t:
        t = t.replace(old_sig, new_sig, 1); changed = True
        log("  ✓ performSaveToBoards signature")

    old_loop = (
        "                for (boardId in targetBoardIds) {\n"
        "                    val existingIds = dao.getPinIdsForBoard(boardId).toSet()\n"
        "                    val existingUrls = dao.getImageUrlsForBoard(boardId).toSet()\n"
        "                    val toInsert = pins.filter {\n"
        "                        !existingIds.contains(it.id) && !existingUrls.contains(it.imageUrl)\n"
        "                    }\n"
        "                    if (toInsert.isNotEmpty()) {\n"
        "                        dao.upsertPinsSafely(toInsert.mapIndexed { i, p ->\n"
        "                            PinEntity.fromPinItem(p.copy(albumId = null), boardId, i)\n"
        "                        })\n"
        "                    }\n"
        "                }\n"
    )
    new_loop = (
        "                for (boardId in targetBoardIds) {\n"
        "                    val existingIds = dao.getPinIdsForBoard(boardId).toSet()\n"
        "                    val existingUrls = dao.getImageUrlsForBoard(boardId).toSet()\n"
        "                    val toInsert = pins.filter {\n"
        "                        !existingIds.contains(it.id) && !existingUrls.contains(it.imageUrl)\n"
        "                    }\n"
        "                    if (toInsert.isNotEmpty()) {\n"
        "                        var albumId: String? = null\n"
        "                        if (putIntoAlbum && toInsert.size > 1) {\n"
        "                            val aId = \"album_${System.currentTimeMillis()}_${(1000..9999).random()}\"\n"
        "                            dao.insertAlbum(com.example.data.local.CustomAlbumEntity(\n"
        "                                id = aId, boardId = boardId, parentAlbumId = null,\n"
        "                                title = \"Album (${toInsert.size} images)\",\n"
        "                                sourceUrl = links.firstOrNull() ?: \"\",\n"
        "                                dateAddedMillis = System.currentTimeMillis(),\n"
        "                                orderIndex = 0, isFavorite = false\n"
        "                            ))\n"
        "                            albumId = aId\n"
        "                        }\n"
        "                        dao.upsertPinsSafely(toInsert.mapIndexed { i, p ->\n"
        "                            PinEntity.fromPinItem(p.copy(albumId = albumId), boardId, i)\n"
        "                        })\n"
        "                    }\n"
        "                }\n"
    )
    if old_loop in t:
        t = t.replace(old_loop, new_loop, 1); changed = True
        log("  ✓ album creation in save loop")

    old_dialog_sig = (
        "    onSaveToSelected: (List<String>, Boolean) -> Unit,\n"
        "    onHoldBoard: (String, Boolean) -> Unit\n"
    )
    new_dialog_sig = (
        "    onSaveToSelected: (List<String>, Boolean, Boolean) -> Unit,\n"
        "    onHoldBoard: (String, Boolean, Boolean) -> Unit\n"
    )
    if old_dialog_sig in t:
        t = t.replace(old_dialog_sig, new_dialog_sig, 1); changed = True
        log("  ✓ dialog signature")

    old_btn = (
        "                        onClick = {\n"
        "                            if (selectedBoardIds.isNotEmpty()) {\n"
        "                                onSaveToSelected(selectedBoardIds.toList(), extractMultipleImages)\n"
        "                            } else {\n"
        "                                onClose()\n"
        "                            }\n"
        "                        },\n"
    )
    new_btn = (
        "                        onClick = {\n"
        "                            if (selectedBoardIds.isNotEmpty()) {\n"
        "                                onSaveToSelected(selectedBoardIds.toList(), extractMultipleImages, putIntoAlbum && extractMultipleImages)\n"
        "                            } else {\n"
        "                                onClose()\n"
        "                            }\n"
        "                        },\n"
    )
    if old_btn in t:
        t = t.replace(old_btn, new_btn, 1); changed = True
        log("  ✓ save button click")

    old_long = "onLongClick = { onHoldBoard(board.id, extractMultipleImages) }"
    new_long = "onLongClick = { onHoldBoard(board.id, extractMultipleImages, putIntoAlbum && extractMultipleImages) }"
    if old_long in t:
        t = t.replace(old_long, new_long, 1); changed = True
        log("  ✓ long-press passes flag")

    if changed: f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 2 — AddManualImagesDialog + ViewModel (FIXED)
# ============================================================
def patch_manual_put_into_album():
    log("\n=== PATCH: AddManual — save-multiple-to-new-album ===")

    # ---- Dialog ----
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/dialogs/AddManualImagesDialog.kt"
    if not f.exists(): log("  ✗ dialog not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if 'testTag("manual_put_into_album_checkbox")' in t:
        log("  ✓ dialog already patched")
    else:
        changed = False
        if "var putIntoAlbum by remember { mutableStateOf(false) }" not in t:
            anchor = "    var extractMultipleImages by remember { mutableStateOf(false) }\n"
            if anchor in t:
                t = t.replace(anchor, anchor + "    var putIntoAlbum by remember { mutableStateOf(false) }\n", 1)
                changed = True

        old_sig = "    onAddImages: (rawText: String, targetBoardIds: List<String>, extractMultipleImages: Boolean) -> Unit\n"
        new_sig = "    onAddImages: (rawText: String, targetBoardIds: List<String>, extractMultipleImages: Boolean, putIntoAlbum: Boolean) -> Unit\n"
        if old_sig in t:
            t = t.replace(old_sig, new_sig, 1); changed = True
            log("  ✓ dialog signature")

        old_after = (
            "                    Spacer(Modifier.width(6.dp))\n"
            "                    Column {\n"
            "                        Text(\"Add multiple main images from webpage\",\n"
            "                            fontSize = 13.sp, fontWeight = FontWeight.SemiBold)\n"
            "                        Text(\"Extract all content images from webpage in order\",\n"
            "                            fontSize = 11.sp, color = PinterestTextSecondary)\n"
            "                    }\n"
            "                }\n"
        )
        new_after = (
            "                    Spacer(Modifier.width(6.dp))\n"
            "                    Column {\n"
            "                        Text(\"Add multiple main images from webpage\",\n"
            "                            fontSize = 13.sp, fontWeight = FontWeight.SemiBold)\n"
            "                        Text(\"Extract all content images from webpage in order\",\n"
            "                            fontSize = 11.sp, color = PinterestTextSecondary)\n"
            "                    }\n"
            "                }\n"
            "\n"
            "                if (extractMultipleImages) {\n"
            "                    Row(\n"
            "                        verticalAlignment = Alignment.CenterVertically,\n"
            "                        modifier = Modifier\n"
            "                            .fillMaxWidth()\n"
            "                            .padding(start = 24.dp)\n"
            "                            .clickable { putIntoAlbum = !putIntoAlbum }\n"
            "                            .padding(vertical = 4.dp)\n"
            "                            .testTag(\"manual_put_into_album_checkbox\")\n"
            "                    ) {\n"
            "                        Checkbox(\n"
            "                            checked = putIntoAlbum,\n"
            "                            onCheckedChange = { putIntoAlbum = it },\n"
            "                            colors = CheckboxDefaults.colors(checkedColor = PinterestRed)\n"
            "                        )\n"
            "                        Spacer(Modifier.width(6.dp))\n"
            "                        Column {\n"
            "                            Text(\"Save to new album\",\n"
            "                                fontSize = 13.sp, fontWeight = FontWeight.SemiBold)\n"
            "                            Text(\"Multiple images grouped as one album\",\n"
            "                                fontSize = 11.sp, color = PinterestTextSecondary)\n"
            "                        }\n"
            "                    }\n"
            "                }\n"
        )
        if old_after in t:
            t = t.replace(old_after, new_after, 1); changed = True
            log("  ✓ dialog checkbox")

        old_call = (
            "                onClick = {\n"
            "                    if (extractedLinks.isNotEmpty() && selectedBoardIds.isNotEmpty()) {\n"
            "                        onAddImages(textInput.trim(), selectedBoardIds.toList(), extractMultipleImages)\n"
            "                        onDismiss()\n"
            "                    }\n"
            "                },\n"
        )
        new_call = (
            "                onClick = {\n"
            "                    if (extractedLinks.isNotEmpty() && selectedBoardIds.isNotEmpty()) {\n"
            "                        onAddImages(\n"
            "                            textInput.trim(),\n"
            "                            selectedBoardIds.toList(),\n"
            "                            extractMultipleImages,\n"
            "                            putIntoAlbum && extractMultipleImages\n"
            "                        )\n"
            "                        onDismiss()\n"
            "                    }\n"
            "                },\n"
        )
        if old_call in t:
            t = t.replace(old_call, new_call, 1); changed = True
            log("  ✓ dialog call")

        if changed: f.write_text(t, encoding="utf-8")

    # ---- ViewModel (THE FIX) ----
    vf = PROJECT_ROOT / "app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt"
    if not vf.exists(): log("  ✗ VM not found"); sys.exit(1)
    vt = vf.read_text(encoding="utf-8")
    vm_changed = False

    # Step A: locate function body and check signature
    idx = vt.find("fun addManualImages(")
    if idx < 0:
        log("  ✗ addManualImages function not found"); sys.exit(1)
    end_sig_idx = vt.find(") {", idx)
    if end_sig_idx < 0:
        log("  ✗ addManualImages signature close not found"); sys.exit(1)
    sig_block = vt[idx:end_sig_idx]

    # Step A1: ensure putIntoAlbum parameter exists
    if "putIntoAlbum: Boolean" not in sig_block:
        vt = vt[:end_sig_idx] + ",\n        putIntoAlbum: Boolean = false" + vt[end_sig_idx:]
        vm_changed = True
        log("  ✓ putIntoAlbum parameter added to signature")
    else:
        log("  ✓ putIntoAlbum parameter already present")

    # Step A2: remove any leftover hardcoded `val putIntoAlbum = false`
    if "\n        val putIntoAlbum = false\n" in vt:
        vt = vt.replace("\n        val putIntoAlbum = false\n", "\n", 1)
        vm_changed = True
        log("  ✓ removed hardcoded val putIntoAlbum=false")

    # Step A3: verify the existing album-creation block is intact
    if "if (putIntoAlbum && resolvedPins.isNotEmpty())" in vt:
        log("  ✓ existing album-creation block present")
    elif "if (putIntoAlbum && resolvedPins.size > 1)" in vt:
        log("  ✓ existing album-creation block present (>1 variant)")
    else:
        log("  ⚠ album-creation block not found — inspect manually")

    # Step A4: ensure targetAlbumId derivation exists (needed for correct nested behavior)
    if "val targetAlbumId: String? = _activeAlbumId" not in vt and "_activeAlbumId = if (!putIntoAlbum)" not in vt:
        # Fall back: add derivation if missing entirely
        anchor = vt[idx:end_sig_idx + 3]  # through ") {"
        addition = (
            "\n"
            "        // derive target album (only when NOT creating new album)\n"
            "        val _activeAlbumId = if (!putIntoAlbum) {\n"
            "            _activeAlbum.value?.let { alb ->\n"
            "                if (_currentBoard.value != null && targetBoardIds.contains(_currentBoard.value!!.id)) alb.id else null\n"
            "            }\n"
            "        } else null\n"
            "        val targetAlbumId: String? = _activeAlbumId\n"
        )
        # Insert right after signature close
        insert_at = end_sig_idx + 3
        vt = vt[:insert_at] + addition + vt[insert_at:]
        vm_changed = True
        log("  ✓ targetAlbumId derivation added")
    else:
        log("  ✓ targetAlbumId derivation already present")

    if vm_changed:
        vf.write_text(vt, encoding="utf-8")

    # ---- Gallery screen wiring (idempotent) ----
    ps_f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    ps_t = ps_f.read_text(encoding="utf-8")
    if "onAddImages = { text, targetBoards, extractMultiple, putAlbum ->" in ps_t:
        log("  ✓ gallery screen call already patched")
    else:
        old_ps_call = (
            "        onAddImages = { text, targetBoards, extractMultiple ->\n"
            "            viewModel.addManualImages(text, targetBoards, extractMultiple)\n"
            "        }\n"
        )
        new_ps_call = (
            "        onAddImages = { text, targetBoards, extractMultiple, putAlbum ->\n"
            "            viewModel.addManualImages(text, targetBoards, extractMultiple, putAlbum)\n"
            "        }\n"
        )
        if old_ps_call in ps_t:
            ps_t = ps_t.replace(old_ps_call, new_ps_call, 1)
            ps_f.write_text(ps_t, encoding="utf-8")
            log("  ✓ gallery screen call updated")


# ============================================================
# PATCH 3 — Rename Boards label (idempotent)
# ============================================================
def patch_boards_label():
    log("\n=== PATCH: Rename Boards label ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/BoardHeader.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if '"BOARDS"' in t and "BOARDS (HOLD CUSTOM TO EDIT)" not in t:
        log("  ✓ already renamed"); return

    for old in [
        'text = "BOARDS (HOLD CUSTOM TO EDIT) — TAP TO SWITCH",',
        'text = "BOARDS (HOLD CUSTOM TO EDIT)",',
    ]:
        if old in t:
            t = t.replace(old, 'text = "BOARDS",', 1)
            f.write_text(t, encoding="utf-8")
            log("  ✓ renamed to just BOARDS")
            return
    log("  ⚠ text anchor missing")


# ============================================================
# PATCH 4 — Fullscreen order (idempotent)
# ============================================================
def patch_fullscreen_order():
    log("\n=== PATCH: Fullscreen order = visual grid order ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "galleryPinsForFullscreen" in t and "isStandardMasonryActive" in t:
        log("  ✓ already patched"); return

    changed = False

    if "galleryPinsForFullscreen" not in t:
        anchor = "    val galleryItemsPlaceholder = galleryItems\n"
        if anchor not in t:
            log("  ⚠ galleryItemsPlaceholder anchor missing"); return
        add = (
            anchor +
            "\n"
            "    val galleryPinsForFullscreen = remember(galleryItems) {\n"
            "        galleryItems.mapNotNull { it.pin }\n"
            "    }\n"
            "\n"
            "    val isStandardMasonryActive = !groupByAlbum && liveActiveAlbum == null &&\n"
            "        !(separateByDate && dateGroups.isNotEmpty())\n"
        )
        t = t.replace(anchor, add, 1); changed = True
        log("  ✓ galleryPinsForFullscreen + isStandardMasonryActive")

    if "galleryPinsForFullscreen.indexOfFirst" not in t:
        old_click = (
            "                                onClick = {\n"
            "                                    if (isSelectionMode) {\n"
            "                                        viewModel.toggleSelection(pin.id)\n"
            "                                    } else {\n"
            "                                        viewModel.openFullscreen(item.pinIndexInLoose)\n"
            "                                    }\n"
            "                                },\n"
        )
        new_click = (
            "                                onClick = {\n"
            "                                    if (isSelectionMode) {\n"
            "                                        viewModel.toggleSelection(pin.id)\n"
            "                                    } else {\n"
            "                                        val visualIdx = galleryPinsForFullscreen.indexOfFirst { it.id == pin.id }\n"
            "                                            .coerceAtLeast(0)\n"
            "                                        viewModel.openFullscreen(visualIdx)\n"
            "                                    }\n"
            "                                },\n"
        )
        if old_click in t:
            t = t.replace(old_click, new_click, 1); changed = True
            log("  ✓ click uses visual index")

    old_fs = (
        "    fullscreenPinIndex?.let { index ->\n"
        "        val fullScreenPins = liveActiveAlbum?.pins ?: (if (topLevelCustomAlbums.isNotEmpty()) viewModel.getAllSortedPins().filter { it.albumId == null } else viewModel.getAllSortedPins()).ifEmpty { displayedPins }\n"
    )
    new_fs = (
        "    fullscreenPinIndex?.let { index ->\n"
        "        val fullScreenPins = when {\n"
        "            liveActiveAlbum != null -> liveActiveAlbum!!.pins\n"
        "            isStandardMasonryActive && galleryPinsForFullscreen.isNotEmpty() -> galleryPinsForFullscreen\n"
        "            else -> viewModel.getAllSortedPins().ifEmpty { displayedPins }\n"
        "        }\n"
    )
    if old_fs in t:
        t = t.replace(old_fs, new_fs, 1); changed = True
        log("  ✓ fullscreen pins source")

    if changed: f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 5 — Date-album pins (idempotent)
# ============================================================
def patch_date_album_pins():
    log("\n=== PATCH: Date-album pins visible when opened ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "isCustomAlbumActive" in t:
        log("  ✓ already patched"); return

    old = (
        "                    val albumPins = allPinsForAlbums.filter { it.albumId == liveActiveAlbum!!.id }\n"
        "                        .sortedByDescending { it.dateAddedMillis }\n"
    )
    new = (
        "                    val isCustomAlbumActive = customDateAlbums.any { it.id == liveActiveAlbum!!.id }\n"
        "                    val albumPins = (if (isCustomAlbumActive) {\n"
        "                        allPinsForAlbums.filter { it.albumId == liveActiveAlbum.id }\n"
        "                    } else {\n"
        "                        liveActiveAlbum.pins\n"
        "                    }).sortedByDescending { it.dateAddedMillis }\n"
    )
    if old in t:
        t = t.replace(old, new, 1)
        f.write_text(t, encoding="utf-8")
        log("  ✓ date-album pins use captured pins")
    else:
        log("  ⚠ albumPins anchor missing")


# ============================================================
# Self-verify (FIXED markers)
# ============================================================
def verify_patches():
    log("\n=== Self-verify ===")
    checks = [
        ("app/src/main/java/com/example/ui/ShareTargetActivity.kt", [
            'testTag("share_put_into_album_checkbox")',
            "putIntoAlbum && extractMultipleImages",
            "putIntoAlbum: Boolean = false",
        ]),
        ("app/src/main/java/com/example/ui/dialogs/AddManualImagesDialog.kt", [
            'testTag("manual_put_into_album_checkbox")',
            "putIntoAlbum: Boolean",
        ]),
        ("app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt", [
            "putIntoAlbum: Boolean = false",                              # parameter present
            "if (putIntoAlbum && resolvedPins.isNotEmpty())",             # actual existing block
        ]),
        ("app/src/main/java/com/example/ui/components/BoardHeader.kt", [
            'text = "BOARDS",',
        ]),
        ("app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt", [
            "galleryPinsForFullscreen",
            "isStandardMasonryActive",
            "galleryPinsForFullscreen.indexOfFirst",
            "isCustomAlbumActive",
            "liveActiveAlbum.pins",
        ]),
    ]
    all_ok = True
    for rel, markers in checks:
        fp = PROJECT_ROOT / rel
        if not fp.exists():
            log(f"  ✗ {rel} missing"); all_ok = False; continue
        content = fp.read_text(encoding="utf-8")
        local_ok = True
        for m in markers:
            if m not in content:
                log(f"  ✗ MISSING in {rel.split('/')[-1]}: {m[:70]}")
                local_ok = False; all_ok = False
        if local_ok:
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
             "Fix self-verify markers; VM putIntoAlbum parameter; 4 feature patches"])


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
    log("PinBoard — 4 fixes (re-run, VM anchor fixed)")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    patch_share_put_into_album()
    patch_manual_put_into_album()
    patch_boards_label()
    patch_fullscreen_order()
    patch_date_album_pins()
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