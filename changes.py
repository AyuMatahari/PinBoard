#!/usr/bin/env python3
"""
PinBoard Gallery — rollback unified cache; separate video limit + clear in settings
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
# PATCH 1 — Delete CacheBudgetEnforcer + remove references
# ============================================================
def rollback_cache_budget_enforcer():
    log("\n=== PATCH: rollback CacheBudgetEnforcer ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/CacheBudgetEnforcer.kt"
    if f.exists():
        f.unlink()
        log("  ✓ CacheBudgetEnforcer.kt deleted")
    else:
        log("  ✓ already absent")

    pa = PROJECT_ROOT / "app/src/main/java/com/example/PinBoardApplication.kt"
    if pa.exists():
        t = pa.read_text(encoding="utf-8")
        old = "        com.example.util.CacheBudgetEnforcer.init(this)\n"
        if old in t:
            t = t.replace(old, "", 1)
            pa.write_text(t, encoding="utf-8")
            log("  ✓ init removed from PinBoardApplication")


# ============================================================
# PATCH 2 — Rewrite VideoPlayerManager (fix import, add limit prefs)
# ============================================================
NEW_VIDEO_PLAYER_MANAGER = r'''package com.example.util

import android.content.Context
import android.net.Uri
import androidx.media3.common.MediaItem
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.datasource.cache.CacheDataSource
import androidx.media3.datasource.cache.LeastRecentlyUsedCacheEvictor
import androidx.media3.datasource.cache.SimpleCache
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.dash.DashMediaSource
import androidx.media3.exoplayer.hls.HlsMediaSource
import androidx.media3.exoplayer.source.MediaSource
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import androidx.media3.exoplayer.upstream.DefaultLoadErrorHandlingPolicy
import com.example.model.PinItem
import java.io.File

/**
 * In-app video player backed by Media3 ExoPlayer with SimpleCache.
 *
 * Cache behaviour:
 *   - Video cache has its OWN configurable limit (MIN 20 / MAX 4096 MB).
 *   - Cache lives in cacheDir/media3_video_cache (cleared by Android when low on space).
 *   - Downloads occur while player is playing; pause stops fetching; resume continues.
 *
 * Cache budgeting is SEPARATE from ImageCacheManager (image cache).
 */
object VideoPlayerManager {

    private const val PREFS_NAME = "video_cache_prefs"
    private const val KEY_MAX_VIDEO_CACHE_MB = "max_video_cache_mb"
    const val DEFAULT_MAX_VIDEO_CACHE_MB = 512
    const val MIN_VIDEO_CACHE_MB = 20
    const val MAX_VIDEO_CACHE_MB = 4096

    private var player: ExoPlayer? = null
    private var simpleCache: SimpleCache? = null
    private var cacheBudgetMb: Int = -1
    private var currentPinId: String? = null

    fun getMaxVideoCacheMb(context: Context): Int {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getInt(KEY_MAX_VIDEO_CACHE_MB, DEFAULT_MAX_VIDEO_CACHE_MB)
    }

    fun setMaxVideoCacheMb(context: Context, mb: Int) {
        val clamped = mb.coerceIn(MIN_VIDEO_CACHE_MB, MAX_VIDEO_CACHE_MB)
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit().putInt(KEY_MAX_VIDEO_CACHE_MB, clamped).apply()
        // Release existing cache so next access rebuilds with new budget
        try { simpleCache?.release() } catch (_: Throwable) {}
        simpleCache = null
        cacheBudgetMb = -1
    }

    fun getOrCreatePlayer(context: Context): ExoPlayer {
        player?.let { return it }
        val ctx = context.applicationContext
        val p = ExoPlayer.Builder(ctx).build()
        p.repeatMode = ExoPlayer.REPEAT_MODE_OFF
        player = p
        return p
    }

    private fun getSimpleCache(context: Context): SimpleCache {
        val ctx = context.applicationContext
        val maxMb = getMaxVideoCacheMb(ctx)
        if (simpleCache != null && cacheBudgetMb == maxMb) {
            return simpleCache!!
        }
        try { simpleCache?.release() } catch (_: Throwable) {}

        val budgetBytes = maxMb.toLong() * 1024L * 1024L
        val cacheDir = File(ctx.cacheDir, "media3_video_cache").apply { mkdirs() }
        val evictor = LeastRecentlyUsedCacheEvictor(budgetBytes)
        val cache = SimpleCache(cacheDir, evictor)
        simpleCache = cache
        cacheBudgetMb = maxMb
        return cache
    }

    fun play(context: Context, pin: PinItem) {
        val videoUrl = (pin.videoUrl ?: pin.imageUrl).ifBlank { return }
        val p = getOrCreatePlayer(context)

        if (currentPinId == pin.id && p.mediaItemCount > 0) {
            p.play()
            return
        }

        currentPinId = pin.id
        val cache = getSimpleCache(context)
        val upstream = DefaultHttpDataSource.Factory()
            .setUserAgent("Mozilla/5.0 (Android; Mobile; rv:109.0)")
            .setAllowCrossProtocolRedirects(true)
            .setConnectTimeoutMs(15_000)
            .setReadTimeoutMs(30_000)

        val cacheFactory = CacheDataSource.Factory()
            .setCache(cache)
            .setUpstreamDataSourceFactory(upstream)
            .setFlags(CacheDataSource.FLAG_IGNORE_CACHE_ON_ERROR)

        val mediaItem = MediaItem.fromUri(Uri.parse(videoUrl))
        val mediaSource: MediaSource = when {
            videoUrl.contains(".m3u8", ignoreCase = true) ->
                HlsMediaSource.Factory(cacheFactory)
                    .setAllowChunklessPreparation(true)
                    .createMediaSource(mediaItem)
            videoUrl.contains(".mpd", ignoreCase = true) ->
                DashMediaSource.Factory(cacheFactory)
                    .createMediaSource(mediaItem)
            else ->
                ProgressiveMediaSource.Factory(cacheFactory)
                    .setLoadErrorHandlingPolicy(DefaultLoadErrorHandlingPolicy(5))
                    .createMediaSource(mediaItem)
        }

        p.setMediaSource(mediaSource)
        p.prepare()
        p.playWhenReady = true
    }

    fun pause() {
        try { player?.pause() } catch (_: Throwable) {}
    }

    fun release() {
        try {
            player?.stop()
            player?.clearMediaItems()
            player?.release()
        } catch (_: Throwable) {}
        player = null
        currentPinId = null
    }

    fun currentPlayingPinId(): String? = currentPinId

    fun getCacheSizeBytes(context: Context): Long {
        val dir = File(context.cacheDir, "media3_video_cache")
        if (!dir.exists()) return 0L
        return dirSize(dir)
    }

    fun clearCache(context: Context) {
        release()
        try { simpleCache?.release() } catch (_: Throwable) {}
        simpleCache = null
        cacheBudgetMb = -1
        val dir = File(context.cacheDir, "media3_video_cache")
        if (dir.exists()) {
            try { dir.deleteRecursively() } catch (_: Throwable) {}
        }
    }

    fun invalidateCache() {
        try { simpleCache?.release() } catch (_: Throwable) {}
        simpleCache = null
        cacheBudgetMb = -1
    }

    private fun dirSize(dir: File): Long {
        var total = 0L
        dir.listFiles()?.forEach { f ->
            total += if (f.isDirectory) dirSize(f) else f.length()
        }
        return total
    }
}
'''


def rewrite_video_player_manager():
    log("\n=== PATCH: rewrite VideoPlayerManager ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/VideoPlayerManager.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    if ("androidx.media3.exoplayer.upstream.DefaultLoadErrorHandlingPolicy" in t
            and "getMaxVideoCacheMb" in t
            and "CacheBudgetEnforcer" not in t):
        log("  ✓ already correct"); return
    f.write_text(NEW_VIDEO_PLAYER_MANAGER, encoding="utf-8")
    log("  ✓ rewritten (correct import, separate budget, enforcer removed)")


# ============================================================
# PATCH 3 — ImageCacheManager: image-only (no video coupling)
# ============================================================
def patch_image_cache_manager():
    log("\n=== PATCH: ImageCacheManager (image-only rollback) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageCacheManager.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # 3a. getDiskCacheUsageBytes — image only
    old_gd = (
        '    /** Combined image + video cache size. Enforced as a single budget by CacheBudgetEnforcer. */\n'
        '    fun getDiskCacheUsageBytes(context: Context): Long {\n'
        '        val cacheDir = context.cacheDir.resolve("image_cache")\n'
        '        val imageBytes = if (!cacheDir.exists()) 0L else getDirSize(cacheDir)\n'
        '        val videoBytes = try { com.example.util.VideoPlayerManager.getCacheSizeBytes(context) } catch (_: Throwable) { 0L }\n'
        '        return imageBytes + videoBytes\n'
        '    }\n'
    )
    new_gd = (
        '    fun getDiskCacheUsageBytes(context: Context): Long {\n'
        '        val cacheDir = context.cacheDir.resolve("image_cache")\n'
        '        if (!cacheDir.exists()) return 0L\n'
        '        return getDirSize(cacheDir)\n'
        '    }\n'
    )
    if old_gd in t:
        t = t.replace(old_gd, new_gd, 1)
        changed = True
        log("  ✓ getDiskCacheUsageBytes → image only")
    else:
        # Try simpler replacement if comment was different
        old_gd2 = (
            '    fun getDiskCacheUsageBytes(context: Context): Long {\n'
            '        val cacheDir = context.cacheDir.resolve("image_cache")\n'
            '        val imageBytes = if (!cacheDir.exists()) 0L else getDirSize(cacheDir)\n'
            '        val videoBytes = try { com.example.util.VideoPlayerManager.getCacheSizeBytes(context) } catch (_: Throwable) { 0L }\n'
            '        return imageBytes + videoBytes\n'
            '    }\n'
        )
        if old_gd2 in t:
            t = t.replace(old_gd2, new_gd, 1)
            changed = True
            log("  ✓ getDiskCacheUsageBytes → image only (v2)")

    # 3b. clearCache — remove video clear
    old_cc = (
        '            try { com.example.util.VideoPlayerManager.clearCache(context) } catch (_: Throwable) {}\n'
    )
    if old_cc in t:
        t = t.replace(old_cc, "", 1)
        changed = True
        log("  ✓ clearCache → image only")

    # 3c. applyImageLoader — remove invalidateCache
    old_ap = (
        '        Coil.setImageLoader(imageLoader)\n'
        '        try { com.example.util.VideoPlayerManager.invalidateCache() } catch (_: Throwable) {}\n'
        '    }\n'
    )
    new_ap = (
        '        Coil.setImageLoader(imageLoader)\n'
        '    }\n'
    )
    if old_ap in t:
        t = t.replace(old_ap, new_ap, 1)
        changed = True
        log("  ✓ applyImageLoader → no video invalidation")

    if changed:
        f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 4 — FullscreenGalleryViewer: fix overlay scope
# ============================================================
def fix_fullscreen_video_overlay():
    log("\n=== PATCH: FullscreenGalleryViewer (top-level overlay) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/FullscreenGalleryViewer.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # 4a. Remove any existing broken overlay (inside pager — bad scope)
    bad_if = "if (pin.isVideo && playingVideoPinId == pin.id) {"
    bidx = t.find(bad_if)
    if bidx >= 0:
        prev_comment = t.rfind("// In-app video player overlay", 0, bidx)
        if prev_comment < 0:
            prev_comment = bidx
        # Back up to start of comment line
        line_start = t.rfind("\n", 0, prev_comment) + 1
        # Trim leading blank line if present
        while line_start >= 2 and t[line_start-1] == "\n" and t[line_start-2] == "\n":
            line_start -= 1

        # Brace balance the if block
        ob = t.find("{", bidx)
        depth = 0
        i = ob
        close_brace = -1
        while i < len(t):
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
                if depth == 0:
                    close_brace = i
                    break
            i += 1
        if close_brace > 0:
            end = close_brace + 1
            while end < len(t) and t[end] == "\n":
                end += 1
            t = t[:line_start] + t[end:]
            changed = True
            log("  ✓ removed broken overlay (was inside pager)")

    # 4b. Insert new top-level overlay before pinForImageHoldDialog
    if "// In-app video player overlay (top-level)" not in t:
        anchor = "\n        pinForImageHoldDialog?.let { pin ->\n"
        if anchor not in t:
            log("  ⚠ pinForImageHoldDialog anchor not found"); sys.exit(1)

        overlay = (
            "\n"
            "        // In-app video player overlay (top-level) — plays the pin whose id matches\n"
            "        val playingPin = playingVideoPinId?.let { id -> pins.firstOrNull { it.id == id } }\n"
            "        if (playingPin != null) {\n"
            "            androidx.compose.foundation.layout.Box(\n"
            "                modifier = Modifier\n"
            "                    .fillMaxSize()\n"
            "                    .background(Color.Black)\n"
            "                    .testTag(\"video_player_overlay\")\n"
            "            ) {\n"
            "                FullscreenVideoPlayer(modifier = Modifier.fillMaxSize())\n"
            "\n"
            "                IconButton(\n"
            "                    onClick = {\n"
            "                        com.example.util.VideoPlayerManager.release()\n"
            "                        playingVideoPinId = null\n"
            "                        onClose()\n"
            "                    },\n"
            "                    modifier = Modifier\n"
            "                        .align(Alignment.TopStart)\n"
            "                        .padding(16.dp)\n"
            "                        .size(44.dp)\n"
            "                        .background(Color.Black.copy(alpha = 0.55f), CircleShape)\n"
            "                ) {\n"
            "                    Icon(\n"
            "                        imageVector = Icons.Default.Close,\n"
            "                        contentDescription = \"Close video\",\n"
            "                        tint = Color.White\n"
            "                    )\n"
            "                }\n"
            "\n"
            "                if (pins.size > 1 && !disableArrowNavigation) {\n"
            "                    IconButton(\n"
            "                        onClick = {\n"
            "                            com.example.util.VideoPlayerManager.pause()\n"
            "                            playingVideoPinId = null\n"
            "                            coroutineScope.launch {\n"
            "                                val target = (pagerState.currentPage - 1).coerceAtLeast(0)\n"
            "                                pagerState.animateScrollToPage(target)\n"
            "                            }\n"
            "                        },\n"
            "                        modifier = Modifier\n"
            "                            .align(Alignment.CenterStart)\n"
            "                            .padding(12.dp)\n"
            "                            .size(44.dp)\n"
            "                            .background(Color.Black.copy(alpha = 0.5f), CircleShape)\n"
            "                    ) {\n"
            "                        Icon(\n"
            "                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,\n"
            "                            contentDescription = \"Previous\",\n"
            "                            tint = Color.White\n"
            "                        )\n"
            "                    }\n"
            "                    IconButton(\n"
            "                        onClick = {\n"
            "                            com.example.util.VideoPlayerManager.pause()\n"
            "                            playingVideoPinId = null\n"
            "                            coroutineScope.launch {\n"
            "                                val target = (pagerState.currentPage + 1).coerceAtMost(virtualPageCount - 1)\n"
            "                                pagerState.animateScrollToPage(target)\n"
            "                            }\n"
            "                        },\n"
            "                        modifier = Modifier\n"
            "                            .align(Alignment.CenterEnd)\n"
            "                            .padding(12.dp)\n"
            "                            .size(44.dp)\n"
            "                            .background(Color.Black.copy(alpha = 0.5f), CircleShape)\n"
            "                    ) {\n"
            "                        Icon(\n"
            "                            imageVector = Icons.AutoMirrored.Filled.ArrowForward,\n"
            "                            contentDescription = \"Next\",\n"
            "                            tint = Color.White\n"
            "                        )\n"
            "                    }\n"
            "                }\n"
            "            }\n"
            "        }\n"
            "\n"
            "        pinForImageHoldDialog?.let { pin ->\n"
        )
        t = t.replace(anchor, overlay, 1)
        changed = True
        log("  ✓ top-level overlay inserted")

    # 4c. Ensure Close icon import
    if "import androidx.compose.material.icons.filled.Close\n" not in t:
        for anchor_imp in [
            "import androidx.compose.material.icons.filled.ContentCopy\n",
            "import androidx.compose.material.icons.filled.DeleteOutline\n",
            "import androidx.compose.material.icons.filled.Download\n",
        ]:
            if anchor_imp in t:
                t = t.replace(anchor_imp, "import androidx.compose.material.icons.filled.Close\n" + anchor_imp, 1)
                changed = True
                log("  ✓ Close icon import added")
                break

    # 4d. Ensure FullscreenVideoPlayer import (same package, no import needed — but verify)
    # (it's com.example.ui.components.FullscreenVideoPlayer — same package as FullscreenGalleryViewer)

    if changed:
        f.write_text(t, encoding="utf-8")


# ============================================================
# PATCH 5 — SettingsDialog: video cache section
# ============================================================
def patch_settings_dialog():
    log("\n=== PATCH: SettingsDialog (video cache section) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/SettingsDialog.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "video_cache_size_slider" in t:
        log("  ✓ already patched"); return

    changed = False

    # 5a. Add PlayArrow import
    if "import androidx.compose.material.icons.filled.PlayArrow" not in t:
        for anchor in [
            "import androidx.compose.material.icons.filled.DeleteSweep\n",
            "import androidx.compose.material.icons.filled.Settings\n",
            "import androidx.compose.material.icons.filled.BugReport\n",
        ]:
            if anchor in t:
                t = t.replace(anchor, anchor + "import androidx.compose.material.icons.filled.PlayArrow\n", 1)
                changed = True
                break

    # 5b. Add state declarations after image cache ones
    old_state = (
        "    var sliderValue by remember { mutableFloatStateOf(currentSavedMb.toFloat()) }\n"
        "    var textValue by remember { mutableStateOf(currentSavedMb.toString()) }\n"
        "    var isInputError by remember { mutableStateOf(false) }\n"
    )
    new_state = (
        old_state +
        "\n"
        "    // Video cache state\n"
        "    val currentVideoSavedMb = remember { com.example.util.VideoPlayerManager.getMaxVideoCacheMb(context) }\n"
        "    var currentVideoCacheUsageBytes by remember { mutableLongStateOf(0L) }\n"
        "    var videoSliderValue by remember { mutableFloatStateOf(currentVideoSavedMb.toFloat()) }\n"
        "    var videoTextValue by remember { mutableStateOf(currentVideoSavedMb.toString()) }\n"
        "    var videoInputError by remember { mutableStateOf(false) }\n"
    )
    if old_state in t:
        t = t.replace(old_state, new_state, 1)
        changed = True
        log("  ✓ video cache state added")

    # 5c. Extend LaunchedEffect(isOpen) to read video usage
    old_lc = (
        "    LaunchedEffect(isOpen) {\n"
        "        currentCacheUsageBytes = ImageCacheManager.getDiskCacheUsageBytes(context)\n"
        "    }\n"
    )
    new_lc = (
        "    LaunchedEffect(isOpen) {\n"
        "        currentCacheUsageBytes = ImageCacheManager.getDiskCacheUsageBytes(context)\n"
        "        currentVideoCacheUsageBytes = try {\n"
        "            com.example.util.VideoPlayerManager.getCacheSizeBytes(context)\n"
        "        } catch (_: Throwable) { 0L }\n"
        "    }\n"
    )
    if old_lc in t:
        t = t.replace(old_lc, new_lc, 1)
        changed = True
        log("  ✓ LaunchedEffect reads video usage")

    # 5d. Insert video section before Crash & Error Diagnostics card
    anchor_diag = (
        "                Spacer(modifier = Modifier.height(16.dp))\n"
        "                HorizontalDivider(color = PinterestPillDarkGray.copy(alpha = 0.5f))\n"
        "                Spacer(modifier = Modifier.height(12.dp))\n"
        "\n"
        "                // Crash & Error Diagnostics\n"
    )
    if anchor_diag not in t:
        log("  ⚠ diagnostics anchor missing"); sys.exit(1)

    video_section = (
        "                Spacer(modifier = Modifier.height(16.dp))\n"
        "                HorizontalDivider(color = PinterestPillDarkGray.copy(alpha = 0.5f))\n"
        "                Spacer(modifier = Modifier.height(12.dp))\n"
        "\n"
        "                // Video cache usage card\n"
        "                Card(\n"
        "                    shape = RoundedCornerShape(12.dp),\n"
        "                    colors = CardDefaults.cardColors(containerColor = PinterestPillGray),\n"
        "                    modifier = Modifier.fillMaxWidth()\n"
        "                ) {\n"
        "                    Row(\n"
        "                        modifier = Modifier\n"
        "                            .fillMaxWidth()\n"
        "                            .padding(horizontal = 12.dp, vertical = 10.dp),\n"
        "                        verticalAlignment = Alignment.CenterVertically,\n"
        "                        horizontalArrangement = Arrangement.SpaceBetween\n"
        "                    ) {\n"
        "                        Row(verticalAlignment = Alignment.CenterVertically) {\n"
        "                            Icon(\n"
        "                                imageVector = Icons.Default.PlayArrow,\n"
        "                                contentDescription = null,\n"
        "                                tint = PinterestRed,\n"
        "                                modifier = Modifier.size(20.dp)\n"
        "                            )\n"
        "                            Spacer(modifier = Modifier.width(8.dp))\n"
        "                            Column {\n"
        "                                Text(\n"
        "                                    text = \"Current Video Cache\",\n"
        "                                    fontSize = 12.sp,\n"
        "                                    color = PinterestTextSecondary,\n"
        "                                    fontWeight = FontWeight.Medium\n"
        "                                )\n"
        "                                Text(\n"
        "                                    text = ImageCacheManager.formatBytes(currentVideoCacheUsageBytes),\n"
        "                                    fontSize = 14.sp,\n"
        "                                    fontWeight = FontWeight.Bold,\n"
        "                                    color = PinterestBlack\n"
        "                                )\n"
        "                            }\n"
        "                        }\n"
        "                        Button(\n"
        "                            onClick = {\n"
        "                                com.example.util.VideoPlayerManager.clearCache(context)\n"
        "                                currentVideoCacheUsageBytes = 0L\n"
        "                            },\n"
        "                            colors = ButtonDefaults.buttonColors(\n"
        "                                containerColor = MaterialTheme.colorScheme.surface,\n"
        "                                contentColor = PinterestRed\n"
        "                            ),\n"
        "                            shape = RoundedCornerShape(16.dp),\n"
        "                            elevation = ButtonDefaults.buttonElevation(defaultElevation = 1.dp),\n"
        "                            modifier = Modifier.testTag(\"clear_video_cache_button\")\n"
        "                        ) {\n"
        "                            Icon(\n"
        "                                imageVector = Icons.Default.DeleteSweep,\n"
        "                                contentDescription = null,\n"
        "                                modifier = Modifier.size(16.dp)\n"
        "                            )\n"
        "                            Spacer(modifier = Modifier.width(4.dp))\n"
        "                            Text(\"Clear\", fontSize = 12.sp, fontWeight = FontWeight.Bold)\n"
        "                        }\n"
        "                    }\n"
        "                }\n"
        "\n"
        "                Spacer(modifier = Modifier.height(16.dp))\n"
        "                Text(\n"
        "                    text = \"MAX VIDEO CACHE SIZE\",\n"
        "                    style = MaterialTheme.typography.labelSmall.copy(\n"
        "                        fontWeight = FontWeight.Bold,\n"
        "                        fontSize = 11.sp,\n"
        "                        letterSpacing = 0.5.sp,\n"
        "                        color = PinterestTextSecondary\n"
        "                    )\n"
        "                )\n"
        "                Spacer(modifier = Modifier.height(4.dp))\n"
        "                Text(\n"
        "                    text = \"Maximum disk space (MB) reserved for in-app video playback cache:\",\n"
        "                    style = MaterialTheme.typography.bodySmall.copy(\n"
        "                        fontSize = 12.sp,\n"
        "                        color = PinterestTextSecondary\n"
        "                    )\n"
        "                )\n"
        "                Spacer(modifier = Modifier.height(12.dp))\n"
        "\n"
        "                OutlinedTextField(\n"
        "                    value = videoTextValue,\n"
        "                    onValueChange = { input ->\n"
        "                        val filtered = input.filter { it.isDigit() }\n"
        "                        videoTextValue = filtered\n"
        "                        val parsed = filtered.toIntOrNull()\n"
        "                        if (parsed != null && parsed in com.example.util.VideoPlayerManager.MIN_VIDEO_CACHE_MB..com.example.util.VideoPlayerManager.MAX_VIDEO_CACHE_MB) {\n"
        "                            videoInputError = false\n"
        "                            videoSliderValue = parsed.toFloat()\n"
        "                        } else {\n"
        "                            videoInputError = filtered.isNotEmpty()\n"
        "                        }\n"
        "                    },\n"
        "                    label = { Text(\"Video Cache Size (MB)\") },\n"
        "                    suffix = { Text(\"MB\", fontWeight = FontWeight.Bold) },\n"
        "                    singleLine = true,\n"
        "                    isError = videoInputError,\n"
        "                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),\n"
        "                    colors = OutlinedTextFieldDefaults.colors(\n"
        "                        focusedBorderColor = PinterestRed,\n"
        "                        cursorColor = PinterestRed,\n"
        "                        focusedLabelColor = PinterestRed\n"
        "                    ),\n"
        "                    shape = RoundedCornerShape(12.dp),\n"
        "                    modifier = Modifier\n"
        "                        .fillMaxWidth()\n"
        "                        .testTag(\"video_cache_size_text_input\")\n"
        "                )\n"
        "\n"
        "                if (videoInputError) {\n"
        "                    Text(\n"
        "                        text = \"Enter a value between ${com.example.util.VideoPlayerManager.MIN_VIDEO_CACHE_MB} and ${com.example.util.VideoPlayerManager.MAX_VIDEO_CACHE_MB} MB\",\n"
        "                        color = MaterialTheme.colorScheme.error,\n"
        "                        fontSize = 11.sp,\n"
        "                        modifier = Modifier.padding(start = 4.dp, top = 2.dp)\n"
        "                    )\n"
        "                }\n"
        "\n"
        "                Spacer(modifier = Modifier.height(10.dp))\n"
        "\n"
        "                Row(\n"
        "                    modifier = Modifier.fillMaxWidth(),\n"
        "                    horizontalArrangement = Arrangement.SpaceBetween,\n"
        "                    verticalAlignment = Alignment.CenterVertically\n"
        "                ) {\n"
        "                    Text(\"${com.example.util.VideoPlayerManager.MIN_VIDEO_CACHE_MB} MB\", fontSize = 11.sp, color = PinterestTextSecondary)\n"
        "                    Text(\"${videoSliderValue.toInt()} MB\", fontSize = 13.sp, fontWeight = FontWeight.ExtraBold, color = PinterestRed)\n"
        "                    Text(\"${com.example.util.VideoPlayerManager.MAX_VIDEO_CACHE_MB} MB\", fontSize = 11.sp, color = PinterestTextSecondary)\n"
        "                }\n"
        "\n"
        "                Slider(\n"
        "                    value = videoSliderValue,\n"
        "                    onValueChange = { v ->\n"
        "                        videoSliderValue = v\n"
        "                        videoTextValue = v.toInt().toString()\n"
        "                        videoInputError = false\n"
        "                    },\n"
        "                    valueRange = com.example.util.VideoPlayerManager.MIN_VIDEO_CACHE_MB.toFloat()..com.example.util.VideoPlayerManager.MAX_VIDEO_CACHE_MB.toFloat(),\n"
        "                    colors = SliderDefaults.colors(\n"
        "                        thumbColor = PinterestRed,\n"
        "                        activeTrackColor = PinterestRed,\n"
        "                        inactiveTrackColor = PinterestPillGray\n"
        "                    ),\n"
        "                    modifier = Modifier\n"
        "                        .fillMaxWidth()\n"
        "                        .testTag(\"video_cache_size_slider\")\n"
        "                )\n"
        "\n"
        "                Spacer(modifier = Modifier.height(8.dp))\n"
        "\n"
        "                Row(\n"
        "                    modifier = Modifier.fillMaxWidth(),\n"
        "                    horizontalArrangement = Arrangement.spacedBy(6.dp)\n"
        "                ) {\n"
        "                    listOf(256, 512, 1024, 2048).forEach { presetMb ->\n"
        "                        val isSelected = videoSliderValue.toInt() == presetMb\n"
        "                        Surface(\n"
        "                            shape = RoundedCornerShape(16.dp),\n"
        "                            color = if (isSelected) PinterestBlack else PinterestPillGray,\n"
        "                            modifier = Modifier\n"
        "                                .weight(1f)\n"
        "                                .clickable {\n"
        "                                    videoSliderValue = presetMb.toFloat()\n"
        "                                    videoTextValue = presetMb.toString()\n"
        "                                    videoInputError = false\n"
        "                                }\n"
        "                        ) {\n"
        "                            Box(\n"
        "                                contentAlignment = Alignment.Center,\n"
        "                                modifier = Modifier.padding(vertical = 6.dp)\n"
        "                            ) {\n"
        "                                Text(\n"
        "                                    text = if (presetMb >= 1024) \"${presetMb / 1024} GB\" else \"${presetMb} M\",\n"
        "                                    fontSize = 11.sp,\n"
        "                                    fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium,\n"
        "                                    color = if (isSelected) Color.White else PinterestBlack\n"
        "                                )\n"
        "                            }\n"
        "                        }\n"
        "                    }\n"
        "                }\n"
        "\n"
        + anchor_diag
    )
    t = t.replace(anchor_diag, video_section, 1)
    changed = True
    log("  ✓ video cache section inserted")

    # 5e. Extend confirmButton save to include video
    old_save = (
        "                onClick = {\n"
        "                    focusManager.clearFocus()\n"
        "                    val finalMb = textValue.toIntOrNull() ?: sliderValue.toInt()\n"
        "                    val clamped = finalMb.coerceIn(ImageCacheManager.MIN_CACHE_MB, ImageCacheManager.MAX_CACHE_MB)\n"
        "                    ImageCacheManager.setMaxDiskCacheMb(context, clamped)\n"
        "                    onCacheSizeSaved(clamped)\n"
        "\n"
        "                    onDismiss()\n"
        "                },\n"
    )
    new_save = (
        "                onClick = {\n"
        "                    focusManager.clearFocus()\n"
        "                    val finalMb = textValue.toIntOrNull() ?: sliderValue.toInt()\n"
        "                    val clamped = finalMb.coerceIn(ImageCacheManager.MIN_CACHE_MB, ImageCacheManager.MAX_CACHE_MB)\n"
        "                    ImageCacheManager.setMaxDiskCacheMb(context, clamped)\n"
        "                    val finalVideoMb = videoTextValue.toIntOrNull() ?: videoSliderValue.toInt()\n"
        "                    val videoClamped = finalVideoMb.coerceIn(\n"
        "                        com.example.util.VideoPlayerManager.MIN_VIDEO_CACHE_MB,\n"
        "                        com.example.util.VideoPlayerManager.MAX_VIDEO_CACHE_MB\n"
        "                    )\n"
        "                    com.example.util.VideoPlayerManager.setMaxVideoCacheMb(context, videoClamped)\n"
        "                    onCacheSizeSaved(clamped)\n"
        "\n"
        "                    onDismiss()\n"
        "                },\n"
    )
    if old_save in t:
        t = t.replace(old_save, new_save, 1)
        changed = True
        log("  ✓ confirmButton saves video limit")
    else:
        log("  ⚠ confirmButton anchor missing — saving video limit may not work")

    if changed:
        f.write_text(t, encoding="utf-8")


# ============================================================
# Verify
# ============================================================
def verify_all():
    log("\n=== VERIFY ===")

    vpm = PROJECT_ROOT / "app/src/main/java/com/example/util/VideoPlayerManager.kt"
    icm = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageCacheManager.kt"
    fsv = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/FullscreenGalleryViewer.kt"
    sd = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/SettingsDialog.kt"
    pa = PROJECT_ROOT / "app/src/main/java/com/example/PinBoardApplication.kt"
    cbe = PROJECT_ROOT / "app/src/main/java/com/example/util/CacheBudgetEnforcer.kt"

    for p in (vpm, icm, fsv, sd, pa):
        if not p.exists(): log(f"  ✗ missing: {p}"); sys.exit(1)

    checks = []

    checks.append(("CacheBudgetEnforcer.kt deleted", not cbe.exists()))

    vpm_t = vpm.read_text(encoding="utf-8")
    checks.append(("VideoPlayerManager correct import",
                   "import androidx.media3.exoplayer.upstream.DefaultLoadErrorHandlingPolicy" in vpm_t))
    checks.append(("VideoPlayerManager getMaxVideoCacheMb",
                   "fun getMaxVideoCacheMb(" in vpm_t))
    checks.append(("VideoPlayerManager setMaxVideoCacheMb",
                   "fun setMaxVideoCacheMb(" in vpm_t))
    checks.append(("VideoPlayerManager no enforcer calls",
                   "CacheBudgetEnforcer" not in vpm_t))
    checks.append(("VideoPlayerManager no getSimpleCacheForEviction",
                   "getSimpleCacheForEviction" not in vpm_t))

    pa_t = pa.read_text(encoding="utf-8")
    checks.append(("PinBoardApplication no enforcer init",
                   "CacheBudgetEnforcer" not in pa_t))

    icm_t = icm.read_text(encoding="utf-8")
    checks.append(("ImageCacheManager no video coupling in usage",
                   "VideoPlayerManager.getCacheSizeBytes" not in icm_t))
    checks.append(("ImageCacheManager no video clear",
                   "VideoPlayerManager.clearCache" not in icm_t))
    checks.append(("ImageCacheManager no invalidateCache",
                   "VideoPlayerManager.invalidateCache" not in icm_t))

    fsv_t = fsv.read_text(encoding="utf-8")
    checks.append(("Fullscreen has top-level overlay",
                   "// In-app video player overlay (top-level)" in fsv_t))
    checks.append(("Fullscreen overlay uses playingPin",
                   "val playingPin = playingVideoPinId?.let { id -> pins.firstOrNull { it.id == id } }" in fsv_t))
    checks.append(("Fullscreen no broken pin.isVideo&&playingVideoPinId",
                   "if (pin.isVideo && playingVideoPinId == pin.id)" not in fsv_t))
    checks.append(("Fullscreen Close import",
                   "import androidx.compose.material.icons.filled.Close" in fsv_t))

    sd_t = sd.read_text(encoding="utf-8")
    checks.append(("Settings video slider", "video_cache_size_slider" in sd_t))
    checks.append(("Settings video text input", "video_cache_size_text_input" in sd_t))
    checks.append(("Settings video clear button", "clear_video_cache_button" in sd_t))
    checks.append(("Settings video state",
                   "videoSliderValue" in sd_t and "currentVideoCacheUsageBytes" in sd_t))
    checks.append(("Settings saves video limit",
                   "VideoPlayerManager.setMaxVideoCacheMb" in sd_t))
    checks.append(("Settings PlayArrow import",
                   "import androidx.compose.material.icons.filled.PlayArrow" in sd_t))

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
            elif c == "/" and i + 1 < len(text) and text[i + 1] == "/":
                while i < len(text) and text[i] != "\n": i += 1
            elif c == "/" and i + 1 < len(text) and text[i + 1] == "*":
                i += 2
                while i + 1 < len(text):
                    if text[i] == "*" and text[i + 1] == "/":
                        i += 2; break
                    i += 1
            else:
                out.append(c); i += 1
        return "".join(out)

    for label, path in [("Manager", vpm), ("Fullscreen", fsv), ("Settings", sd), ("ICM", icm)]:
        s = strip(path.read_text(encoding="utf-8"))
        po, pc = s.count("("), s.count(")")
        bo, bc = s.count("{"), s.count("}")
        checks.append((f"{label} paren balance ({po}/{pc})", po == pc))
        checks.append((f"{label} brace balance ({bo}/{bc})", bo == bc))

    all_ok = True
    for name, ok in checks:
        log(f"  {'✓' if ok else '✗'} {name}")
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


def patch_build_gradle_keystore():
    log("\n=== build.gradle.kts (keystore) ===")
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
        x = x[:ob + 1] + nc + x[cb:]
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
             "Rollback unified cache; separate video limit + clear in settings; fix overlay scope"])


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
    log("PinBoard — separate video cache + clear in settings; fix overlay")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    rollback_cache_budget_enforcer()
    rewrite_video_player_manager()
    patch_image_cache_manager()
    fix_fullscreen_video_overlay()
    patch_settings_dialog()
    verify_all()

    ensure_release_keystore()
    patch_build_gradle_keystore()
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