#!/usr/bin/env python3
"""
PinBoard Gallery - Release Build + Deploy (auto)
------------------------------------------------
New features added on top of the previous script:
  * Fullscreen image refresh button (reloads image from source URL)
  * Unlimited option for backup files retention
  * Restore dialog lists ALL .json files in the backup folder
  * Backups are pretty-printed (compact restore still works)

Plus the earlier fixes:
  * Disable Arrow Navigation wiring
  * release.keystore signing + assembleRelease CI
  * Signature verification + device install
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
# NEW PATCH 1: Fullscreen image refresh button
# ============================================================
def patch_fullscreen_refresh_button():
    log("\n=== PATCH: Fullscreen image refresh button ===")
    path = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/FullscreenGalleryViewer.kt"
    if not path.exists():
        log(f"  ✗ {path} not found"); sys.exit(1)

    text = path.read_text(encoding="utf-8")

    if "fullscreen_refresh_image_button" in text:
        log("  ✓ Already patched."); return

    changed = False

    # 1. Import Refresh icon
    if "import androidx.compose.material.icons.filled.Refresh\n" not in text:
        text = text.replace(
            "import androidx.compose.material.icons.filled.Download\n",
            "import androidx.compose.material.icons.filled.Download\n"
            "import androidx.compose.material.icons.filled.Refresh\n",
            1,
        )
        changed = True

    # 2. Import mutableStateMapOf
    if "import androidx.compose.runtime.mutableStateMapOf\n" not in text:
        text = text.replace(
            "import androidx.compose.runtime.mutableStateOf\n",
            "import androidx.compose.runtime.mutableStateMapOf\n"
            "import androidx.compose.runtime.mutableStateOf\n",
            1,
        )
        changed = True

    # 3. Add per-pin refresh counter state (next to pinForImageHoldDialog)
    anchor_state = "    var pinForImageHoldDialog by remember { mutableStateOf<PinItem?>(null) }\n"
    if anchor_state in text and "imageRefreshKeys" not in text:
        text = text.replace(
            anchor_state,
            anchor_state +
            "    // Per-pin refresh counter; increment forces a fresh network fetch\n"
            "    val imageRefreshKeys = remember { mutableStateMapOf<String, Int>() }\n",
            1,
        )
        changed = True

    # 4. Insert refresh button right after the favorite toggle button
    fav_block = (
        "                        // Favorite toggle button (User requirement)\n"
        "                        IconButton(\n"
        "                            onClick = { onToggleFavorite(currentPin) },\n"
        "                            modifier = Modifier\n"
        "                                .size(38.dp)\n"
        "                                .testTag(\"fullscreen_favorite_button\")\n"
        "                        ) {\n"
        "                            Icon(\n"
        "                                imageVector = if (pinIsFavorite) Icons.Default.Favorite else Icons.Default.FavoriteBorder,\n"
        "                                contentDescription = \"Toggle favorite\",\n"
        "                                tint = if (pinIsFavorite) PinterestRed else Color.White\n"
        "                            )\n"
        "                        }\n"
    )
    refresh_insert = (
        "\n"
        "                        // Refresh image button (reloads from source URL, bypasses cache)\n"
        "                        IconButton(\n"
        "                            onClick = {\n"
        "                                val key = currentPin.id\n"
        "                                imageRefreshKeys[key] = (imageRefreshKeys[key] ?: 0) + 1\n"
        "                                Toast.makeText(context, \"Refreshing image...\", Toast.LENGTH_SHORT).show()\n"
        "                            },\n"
        "                            modifier = Modifier\n"
        "                                .size(38.dp)\n"
        "                                .testTag(\"fullscreen_refresh_image_button\")\n"
        "                        ) {\n"
        "                            Icon(\n"
        "                                imageVector = Icons.Default.Refresh,\n"
        "                                contentDescription = \"Refresh image\",\n"
        "                                tint = Color.White\n"
        "                            )\n"
        "                        }\n"
    )
    if fav_block in text and "fullscreen_refresh_image_button" not in text:
        text = text.replace(fav_block, fav_block + refresh_insert, 1)
        changed = True

    # 5. Use refresh key in the pager's AsyncImage so a fresh network fetch happens
    img_old = (
        "                AsyncImage(\n"
        "                    model = ImageRequest.Builder(context)\n"
        "                        .data(pin.imageUrl)\n"
        "                        .crossfade(true)\n"
        "                        .build(),\n"
        "                    contentDescription = pin.title,\n"
        "                    contentScale = ContentScale.Fit,\n"
        "                    modifier = Modifier\n"
        "                        .fillMaxSize()\n"
        "                        .graphicsLayer {\n"
        "                            scaleX = scale\n"
        "                            scaleY = scale\n"
        "                            translationX = offsetX\n"
        "                            translationY = offsetY\n"
        "                        }\n"
        "                )"
    )
    img_new = (
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
        "                        .crossfade(true)\n"
        "                        .build(),\n"
        "                    contentDescription = pin.title,\n"
        "                    contentScale = ContentScale.Fit,\n"
        "                    modifier = Modifier\n"
        "                        .fillMaxSize()\n"
        "                        .graphicsLayer {\n"
        "                            scaleX = scale\n"
        "                            scaleY = scale\n"
        "                            translationX = offsetX\n"
        "                            translationY = offsetY\n"
        "                        }\n"
        "                )"
    )
    if img_old in text:
        text = text.replace(img_old, img_new, 1)
        changed = True
    else:
        log("  ⚠ Could not locate AsyncImage block in pager")

    if changed:
        path.write_text(text, encoding="utf-8")
        log("  ✓ Patched FullscreenGalleryViewer.kt (refresh button + cache-bust)")
    else:
        log("  ⚠ Nothing changed — manual inspection may be needed")


# ============================================================
# NEW PATCH 2: BackupManager (unlimited files + all files + pretty JSON)
# ============================================================
def patch_backup_manager():
    log("\n=== PATCH: BackupManager (unlimited + all files + pretty JSON) ===")
    path = PROJECT_ROOT / "app/src/main/java/com/example/util/BackupManager.kt"
    if not path.exists():
        log(f"  ✗ {path} not found"); sys.exit(1)

    text = path.read_text(encoding="utf-8")
    changed = False

    # 1. Add UNLIMITED constant
    if "UNLIMITED_MAX_BACKUP_FILES" not in text:
        text = text.replace(
            "    const val DEFAULT_MAX_BACKUP_FILES = 5\n",
            "    const val DEFAULT_MAX_BACKUP_FILES = 5\n"
            "    /** Value 0 means unlimited: never prune old backup files. */\n"
            "    const val UNLIMITED_MAX_BACKUP_FILES = 0\n",
            1,
        )
        changed = True

    # 2. Add 0 (Unlimited) to the options list
    old_opts = "val MAX_FILES_OPTIONS: List<Int> = listOf(1, 2, 3, 5, 10, 15, 20, 30, 50)"
    new_opts = "val MAX_FILES_OPTIONS: List<Int> = listOf(0, 1, 2, 3, 5, 10, 15, 20, 30, 50)  // 0 = Unlimited"
    if old_opts in text:
        text = text.replace(old_opts, new_opts, 1)
        changed = True

    # 3. setMaxBackupFiles - accept 0 = unlimited, skip pruning then
    set_old = (
        "    fun setMaxBackupFiles(context: Context, maxFiles: Int) {\n"
        "        val clamped = maxFiles.coerceAtLeast(1)\n"
        "        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)\n"
        "        prefs.edit().putInt(KEY_MAX_BACKUP_FILES, clamped).apply()\n"
        "        try {\n"
        "            val dir = getBackupDirectory(context)\n"
        "            pruneOldBackups(dir, clamped)\n"
        "        } catch (_: Exception) {}\n"
        "    }"
    )
    set_new = (
        "    fun setMaxBackupFiles(context: Context, maxFiles: Int) {\n"
        "        val clamped = maxFiles.coerceAtLeast(0)  // 0 = Unlimited\n"
        "        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)\n"
        "        prefs.edit().putInt(KEY_MAX_BACKUP_FILES, clamped).apply()\n"
        "        if (clamped > 0) {\n"
        "            try {\n"
        "                val dir = getBackupDirectory(context)\n"
        "                pruneOldBackups(dir, clamped)\n"
        "            } catch (_: Exception) {}\n"
        "        }\n"
        "    }"
    )
    if set_old in text:
        text = text.replace(set_old, set_new, 1)
        changed = True

    # 4. pruneOldBackups - return early when unlimited
    prune_anchor = (
        "    private fun pruneOldBackups(backupDir: File, maxCount: Int) {\n"
        "        try {"
    )
    prune_new = (
        "    private fun pruneOldBackups(backupDir: File, maxCount: Int) {\n"
        "        if (maxCount <= 0) return  // Unlimited: never delete old backups\n"
        "        try {"
    )
    if prune_anchor in text:
        text = text.replace(prune_anchor, prune_new, 1)
        changed = True

    # 5. Pretty-printed main backup JSON (restore still accepts compact)
    if "val jsonString = rootJson.toString()" in text:
        text = text.replace(
            "            val jsonString = rootJson.toString()\n",
            "            // Pretty-printed (indent = 2) for human readability; compact JSON\n"
            "            // files can still be restored because JSONObject() accepts both.\n"
            "            val jsonString = rootJson.toString(2)\n",
            1,
        )
        changed = True

    # 6. getAvailableBackups - list ALL .json files in the backup folder
    get_old = (
        "    fun getAvailableBackups(context: Context): List<File> {\n"
        "        val primaryDir = getBackupDirectory(context)\n"
        "        val files = mutableListOf<File>()\n"
        "\n"
        "        fun collectFrom(dir: File) {\n"
        "            if (dir.exists() && dir.isDirectory) {\n"
        "                dir.listFiles { f ->\n"
        "                    f.isFile && f.extension.equals(\"json\", ignoreCase = true) &&\n"
        "                            (f.name.startsWith(\"pinboard_backup_\") || f.name == \"latest_backup.json\")\n"
        "                }?.let { files.addAll(it) }\n"
        "            }\n"
        "        }\n"
        "\n"
        "        collectFrom(primaryDir)\n"
        "        // Also check parent folder in case previous backups were placed there\n"
        "        primaryDir.parentFile?.let { parent ->\n"
        "            if (parent.name == \"PinterestViewerDownloads\") {\n"
        "                collectFrom(parent)\n"
        "            }\n"
        "        }\n"
        "\n"
        "        return files.distinctBy { it.absolutePath }\n"
        "            .sortedByDescending { it.lastModified() }\n"
        "    }"
    )
    get_new = (
        "    fun getAvailableBackups(context: Context): List<File> {\n"
        "        // Return ALL .json files in the backup folder (and its parent\n"
        "        // PinterestViewerDownloads folder, if any), so user-created or\n"
        "        // manually-copied backups are listed. Compact and pretty JSON are\n"
        "        // both supported by the restore path.\n"
        "        val primaryDir = getBackupDirectory(context)\n"
        "        val files = mutableListOf<File>()\n"
        "\n"
        "        fun collectFrom(dir: File) {\n"
        "            if (dir.exists() && dir.isDirectory) {\n"
        "                dir.listFiles { f ->\n"
        "                    f.isFile && f.extension.equals(\"json\", ignoreCase = true)\n"
        "                }?.let { files.addAll(it) }\n"
        "            }\n"
        "        }\n"
        "\n"
        "        collectFrom(primaryDir)\n"
        "        primaryDir.parentFile?.let { parent ->\n"
        "            if (parent.name == \"PinterestViewerDownloads\") {\n"
        "                collectFrom(parent)\n"
        "            }\n"
        "        }\n"
        "\n"
        "        return files.distinctBy { it.absolutePath }\n"
        "            .sortedByDescending { it.lastModified() }\n"
        "    }"
    )
    if get_old in text:
        text = text.replace(get_old, get_new, 1)
        changed = True

    if changed:
        path.write_text(text, encoding="utf-8")
        log("  ✓ Patched BackupManager.kt")
    else:
        log("  ✓ Already patched (or no matching anchors found)")


# ============================================================
# NEW PATCH 3: SettingsDialog — Unlimited label handling
# ============================================================
def patch_settings_dialog():
    log("\n=== PATCH: SettingsDialog (Unlimited label) ===")
    path = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/SettingsDialog.kt"
    if not path.exists():
        log(f"  ✗ {path} not found"); sys.exit(1)

    text = path.read_text(encoding="utf-8")

    if 'if (maxBackupFiles == 0) "Unlimited ▾"' in text:
        log("  ✓ Already patched."); return

    changed = False

    # 1. Header/current selection label
    sel_old = '                                        text = "$maxBackupFiles files ▾",'
    sel_new = (
        '                                        text = if (maxBackupFiles == 0) "Unlimited ▾" '
        'else "$maxBackupFiles files ▾",'
    )
    if sel_old in text:
        text = text.replace(sel_old, sel_new, 1)
        changed = True

    # 2. Dropdown item label
    item_old = (
        "                                            Text(\n"
        '                                                text = "$count file${if (count > 1) "s" else ""}",\n'
    )
    item_new = (
        "                                            Text(\n"
        "                                                text = if (count == 0) \"Unlimited\" "
        "else \"$count file${if (count > 1) \"s\" else \"\"}\",\n"
    )
    if item_old in text:
        text = text.replace(item_old, item_new, 1)
        changed = True

    if changed:
        path.write_text(text, encoding="utf-8")
        log("  ✓ Patched SettingsDialog.kt")
    else:
        log("  ⚠ Could not locate the exact label strings — inspect manually.")


# ============================================================
# EXISTING PATCH: Disable Arrow Navigation wiring
# ============================================================
def fix_disable_arrow_navigation():
    log("\n=== PATCH: Disable Arrow Navigation wiring ===")
    path = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not path.exists():
        log(f"  ✗ {path} not found"); sys.exit(1)

    text = path.read_text(encoding="utf-8")
    if "onToggleDisableArrowNavigation = { viewModel.setDisableArrowNavigation(it) }" in text:
        log("  ✓ Already wired."); return

    old = (
        "        portraitAlbumCards = portraitAlbumCards,\n"
        "        onTogglePortraitAlbumCards = { viewModel.setPortraitAlbumCards(it) },\n"
        "        isBrowserTestingVisible = isBrowserTestingVisible,\n"
    )
    new = (
        "        portraitAlbumCards = portraitAlbumCards,\n"
        "        onTogglePortraitAlbumCards = { viewModel.setPortraitAlbumCards(it) },\n"
        "        disableArrowNavigation = disableArrowNavigation,\n"
        "        onToggleDisableArrowNavigation = { viewModel.setDisableArrowNavigation(it) },\n"
        "        isBrowserTestingVisible = isBrowserTestingVisible,\n"
    )
    if old in text:
        text = text.replace(old, new, 1)
    else:
        m = re.search(
            r"(onTogglePortraitAlbumCards\s*=\s*\{[^}]+\}\s*,\s*\n)(\s*isBrowserTestingVisible\s*=)",
            text,
        )
        if not m:
            log("  ✗ Could not locate SettingsDialog anchor."); sys.exit(1)
        inject = (
            "        disableArrowNavigation = disableArrowNavigation,\n"
            "        onToggleDisableArrowNavigation = { viewModel.setDisableArrowNavigation(it) },\n"
        )
        text = text[:m.end(1)] + inject + text[m.end(1):]

    path.write_text(text, encoding="utf-8")
    log("  ✓ Wired disableArrowNavigation into SettingsDialog")


# ============================================================
# EXISTING PATCH: release.keystore
# ============================================================
def ensure_release_keystore():
    log("\n=== Ensuring release.keystore ===")
    ks = PROJECT_ROOT / KEYSTORE_FILE
    if ks.exists() and ks.stat().st_size > 0:
        r = subprocess.run(
            ["keytool", "-list", "-keystore", str(ks), "-storepass", KEYSTORE_PASS],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and KEYSTORE_ALIAS in r.stdout:
            log(f"  ✓ {KEYSTORE_FILE} OK (alias '{KEYSTORE_ALIAS}')")
            return
        log(f"  ✗ {KEYSTORE_FILE} exists but password/alias mismatch. Delete it and re-run.")
        sys.exit(1)

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
        log(f"  ✗ keytool failed: {r.stderr.strip()}"); sys.exit(1)
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
    if not p.exists():
        log(f"  ✗ {p} not found"); sys.exit(1)

    text = p.read_text(encoding="utf-8")
    orig = text

    marker = 'create("release")'
    idx = text.find(marker)
    if idx == -1:
        log(f"  ✗ {marker} not found"); sys.exit(1)
    span = find_braced_block_at(text, idx)
    if not span:
        log(f"  ✗ could not locate braces for {marker}"); sys.exit(1)
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
                rel_open, rel_close = rel_span
                block = text[rel_open + 1:rel_close]
                if "isDebuggable = true" in block:
                    text = text[:rel_open + 1] + block.replace("isDebuggable = true", "isDebuggable = false") + text[rel_close:]
                    log("  ✓ release buildType: isDebuggable -> false")
                elif "isDebuggable" not in block:
                    nb = block.replace("isMinifyEnabled = false",
                                       "isMinifyEnabled = false\n      isDebuggable = false", 1)
                    if nb != block:
                        text = text[:rel_open + 1] + nb + text[rel_close:]
                        log("  ✓ release buildType: added isDebuggable = false")

    if text != orig:
        p.write_text(text, encoding="utf-8")


# ============================================================
# Gradle wrapper / workflow / git / CI / adb (from previous script)
# ============================================================
def latest_gradle_version():
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/gradle/gradle/releases/latest",
            headers={"User-Agent": "pinboard-build"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            tag = json.load(resp).get("tag_name", "").lstrip("v")
            if tag: return tag
    except Exception:
        pass
    props = PROJECT_ROOT / "gradle/wrapper/gradle-wrapper.properties"
    if props.exists():
        m = re.search(r"gradle-([\d.]+)-bin\.zip", props.read_text(encoding="utf-8"))
        if m: return m.group(1)
    return "9.3.1"


def ensure_gradle_wrapper():
    log("\n=== Ensuring Gradle wrapper ===")
    gradlew = PROJECT_ROOT / "gradlew"
    gradlew_bat = PROJECT_ROOT / "gradlew.bat"
    wrapper_jar = PROJECT_ROOT / "gradle/wrapper/gradle-wrapper.jar"
    if gradlew.exists() and gradlew_bat.exists() and wrapper_jar.exists():
        log("  ✓ Present."); return
    ver = latest_gradle_version()
    log(f"  Using Gradle v{ver}")
    base = f"https://raw.githubusercontent.com/gradle/gradle/v{ver}"
    for url, dest in [
        (f"{base}/gradlew", gradlew),
        (f"{base}/gradlew.bat", gradlew_bat),
        (f"{base}/gradle/wrapper/gradle-wrapper.jar", wrapper_jar),
    ]:
        if dest.exists() and dest.stat().st_size > 0: continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try: urllib.request.urlretrieve(url, dest)
        except Exception as e:
            log(f"  ✗ {e}"); sys.exit(1)
    try: os.chmod(gradlew, 0o755)
    except Exception: pass


def write_workflow():
    log("\n=== Writing GitHub Actions workflow ===")
    wf_dir = PROJECT_ROOT / ".github/workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "build.yml").write_text(WORKFLOW_YAML, encoding="utf-8")
    log("  ✓ Written.")


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
             "Add fullscreen refresh + unlimited backups + all-files restore + pretty JSON"])
        log("  ✓ Committed.")


def verify_release_keystore_tracked():
    r = subprocess.run(
        ["git", "ls-files", "--error-unmatch", KEYSTORE_FILE],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    if r.returncode != 0:
        run(["git", "add", "-f", KEYSTORE_FILE])
        run(["git", "commit", "-m", f"Add {KEYSTORE_FILE}"])


def gh_user():
    r = subprocess.run(["gh", "api", "user", "--jq", ".login"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        log("ERROR: gh not authenticated. Run: gh auth login"); sys.exit(1)
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
    for attempt in range(6):
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


def move_apk(dl_dir):
    apks = list(dl_dir.glob("*.apk"))
    if not apks: log("  ✗ No APK."); sys.exit(1)
    apk = apks[0]
    tf = PROJECT_ROOT / "Apk Directory.txt"
    target_dir = (Path(tf.read_text(encoding="utf-8").strip())
                  if tf.exists() else Path.home() / "Downloads")
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / apk.name
    if dest.exists():
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = target_dir / f"{apk.stem}_{ts}{apk.suffix}"
    shutil.copy2(apk, dest)
    log(f"  ✓ APK -> {dest}")
    return dest


def device_install(apk_path):
    log("\n=== Device install ===")
    adb = find_adb()
    if not adb or not adb_device_connected(adb):
        log("  No device — skipping.")
        log(f"    adb uninstall {PACKAGE_ID}")
        log(f'    adb install "{apk_path}"')
        return
    subprocess.run([adb, "uninstall", PACKAGE_ID], capture_output=True, text=True, timeout=60)
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
    log("PinBoard Gallery - Feature patches + release build")
    log("=" * 70)

    if not (PROJECT_ROOT / "app/build.gradle.kts").exists():
        log(f"ERROR: {PROJECT_ROOT} isn't a PinBoard project."); sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t):
            log(f"ERROR: {t} not found in PATH"); sys.exit(1)

    # Code patches
    patch_fullscreen_refresh_button()
    patch_backup_manager()
    patch_settings_dialog()
    fix_disable_arrow_navigation()

    # Build infrastructure
    ensure_release_keystore()
    patch_build_gradle()
    ensure_gradle_wrapper()
    write_workflow()

    # Repo + CI
    setup_git()
    verify_release_keystore_tracked()
    repo = ensure_github_repo()
    dl   = trigger_and_download(repo)

    # Output
    apk = move_apk(dl)
    verify_apk_signature(apk)
    device_install(apk)

    log("\n" + "=" * 70)
    log(f"DONE -> {apk}")
    log("=" * 70)


if __name__ == "__main__":
    main()