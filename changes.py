#!/usr/bin/env python3
"""
PinBoard Gallery — fix coil.decode package + magic-byte sniff fallback
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
# NEW ImageMimeUtils.kt (with magic-byte sniff)
# ============================================================
NEW_IMAGE_MIME_UTILS = r'''package com.example.util

/**
 * MIME / extension resolution with magic-byte fallback.
 *
 * Priority (highest → lowest):
 *   1. Magic-byte sniff       (ground truth — actual image bytes)
 *   2. HTTP Content-Type      (server's claim)
 *   3. pin.mimeType           (cached, if not default)
 *   4. URL extension
 *   5. "image/jpeg"           (final fallback)
 */
object ImageMimeUtils {

    fun resolveMime(
        pinMime: String,
        imageUrl: String,
        contentTypeHeader: String? = null,
        sampleBytes: ByteArray? = null,
        sampleLength: Int = 0
    ): String {
        // 1. Magic bytes
        if (sampleBytes != null && sampleLength > 0) {
            sniffMimeFromBytes(sampleBytes, sampleLength)?.let { return it }
        }
        // 2. Content-Type header
        if (!contentTypeHeader.isNullOrBlank()) {
            val ct = contentTypeHeader.substringBefore(";").trim().lowercase()
            if (ct.startsWith("image/")) return ct
        }
        // 3. pin.mimeType
        val pm = pinMime.lowercase().substringBefore(";").trim()
        if (pm.startsWith("image/") && pm != "image/jpeg") return pm
        // 4. URL
        mimeFromUrl(imageUrl)?.let { return it }
        // 5. jpg fallback
        return "image/jpeg"
    }

    fun sniffMimeFromBytes(bytes: ByteArray, length: Int): String? {
        if (length < 2) return null
        fun b(i: Int): Int = bytes[i].toInt() and 0xFF

        // JPEG: FF D8 FF
        if (length >= 3 && b(0) == 0xFF && b(1) == 0xD8 && b(2) == 0xFF) return "image/jpeg"

        // PNG: 89 50 4E 47 0D 0A 1A 0A
        if (length >= 8 && b(0) == 0x89 && b(1) == 0x50 && b(2) == 0x4E && b(3) == 0x47
            && b(4) == 0x0D && b(5) == 0x0A && b(6) == 0x1A && b(7) == 0x0A) return "image/png"

        // GIF: 'GIF8' (GIF87a / GIF89a)
        if (length >= 4 && b(0) == 0x47 && b(1) == 0x49 && b(2) == 0x46 && b(3) == 0x38) return "image/gif"

        // WebP: 'RIFF' ..... 'WEBP'
        if (length >= 12 && b(0) == 0x52 && b(1) == 0x49 && b(2) == 0x46 && b(3) == 0x46
            && b(8) == 0x57 && b(9) == 0x45 && b(10) == 0x42 && b(11) == 0x50) return "image/webp"

        // BMP: 'BM'
        if (b(0) == 0x42 && b(1) == 0x4D) return "image/bmp"

        // AVIF / HEIC: ....'ftyp'brand
        if (length >= 12 && b(4) == 0x66 && b(5) == 0x74 && b(6) == 0x79 && b(7) == 0x70) {
            val brand = String(bytes, 8, 4, Charsets.US_ASCII)
            when (brand) {
                "avif", "avis" -> return "image/avif"
                "heic", "heix", "heif", "mif1", "msf1" -> return "image/heic"
            }
        }

        // SVG (loose — starts with '<svg' or '<?xml')
        if (length >= 4) {
            val head = String(bytes, 0, minOf(length, 64), Charsets.US_ASCII).trimStart()
            if (head.startsWith("<svg", ignoreCase = true)) return "image/svg+xml"
        }

        return null
    }

    fun mimeFromUrl(url: String): String? {
        if (url.isBlank()) return null
        val lower = url.lowercase().substringBefore('?').substringBefore('#')
        return when {
            lower.endsWith(".gif") -> "image/gif"
            lower.endsWith(".png") -> "image/png"
            lower.endsWith(".webp") -> "image/webp"
            lower.endsWith(".avif") -> "image/avif"
            lower.endsWith(".svg") -> "image/svg+xml"
            lower.endsWith(".bmp") -> "image/bmp"
            lower.endsWith(".heic") -> "image/heic"
            lower.endsWith(".jpeg") || lower.endsWith(".jpg") -> "image/jpeg"
            else -> null
        }
    }

    fun extensionFor(mime: String): String = when (mime.lowercase().substringBefore(";").trim()) {
        "image/gif" -> "gif"
        "image/png" -> "png"
        "image/webp" -> "webp"
        "image/avif" -> "avif"
        "image/svg+xml" -> "svg"
        "image/bmp" -> "bmp"
        "image/heic" -> "heic"
        else -> "jpg"
    }

    fun isAnimated(mime: String, url: String): Boolean {
        if (mime.lowercase().contains("gif")) return true
        val lower = url.lowercase().substringBefore('?').substringBefore('#')
        return lower.endsWith(".gif")
    }
}
'''


def patch_image_mime_utils():
    log("\n=== PATCH: ImageMimeUtils (magic-byte sniff) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageMimeUtils.kt"
    f.parent.mkdir(parents=True, exist_ok=True)
    t = f.read_text(encoding="utf-8") if f.exists() else ""
    if "fun sniffMimeFromBytes" in t:
        log("  ✓ already has sniff"); return
    f.write_text(NEW_IMAGE_MIME_UTILS, encoding="utf-8")
    log("  ✓ rewritten with sniffMimeFromBytes")


# ============================================================
# NEW Downloader.kt (sniff-aware)
# ============================================================
NEW_DOWNLOADER = r'''package com.example.util

import android.content.ContentValues
import android.content.Context
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import com.example.model.PinItem
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStream
import java.io.PushbackInputStream
import java.util.concurrent.TimeUnit

data class DownloadProgress(
    val current: Int,
    val total: Int,
    val currentPinTitle: String,
    val isComplete: Boolean = false,
    val destinationFolder: String = "Download/PinterestViewerDownloads",
    val error: String? = null
)

object Downloader {
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

    const val FOLDER_NAME = "PinterestViewerDownloads"

    suspend fun downloadPins(
        context: Context,
        pins: List<PinItem>,
        onProgress: (DownloadProgress) -> Unit
    ): Int = withContext(Dispatchers.IO) {
        var successCount = 0
        val total = pins.size
        pins.forEachIndexed { index, pin ->
            onProgress(DownloadProgress(current = index + 1, total = total,
                currentPinTitle = pin.title.ifBlank { "Pin #${pin.id}" }))
            if (downloadSinglePinInternal(context, pin)) successCount++
        }
        onProgress(DownloadProgress(current = total, total = total,
            currentPinTitle = "Done", isComplete = true))
        successCount
    }

    suspend fun downloadSinglePin(context: Context, pin: PinItem): Boolean =
        withContext(Dispatchers.IO) { downloadSinglePinInternal(context, pin) }

    private fun downloadSinglePinInternal(context: Context, pin: PinItem): Boolean {
        try {
            val candidateUrls = listOf(pin.imageUrl, pin.thumbnailUrl).filter { it.isNotBlank() }.distinct()
            var responseBody: okhttp3.ResponseBody? = null
            var contentTypeHeader: String? = null
            var chosenUrl: String = pin.imageUrl
            for (url in candidateUrls) {
                try {
                    val request = Request.Builder()
                        .url(url)
                        .header("User-Agent", "Mozilla/5.0 (Android; Mobile; rv:109.0)")
                        .build()
                    val response = client.newCall(request).execute()
                    if (response.isSuccessful && response.body != null) {
                        responseBody = response.body
                        contentTypeHeader = response.header("Content-Type")
                        chosenUrl = url
                        break
                    }
                } catch (_: Exception) {}
            }
            if (responseBody == null) return false

            // Peek first 16 bytes for magic-byte sniffing, then unread
            val raw = responseBody.byteStream()
            val pushback = PushbackInputStream(raw, 32)
            val sample = ByteArray(16)
            val sampleLen = try { pushback.read(sample, 0, 16) } catch (_: Exception) { -1 }
            if (sampleLen > 0) {
                try { pushback.unread(sample, 0, sampleLen) } catch (_: Exception) {}
            }

            val resolvedMime = ImageMimeUtils.resolveMime(
                pin.mimeType, chosenUrl, contentTypeHeader,
                if (sampleLen > 0) sample else null,
                if (sampleLen > 0) sampleLen else 0
            )
            val extension = ImageMimeUtils.extensionFor(resolvedMime)

            val sanitizedTitle = pin.title.take(30)
                .replace(Regex("[^a-zA-Z0-9_-]"), "_")
                .trim('_')
                .ifBlank { "pin" }
            val fileName = "Pinterest_${sanitizedTitle}_${pin.id}.$extension"

            return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val values = ContentValues().apply {
                    put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
                    put(MediaStore.MediaColumns.MIME_TYPE, resolvedMime)
                    put(MediaStore.MediaColumns.RELATIVE_PATH,
                        "${Environment.DIRECTORY_DOWNLOADS}/$FOLDER_NAME")
                    put(MediaStore.MediaColumns.IS_PENDING, 1)
                }
                val resolver = context.contentResolver
                val uri: Uri? = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                    ?: resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
                if (uri != null) {
                    resolver.openOutputStream(uri)?.use { out: OutputStream -> pushback.copyTo(out) }
                    values.clear()
                    values.put(MediaStore.MediaColumns.IS_PENDING, 0)
                    resolver.update(uri, values, null, null)
                    true
                } else false
            } else {
                val downloadsDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                val targetDir = File(downloadsDir, FOLDER_NAME)
                if (!targetDir.exists()) targetDir.mkdirs()
                val outputFile = File(targetDir, fileName)
                FileOutputStream(outputFile).use { out -> pushback.copyTo(out) }
                MediaScannerConnection.scanFile(context,
                    arrayOf(outputFile.absolutePath), arrayOf(resolvedMime), null)
                true
            }
        } catch (e: Exception) {
            e.printStackTrace()
            return false
        }
    }
}
'''


def patch_downloader():
    log("\n=== PATCH: Downloader (sniff) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/Downloader.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    if "PushbackInputStream" in t and "sniffMimeFromBytes" not in t and "ImageMimeUtils.resolveMime" in t and "sample" in t:
        # Already sniff-aware (from this patch) — check marker
        pass
    if "PushbackInputStream(raw, 32)" in t:
        log("  ✓ already sniff-aware"); return
    f.write_text(NEW_DOWNLOADER, encoding="utf-8")
    log("  ✓ written")


# ============================================================
# ImageCacheManager — fix coil.decode package
# ============================================================
def patch_image_cache_manager():
    log("\n=== PATCH: ImageCacheManager (coil.decode fix) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageCacheManager.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    # Detect the previous (buggy) block
    buggy = (
        "            .components {\n"
        "                try {\n"
        "                    add(coil.gif.GifDecoder.Factory())\n"
        "                } catch (_: Throwable) {\n"
        "                    // coil-gif unavailable — static decoding only\n"
        "                }\n"
        "            }\n"
    )
    fixed = (
        "            .components {\n"
        "                try {\n"
        "                    if (android.os.Build.VERSION.SDK_INT >= 28) {\n"
        "                        add(coil.decode.ImageDecoderDecoder.Factory())\n"
        "                    } else {\n"
        "                        add(coil.decode.GifDecoder.Factory())\n"
        "                    }\n"
        "                } catch (_: Throwable) {}\n"
        "            }\n"
    )

    if fixed in t:
        log("  ✓ already fixed"); return

    if buggy in t:
        t = t.replace(buggy, fixed, 1)
        f.write_text(t, encoding="utf-8")
        log("  ✓ coil.gif → coil.decode + ImageDecoderDecoder (API 28+)")
        return

    # Fallback: try any string that mentions coil.gif.GifDecoder
    if "coil.gif.GifDecoder" in t:
        t = t.replace(
            "add(coil.gif.GifDecoder.Factory())",
            "if (android.os.Build.VERSION.SDK_INT >= 28) {\n"
            "                        add(coil.decode.ImageDecoderDecoder.Factory())\n"
            "                    } else {\n"
            "                        add(coil.decode.GifDecoder.Factory())\n"
            "                    }",
            1,
        )
        f.write_text(t, encoding="utf-8")
        log("  ✓ fixed via fallback (line substitution)")
        return

    # Fallback: no components block at all — insert it
    anchor = "        val imageLoader = ImageLoader.Builder(context)\n"
    if anchor in t:
        t = t.replace(
            anchor,
            anchor + (
                "            .components {\n"
                "                try {\n"
                "                    if (android.os.Build.VERSION.SDK_INT >= 28) {\n"
                "                        add(coil.decode.ImageDecoderDecoder.Factory())\n"
                "                    } else {\n"
                "                        add(coil.decode.GifDecoder.Factory())\n"
                "                    }\n"
                "                } catch (_: Throwable) {}\n"
                "            }\n"
            ),
            1,
        )
        f.write_text(t, encoding="utf-8")
        log("  ✓ components block inserted")
    else:
        log("  ✗ anchor missing — inspect manually")


# ============================================================
# CopyOrMoveImagesDialog — sniff in downloadToCacheUri
# ============================================================
def patch_copy_move_sniff():
    log("\n=== PATCH: CopyOrMoveImagesDialog (sniff) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/dialogs/CopyOrMoveImagesDialog.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "PushbackInputStream" in t and "sniffMimeFromBytes" not in t and "sample" in t and "downloadToCacheUri" in t and "hdr" in t:
        pass
    if "PushbackInputStream(raw, 32)" in t:
        log("  ✓ already sniff-aware"); return

    # Find downloadToCacheUri function and replace it
    marker = "private suspend fun downloadToCacheUri(context: Context, pin: PinItem): Pair<Uri, String>? = withContext(Dispatchers.IO) {"
    idx = t.find(marker)
    if idx < 0:
        # Maybe not updated to Pair yet — also check old signature
        marker_old = "private suspend fun downloadToCacheUri(context: Context, pin: PinItem): Uri? = withContext(Dispatchers.IO) {"
        idx = t.find(marker_old)
        if idx < 0:
            log("  ✗ downloadToCacheUri not found"); sys.exit(1)

    # Find matching close
    open_brace = t.find("{", idx)
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
            if depth == 0: break
        i += 1
    end = i + 1

    new_fn = '''private suspend fun downloadToCacheUri(context: Context, pin: PinItem): Pair<Uri, String>? = withContext(Dispatchers.IO) {
    try {
        val client = OkHttpClient()
        val request = Request.Builder()
            .url(pin.imageUrl)
            .header("User-Agent", "Mozilla/5.0 (Android; Mobile; rv:109.0)")
            .build()
        client.newCall(request).execute().use { resp ->
            if (!resp.isSuccessful || resp.body == null) return@withContext null
            val contentTypeHeader = resp.header("Content-Type")
            val raw = resp.body!!.byteStream()
            val pushback = java.io.PushbackInputStream(raw, 32)
            val hdr = ByteArray(16)
            val n = try { pushback.read(hdr, 0, 16) } catch (_: Exception) { -1 }
            if (n > 0) { try { pushback.unread(hdr, 0, n) } catch (_: Exception) {} }
            val mime = com.example.util.ImageMimeUtils.resolveMime(
                pin.mimeType, pin.imageUrl, contentTypeHeader,
                if (n > 0) hdr else null, if (n > 0) n else 0
            )
            val ext = com.example.util.ImageMimeUtils.extensionFor(mime)
            val cacheDir = File(context.cacheDir, "shared_images").apply { if (!exists()) mkdirs() }
            val file = File(cacheDir, "share_${pin.id.take(20)}.$ext")
            FileOutputStream(file).use { out -> pushback.copyTo(out) }
            FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file) to mime
        }
    } catch (_: Exception) {
        null
    }
}'''
    t = t[:idx] + new_fn + t[end:]
    f.write_text(t, encoding="utf-8")
    log("  ✓ downloadToCacheUri rewritten with sniff")


# ============================================================
# FullscreenGalleryViewer — sniff in prepareImageUriForPin
# ============================================================
def patch_fullscreen_sniff():
    log("\n=== PATCH: FullscreenGalleryViewer (sniff) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/FullscreenGalleryViewer.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "PushbackInputStream(raw, 32)" in t and "prepareImageUriForPin" in t:
        log("  ✓ already sniff-aware"); return

    marker = "private suspend fun prepareImageUriForPin(context: Context, pin: PinItem): Pair<Uri, String>? = withContext(Dispatchers.IO) {"
    idx = t.find(marker)
    if idx < 0:
        log("  ✗ prepareImageUriForPin (Pair variant) not found"); sys.exit(1)

    open_brace = t.find("{", idx)
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
            if depth == 0: break
        i += 1
    end = i + 1

    new_fn = '''private suspend fun prepareImageUriForPin(context: Context, pin: PinItem): Pair<Uri, String>? = withContext(Dispatchers.IO) {
    try {
        if (pin.imageUrl.startsWith("content://")) {
            val uri = Uri.parse(pin.imageUrl)
            val mime = context.contentResolver.getType(uri)
                ?: com.example.util.ImageMimeUtils.resolveMime(pin.mimeType, pin.imageUrl, null)
            return@withContext uri to mime
        }
        if (pin.imageUrl.startsWith("file://")) {
            val f = File(Uri.parse(pin.imageUrl).path ?: "")
            if (f.exists()) {
                val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", f)
                val mime = com.example.util.ImageMimeUtils.resolveMime(pin.mimeType, pin.imageUrl, null)
                return@withContext uri to mime
            }
        }
        val client = okhttp3.OkHttpClient.Builder()
            .connectTimeout(10, java.util.concurrent.TimeUnit.SECONDS)
            .readTimeout(15, java.util.concurrent.TimeUnit.SECONDS)
            .build()
        val request = okhttp3.Request.Builder()
            .url(pin.imageUrl)
            .header("User-Agent", "Mozilla/5.0 (Android; Mobile; rv:109.0)")
            .build()
        client.newCall(request).execute().use { resp ->
            if (!resp.isSuccessful || resp.body == null) return@withContext null
            val contentTypeHeader = resp.header("Content-Type")
            val raw = resp.body!!.byteStream()
            val pushback = java.io.PushbackInputStream(raw, 32)
            val hdr = ByteArray(16)
            val n = try { pushback.read(hdr, 0, 16) } catch (_: Exception) { -1 }
            if (n > 0) { try { pushback.unread(hdr, 0, n) } catch (_: Exception) {} }
            val mime = com.example.util.ImageMimeUtils.resolveMime(
                pin.mimeType, pin.imageUrl, contentTypeHeader,
                if (n > 0) hdr else null, if (n > 0) n else 0
            )
            val ext = com.example.util.ImageMimeUtils.extensionFor(mime)
            val cacheDir = File(context.cacheDir, "shared_images").apply { if (!exists()) mkdirs() }
            val safeName = "share_${pin.id.filter { it.isLetterOrDigit() }.take(25).ifBlank { "img_${System.currentTimeMillis()}" }}.$ext"
            val file = File(cacheDir, safeName)
            if (!file.exists() || file.length() == 0L) {
                FileOutputStream(file).use { out -> pushback.copyTo(out) }
            }
            if (file.exists() && file.length() > 0L) {
                FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file) to mime
            } else null
        }
    } catch (e: Exception) {
        android.util.Log.e("FullscreenGalleryViewer", "prepareImageUriForPin error", e)
        null
    }
}'''
    t = t[:idx] + new_fn + t[end:]
    f.write_text(t, encoding="utf-8")
    log("  ✓ prepareImageUriForPin rewritten with sniff")


# ============================================================
# Defensive: verify coil-gif dependency still present
# ============================================================
def ensure_coil_gif_dependency():
    log("\n=== VERIFY: coil-gif dependency ===")
    toml = PROJECT_ROOT / "gradle/libs.versions.toml"
    gradle = PROJECT_ROOT / "app/build.gradle.kts"
    toml_ok = toml.exists() and "coil-gif" in toml.read_text(encoding="utf-8")
    gradle_ok = gradle.exists() and "libs.coil.gif" in gradle.read_text(encoding="utf-8")
    if toml_ok and gradle_ok:
        log("  ✓ coil-gif in toml + build.gradle.kts")
        return
    # Add missing
    if not toml_ok and toml.exists():
        t = toml.read_text(encoding="utf-8")
        if "coilGif" not in t:
            t = t.replace('coilCompose = "2.7.0"\n', 'coilCompose = "2.7.0"\ncoilGif = "2.7.0"\n', 1)
        if "coil-gif" not in t:
            t = t.replace(
                'coil-compose = { group = "io.coil-kt", name = "coil-compose", version.ref = "coilCompose" }\n',
                'coil-compose = { group = "io.coil-kt", name = "coil-compose", version.ref = "coilCompose" }\n'
                'coil-gif = { group = "io.coil-kt", name = "coil-gif", version.ref = "coilGif" }\n',
                1,
            )
        toml.write_text(t, encoding="utf-8")
        log("  ✓ toml repaired")
    if not gradle_ok and gradle.exists():
        g = gradle.read_text(encoding="utf-8")
        if "libs.coil.gif" not in g:
            g = g.replace("  implementation(libs.coil.compose)\n",
                          "  implementation(libs.coil.compose)\n  implementation(libs.coil.gif)\n", 1)
            gradle.write_text(g, encoding="utf-8")
            log("  ✓ build.gradle.kts repaired")


# ============================================================
# Verify
# ============================================================
def verify_all():
    log("\n=== VERIFY ===")
    checks = []

    imu = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageMimeUtils.kt"
    icm = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageCacheManager.kt"
    dl = PROJECT_ROOT / "app/src/main/java/com/example/util/Downloader.kt"
    cm = PROJECT_ROOT / "app/src/main/java/com/example/ui/dialogs/CopyOrMoveImagesDialog.kt"
    fs = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/FullscreenGalleryViewer.kt"

    for p in (imu, icm, dl, cm, fs):
        if not p.exists(): log(f"  ✗ missing: {p}"); sys.exit(1)

    imu_t = imu.read_text(encoding="utf-8")
    icm_t = icm.read_text(encoding="utf-8")
    dl_t = dl.read_text(encoding="utf-8")
    cm_t = cm.read_text(encoding="utf-8")
    fs_t = fs.read_text(encoding="utf-8")

    checks.append(("ImageMimeUtils sniffMimeFromBytes",
                   "fun sniffMimeFromBytes" in imu_t))
    checks.append(("ImageMimeUtils sampleBytes param",
                   "sampleBytes: ByteArray?" in imu_t))
    checks.append(("ImageCacheManager uses coil.decode.GifDecoder",
                   "coil.decode.GifDecoder" in icm_t))
    checks.append(("ImageCacheManager uses coil.decode.ImageDecoderDecoder",
                   "coil.decode.ImageDecoderDecoder" in icm_t))
    checks.append(("ImageCacheManager no coil.gif (buggy)",
                   "coil.gif.GifDecoder" not in icm_t))
    checks.append(("Downloader sniff-aware",
                   "PushbackInputStream(raw, 32)" in dl_t))
    checks.append(("Downloader uses ImageMimeUtils",
                   "ImageMimeUtils.resolveMime(" in dl_t))
    checks.append(("Downloader no hardcoded .jpg",
                   '".jpg"' not in dl_t))
    checks.append(("CopyMove sniff-aware",
                   "PushbackInputStream(raw, 32)" in cm_t))
    checks.append(("Fullscreen sniff-aware",
                   "PushbackInputStream(raw, 32)" in fs_t))

    toml = PROJECT_ROOT / "gradle/libs.versions.toml"
    gradle = PROJECT_ROOT / "app/build.gradle.kts"
    checks.append(("coil-gif in toml",
                   toml.exists() and "coil-gif" in toml.read_text(encoding="utf-8")))
    checks.append(("coil-gif in build.gradle.kts",
                   gradle.exists() and "libs.coil.gif" in gradle.read_text(encoding="utf-8")))

    all_ok = True
    for name, ok in checks:
        log(f"  {'✓' if ok else '✗'} {name}")
        if not ok: all_ok = False

    if not all_ok:
        log("\n✗ VERIFICATION FAILED"); sys.exit(1)


# ============================================================
# Pipeline
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
        run(["git", "commit", "-m", "Fix coil.decode package + magic-byte sniff fallback"])


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
    log("PinBoard — coil.decode fix + magic-byte sniff fallback")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    ensure_coil_gif_dependency()
    patch_image_mime_utils()
    patch_image_cache_manager()
    patch_downloader()
    patch_copy_move_sniff()
    patch_fullscreen_sniff()
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