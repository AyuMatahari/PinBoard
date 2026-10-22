#!/usr/bin/env python3
"""
PinBoard Gallery
----------------
CURRENT CHANGE: Full backup completeness
  * pins: every (id, boardId) pair is preserved (no more dedup-by-id-only)
  * pins: albumId is serialized and restored (non-sort albums keep membership)
  * custom_albums table is backed up & restored
  * additional prefs backed up & restored: board_layout_prefs,
    image_cache_prefs, backup_prefs (minus last_backup_time)
  * ViewModel reloads custom albums + favorites after a restore

FULL PIPELINE runs after the patch:
  1. apply this patch
  2. verify release.keystore + patch app/build.gradle.kts
  3. ensure gradle wrapper + write CI workflow
  4. commit + push to <user>/PinBoard
  5. trigger CI -> poll -> download app-release artifact
  6. save as  PinBoard-v{versionName}-{versionCode}.apk
     into the folder from 'Apk Directory.txt'
  7. verify signature -> uninstall + install on device
"""

import os
import re
import sys
import json
import time
import shutil
import datetime
import subprocess
import urllib.request
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
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Set up Android SDK
        uses: android-actions/setup-android@v3
        with:
          packages: ''

      - name: Accept Android licenses
        run: yes | sdkmanager --licenses >/dev/null 2>&1 || true

      - name: Install SDK components
        run: sdkmanager --install "platforms;android-36" "build-tools;36.0.0" >/dev/null 2>&1 || true

      - name: Verify release.keystore is committed
        run: |
          if [ ! -f release.keystore ]; then
            echo "ERROR: release.keystore missing from repo"
            exit 1
          fi
          if ! keytool -list -keystore release.keystore -storepass PinBoardRelease2025 2>/dev/null | grep -q upload; then
            echo "ERROR: alias 'upload' not found in release.keystore"
            exit 1
          fi
          echo "release.keystore OK"

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v3
        with:
          gradle-version: wrapper

      - name: Make gradlew executable
        run: chmod +x ./gradlew

      - name: Build Release APK
        run: ./gradlew :app:assembleRelease --stacktrace --no-daemon

      - name: Verify APK signature
        run: |
          APK=$(find app/build/outputs/apk/release -name "*.apk" | head -1)
          if [ -z "$APK" ]; then echo "ERROR: no release APK produced"; exit 1; fi
          echo "APK: $APK"
          BT=$(ls -d $ANDROID_HOME/build-tools/* | sort -V | tail -1)
          "$BT/apksigner" verify --verbose --print-certs "$APK"

      - name: Upload APK
        uses: actions/upload-artifact@v4
        with:
          name: app-release
          path: app/build/outputs/apk/release/*.apk
          if-no-files-found: error
"""


def log(msg): print(msg, flush=True)


def run(cmd, cwd=None, check=True, capture=False):
    log(f"> {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    try:
        return subprocess.run(
            cmd, cwd=str(cwd or PROJECT_ROOT),
            check=check, capture_output=capture, text=True,
            shell=isinstance(cmd, str),
        )
    except subprocess.CalledProcessError as e:
        log(f"  Command failed (rc={e.returncode})")
        if e.stdout: log(f"  stdout: {e.stdout}")
        if e.stderr: log(f"  stderr: {e.stderr}")
        if check: raise


def tool_available(name):
    try:
        subprocess.run([name, "--version"], capture_output=True, check=True, timeout=5)
        return True
    except Exception:
        return False


# ============================================================
# THIS TASK'S ONLY CODE PATCH — Backup completeness
# ============================================================
def patch_backup_completeness():
    log("\n=== PATCH: Backup completeness (pins, albums, prefs) ===")
    bm = PROJECT_ROOT / "app/src/main/java/com/example/util/BackupManager.kt"
    vm = PROJECT_ROOT / "app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt"
    if not bm.exists(): log(f"  ✗ {bm} not found"); sys.exit(1)
    if not vm.exists(): log(f"  ✗ {vm} not found"); sys.exit(1)

    t = bm.read_text(encoding="utf-8")
    changed = False

    # Marker check — skip if fully applied
    fully_done = (
        "fullPinsList.add(pObj)" in t
        and 'put("albumId", p.albumId ?: "")' in t
        and "rootJson.put(\"custom_albums\", albumsArray)" in t
        and "board_layout_prefs" in t
        and "restorePrefsObject" in t
        and "albumId = pObj.optString(\"albumId\", \"\").ifBlank { null }" in t
    )
    if fully_done:
        log("  ✓ BackupManager.kt already patched")
    else:
        # --- FIX 1: pin serialization — albumId + full (non-deduped) list ---
        if "fullPinsList.add(pObj)" in t and 'put("albumId", p.albumId ?: "")' in t:
            log("  ✓ pin serialization already patched")
        else:
            old_pin = (
                "                val pObj = JSONObject().apply {\n"
                "                    put(\"id\", p.id)\n"
                "                    put(\"boardId\", p.boardId)\n"
                "                    put(\"title\", p.title)\n"
                "                    put(\"description\", p.description)\n"
                "                    put(\"imageUrl\", p.imageUrl)\n"
                "                    put(\"thumbnailUrl\", p.thumbnailUrl)\n"
                "                    put(\"author\", p.author)\n"
                "                    put(\"boardName\", p.boardName)\n"
                "                    put(\"sourceUrl\", p.sourceUrl)\n"
                "                    put(\"width\", p.width)\n"
                "                    put(\"height\", p.height)\n"
                "                    put(\"dominantColor\", p.dominantColor)\n"
                "                    put(\"dateAddedMillis\", p.dateAddedMillis)\n"
                "                    put(\"savesCount\", p.savesCount)\n"
                "                    put(\"likesCount\", p.likesCount)\n"
                "                    put(\"fileSizeKb\", p.fileSizeKb)\n"
                "                    put(\"orderIndex\", p.orderIndex)\n"
                "                    put(\"boardPosition\", p.boardPosition)\n"
                "                    put(\"firstSeenAt\", p.firstSeenAt)\n"
                "                    put(\"firstSeenAtMillis\", p.firstSeenAtMillis)\n"
                "                    put(\"pinterestCreatedAt\", p.pinterestCreatedAt ?: \"\")\n"
                "                    put(\"mimeType\", p.mimeType)\n"
                "                    put(\"sourceDomain\", p.sourceDomain)\n"
                "                    put(\"isBrokenOrUnreachable\", p.isBrokenOrUnreachable)\n"
                "                }\n"
                "                val key = p.id.ifBlank { p.imageUrl }\n"
                "                archivedPinsMap[key] = pObj\n"
                "            }"
            )
            new_pin = (
                "                val pObj = JSONObject().apply {\n"
                "                    put(\"id\", p.id)\n"
                "                    put(\"boardId\", p.boardId)\n"
                "                    put(\"title\", p.title)\n"
                "                    put(\"description\", p.description)\n"
                "                    put(\"imageUrl\", p.imageUrl)\n"
                "                    put(\"thumbnailUrl\", p.thumbnailUrl)\n"
                "                    put(\"author\", p.author)\n"
                "                    put(\"boardName\", p.boardName)\n"
                "                    put(\"sourceUrl\", p.sourceUrl)\n"
                "                    put(\"width\", p.width)\n"
                "                    put(\"height\", p.height)\n"
                "                    put(\"dominantColor\", p.dominantColor)\n"
                "                    put(\"dateAddedMillis\", p.dateAddedMillis)\n"
                "                    put(\"savesCount\", p.savesCount)\n"
                "                    put(\"likesCount\", p.likesCount)\n"
                "                    put(\"fileSizeKb\", p.fileSizeKb)\n"
                "                    put(\"orderIndex\", p.orderIndex)\n"
                "                    put(\"boardPosition\", p.boardPosition)\n"
                "                    put(\"firstSeenAt\", p.firstSeenAt)\n"
                "                    put(\"firstSeenAtMillis\", p.firstSeenAtMillis)\n"
                "                    put(\"pinterestCreatedAt\", p.pinterestCreatedAt ?: \"\")\n"
                "                    put(\"mimeType\", p.mimeType)\n"
                "                    put(\"sourceDomain\", p.sourceDomain)\n"
                "                    put(\"isBrokenOrUnreachable\", p.isBrokenOrUnreachable)\n"
                "                    put(\"albumId\", p.albumId ?: \"\")\n"
                "                }\n"
                "                val key = p.id.ifBlank { p.imageUrl }\n"
                "                archivedPinsMap[key] = pObj\n"
                "                fullPinsList.add(pObj)\n"
                "            }"
            )
            if old_pin in t:
                t = t.replace(old_pin, new_pin, 1); changed = True
                log("  ✓ pin JSON: albumId + fullPinsList")

        # Declare fullPinsList
        decl_anchor = "            val archivedPinsMap = linkedMapOf<String, JSONObject>()\n"
        if decl_anchor in t and "val fullPinsList = mutableListOf<JSONObject>()" not in t:
            t = t.replace(
                decl_anchor,
                decl_anchor + "            val fullPinsList = mutableListOf<JSONObject>()\n",
                1,
            )
            changed = True
            log("  ✓ fullPinsList declared")

        # --- FIX 2: split archive-write from backup-write + add custom_albums ---
        old_write = (
            "            val pinsArray = JSONArray()\n"
            "            archivedPinsMap.values.forEach { pinsArray.put(it) }\n"
            "            rootJson.put(\"pins\", pinsArray)\n"
            "\n"
            "            try {\n"
            "                archiveFile.writeText(pinsArray.toString())\n"
            "            } catch (_: Exception) {}\n"
        )
        new_write = (
            "            // Archive: deduped by pin id (metadata preservation after deletion)\n"
            "            val archivePinsArray = JSONArray()\n"
            "            archivedPinsMap.values.forEach { archivePinsArray.put(it) }\n"
            "            try {\n"
            "                archiveFile.writeText(archivePinsArray.toString())\n"
            "            } catch (_: Exception) {}\n"
            "\n"
            "            // Backup pins: ALL (id, boardId) pairs, NO dedup — preserves pins\n"
            "            // that live on multiple boards (Dump / My Save / Favorites / custom).\n"
            "            val pinsArray = JSONArray()\n"
            "            fullPinsList.forEach { pinsArray.put(it) }\n"
            "            rootJson.put(\"pins\", pinsArray)\n"
            "\n"
            "            // Custom albums (non-sort albums created from multi-image links)\n"
            "            try {\n"
            "                val customAlbums = dao.getAllAlbums()\n"
            "                val albumsArray = JSONArray()\n"
            "                customAlbums.forEach { a ->\n"
            "                    val aObj = JSONObject().apply {\n"
            "                        put(\"id\", a.id)\n"
            "                        put(\"boardId\", a.boardId)\n"
            "                        put(\"parentAlbumId\", a.parentAlbumId ?: \"\")\n"
            "                        put(\"title\", a.title)\n"
            "                        put(\"sourceUrl\", a.sourceUrl)\n"
            "                        put(\"dateAddedMillis\", a.dateAddedMillis)\n"
            "                        put(\"orderIndex\", a.orderIndex)\n"
            "                        put(\"isFavorite\", a.isFavorite)\n"
            "                    }\n"
            "                    albumsArray.put(aObj)\n"
            "                }\n"
            "                rootJson.put(\"custom_albums\", albumsArray)\n"
            "            } catch (_: Exception) {}\n"
        )
        if old_write in t:
            t = t.replace(old_write, new_write, 1); changed = True
            log("  ✓ pins: full list + custom_albums")

        # --- FIX 3: extra prefs in performBackup ---
        old_prefs = (
            "            // Export board history\n"
            "            val historyPrefs = context.getSharedPreferences(\"pinterest_board_history\", Context.MODE_PRIVATE)\n"
        )
        new_prefs = (
            "            // Board layout prefs (per-board columns and sort)\n"
            "            try {\n"
            "                val blPrefs = context.getSharedPreferences(\"board_layout_prefs\", Context.MODE_PRIVATE)\n"
            "                val blObj = JSONObject()\n"
            "                blPrefs.all.forEach { (k, v) -> blObj.put(k, v ?: JSONObject.NULL) }\n"
            "                rootJson.put(\"board_layout_prefs\", blObj)\n"
            "            } catch (_: Exception) {}\n"
            "\n"
            "            // Image cache prefs\n"
            "            try {\n"
            "                val icPrefs = context.getSharedPreferences(\"image_cache_prefs\", Context.MODE_PRIVATE)\n"
            "                val icObj = JSONObject()\n"
            "                icPrefs.all.forEach { (k, v) -> icObj.put(k, v ?: JSONObject.NULL) }\n"
            "                rootJson.put(\"image_cache_prefs\", icObj)\n"
            "            } catch (_: Exception) {}\n"
            "\n"
            "            // Backup prefs (excluding last_backup_time)\n"
            "            try {\n"
            "                val bPrefs = context.getSharedPreferences(\"pinboard_backup_prefs\", Context.MODE_PRIVATE)\n"
            "                val bObj = JSONObject()\n"
            "                bPrefs.all.forEach { (k, v) ->\n"
            "                    if (k != \"last_backup_time\") bObj.put(k, v ?: JSONObject.NULL)\n"
            "                }\n"
            "                rootJson.put(\"backup_prefs\", bObj)\n"
            "            } catch (_: Exception) {}\n"
            "\n"
            "            // Export board history\n"
            "            val historyPrefs = context.getSharedPreferences(\"pinterest_board_history\", Context.MODE_PRIVATE)\n"
        )
        if old_prefs in t and "board_layout_prefs" not in t:
            t = t.replace(old_prefs, new_prefs, 1); changed = True
            log("  ✓ extra prefs in backup")

        # --- FIX 4a: restore pin.albumId ---
        old_rpin = (
            "                                sourceDomain = pObj.optString(\"sourceDomain\", \"\"),\n"
            "                                isBrokenOrUnreachable = pObj.optBoolean(\"isBrokenOrUnreachable\", false)\n"
            "                            )\n"
            "                        )\n"
        )
        new_rpin = (
            "                                sourceDomain = pObj.optString(\"sourceDomain\", \"\"),\n"
            "                                isBrokenOrUnreachable = pObj.optBoolean(\"isBrokenOrUnreachable\", false),\n"
            "                                albumId = pObj.optString(\"albumId\", \"\").ifBlank { null }\n"
            "                            )\n"
            "                        )\n"
        )
        if old_rpin in t and "albumId = pObj.optString(\"albumId\"" not in t:
            t = t.replace(old_rpin, new_rpin, 1); changed = True
            log("  ✓ restore: pin.albumId")

        # --- FIX 4b: restore custom_albums ---
        old_rend = (
            "                if (pinEntities.isNotEmpty()) {\n"
            "                    dao.upsertPinsSafely(pinEntities)\n"
            "                    restoredPinsCount = pinEntities.size\n"
            "                }\n"
            "            }\n"
        )
        new_rend = (
            "                if (pinEntities.isNotEmpty()) {\n"
            "                    dao.upsertPinsSafely(pinEntities)\n"
            "                    restoredPinsCount = pinEntities.size\n"
            "                }\n"
            "            }\n"
            "\n"
            "            // 2b. Restore custom albums (non-sort albums)\n"
            "            val albumsArray = rootJson.optJSONArray(\"custom_albums\")\n"
            "            if (albumsArray != null && albumsArray.length() > 0) {\n"
            "                val albumEntities = mutableListOf<com.example.data.local.CustomAlbumEntity>()\n"
            "                for (i in 0 until albumsArray.length()) {\n"
            "                    val aObj = albumsArray.getJSONObject(i)\n"
            "                    val aId = aObj.optString(\"id\")\n"
            "                    if (aId.isBlank()) continue\n"
            "                    albumEntities.add(\n"
            "                        com.example.data.local.CustomAlbumEntity(\n"
            "                            id = aId,\n"
            "                            boardId = aObj.optString(\"boardId\"),\n"
            "                            parentAlbumId = aObj.optString(\"parentAlbumId\", \"\").ifBlank { null },\n"
            "                            title = aObj.optString(\"title\", \"\"),\n"
            "                            sourceUrl = aObj.optString(\"sourceUrl\", \"\"),\n"
            "                            dateAddedMillis = aObj.optLong(\"dateAddedMillis\", System.currentTimeMillis()),\n"
            "                            orderIndex = aObj.optInt(\"orderIndex\", 0),\n"
            "                            isFavorite = aObj.optBoolean(\"isFavorite\", false)\n"
            "                        )\n"
            "                    )\n"
            "                }\n"
            "                if (albumEntities.isNotEmpty()) {\n"
            "                    dao.insertAlbums(albumEntities)\n"
            "                }\n"
            "            }\n"
        )
        if old_rend in t and "custom_albums" not in t:
            t = t.replace(old_rend, new_rend, 1); changed = True
            log("  ✓ restore: custom albums")

        # --- FIX 4c: restore extra prefs ---
        old_send = (
            "                editor.apply()\n"
            "                settingsRestored = true\n"
            "            }\n"
        )
        new_send = (
            "                editor.apply()\n"
            "                settingsRestored = true\n"
            "            }\n"
            "\n"
            "            // 3b. Restore board_layout_prefs\n"
            "            restorePrefsObject(context, rootJson.optJSONObject(\"board_layout_prefs\"), \"board_layout_prefs\")\n"
            "\n"
            "            // 3c. Restore image_cache_prefs\n"
            "            restorePrefsObject(context, rootJson.optJSONObject(\"image_cache_prefs\"), \"image_cache_prefs\")\n"
            "\n"
            "            // 3d. Restore backup_prefs (skip last_backup_time)\n"
            "            run {\n"
            "                val bPrefs = rootJson.optJSONObject(\"backup_prefs\")\n"
            "                if (bPrefs != null) {\n"
            "                    val ed = context.getSharedPreferences(\"pinboard_backup_prefs\", Context.MODE_PRIVATE).edit()\n"
            "                    val ks = bPrefs.keys()\n"
            "                    while (ks.hasNext()) {\n"
            "                        val k = ks.next()\n"
            "                        if (k == \"last_backup_time\") continue\n"
            "                        when (val v = bPrefs.get(k)) {\n"
            "                            is Boolean -> ed.putBoolean(k, v)\n"
            "                            is Int -> ed.putInt(k, v)\n"
            "                            is Long -> ed.putLong(k, v)\n"
            "                            is Float -> ed.putFloat(k, v)\n"
            "                            is String -> ed.putString(k, v)\n"
            "                        }\n"
            "                    }\n"
            "                    ed.apply()\n"
            "                }\n"
            "            }\n"
        )
        if old_send in t and "restorePrefsObject" not in t:
            t = t.replace(old_send, new_send, 1); changed = True
            log("  ✓ restore: extra prefs")

        # --- FIX 4d: restorePrefsObject helper ---
        helper_anchor = "    suspend fun restoreBackup(context: Context, backupFile: File): Result<RestoreSummary> = withContext(Dispatchers.IO) {\n"
        if helper_anchor in t and "private fun restorePrefsObject" not in t:
            helper = (
                "    private fun restorePrefsObject(context: Context, prefsObj: JSONObject?, prefsName: String) {\n"
                "        if (prefsObj == null) return\n"
                "        try {\n"
                "            val editor = context.getSharedPreferences(prefsName, Context.MODE_PRIVATE).edit()\n"
                "            val keys = prefsObj.keys()\n"
                "            while (keys.hasNext()) {\n"
                "                val key = keys.next()\n"
                "                when (val value = prefsObj.get(key)) {\n"
                "                    is Boolean -> editor.putBoolean(key, value)\n"
                "                    is Int -> editor.putInt(key, value)\n"
                "                    is Long -> editor.putLong(key, value)\n"
                "                    is Float -> editor.putFloat(key, value)\n"
                "                    is Double -> editor.putFloat(key, value.toFloat())\n"
                "                    is String -> editor.putString(key, value)\n"
                "                }\n"
                "            }\n"
                "            editor.apply()\n"
                "        } catch (_: Exception) {}\n"
                "    }\n"
                "\n"
            )
            t = t.replace(helper_anchor, helper + helper_anchor, 1)
            changed = True
            log("  ✓ restorePrefsObject helper added")

        if changed:
            bm.write_text(t, encoding="utf-8")
            log("  ✓ BackupManager.kt updated")

    # --- FIX 5: ViewModel reload after restore ---
    v = vm.read_text(encoding="utf-8")
    if "// Reload custom albums & favorites after restore" in v:
        log("  ✓ ViewModel already patched")
    else:
        old_vm = (
            "            _currentBoard.value?.let { curr ->\n"
            "                val updatedPins = withContext(Dispatchers.IO) { dao.getPinsForBoard(curr.id) }.map { it.toPinItem() }\n"
            "                _rawPins.value = updatedPins\n"
            "                _currentBoard.value = curr.copy(pins = updatedPins, pinCount = updatedPins.size)\n"
            "                updateDisplayedPins()\n"
            "            }\n"
        )
        new_vm = (
            "            _currentBoard.value?.let { curr ->\n"
            "                val updatedPins = withContext(Dispatchers.IO) { dao.getPinsForBoard(curr.id) }.map { it.toPinItem() }\n"
            "                _rawPins.value = updatedPins\n"
            "                _currentBoard.value = curr.copy(pins = updatedPins, pinCount = updatedPins.size)\n"
            "                updateDisplayedPins()\n"
            "                val albums = withContext(Dispatchers.IO) { dao.getAlbumsForBoard(curr.id) }\n"
            "                _customAlbums.value = albums\n"
            "            }\n"
            "\n"
            "            // Reload custom albums & favorites after restore\n"
            "            val restoredFavIds = withContext(Dispatchers.IO) { dao.getFavoritesPinIds(\"board_favorites\") }\n"
            "            val restoredFavUrls = withContext(Dispatchers.IO) { dao.getFavoritesImageUrls(\"board_favorites\") }\n"
            "            _favoritePinKeys.value = (restoredFavIds + restoredFavUrls).toSet()\n"
            "            val restoredFavPins = withContext(Dispatchers.IO) { dao.getPinsForBoard(\"board_favorites\") }\n"
            "            restoredFavPins.forEach { p ->\n"
            "                favoriteTimestamps[p.id] = p.dateAddedMillis\n"
            "                favoriteTimestamps[p.imageUrl] = p.dateAddedMillis\n"
            "            }\n"
        )
        if old_vm in v:
            v = v.replace(old_vm, new_vm, 1)
            vm.write_text(v, encoding="utf-8")
            log("  ✓ PinBoardViewModel.kt updated (albums + favorites reload)")
        else:
            log("  ⚠ ViewModel anchor not found — custom albums may need manual rescan")


# ============================================================
# Versioned APK naming
# ============================================================
def read_app_version():
    build_path = PROJECT_ROOT / "app/build.gradle.kts"
    if not build_path.exists():
        return ("unknown", "0")
    text = build_path.read_text(encoding="utf-8")
    vn = re.search(r'versionName\s*=\s*"([^"]+)"', text)
    vc = re.search(r"versionCode\s*=\s*(\d+)", text)
    return (vn.group(1) if vn else "unknown",
            vc.group(1) if vc else "0")


# ============================================================
# Build infrastructure
# ============================================================
def ensure_release_keystore():
    log("\n=== Ensuring release.keystore ===")
    ks = PROJECT_ROOT / KEYSTORE_FILE
    if ks.exists() and ks.stat().st_size > 0:
        r = subprocess.run(["keytool", "-list", "-keystore", str(ks),
                            "-storepass", KEYSTORE_PASS],
                           capture_output=True, text=True)
        if r.returncode == 0 and KEYSTORE_ALIAS in r.stdout:
            log(f"  ✓ {KEYSTORE_FILE} OK"); return
        log(f"  ✗ {KEYSTORE_FILE} exists but password/alias mismatch."); sys.exit(1)
    log(f"  Generating {KEYSTORE_FILE}…")
    r = subprocess.run([
        "keytool", "-genkeypair", "-v",
        "-keystore", str(ks),
        "-alias", KEYSTORE_ALIAS,
        "-keyalg", "RSA", "-keysize", "2048",
        "-validity", KEYSTORE_VALIDITY,
        "-storepass", KEYSTORE_PASS,
        "-keypass", KEYSTORE_PASS,
        "-dname", KEYSTORE_DNAME,
    ], capture_output=True, text=True)
    if r.returncode != 0:
        log(f"  ✗ keytool: {r.stderr.strip()}"); sys.exit(1)
    log(f"  ✓ Generated {KEYSTORE_FILE}")


def find_braced_block_at(text, start):
    open_brace = text.find("{", start)
    if open_brace == -1: return None
    depth, i = 1, open_brace + 1
    while i < len(text) and depth > 0:
        c = text[i]
        if c == '"':
            i += 1
            while i < len(text):
                if text[i] == "\\": i += 2; continue
                if text[i] == '"': break
                i += 1
        elif c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0: return (open_brace, i)
        i += 1
    return None


def patch_build_gradle():
    log("\n=== Patching app/build.gradle.kts ===")
    p = PROJECT_ROOT / "app/build.gradle.kts"
    if not p.exists(): log(f"  ✗ {p} not found"); sys.exit(1)
    text = p.read_text(encoding="utf-8"); orig = text

    idx = text.find('create("release")')
    if idx == -1: log(f'  ✗ create("release") not found'); sys.exit(1)
    span = find_braced_block_at(text, idx)
    if not span: log("  ✗ braces not found"); sys.exit(1)
    open_b, close_b = span
    if f'storeFile = file("${{rootDir}}/{KEYSTORE_FILE}")' not in text[open_b:close_b]:
        new_contents = (
            f'\n      storeFile = file("${{rootDir}}/{KEYSTORE_FILE}")\n'
            f'      storePassword = "{KEYSTORE_PASS}"\n'
            f'      keyAlias = "{KEYSTORE_ALIAS}"\n'
            f'      keyPassword = "{KEYSTORE_PASS}"\n    '
        )
        text = text[:open_b + 1] + new_contents + text[close_b:]
        log(f'  ✓ create("release") uses ${{rootDir}}/{KEYSTORE_FILE}')

    bt_idx = text.find("buildTypes {")
    if bt_idx != -1:
        rel_start = text.find("release {", bt_idx)
        if rel_start != -1:
            rel_span = find_braced_block_at(text, rel_start)
            if rel_span:
                ro, rc = rel_span
                block = text[ro + 1:rc]
                if "isDebuggable = true" in block:
                    text = text[:ro + 1] + block.replace("isDebuggable = true", "isDebuggable = false") + text[rc:]
                    log("  ✓ release buildType: isDebuggable -> false")
                elif "isDebuggable" not in block:
                    nb = block.replace("isMinifyEnabled = false",
                                       "isMinifyEnabled = false\n      isDebuggable = false", 1)
                    if nb != block:
                        text = text[:ro + 1] + nb + text[rc:]
                        log("  ✓ added isDebuggable = false")

    if text != orig: p.write_text(text, encoding="utf-8")


def latest_gradle_version():
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/gradle/gradle/releases/latest",
            headers={"User-Agent": "pinboard-build"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            tag = json.load(resp).get("tag_name", "").lstrip("v")
            if tag: return tag
    except Exception: pass
    props = PROJECT_ROOT / "gradle/wrapper/gradle-wrapper.properties"
    if props.exists():
        m = re.search(r"gradle-([\d.]+)-bin\.zip", props.read_text(encoding="utf-8"))
        if m: return m.group(1)
    return "9.3.1"


def ensure_gradle_wrapper():
    log("\n=== Ensuring Gradle wrapper ===")
    gw = PROJECT_ROOT / "gradlew"
    gwb = PROJECT_ROOT / "gradlew.bat"
    jar = PROJECT_ROOT / "gradle/wrapper/gradle-wrapper.jar"
    if gw.exists() and gwb.exists() and jar.exists():
        log("  ✓ Present."); return
    ver = latest_gradle_version(); log(f"  Using Gradle v{ver}")
    base = f"https://raw.githubusercontent.com/gradle/gradle/v{ver}"
    for url, dest in [
        (f"{base}/gradlew", gw),
        (f"{base}/gradlew.bat", gwb),
        (f"{base}/gradle/wrapper/gradle-wrapper.jar", jar),
    ]:
        if dest.exists() and dest.stat().st_size > 0: continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try: urllib.request.urlretrieve(url, dest)
        except Exception as e: log(f"  ✗ {e}"); sys.exit(1)
    try: os.chmod(gw, 0o755)
    except Exception: pass


def write_workflow():
    log("\n=== Writing GitHub Actions workflow ===")
    wf = PROJECT_ROOT / ".github/workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "build.yml").write_text(WORKFLOW_YAML, encoding="utf-8")
    log("  ✓ Written.")


# ============================================================
# Git + GitHub
# ============================================================
def setup_git():
    log("\n=== Setting up git repo ===")
    if not (PROJECT_ROOT / ".git").exists():
        run(["git", "init"]); run(["git", "branch", "-M", "main"])
    if not subprocess.run(["git", "config", "--global", "user.name"],
                          capture_output=True, text=True).stdout.strip():
        run(["git", "config", "--global", "user.name", "PinBoard Build"])
    if not subprocess.run(["git", "config", "--global", "user.email"],
                          capture_output=True, text=True).stdout.strip():
        run(["git", "config", "--global", "user.email", "pinboard@build.local"])

    gi = PROJECT_ROOT / ".gitignore"
    required = [
        "build/", "*/build/", ".gradle/", "local.properties",
        "*.iml", ".idea/", ".cxx/", ".DS_Store",
        ".kotlin/", ".env", "_downloads/",
        "*.jks", "*.keystore", "!debug.keystore", "!release.keystore",
    ]
    existing = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    merged = list(existing)
    for line in required:
        if line not in merged: merged.append(line)
    gi.write_text("\n".join(merged) + "\n", encoding="utf-8")

    run(["git", "add", "-A"])
    for name in (KEYSTORE_FILE, "debug.keystore"):
        if (PROJECT_ROOT / name).exists():
            run(["git", "add", "-f", name], check=False)

    if subprocess.run(["git", "status", "--porcelain"],
                      capture_output=True, text=True).stdout.strip():
        run(["git", "commit", "-m",
             "Backup completeness: all pins/albums/prefs + viewmodel reload"])
        log("  ✓ Committed.")


def verify_release_keystore_tracked():
    r = subprocess.run(["git", "ls-files", "--error-unmatch", KEYSTORE_FILE],
                       capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    if r.returncode != 0:
        run(["git", "add", "-f", KEYSTORE_FILE])
        run(["git", "commit", "-m", f"Add {KEYSTORE_FILE}"])


def gh_user():
    r = subprocess.run(["gh", "api", "user", "--jq", ".login"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        log("ERROR: gh not authenticated."); sys.exit(1)
    return r.stdout.strip()


def ensure_github_repo():
    log("\n=== Ensuring GitHub repo ===")
    user = gh_user(); full = f"{user}/{REPO_NAME}"
    if subprocess.run(["gh", "repo", "view", full], capture_output=True).returncode != 0:
        subprocess.run(["gh", "repo", "create", REPO_NAME, "--public",
                        "--source", ".", "--remote", "origin", "--push"],
                       capture_output=True, text=True)
    if subprocess.run(["git", "remote", "get-url", "origin"],
                      capture_output=True).returncode != 0:
        run(["git", "remote", "add", "origin", f"https://github.com/{full}.git"])
    r = subprocess.run(["git", "push", "-u", "origin", "main"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(["git", "push", "-u", "origin", "main", "--force"],
                       capture_output=True, text=True)
    return full


def trigger_and_download(repo_full):
    log("\n=== Triggering CI ===")
    for _ in range(6):
        r = subprocess.run(["gh", "workflow", "run", "build.yml",
                            "--ref", "main", "--repo", repo_full],
                           capture_output=True, text=True)
        if r.returncode == 0: break
        time.sleep(10)
    else:
        log(f"  ✗ {r.stderr.strip()}"); sys.exit(1)

    time.sleep(10)
    run_id = None
    for _ in range(20):
        r = subprocess.run(["gh", "run", "list", "--repo", repo_full,
                            "--workflow", "build.yml", "--limit", "1",
                            "--json", "databaseId"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            try:
                runs = json.loads(r.stdout)
                if runs: run_id = runs[0]["databaseId"]; break
            except json.JSONDecodeError: pass
        time.sleep(5)
    if run_id is None: log("  ✗ No run found."); sys.exit(1)

    while True:
        r = subprocess.run(["gh", "run", "view", str(run_id), "--repo", repo_full,
                            "--json", "status,conclusion"],
                           capture_output=True, text=True)
        if r.returncode != 0: time.sleep(15); continue
        try: info = json.loads(r.stdout)
        except json.JSONDecodeError: time.sleep(15); continue
        st, cc = info.get("status", ""), info.get("conclusion", "")
        log(f"  status={st} conclusion={cc}")
        if st == "completed":
            if cc != "success":
                subprocess.run(["gh", "run", "view", str(run_id), "--repo", repo_full,
                                "--log-failed"], check=False)
                sys.exit(1)
            break
        time.sleep(20)

    dl = PROJECT_ROOT / "_downloads"
    if dl.exists(): shutil.rmtree(dl)
    dl.mkdir()
    r = subprocess.run(["gh", "run", "download", str(run_id), "--repo", repo_full,
                        "--name", ARTIFACT, "--dir", str(dl)],
                       capture_output=True, text=True)
    if r.returncode != 0: log(f"  ✗ {r.stderr.strip()}"); sys.exit(1)
    return dl


def move_apk(dl_dir):
    log("\n=== Moving APK to target (name + version) ===")
    apks = list(dl_dir.glob("*.apk"))
    if not apks: log("  ✗ No APK."); sys.exit(1)
    apk = apks[0]
    vn, vc = read_app_version()
    log(f"  App version: {vn} (code {vc})")
    tf = PROJECT_ROOT / "Apk Directory.txt"
    target_dir = (Path(tf.read_text(encoding="utf-8").strip())
                  if tf.exists() else Path.home() / "Downloads")
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / f"{APP_NAME}-v{vn}-{vc}{apk.suffix}"
    if dest.exists():
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = target_dir / f"{APP_NAME}-v{vn}-{vc}_{ts}{apk.suffix}"
        log("  Prior copy exists → timestamped name")
    shutil.copy2(apk, dest)
    log(f"  ✓ APK -> {dest}")
    return dest


def find_apksigner():
    for sdk in [
        Path(os.environ.get("ANDROID_HOME", "")),
        Path(os.environ.get("ANDROID_SDK_ROOT", "")),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Android/Sdk",
        Path.home() / "AppData/Local/Android/Sdk",
        Path.home() / "Library/Android/sdk",
        Path("/usr/local/lib/android/sdk"),
    ]:
        if not str(sdk).strip() or not sdk.exists(): continue
        bt = sdk / "build-tools"
        if not bt.exists(): continue
        for v in sorted([d for d in bt.iterdir() if d.is_dir()],
                        key=lambda d: d.name, reverse=True):
            for n in ("apksigner.bat", "apksigner"):
                e = v / n
                if e.exists(): return str(e)
    return None


def verify_apk_signature(apk):
    log("\n=== Verifying APK signature ===")
    signer = find_apksigner()
    if not signer:
        log("  (apksigner not found locally — CI already verified)"); return
    r = subprocess.run([signer, "verify", "--verbose", "--print-certs", str(apk)],
                       capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    log("\n".join(f"    {l}" for l in out.splitlines()[:15]))
    if r.returncode != 0 or "Verifies" not in out:
        log("  ✗ Signature verification FAILED."); sys.exit(1)
    log("  ✓ APK signature verified.")


def find_adb():
    if tool_available("adb"): return "adb"
    for c in [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Android/Sdk/platform-tools/adb.exe",
        Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe",
        Path.home() / "Library/Android/sdk/platform-tools/adb",
        Path("/usr/local/bin/adb"),
    ]:
        if c.exists(): return str(c)
    return None


def adb_device_connected(adb):
    try:
        r = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=5)
        if r.returncode != 0: return False
        return any("\tdevice" in l or " device" in l
                   for l in r.stdout.strip().splitlines()[1:])
    except Exception:
        return False


def device_install(apk_path):
    log("\n=== Device install ===")
    adb = find_adb()
    if not adb or not adb_device_connected(adb):
        log("  No device — skipping.")
        log(f"    adb uninstall {PACKAGE_ID}")
        log(f'    adb install "{apk_path}"')
        return
    subprocess.run([adb, "uninstall", PACKAGE_ID],
                   capture_output=True, text=True, timeout=60)
    r = subprocess.run([adb, "install", str(apk_path)],
                       capture_output=True, text=True, timeout=300)
    out = (r.stdout + r.stderr).strip()
    log(f"    {out}")
    if "Success" in out: log("  ✓ Installed.")


# ============================================================
# main
# ============================================================
def main():
    log("=" * 70)
    log("PinBoard Gallery - Backup completeness + full build pipeline")
    log("=" * 70)

    if not (PROJECT_ROOT / "app/build.gradle.kts").exists():
        log(f"ERROR: {PROJECT_ROOT} isn't a PinBoard project."); sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t):
            log(f"ERROR: {t} not in PATH"); sys.exit(1)

    # 1. This change
    patch_backup_completeness()

    # 2. Build infrastructure
    ensure_release_keystore()
    patch_build_gradle()
    ensure_gradle_wrapper()
    write_workflow()

    # 3. Git + repo
    setup_git()
    verify_release_keystore_tracked()
    repo = ensure_github_repo()

    # 4. CI
    dl = trigger_and_download(repo)

    # 5. Versioned move + verify
    apk = move_apk(dl)
    verify_apk_signature(apk)

    # 6. Device install
    device_install(apk)

    log("\n" + "=" * 70)
    log(f"DONE -> {apk}")
    log("=" * 70)


if __name__ == "__main__":
    main()