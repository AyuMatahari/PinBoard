#!/usr/bin/env python3
"""
PinBoard Gallery — video format support
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
# NEW FILE: VideoThumbnailCache.kt
# ============================================================
NEW_VIDEO_THUMB_CACHE = r'''package com.example.util

import android.content.Context
import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import com.example.model.PinItem
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * Video thumbnail + lazy video download manager.
 *
 * - Thumbnail extraction: downloads only the first ~2 MB of the video (HTTP Range),
 *   then uses MediaMetadataRetriever to extract a single frame → saves as .jpg.
 * - Full video download: full fetch, only triggered when user taps the play button.
 *
 * All artifacts live under app cacheDir so they are cleaned by the OS
 * exactly like Coil's image cache.
 */
object VideoThumbnailCache {

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

    private const val PARTIAL_BYTES = 2L * 1024L * 1024L  // 2 MB

    fun thumbFile(context: Context, pinId: String): File {
        val dir = File(context.cacheDir, "video_thumbs").apply { mkdirs() }
        return File(dir, "$pinId.jpg")
    }

    fun videoFile(context: Context, pin: PinItem): File {
        val dir = File(context.cacheDir, "videos").apply { mkdirs() }
        val ext = extForMime(pin.videoMimeType.ifBlank {
            ImageMimeUtils.videoMimeFromUrl(pin.videoUrl ?: pin.imageUrl) ?: "video/mp4"
        })
        return File(dir, "${pin.id}.$ext")
    }

    /**
     * Extracts first-frame thumbnail from a video URL via bounded partial download.
     * Returns the cached JPEG file or null on failure.
     */
    suspend fun getOrExtract(context: Context, pin: PinItem): File? = withContext(Dispatchers.IO) {
        val existing = thumbFile(context, pin.id)
        if (existing.exists() && existing.length() > 0) return@withContext existing

        val videoUrl = pin.videoUrl ?: pin.imageUrl
        if (videoUrl.isBlank()) return@withContext null

        val partialDir = File(context.cacheDir, "video_partials").apply { mkdirs() }
        val partial = File(partialDir, "${pin.id}.part")
        try {
            val request = Request.Builder()
                .url(videoUrl)
                .header("User-Agent", "Mozilla/5.0 (Android; Mobile; rv:109.0)")
                .header("Range", "bytes=0-${PARTIAL_BYTES - 1}")
                .build()
            client.newCall(request).execute().use { resp ->
                if (!resp.isSuccessful && resp.code != 206) return@withContext null
                resp.body?.byteStream()?.use { input ->
                    partial.outputStream().use { out ->
                        val buf = ByteArray(64 * 1024)
                        var total = 0L
                        while (total < PARTIAL_BYTES) {
                            val n = input.read(buf)
                            if (n <= 0) break
                            out.write(buf, 0, n)
                            total += n
                        }
                    }
                } ?: return@withContext null
            }
            if (!partial.exists() || partial.length() == 0L) return@withContext null

            val retriever = MediaMetadataRetriever()
            try {
                retriever.setDataSource(partial.absolutePath)
                val bitmap: Bitmap? = retriever.getFrameAtTime(
                    0L, MediaMetadataRetriever.OPTION_CLOSEST_SYNC
                )
                if (bitmap == null) return@withContext null
                existing.outputStream().use { out ->
                    bitmap.compress(Bitmap.CompressFormat.JPEG, 85, out)
                }
                bitmap.recycle()
                return@withContext existing
            } finally {
                try { retriever.release() } catch (_: Throwable) {}
                partial.delete()
            }
        } catch (e: Exception) {
            android.util.Log.w("VideoThumbnailCache", "extract failed for ${pin.id}: ${e.message}")
            try { partial.delete() } catch (_: Throwable) {}
            return@withContext null
        }
    }

    /**
     * Full video download — triggered only when user taps Play.
     */
    suspend fun downloadVideo(context: Context, pin: PinItem): File? = withContext(Dispatchers.IO) {
        val file = videoFile(context, pin)
        if (file.exists() && file.length() > 0) return@withContext file
        val videoUrl = pin.videoUrl ?: pin.imageUrl
        if (videoUrl.isBlank()) return@withContext null
        try {
            val request = Request.Builder()
                .url(videoUrl)
                .header("User-Agent", "Mozilla/5.0 (Android; Mobile; rv:109.0)")
                .build()
            client.newCall(request).execute().use { resp ->
                if (!resp.isSuccessful || resp.body == null) return@withContext null
                resp.body!!.byteStream().use { input ->
                    file.outputStream().use { out -> input.copyTo(out) }
                }
            }
            return@withContext if (file.exists() && file.length() > 0) file else null
        } catch (e: Exception) {
            android.util.Log.w("VideoThumbnailCache", "video download failed: ${e.message}")
            try { file.delete() } catch (_: Throwable) {}
            return@withContext null
        }
    }

    private fun extForMime(mime: String): String = when {
        mime.contains("webm") -> "webm"
        mime.contains("quicktime") || mime.contains("mov") -> "mov"
        mime.contains("matroska") -> "mkv"
        mime.contains("avi") -> "avi"
        mime.contains("ogg") -> "ogv"
        mime.contains("3gpp") -> "3gp"
        mime.contains("mp2t") -> "ts"
        else -> "mp4"
    }
}
'''


def write_video_thumb_cache():
    log("\n=== PATCH: new VideoThumbnailCache.kt ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/VideoThumbnailCache.kt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(NEW_VIDEO_THUMB_CACHE, encoding="utf-8")
    log("  ✓ created")


# ============================================================
# PinItem — add video fields
# ============================================================
def patch_pin_item():
    log("\n=== PATCH: PinItem (video fields) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/model/PinItem.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "videoUrl: String?" in t:
        log("  ✓ already patched"); return

    old = (
        "    val isBrokenOrUnreachable: Boolean = false,\n"
        "    val albumId: String? = null\n"
        ") {\n"
    )
    new = (
        "    val isBrokenOrUnreachable: Boolean = false,\n"
        "    val albumId: String? = null,\n"
        "    // Video support\n"
        "    val videoUrl: String? = null,\n"
        "    val isVideo: Boolean = false,\n"
        "    val hasSeparateThumbnail: Boolean = false,\n"
        "    val videoMimeType: String = \"\"\n"
        ") {\n"
    )
    if old in t:
        t = t.replace(old, new, 1)
        f.write_text(t, encoding="utf-8")
        log("  ✓ video fields added")
    else:
        log("  ⚠ anchor missing"); sys.exit(1)


# ============================================================
# PinEntity — add columns + conversions
# ============================================================
def patch_pin_entity():
    log("\n=== PATCH: PinEntity (video columns) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/data/local/PinEntity.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "videoUrl: String?" in t:
        log("  ✓ already patched"); return

    old_fields = (
        "    val isBrokenOrUnreachable: Boolean = false,\n"
        "    val albumId: String? = null\n"
        ") {\n"
    )
    new_fields = (
        "    val isBrokenOrUnreachable: Boolean = false,\n"
        "    val albumId: String? = null,\n"
        "    val videoUrl: String? = null,\n"
        "    val isVideo: Boolean = false,\n"
        "    val hasSeparateThumbnail: Boolean = false,\n"
        "    val videoMimeType: String = \"\"\n"
        ") {\n"
    )
    if old_fields in t:
        t = t.replace(old_fields, new_fields, 1)
    else:
        log("  ⚠ fields anchor missing"); sys.exit(1)

    old_to = (
        "        isBrokenOrUnreachable = isBrokenOrUnreachable,\n"
        "        albumId = albumId\n"
        "    )\n"
    )
    new_to = (
        "        isBrokenOrUnreachable = isBrokenOrUnreachable,\n"
        "        albumId = albumId,\n"
        "        videoUrl = videoUrl,\n"
        "        isVideo = isVideo,\n"
        "        hasSeparateThumbnail = hasSeparateThumbnail,\n"
        "        videoMimeType = videoMimeType\n"
        "    )\n"
    )
    if old_to in t:
        t = t.replace(old_to, new_to, 1)
    else:
        log("  ⚠ toPinItem anchor missing")

    old_from = (
        "            isBrokenOrUnreachable = item.isBrokenOrUnreachable,\n"
        "            albumId = item.albumId\n"
        "        )\n"
    )
    new_from = (
        "            isBrokenOrUnreachable = item.isBrokenOrUnreachable,\n"
        "            albumId = item.albumId,\n"
        "            videoUrl = item.videoUrl,\n"
        "            isVideo = item.isVideo,\n"
        "            hasSeparateThumbnail = item.hasSeparateThumbnail,\n"
        "            videoMimeType = item.videoMimeType\n"
        "        )\n"
    )
    if old_from in t:
        t = t.replace(old_from, new_from, 1)
    else:
        log("  ⚠ fromPinItem anchor missing")

    f.write_text(t, encoding="utf-8")
    log("  ✓ PinEntity updated")


# ============================================================
# AppDatabase — migration v5→v6
# ============================================================
def patch_app_database():
    log("\n=== PATCH: AppDatabase (migration v5→v6) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/data/local/AppDatabase.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "migrateToVersion6" in t:
        log("  ✓ already patched"); return

    # Bump version
    t = t.replace("    version = 5,\n", "    version = 6,\n", 1)

    # Add migration function + migrations before getDatabase
    old_mig = (
        "        val MIGRATION_1_5 = object : androidx.room.migration.Migration(1, 5) {\n"
        "            override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) = migrateToVersion5(db)\n"
        "        }\n"
        "        val MIGRATION_2_5 = object : androidx.room.migration.Migration(2, 5) {\n"
        "            override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) = migrateToVersion5(db)\n"
        "        }\n"
        "        val MIGRATION_3_5 = object : androidx.room.migration.Migration(3, 5) {\n"
        "            override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) = migrateToVersion5(db)\n"
        "        }\n"
        "        val MIGRATION_4_5 = object : androidx.room.migration.Migration(4, 5) {\n"
        "            override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) = migrateToVersion5(db)\n"
        "        }\n"
    )
    new_mig = (
        "        private fun migrateToVersion6(db: androidx.sqlite.db.SupportSQLiteDatabase) {\n"
        "            // Ensure v5 schema exists first (idempotent)\n"
        "            migrateToVersion5(db)\n"
        "            // Add v6 columns, checking existing first (idempotent)\n"
        "            val existingCols = mutableSetOf<String>()\n"
        "            try {\n"
        "                val cursor = db.query(\"PRAGMA table_info(pins)\")\n"
        "                while (cursor.moveToNext()) existingCols.add(cursor.getString(1).lowercase())\n"
        "                cursor.close()\n"
        "            } catch (_: Throwable) {}\n"
        "            if (!existingCols.contains(\"videourl\")) {\n"
        "                try { db.execSQL(\"ALTER TABLE `pins` ADD COLUMN `videoUrl` TEXT DEFAULT NULL\") } catch (_: Throwable) {}\n"
        "            }\n"
        "            if (!existingCols.contains(\"isvideo\")) {\n"
        "                try { db.execSQL(\"ALTER TABLE `pins` ADD COLUMN `isVideo` INTEGER NOT NULL DEFAULT 0\") } catch (_: Throwable) {}\n"
        "            }\n"
        "            if (!existingCols.contains(\"hasseparatethumbnail\")) {\n"
        "                try { db.execSQL(\"ALTER TABLE `pins` ADD COLUMN `hasSeparateThumbnail` INTEGER NOT NULL DEFAULT 0\") } catch (_: Throwable) {}\n"
        "            }\n"
        "            if (!existingCols.contains(\"videomimetype\")) {\n"
        "                try { db.execSQL(\"ALTER TABLE `pins` ADD COLUMN `videoMimeType` TEXT NOT NULL DEFAULT ''\") } catch (_: Throwable) {}\n"
        "            }\n"
        "        }\n"
        "\n"
        "        val MIGRATION_1_6 = object : androidx.room.migration.Migration(1, 6) {\n"
        "            override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) = migrateToVersion6(db)\n"
        "        }\n"
        "        val MIGRATION_2_6 = object : androidx.room.migration.Migration(2, 6) {\n"
        "            override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) = migrateToVersion6(db)\n"
        "        }\n"
        "        val MIGRATION_3_6 = object : androidx.room.migration.Migration(3, 6) {\n"
        "            override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) = migrateToVersion6(db)\n"
        "        }\n"
        "        val MIGRATION_4_6 = object : androidx.room.migration.Migration(4, 6) {\n"
        "            override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) = migrateToVersion6(db)\n"
        "        }\n"
        "        val MIGRATION_5_6 = object : androidx.room.migration.Migration(5, 6) {\n"
        "            override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) = migrateToVersion6(db)\n"
        "        }\n"
    )
    if old_mig in t:
        t = t.replace(old_mig, new_mig, 1)
    else:
        log("  ⚠ migration anchor missing"); sys.exit(1)

    # Update .addMigrations
    t = t.replace(
        ".addMigrations(MIGRATION_1_5, MIGRATION_2_5, MIGRATION_3_5, MIGRATION_4_5)",
        ".addMigrations(MIGRATION_1_6, MIGRATION_2_6, MIGRATION_3_6, MIGRATION_4_6, MIGRATION_5_6)",
        1,
    )

    f.write_text(t, encoding="utf-8")
    log("  ✓ version 6 + migration")


# ============================================================
# ImageMimeUtils — video detection
# ============================================================
def patch_image_mime_utils_video():
    log("\n=== PATCH: ImageMimeUtils (video) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageMimeUtils.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "fun videoMimeFromUrl" in t:
        log("  ✓ already patched"); return

    # Add video extension map before the closing brace of the object
    anchor = (
        "    fun isAnimated(mime: String, url: String): Boolean {\n"
        "        if (mime.lowercase().contains(\"gif\")) return true\n"
        "        val lower = url.lowercase().substringBefore('?').substringBefore('#')\n"
        "        return lower.endsWith(\".gif\")\n"
        "    }\n"
    )
    new = (
        anchor +
        "\n"
        "    // ---------- Video support ----------\n"
        "\n"
        "    fun isVideoMime(mime: String): Boolean =\n"
        "        mime.lowercase().substringBefore(\";\").trim().startsWith(\"video/\")\n"
        "\n"
        "    fun isVideoUrl(url: String): Boolean = videoMimeFromUrl(url) != null\n"
        "\n"
        "    fun videoMimeFromUrl(url: String): String? {\n"
        "        if (url.isBlank()) return null\n"
        "        val lower = url.lowercase().substringBefore('?').substringBefore('#')\n"
        "        return when {\n"
        "            lower.endsWith(\".mp4\") -> \"video/mp4\"\n"
        "            lower.endsWith(\".m4v\") -> \"video/mp4\"\n"
        "            lower.endsWith(\".webm\") -> \"video/webm\"\n"
        "            lower.endsWith(\".mov\") -> \"video/quicktime\"\n"
        "            lower.endsWith(\".mkv\") -> \"video/x-matroska\"\n"
        "            lower.endsWith(\".avi\") -> \"video/x-msvideo\"\n"
        "            lower.endsWith(\".ogv\") -> \"video/ogg\"\n"
        "            lower.endsWith(\".3gp\") -> \"video/3gpp\"\n"
        "            lower.endsWith(\".flv\") -> \"video/x-flv\"\n"
        "            lower.endsWith(\".wmv\") -> \"video/x-ms-wmv\"\n"
        "            lower.endsWith(\".mpg\") || lower.endsWith(\".mpeg\") -> \"video/mpeg\"\n"
        "            lower.endsWith(\".ts\") -> \"video/mp2t\"\n"
        "            lower.contains(\".m3u8\") -> \"application/vnd.apple.mpegurl\"\n"
        "            else -> null\n"
        "        }\n"
        "    }\n"
    )
    if anchor in t:
        t = t.replace(anchor, new, 1)
    else:
        log("  ⚠ anchor missing"); sys.exit(1)

    # Extend sniffMimeFromBytes with video signatures — insert before "return null"
    old_sniff_tail = (
        "        // SVG (loose — starts with '<svg' or '<?xml')\n"
        "        if (length >= 4) {\n"
        "            val head = String(bytes, 0, minOf(length, 64), Charsets.US_ASCII).trimStart()\n"
        "            if (head.startsWith(\"<svg\", ignoreCase = true)) return \"image/svg+xml\"\n"
        "        }\n"
        "\n"
        "        return null\n"
    )
    new_sniff_tail = (
        "        // SVG (loose — starts with '<svg' or '<?xml')\n"
        "        if (length >= 4) {\n"
        "            val head = String(bytes, 0, minOf(length, 64), Charsets.US_ASCII).trimStart()\n"
        "            if (head.startsWith(\"<svg\", ignoreCase = true)) return \"image/svg+xml\"\n"
        "        }\n"
        "\n"
        "        // ---- Video containers ----\n"
        "        // MP4 / MOV / M4V / 3GP: bytes 4..7 == \"ftyp\", brand at 8..11\n"
        "        if (length >= 12 && b(4) == 0x66 && b(5) == 0x74 && b(6) == 0x79 && b(7) == 0x70) {\n"
        "            val brand = String(bytes, 8, 4, Charsets.US_ASCII)\n"
        "            when {\n"
        "                brand.startsWith(\"qt\") -> return \"video/quicktime\"\n"
        "                brand.startsWith(\"3gp\") || brand.startsWith(\"3gg\") -> return \"video/3gpp\"\n"
        "                brand.startsWith(\"avif\") || brand.startsWith(\"avis\") -> return \"image/avif\"\n"
        "                brand.startsWith(\"heic\") || brand.startsWith(\"heix\") || brand.startsWith(\"mif1\") -> return \"image/heic\"\n"
        "                brand.startsWith(\"M4A\") -> return \"audio/mp4\"\n"
        "                else -> return \"video/mp4\"\n"
        "            }\n"
        "        }\n"
        "        // WebM / Matroska: 1A 45 DF A3 (EBML)\n"
        "        if (length >= 4 && b(0) == 0x1A && b(1) == 0x45 && b(2) == 0xDF && b(3) == 0xA3) {\n"
        "            return \"video/webm\"\n"
        "        }\n"
        "        // AVI: \"RIFF\" .... \"AVI \"\n"
        "        if (length >= 12 && b(0) == 0x52 && b(1) == 0x49 && b(2) == 0x46 && b(3) == 0x46\n"
        "            && b(8) == 0x41 && b(9) == 0x56 && b(10) == 0x49 && b(11) == 0x20) {\n"
        "            return \"video/x-msvideo\"\n"
        "        }\n"
        "        // FLV: \"FLV\"\n"
        "        if (length >= 3 && b(0) == 0x46 && b(1) == 0x4C && b(2) == 0x56) {\n"
        "            return \"video/x-flv\"\n"
        "        }\n"
        "\n"
        "        return null\n"
    )
    if old_sniff_tail in t:
        t = t.replace(old_sniff_tail, new_sniff_tail, 1)
    else:
        log("  ⚠ sniff tail anchor missing")

    f.write_text(t, encoding="utf-8")
    log("  ✓ video detection added")


# ============================================================
# ImageLinkResolver — video detection in resolveLink
# ============================================================
def patch_image_link_resolver():
    log("\n=== PATCH: ImageLinkResolver (video) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageLinkResolver.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "extractMainVideo" in t:
        log("  ✓ already patched"); return

    # 1. Add extractMainVideo helper before extractTitleFromHtml
    anchor_helper = "    fun extractTitleFromHtml(html: String): String {\n"
    helper = '''    /**
     * Returns (videoUrl, videoMime) from og:video, <video src>, <source src>, twitter:player:stream.
     */
    fun extractMainVideo(html: String, baseUrl: String): Pair<String, String>? {
        META_TAG_REGEX.findAll(html).forEach { match ->
            val attrs = parseTagAttributes(match.value)
            val prop = (attrs["property"] ?: attrs["name"] ?: "").lowercase(Locale.ROOT).trim()
            val content = attrs["content"]?.trim() ?: ""
            if (content.isNotBlank() && prop in setOf(
                    "og:video", "og:video:url", "og:video:secure_url",
                    "twitter:player:stream"
                )) {
                val url = resolveAbsoluteUrl(baseUrl, content)
                val mime = when {
                    url.contains(".m3u8") -> "application/vnd.apple.mpegurl"
                    url.contains(".webm") -> "video/webm"
                    url.contains(".mov") -> "video/quicktime"
                    url.contains(".ogv") -> "video/ogg"
                    else -> "video/mp4"
                }
                return url to mime
            }
        }
        val videoSrcRegex = Regex("""<video\\b[^>]*\\bsrc=["']([^"']+)["']""", RegexOption.IGNORE_CASE)
        videoSrcRegex.find(html)?.let { m ->
            val url = resolveAbsoluteUrl(baseUrl, m.groupValues[1])
            val mime = when {
                url.contains(".m3u8") -> "application/vnd.apple.mpegurl"
                url.contains(".webm") -> "video/webm"
                url.contains(".mov") -> "video/quicktime"
                else -> "video/mp4"
            }
            return url to mime
        }
        val sourceRegex = Regex(
            """<source\\b[^>]*\\bsrc=["']([^"']+\\.(?:mp4|webm|m3u8|mov|ogv)(?:\\?[^"']*)?)["']""",
            RegexOption.IGNORE_CASE
        )
        sourceRegex.find(html)?.let { m ->
            val url = resolveAbsoluteUrl(baseUrl, m.groupValues[1])
            val mime = when {
                url.contains(".m3u8") -> "application/vnd.apple.mpegurl"
                url.contains(".webm") -> "video/webm"
                url.contains(".mov") -> "video/quicktime"
                url.contains(".ogv") -> "video/ogg"
                else -> "video/mp4"
            }
            return url to mime
        }
        return null
    }

    fun extractTitleFromHtml(html: String): String {
'''
    if anchor_helper in t:
        t = t.replace(anchor_helper, helper, 1)
    else:
        log("  ⚠ helper anchor missing"); sys.exit(1)

    # 2. In resolveLink, add video detection. Insert right before the "var finalImageUrl" line.
    old_setup = (
        "        var finalImageUrl = cleanUrl\n"
        "        var finalTitle = defaultTitle\n"
        "        var mimeType = guessMimeType(cleanUrl)\n"
        "        var fileSizeKb = 250L\n"
        "        var isBroken = false\n"
        "        var imageWidth = 1080\n"
        "        var imageHeight = 1350\n"
        "        val sourceWebpageUrl = cleanUrl\n"
    )
    new_setup = (
        "        var finalImageUrl = cleanUrl\n"
        "        var finalTitle = defaultTitle\n"
        "        var mimeType = guessMimeType(cleanUrl)\n"
        "        var fileSizeKb = 250L\n"
        "        var isBroken = false\n"
        "        var imageWidth = 1080\n"
        "        var imageHeight = 1920\n"
        "        val sourceWebpageUrl = cleanUrl\n"
        "        var detectedVideoUrl: String? = null\n"
        "        var detectedVideoMime: String = \"\"\n"
        "        var hasSeparateThumb: Boolean = false\n"
    )
    if old_setup in t:
        t = t.replace(old_setup, new_setup, 1)
    else:
        log("  ⚠ setup anchor missing"); sys.exit(1)

    # 3. Insert direct-video branch inside the try, right after the content-type read
    old_branch = (
        "                    val isDirectImage = contentType.startsWith(\"image/\")\n"
        "\n"
        "                    if (isDirectImage) {\n"
    )
    new_branch = (
        "                    val isDirectImage = contentType.startsWith(\"image/\")\n"
        "                    val isDirectVideo = contentType.startsWith(\"video/\") ||\n"
        "                        ImageMimeUtils.isVideoUrl(effectiveUrl)\n"
        "\n"
        "                    if (isDirectVideo) {\n"
        "                        detectedVideoUrl = effectiveUrl\n"
        "                        detectedVideoMime = contentType.substringBefore(\";\").ifBlank {\n"
        "                            ImageMimeUtils.videoMimeFromUrl(effectiveUrl) ?: \"video/mp4\"\n"
        "                        }\n"
        "                        finalImageUrl = effectiveUrl\n"
        "                        mimeType = \"\"\n"
        "                        hasSeparateThumb = false\n"
        "                    } else if (isDirectImage) {\n"
    )
    if old_branch in t:
        t = t.replace(old_branch, new_branch, 1)
    else:
        log("  ⚠ direct-branch anchor missing"); sys.exit(1)

    # 4. In the webpage branch, look for video too
    old_webpage = (
        "                        // Run browserless two-pass main image extractor\n"
        "                        val bestCandidate = extractMainImageTwoPass(htmlBody, effectiveUrl)\n"
    )
    new_webpage = (
        "                        // Look for video in the page\n"
        "                        val videoMatch = extractMainVideo(htmlBody, effectiveUrl)\n"
        "                        if (videoMatch != null) {\n"
        "                            detectedVideoUrl = videoMatch.first\n"
        "                            detectedVideoMime = videoMatch.second\n"
        "                            hasSeparateThumb = true\n"
        "                        }\n"
        "\n"
        "                        // Run browserless two-pass main image extractor\n"
        "                        val bestCandidate = extractMainImageTwoPass(htmlBody, effectiveUrl)\n"
    )
    if old_webpage in t:
        t = t.replace(old_webpage, new_webpage, 1)
    else:
        log("  ⚠ webpage anchor missing"); sys.exit(1)

    # 5. In final PinItem return, populate video fields + flip dimensions if video & no separate image
    old_return = (
        "        PinItem(\n"
        "            id = uniqueId,\n"
        "            title = finalTitle,\n"
        "            description = if (sourceWebpageUrl != finalImageUrl) \"Imported from $domain\" else \"\",\n"
        "            imageUrl = finalImageUrl,\n"
        "            thumbnailUrl = finalImageUrl,\n"
        "            author = domain.ifBlank { \"Web Source\" },\n"
        "            boardName = boardName,\n"
        "            sourceUrl = sourceWebpageUrl,\n"
        "            width = imageWidth,\n"
        "            height = imageHeight,\n"
        "            dominantColor = 0xFF2D2D2DL,\n"
        "            dateAddedMillis = System.currentTimeMillis(),\n"
        "            fileSizeKb = fileSizeKb,\n"
        "            mimeType = mimeType,\n"
        "            sourceDomain = domain,\n"
        "            isBrokenOrUnreachable = isBroken\n"
        "        )\n"
    )
    new_return = (
        "        val isVid = detectedVideoUrl != null\n"
        "        val imgForDisplay = if (isVid && !hasSeparateThumb) detectedVideoUrl!! else finalImageUrl\n"
        "        PinItem(\n"
        "            id = uniqueId,\n"
        "            title = finalTitle,\n"
        "            description = if (sourceWebpageUrl != imgForDisplay) \"Imported from $domain\" else \"\",\n"
        "            imageUrl = imgForDisplay,\n"
        "            thumbnailUrl = imgForDisplay,\n"
        "            author = domain.ifBlank { \"Web Source\" },\n"
        "            boardName = boardName,\n"
        "            sourceUrl = sourceWebpageUrl,\n"
        "            width = imageWidth,\n"
        "            height = imageHeight,\n"
        "            dominantColor = 0xFF2D2D2DL,\n"
        "            dateAddedMillis = System.currentTimeMillis(),\n"
        "            fileSizeKb = fileSizeKb,\n"
        "            mimeType = mimeType,\n"
        "            sourceDomain = domain,\n"
        "            isBrokenOrUnreachable = isBroken,\n"
        "            videoUrl = detectedVideoUrl,\n"
        "            isVideo = isVid,\n"
        "            hasSeparateThumbnail = hasSeparateThumb && isVid,\n"
        "            videoMimeType = detectedVideoMime\n"
        "        )\n"
    )
    if old_return in t:
        t = t.replace(old_return, new_return, 1)
    else:
        log("  ⚠ return anchor missing")

    f.write_text(t, encoding="utf-8")
    log("  ✓ resolveLink video-aware")


# ============================================================
# PinterestRepository — videos from Pinterest JSON
# ============================================================
def patch_pinterest_repository():
    log("\n=== PATCH: PinterestRepository (videos) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/data/PinterestRepository.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "videosObj" in t or "video_list" in t:
        log("  ✓ already patched"); return

    # In parsePinJsonObject, right before the final return, compute video
    old = (
        "        val saves = pObj.optInt(\"repin_count\", pObj.optInt(\"save_count\", 0))\n"
        "        val pLink = pObj.optString(\"link\", \"https://www.pinterest.com/pin/$pinId/\")\n"
        "        val pinAuthor = cleanSpecialText(extractOriginalUploader(pObj, ownerName.ifBlank { username }))\n"
        "        val pinDate = extractPinTimestamp(pObj, currentCount)\n"
        "\n"
        "        return PinItem(\n"
    )
    new = (
        "        val saves = pObj.optInt(\"repin_count\", pObj.optInt(\"save_count\", 0))\n"
        "        val pLink = pObj.optString(\"link\", \"https://www.pinterest.com/pin/$pinId/\")\n"
        "        val pinAuthor = cleanSpecialText(extractOriginalUploader(pObj, ownerName.ifBlank { username }))\n"
        "        val pinDate = extractPinTimestamp(pObj, currentCount)\n"
        "\n"
        "        // Pinterest video detection\n"
        "        var detectedVideoUrl: String? = null\n"
        "        var detectedVideoMime = \"\"\n"
        "        val videosObj = pObj.optJSONObject(\"videos\")\n"
        "        if (videosObj != null) {\n"
        "            val vlist = videosObj.optJSONObject(\"video_list\")\n"
        "            if (vlist != null) {\n"
        "                for (pref in listOf(\"V_720P\", \"V_540P\", \"V_HLSV4\", \"V_HLSV3_MOBILE\")) {\n"
        "                    val vu = vlist.optJSONObject(pref)?.optString(\"url\", \"\") ?: continue\n"
        "                    if (vu.isNotBlank()) {\n"
        "                        detectedVideoUrl = vu\n"
        "                        detectedVideoMime = if (vu.contains(\".m3u8\")) \"application/vnd.apple.mpegurl\" else \"video/mp4\"\n"
        "                        break\n"
        "                    }\n"
        "                }\n"
        "                if (detectedVideoUrl == null) {\n"
        "                    val vk = vlist.keys()\n"
        "                    while (vk.hasNext()) {\n"
        "                        val vu = vlist.optJSONObject(vk.next())?.optString(\"url\", \"\") ?: continue\n"
        "                        if (vu.isNotBlank()) {\n"
        "                            detectedVideoUrl = vu\n"
        "                            detectedVideoMime = if (vu.contains(\".m3u8\")) \"application/vnd.apple.mpegurl\" else \"video/mp4\"\n"
        "                            break\n"
        "                        }\n"
        "                    }\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "        val pinIsVideo = detectedVideoUrl != null\n"
        "        val thumbUrlForPin = if (pinIsVideo && highResUrl.isNotBlank()) highResUrl else highResUrl\n"
        "        val hasSeparateThumbForPin = pinIsVideo && highResUrl.isNotBlank()\n"
        "\n"
        "        return PinItem(\n"
    )
    if old in t:
        t = t.replace(old, new, 1)
    else:
        log("  ⚠ parsePinJsonObject prologue anchor missing"); sys.exit(1)

    # Update the PinItem constructor inside parsePinJsonObject
    old_construct = (
        "            imageUrl = highResUrl,\n"
        "            thumbnailUrl = thumbUrl,\n"
        "            author = pinAuthor,\n"
        "            boardName = boardTitle,\n"
        "            sourceUrl = pLink,\n"
        "            width = w,\n"
        "            height = h,\n"
        "            dateAddedMillis = pinDate,\n"
        "            savesCount = saves,\n"
        "            likesCount = (saves * 0.4).toInt().coerceAtLeast(0),\n"
        "            fileSizeKb = (200..1200).random().toLong(),\n"
        "            mimeType = com.example.util.ImageLinkResolver.guessMimeType(highResUrl),\n"
        "            boardPosition = currentCount\n"
        "        )\n"
    )
    new_construct = (
        "            imageUrl = thumbUrlForPin,\n"
        "            thumbnailUrl = thumbUrlForPin,\n"
        "            author = pinAuthor,\n"
        "            boardName = boardTitle,\n"
        "            sourceUrl = pLink,\n"
        "            width = w,\n"
        "            height = h,\n"
        "            dateAddedMillis = pinDate,\n"
        "            savesCount = saves,\n"
        "            likesCount = (saves * 0.4).toInt().coerceAtLeast(0),\n"
        "            fileSizeKb = (200..1200).random().toLong(),\n"
        "            mimeType = com.example.util.ImageLinkResolver.guessMimeType(highResUrl),\n"
        "            boardPosition = currentCount,\n"
        "            videoUrl = detectedVideoUrl,\n"
        "            isVideo = pinIsVideo,\n"
        "            hasSeparateThumbnail = hasSeparateThumbForPin,\n"
        "            videoMimeType = detectedVideoMime\n"
        "        )\n"
    )
    if old_construct in t:
        t = t.replace(old_construct, new_construct, 1)
    else:
        log("  ⚠ construct anchor missing")

    f.write_text(t, encoding="utf-8")
    log("  ✓ Pinterest videos handled")


# ============================================================
# PinCard — play icon + smart thumbnail
# ============================================================
def patch_pin_card():
    log("\n=== PATCH: PinCard (video) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/PinCard.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "pin.isVideo" in t and "VideoThumbnailCache" in t:
        log("  ✓ already patched"); return

    # Add imports
    for imp, after in [
        ("import androidx.compose.material.icons.filled.PlayArrow\n",
         "import androidx.compose.material.icons.filled.Favorite\n"),
        ("import androidx.compose.runtime.LaunchedEffect\n",
         "import androidx.compose.runtime.Composable\n"),
        ("import androidx.compose.runtime.mutableStateOf\n",
         "import androidx.compose.runtime.remember\n"),
        ("import androidx.compose.runtime.getValue\n",
         "import androidx.compose.runtime.Composable\n"),
        ("import androidx.compose.runtime.setValue\n",
         "import androidx.compose.runtime.Composable\n"),
    ]:
        if imp not in t and after in t:
            t = t.replace(after, after + imp, 1)

    # Insert video state before the Box container
    anchor_state = (
        "        // Image Container with safe aspect ratio\n"
    )
    insert_state = (
        "        // Video thumbnail state\n"
        "        var extractedVideoThumb by remember(pin.id) { mutableStateOf<java.io.File?>(null) }\n"
        "        var videoThumbFailed by remember(pin.id) { mutableStateOf(false) }\n"
        "        LaunchedEffect(pin.id, pin.isVideo, pin.hasSeparateThumbnail) {\n"
        "            if (pin.isVideo && !pin.hasSeparateThumbnail && extractedVideoThumb == null && !videoThumbFailed) {\n"
        "                val f = com.example.util.VideoThumbnailCache.getOrExtract(context, pin)\n"
        "                if (f == null) videoThumbFailed = true else extractedVideoThumb = f\n"
        "            }\n"
        "        }\n"
        "\n"
        "        // Choose effective image model\n"
        "        val effectiveImageModel: Any? = when {\n"
        "            pin.isVideo && pin.hasSeparateThumbnail -> pin.thumbnailUrl.ifBlank { pin.imageUrl }\n"
        "            pin.isVideo -> extractedVideoThumb\n"
        "            else -> {\n"
        "                val isG = com.example.util.ImageMimeUtils.isAnimated(pin.mimeType, pin.imageUrl)\n"
        "                if (isG) pin.imageUrl.ifBlank { pin.thumbnailUrl } else pin.thumbnailUrl.ifBlank { pin.imageUrl }\n"
        "            }\n"
        "        }\n"
        "\n"
        "        // Image Container with safe aspect ratio\n"
    )
    if anchor_state in t:
        t = t.replace(anchor_state, insert_state, 1)
    else:
        log("  ⚠ state anchor missing"); sys.exit(1)

    # Replace AsyncImage model
    old_async_start = (
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
    new_async_start = (
        "            if (effectiveImageModel != null) {\n"
        "            AsyncImage(\n"
        "                model = ImageRequest.Builder(context)\n"
        "                    .data(effectiveImageModel)\n"
        "                    .apply {\n"
        "                        if (refreshCounter > 0) {\n"
        "                            memoryCacheKey(\"pin-thumb:${pin.id}:r$refreshCounter\")\n"
        "                            diskCacheKey(\"pin-thumb:${pin.id}:r$refreshCounter\")\n"
        "                        }\n"
        "                    }\n"
        "                    .crossfade(true)\n"
        "                    .build(),\n"
    )
    if old_async_start in t:
        t = t.replace(old_async_start, new_async_start, 1)
    else:
        log("  ⚠ async anchor missing")

    # Close the if() {} after the AsyncImage — find its trailing `)
    # The AsyncImage block ends with `            )` after `.clip(cardShape)` modifier
    old_async_end = (
        "                modifier = Modifier\n"
        "                    .matchParentSize()\n"
        "                    .clip(cardShape)\n"
        "            )\n"
    )
    new_async_end = (
        "                modifier = Modifier\n"
        "                    .matchParentSize()\n"
        "                    .clip(cardShape)\n"
        "            )\n"
        "            } else {\n"
        "                // Video without thumbnail — placeholder\n"
        "                Box(\n"
        "                    modifier = Modifier\n"
        "                        .matchParentSize()\n"
        "                        .background(PinterestPillGray),\n"
        "                    contentAlignment = Alignment.Center\n"
        "                ) {\n"
        "                    Icon(\n"
        "                        imageVector = Icons.Default.PlayArrow,\n"
        "                        contentDescription = \"Video\",\n"
        "                        tint = PinterestTextSecondary,\n"
        "                        modifier = Modifier.size(36.dp)\n"
        "                    )\n"
        "                }\n"
        "            }\n"
    )
    if old_async_end in t:
        t = t.replace(old_async_end, new_async_end, 1)
    else:
        log("  ⚠ async end anchor missing")

    # Insert play icon overlay — before the existing "// Selection indicator badge"
    old_overlay = (
        "            // Selection indicator badge\n"
        "            if (isSelectionMode) {\n"
    )
    new_overlay = (
        "            // Video play icon (top-left, masonry indicator, not a button)\n"
        "            if (pin.isVideo && !isSelectionMode) {\n"
        "                Box(\n"
        "                    modifier = Modifier\n"
        "                        .align(Alignment.TopStart)\n"
        "                        .padding(6.dp)\n"
        "                        .size(28.dp)\n"
        "                        .clip(CircleShape)\n"
        "                        .background(Color.Black.copy(alpha = 0.55f))\n"
        "                        .border(1.5.dp, Color.White, CircleShape)\n"
        "                        .testTag(\"pin_video_badge_${pin.id}\"),\n"
        "                    contentAlignment = Alignment.Center\n"
        "                ) {\n"
        "                    Icon(\n"
        "                        imageVector = Icons.Default.PlayArrow,\n"
        "                        contentDescription = \"Video\",\n"
        "                        tint = Color.White,\n"
        "                        modifier = Modifier.size(15.dp)\n"
        "                    )\n"
        "                }\n"
        "            }\n"
        "\n"
        "            // Selection indicator badge\n"
        "            if (isSelectionMode) {\n"
    )
    if old_overlay in t:
        t = t.replace(old_overlay, new_overlay, 1)
    else:
        log("  ⚠ overlay anchor missing")

    # Remove old isAnimatedGif/cardImageUrl declarations if still present (replaced by effectiveImageModel)
    if "val isAnimatedGif = com.example.util.ImageMimeUtils.isAnimated" in t:
        t = re.sub(
            r'\n\s*val isAnimatedGif = com\.example\.util\.ImageMimeUtils\.isAnimated\(pin\.mimeType, pin\.imageUrl\)\n'
            r'\s*val cardImageUrl = [^\n]*\n'
            r'\s*if \(isAnimatedGif\)[^\n]*\n',
            '\n', t, count=1,
        )
        # Also remove the multi-line variant if present
        t = re.sub(
            r'\n\s*val isAnimatedGif = com\.example\.util\.ImageMimeUtils\.isAnimated\(pin\.mimeType, pin\.imageUrl\)\n'
            r'\s*val cardImageUrl = if \(isAnimatedGif\)[\s\S]*?else pin\.thumbnailUrl\.ifBlank \{ pin\.imageUrl \}\n',
            '\n', t, count=1,
        )

    f.write_text(t, encoding="utf-8")
    log("  ✓ PinCard video-aware")


# ============================================================
# FullscreenGalleryViewer — play button + no autoplay
# ============================================================
def patch_fullscreen():
    log("\n=== PATCH: FullscreenGalleryViewer (video) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/FullscreenGalleryViewer.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "onPlayVideo" in t and "pin.isVideo" in t:
        log("  ✓ already patched"); return

    # Add PlayArrow import if missing
    if "import androidx.compose.material.icons.filled.PlayArrow" not in t:
        if "import androidx.compose.material.icons.filled.Download" in t:
            t = t.replace(
                "import androidx.compose.material.icons.filled.Download\n",
                "import androidx.compose.material.icons.filled.Download\n"
                "import androidx.compose.material.icons.filled.PlayArrow\n",
                1,
            )

    # Add onPlayVideo parameter after onDownloadSingle
    old_sig = (
        "    onDownloadSingle: (PinItem) -> Unit,\n"
        "    disableArrowNavigation: Boolean = false,\n"
    )
    new_sig = (
        "    onDownloadSingle: (PinItem) -> Unit,\n"
        "    onPlayVideo: (PinItem) -> Unit = {},\n"
        "    disableArrowNavigation: Boolean = false,\n"
    )
    if old_sig in t:
        t = t.replace(old_sig, new_sig, 1)
        log("  ✓ onPlayVideo param")
    else:
        log("  ⚠ sig anchor missing")

    # Add video state before AsyncImage inside page
    old_page = (
        "            Box(\n"
        "                modifier = Modifier\n"
        "                    .fillMaxSize()\n"
        "                    .pointerInput(actualPinIndex) {\n"
        "                        detectTapGestures(\n"
    )
    new_page = (
        "            // Video thumbnail state\n"
        "            var extractedVideoThumb by remember(pin.id) { mutableStateOf<java.io.File?>(null) }\n"
        "            var videoThumbFailed by remember(pin.id) { mutableStateOf(false) }\n"
        "            LaunchedEffect(pin.id, pin.isVideo, pin.hasSeparateThumbnail) {\n"
        "                if (pin.isVideo && !pin.hasSeparateThumbnail && extractedVideoThumb == null && !videoThumbFailed) {\n"
        "                    val vf = com.example.util.VideoThumbnailCache.getOrExtract(context, pin)\n"
        "                    if (vf == null) videoThumbFailed = true else extractedVideoThumb = vf\n"
        "                }\n"
        "            }\n"
        "            val effectiveModel: Any? = when {\n"
        "                pin.isVideo && pin.hasSeparateThumbnail -> pin.thumbnailUrl.ifBlank { pin.imageUrl }\n"
        "                pin.isVideo -> extractedVideoThumb\n"
        "                else -> pin.imageUrl\n"
        "            }\n"
        "\n"
        "            Box(\n"
        "                modifier = Modifier\n"
        "                    .fillMaxSize()\n"
        "                    .pointerInput(actualPinIndex) {\n"
        "                        detectTapGestures(\n"
    )
    if old_page in t:
        t = t.replace(old_page, new_page, 1)
    else:
        log("  ⚠ page anchor missing")

    # Replace the AsyncImage model to use effectiveModel
    old_async = (
        "                val pageRefreshKey = refreshCounters[pin.id] ?: 0\n"
        "                AsyncImage(\n"
        "                    model = ImageRequest.Builder(context)\n"
        "                        .data(pin.imageUrl)\n"
    )
    new_async = (
        "                val pageRefreshKey = refreshCounters[pin.id] ?: 0\n"
        "                if (effectiveModel != null) {\n"
        "                AsyncImage(\n"
        "                    model = ImageRequest.Builder(context)\n"
        "                        .data(effectiveModel)\n"
    )
    if old_async in t:
        t = t.replace(old_async, new_async, 1)
    else:
        log("  ⚠ async anchor missing")

    # Find AsyncImage closing and add else + play button overlay after
    old_async_end = (
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
        "                )\n"
        "            }\n"
    )
    new_async_end = (
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
        "                )\n"
        "                } else if (pin.isVideo) {\n"
        "                    androidx.compose.foundation.layout.Box(\n"
        "                        modifier = Modifier.fillMaxSize(),\n"
        "                        contentAlignment = Alignment.Center\n"
        "                    ) {\n"
        "                        Text(\n"
        "                            text = \"Preparing video preview…\",\n"
        "                            color = Color.White,\n"
        "                            fontSize = 13.sp\n"
        "                        )\n"
        "                    }\n"
        "                }\n"
        "\n"
        "                // Centered play button — no autoplay\n"
        "                if (pin.isVideo) {\n"
        "                    androidx.compose.foundation.layout.Box(\n"
        "                        modifier = Modifier\n"
        "                            .align(Alignment.Center)\n"
        "                            .size(96.dp),\n"
        "                        contentAlignment = Alignment.Center\n"
        "                    ) {\n"
        "                        Surface(\n"
        "                            shape = CircleShape,\n"
        "                            color = Color.Black.copy(alpha = 0.6f),\n"
        "                            modifier = Modifier\n"
        "                                .fillMaxSize()\n"
        "                                .clickable { onPlayVideo(pin) }\n"
        "                                .testTag(\"fullscreen_play_video_${pin.id}\")\n"
        "                        ) {\n"
        "                            androidx.compose.foundation.layout.Box(contentAlignment = Alignment.Center) {\n"
        "                                Icon(\n"
        "                                    imageVector = Icons.Default.PlayArrow,\n"
        "                                    contentDescription = \"Play video\",\n"
        "                                    tint = Color.White,\n"
        "                                    modifier = Modifier.size(56.dp)\n"
        "                                )\n"
        "                            }\n"
        "                        }\n"
        "                    }\n"
        "                }\n"
        "            }\n"
    )
    if old_async_end in t:
        t = t.replace(old_async_end, new_async_end, 1)
        log("  ✓ play button overlay added")
    else:
        log("  ⚠ async end anchor missing")

    f.write_text(t, encoding="utf-8")
    log("  ✓ FullscreenGalleryViewer video-aware")


# ============================================================
# ViewModel — playVideo
# ============================================================
def patch_viewmodel():
    log("\n=== PATCH: ViewModel (playVideo) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "fun playVideo(" in t:
        log("  ✓ already patched"); return

    anchor = "    fun downloadSingle(context: Context, pin: PinItem) {\n"
    method = (
        "    fun playVideo(context: Context, pin: PinItem) {\n"
        "        if (!pin.isVideo) return\n"
        "        viewModelScope.launch {\n"
        "            _snackbarMessage.value = \"Downloading video...\"\n"
        "            val file = com.example.util.VideoThumbnailCache.downloadVideo(context, pin)\n"
        "            if (file == null) {\n"
        "                _snackbarMessage.value = \"Failed to download video\"\n"
        "                return@launch\n"
        "            }\n"
        "            try {\n"
        "                val uri = androidx.core.content.FileProvider.getUriForFile(\n"
        "                    context,\n"
        "                    \"${context.packageName}.fileprovider\",\n"
        "                    file\n"
        "                )\n"
        "                val mime = pin.videoMimeType.ifBlank {\n"
        "                    com.example.util.ImageMimeUtils.videoMimeFromUrl(pin.videoUrl ?: pin.imageUrl)\n"
        "                        ?: \"video/*\"\n"
        "                }\n"
        "                val intent = android.content.Intent(android.content.Intent.ACTION_VIEW).apply {\n"
        "                    setDataAndType(uri, mime)\n"
        "                    addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)\n"
        "                    addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)\n"
        "                }\n"
        "                context.startActivity(android.content.Intent.createChooser(intent, \"Play video\"))\n"
        "                _snackbarMessage.value = null\n"
        "            } catch (e: Exception) {\n"
        "                _snackbarMessage.value = \"No app installed to play this video\"\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "\n"
    )
    if anchor in t:
        t = t.replace(anchor, method + anchor, 1)
        f.write_text(t, encoding="utf-8")
        log("  ✓ playVideo added")
    else:
        log("  ⚠ anchor missing")


# ============================================================
# PinBoardGalleryScreen — wire onPlayVideo
# ============================================================
def patch_gallery_screen():
    log("\n=== PATCH: PinBoardGalleryScreen (onPlayVideo) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "onPlayVideo = { p -> viewModel.playVideo(context, p) }" in t:
        log("  ✓ already patched"); return

    anchor = "                    onDownloadSingle = { pin -> viewModel.downloadSingle(context, pin) }\n"
    if anchor in t:
        t = t.replace(
            anchor,
            anchor + "                    onPlayVideo = { p -> viewModel.playVideo(context, p) }\n",
            1,
        )
        f.write_text(t, encoding="utf-8")
        log("  ✓ wired")
    else:
        # Fallback: paren-balanced insertion at the FullscreenGalleryViewer call
        idx = t.find("FullscreenGalleryViewer(")
        if idx < 0:
            log("  ⚠ FullscreenGalleryViewer not found"); return
        depth = 0
        i = t.find("(", idx)
        while i < len(t):
            if t[i] == "(": depth += 1
            elif t[i] == ")":
                depth -= 1
                if depth == 0:
                    t = t[:i] + "                    onPlayVideo = { p -> viewModel.playVideo(context, p) },\n" + t[i:]
                    f.write_text(t, encoding="utf-8")
                    log("  ✓ wired (fallback)")
                    return
            i += 1


# ============================================================
# Downloader — video download
# ============================================================
def patch_downloader():
    log("\n=== PATCH: Downloader (video) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/Downloader.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "downloadVideoInternal" in t:
        log("  ✓ already patched"); return

    # Insert isVideo branch at start of downloadSinglePinInternal
    old_start = (
        "    private fun downloadSinglePinInternal(context: Context, pin: PinItem): Boolean {\n"
        "        try {\n"
        "            val candidateUrls = listOf(pin.imageUrl, pin.thumbnailUrl).filter { it.isNotBlank() }.distinct()\n"
    )
    new_start = (
        "    private fun downloadSinglePinInternal(context: Context, pin: PinItem): Boolean {\n"
        "        if (pin.isVideo) return downloadVideoInternal(context, pin)\n"
        "        try {\n"
        "            val candidateUrls = listOf(pin.imageUrl, pin.thumbnailUrl).filter { it.isNotBlank() }.distinct()\n"
    )
    if old_start in t:
        t = t.replace(old_start, new_start, 1)
    else:
        log("  ⚠ start anchor missing"); sys.exit(1)

    # Append downloadVideoInternal before the closing brace of the object
    # Find the last closing brace of `object Downloader` — safe anchor is the final "}\n" at end of file
    # Safer: insert before "    }\n}" at the very end
    anchor_end = t.rfind("\n}\n")
    if anchor_end < 0:
        anchor_end = t.rfind("\n}")
    if anchor_end < 0:
        log("  ⚠ end anchor missing"); sys.exit(1)

    method = (
        "\n"
        "    private fun downloadVideoInternal(context: Context, pin: PinItem): Boolean {\n"
        "        try {\n"
        "            val videoUrl = pin.videoUrl ?: pin.imageUrl\n"
        "            if (videoUrl.isBlank()) return false\n"
        "            val mime = pin.videoMimeType.ifBlank {\n"
        "                ImageMimeUtils.videoMimeFromUrl(videoUrl) ?: \"video/mp4\"\n"
        "            }\n"
        "            val ext = when {\n"
        "                mime.contains(\"webm\") -> \"webm\"\n"
        "                mime.contains(\"quicktime\") || mime.contains(\"mov\") -> \"mov\"\n"
        "                mime.contains(\"matroska\") -> \"mkv\"\n"
        "                mime.contains(\"avi\") -> \"avi\"\n"
        "                mime.contains(\"ogg\") -> \"ogv\"\n"
        "                mime.contains(\"3gpp\") -> \"3gp\"\n"
        "                mime.contains(\"mp2t\") || videoUrl.contains(\".ts\") -> \"ts\"\n"
        "                else -> \"mp4\"\n"
        "            }\n"
        "            val sanitizedTitle = pin.title.take(30)\n"
        "                .replace(Regex(\"[^a-zA-Z0-9_-]\"), \"_\")\n"
        "                .trim('_')\n"
        "                .ifBlank { \"video\" }\n"
        "            val fileName = \"Pinterest_${sanitizedTitle}_${pin.id}.$ext\"\n"
        "            val request = Request.Builder()\n"
        "                .url(videoUrl)\n"
        "                .header(\"User-Agent\", \"Mozilla/5.0 (Android; Mobile; rv:109.0)\")\n"
        "                .build()\n"
        "            val response = client.newCall(request).execute()\n"
        "            if (!response.isSuccessful || response.body == null) return false\n"
        "            val input = response.body!!.byteStream()\n"
        "            return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {\n"
        "                val values = ContentValues().apply {\n"
        "                    put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)\n"
        "                    put(MediaStore.MediaColumns.MIME_TYPE, mime)\n"
        "                    put(MediaStore.MediaColumns.RELATIVE_PATH,\n"
        "                        \"${Environment.DIRECTORY_DOWNLOADS}/$FOLDER_NAME\")\n"
        "                    put(MediaStore.MediaColumns.IS_PENDING, 1)\n"
        "                }\n"
        "                val resolver = context.contentResolver\n"
        "                val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)\n"
        "                    ?: resolver.insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, values)\n"
        "                if (uri != null) {\n"
        "                    resolver.openOutputStream(uri)?.use { out: OutputStream -> input.copyTo(out) }\n"
        "                    values.clear()\n"
        "                    values.put(MediaStore.MediaColumns.IS_PENDING, 0)\n"
        "                    resolver.update(uri, values, null, null)\n"
        "                    true\n"
        "                } else false\n"
        "            } else {\n"
        "                val downloadsDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)\n"
        "                val targetDir = File(downloadsDir, FOLDER_NAME)\n"
        "                if (!targetDir.exists()) targetDir.mkdirs()\n"
        "                val outputFile = File(targetDir, fileName)\n"
        "                FileOutputStream(outputFile).use { out -> input.copyTo(out) }\n"
        "                MediaScannerConnection.scanFile(context,\n"
        "                    arrayOf(outputFile.absolutePath), arrayOf(mime), null)\n"
        "                true\n"
        "            }\n"
        "        } catch (e: Exception) {\n"
        "            e.printStackTrace()\n"
        "            return false\n"
        "        }\n"
        "    }\n"
    )
    t = t[:anchor_end] + method + t[anchor_end:]
    f.write_text(t, encoding="utf-8")
    log("  ✓ video download added")


# ============================================================
# file_paths.xml — video paths
# ============================================================
def patch_file_paths():
    log("\n=== PATCH: file_paths.xml ===")
    f = PROJECT_ROOT / "app/src/main/res/xml/file_paths.xml"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if 'name="videos"' in t:
        log("  ✓ already patched"); return

    old = (
        '<paths xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '    <cache-path name="shared_images" path="shared_images/" />\n'
        '</paths>\n'
    )
    new = (
        '<paths xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '    <cache-path name="shared_images" path="shared_images/" />\n'
        '    <cache-path name="videos" path="videos/" />\n'
        '    <cache-path name="video_thumbs" path="video_thumbs/" />\n'
        '    <cache-path name="video_partials" path="video_partials/" />\n'
        '</paths>\n'
    )
    if old in t:
        t = t.replace(old, new, 1)
        f.write_text(t, encoding="utf-8")
        log("  ✓ video cache paths added")
    else:
        log("  ⚠ anchor missing")


# ============================================================
# Verify
# ============================================================
def verify_all():
    log("\n=== VERIFY ===")
    checks = []

    vtc = PROJECT_ROOT / "app/src/main/java/com/example/util/VideoThumbnailCache.kt"
    pi = PROJECT_ROOT / "app/src/main/java/com/example/model/PinItem.kt"
    pe = PROJECT_ROOT / "app/src/main/java/com/example/data/local/PinEntity.kt"
    db = PROJECT_ROOT / "app/src/main/java/com/example/data/local/AppDatabase.kt"
    imu = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageMimeUtils.kt"
    ilr = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageLinkResolver.kt"
    pr = PROJECT_ROOT / "app/src/main/java/com/example/data/PinterestRepository.kt"
    pc = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/PinCard.kt"
    fs = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/FullscreenGalleryViewer.kt"
    vm = PROJECT_ROOT / "app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt"
    ps = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    dl = PROJECT_ROOT / "app/src/main/java/com/example/util/Downloader.kt"
    fp = PROJECT_ROOT / "app/src/main/res/xml/file_paths.xml"

    for p in (vtc, pi, pe, db, imu, ilr, pr, pc, fs, vm, ps, dl, fp):
        if not p.exists():
            log(f"  ✗ missing: {p}"); sys.exit(1)

    for name, p, markers in [
        ("VideoThumbnailCache.kt", vtc, [
            "object VideoThumbnailCache",
            "getOrExtract",
            "downloadVideo",
            "MediaMetadataRetriever",
        ]),
        ("PinItem video fields", pi, [
            "videoUrl: String?",
            "isVideo: Boolean",
            "hasSeparateThumbnail: Boolean",
            "videoMimeType: String",
        ]),
        ("PinEntity video fields", pe, [
            "videoUrl: String?",
            "isVideo: Boolean",
            "hasSeparateThumbnail: Boolean",
            "videoMimeType: String",
        ]),
        ("AppDatabase v6", db, [
            "version = 6",
            "migrateToVersion6",
            "MIGRATION_5_6",
        ]),
        ("ImageMimeUtils video", imu, [
            "fun isVideoMime",
            "fun videoMimeFromUrl",
            "video/webm",
            "video/mp4",
        ]),
        ("ImageLinkResolver video", ilr, [
            "extractMainVideo",
            "detectedVideoUrl",
            "isVideo = isVid",
        ]),
        ("PinterestRepository videos", pr, [
            "videosObj",
            "video_list",
            "isVideo = pinIsVideo",
        ]),
        ("PinCard video", pc, [
            "pin.isVideo",
            "VideoThumbnailCache.getOrExtract",
            "pin_video_badge_",
            "PlayArrow",
        ]),
        ("FullscreenGalleryViewer video", fs, [
            "onPlayVideo",
            "fullscreen_play_video_",
            "pin.isVideo",
        ]),
        ("ViewModel playVideo", vm, [
            "fun playVideo(",
            "VideoThumbnailCache.downloadVideo",
            "ACTION_VIEW",
        ]),
        ("GalleryScreen wiring", ps, [
            "onPlayVideo = { p -> viewModel.playVideo(context, p) }",
        ]),
        ("Downloader video", dl, [
            "downloadVideoInternal",
            "pin.isVideo",
        ]),
        ("file_paths.xml videos", fp, [
            'name="videos"',
            'name="video_thumbs"',
        ]),
    ]:
        content = p.read_text(encoding="utf-8")
        local_ok = True
        for m in markers:
            if m not in content:
                log(f"  ✗ {name}: MISSING {m[:60]}")
                local_ok = False
        if local_ok:
            log(f"  ✓ {name}")
        else:
            checks.append((name, False))

    if checks:
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
        run(["git", "commit", "-m", "Video support: detection, thumb extraction, player, lazy download"])


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
    log("PinBoard — video format support")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    write_video_thumb_cache()
    patch_pin_item()
    patch_pin_entity()
    patch_app_database()
    patch_image_mime_utils_video()
    patch_image_link_resolver()
    patch_pinterest_repository()
    patch_pin_card()
    patch_fullscreen()
    patch_viewmodel()
    patch_gallery_screen()
    patch_downloader()
    patch_file_paths()
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