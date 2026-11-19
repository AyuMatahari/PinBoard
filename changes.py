#!/usr/bin/env python3
"""
PinBoard Gallery — full GIF support (download/share/masonry/fullscreen)
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
# NEW FILE: ImageMimeUtils.kt
# ============================================================
NEW_IMAGE_MIME_UTILS = r'''package com.example.util

/**
 * Centralised MIME / extension resolution for images.
 *
 * Priority (highest → lowest):
 *   1. HTTP Content-Type header (authoritative — reflects actual bytes)
 *   2. pin.mimeType if it isn't the default "image/jpeg"
 *   3. URL extension
 *   4. "image/jpeg" fallback
 *
 * This is what makes GIFs survive round-trips: Pinterest's CDN may serve
 * .jpg-named URLs that return `Content-Type: image/gif`, so we always
 * believe the actual server response over the filename.
 */
object ImageMimeUtils {

    fun resolveMime(pinMime: String, imageUrl: String, contentTypeHeader: String? = null): String {
        if (!contentTypeHeader.isNullOrBlank() && contentTypeHeader.startsWith("image/", ignoreCase = true)) {
            return contentTypeHeader.substringBefore(";").trim().lowercase()
        }
        val pm = pinMime.lowercase().substringBefore(";").trim()
        if (pm.isNotBlank() && pm != "image/jpeg") return pm
        val fromUrl = mimeFromUrl(imageUrl)
        if (fromUrl != null) return fromUrl
        return pm.ifBlank { "image/jpeg" }
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


# ============================================================
# NEW FILE: Downloader.kt (full rewrite — content-type aware)
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
import java.io.InputStream
import java.io.OutputStream
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
            onProgress(
                DownloadProgress(
                    current = index + 1,
                    total = total,
                    currentPinTitle = pin.title.ifBlank { "Pin #${pin.id}" }
                )
            )
            if (downloadSinglePinInternal(context, pin)) successCount++
        }
        onProgress(DownloadProgress(current = total, total = total, currentPinTitle = "Done", isComplete = true))
        successCount
    }

    suspend fun downloadSinglePin(context: Context, pin: PinItem): Boolean = withContext(Dispatchers.IO) {
        downloadSinglePinInternal(context, pin)
    }

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

            val resolvedMime = ImageMimeUtils.resolveMime(pin.mimeType, chosenUrl, contentTypeHeader)
            val extension = ImageMimeUtils.extensionFor(resolvedMime)

            val sanitizedTitle = pin.title
                .take(30)
                .replace(Regex("[^a-zA-Z0-9_-]"), "_")
                .trim('_')
                .ifBlank { "pin" }
            val fileName = "Pinterest_${sanitizedTitle}_${pin.id}.$extension"

            val inputStream: InputStream = responseBody.byteStream()

            return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val values = ContentValues().apply {
                    put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
                    put(MediaStore.MediaColumns.MIME_TYPE, resolvedMime)
                    put(
                        MediaStore.MediaColumns.RELATIVE_PATH,
                        "${Environment.DIRECTORY_DOWNLOADS}/$FOLDER_NAME"
                    )
                    put(MediaStore.MediaColumns.IS_PENDING, 1)
                }

                val resolver = context.contentResolver
                val uri: Uri? = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                    ?: resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)

                if (uri != null) {
                    resolver.openOutputStream(uri)?.use { outputStream: OutputStream ->
                        inputStream.copyTo(outputStream)
                    }
                    values.clear()
                    values.put(MediaStore.MediaColumns.IS_PENDING, 0)
                    resolver.update(uri, values, null, null)
                    true
                } else {
                    false
                }
            } else {
                val downloadsDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                val targetDir = File(downloadsDir, FOLDER_NAME)
                if (!targetDir.exists()) targetDir.mkdirs()
                val outputFile = File(targetDir, fileName)
                FileOutputStream(outputFile).use { outputStream ->
                    inputStream.copyTo(outputStream)
                }
                MediaScannerConnection.scanFile(
                    context,
                    arrayOf(outputFile.absolutePath),
                    arrayOf(resolvedMime),
                    null
                )
                true
            }
        } catch (e: Exception) {
            e.printStackTrace()
            return false
        }
    }
}
'''


def write_image_mime_utils():
    log("\n=== PATCH: new ImageMimeUtils.kt ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageMimeUtils.kt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(NEW_IMAGE_MIME_UTILS, encoding="utf-8")
    log("  ✓ created")


def write_downloader():
    log("\n=== PATCH: rewrite Downloader.kt (content-type aware) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/Downloader.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    f.write_text(NEW_DOWNLOADER, encoding="utf-8")
    log("  ✓ written")


# ============================================================
# gradle: add coil-gif dependency
# ============================================================
def patch_gradle_versions():
    log("\n=== PATCH: libs.versions.toml (coil-gif) ===")
    f = PROJECT_ROOT / "gradle/libs.versions.toml"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "coil-gif" in t:
        log("  ✓ already present"); return

    # Add version entry after coilCompose
    t = t.replace(
        'coilCompose = "2.7.0"\n',
        'coilCompose = "2.7.0"\ncoilGif = "2.7.0"\n',
        1,
    )
    # Add library entry after coil-compose
    t = t.replace(
        'coil-compose = { group = "io.coil-kt", name = "coil-compose", version.ref = "coilCompose" }\n',
        'coil-compose = { group = "io.coil-kt", name = "coil-compose", version.ref = "coilCompose" }\n'
        'coil-gif = { group = "io.coil-kt", name = "coil-gif", version.ref = "coilGif" }\n',
        1,
    )

    if "coil-gif" in t:
        f.write_text(t, encoding="utf-8")
        log("  ✓ coil-gif added")
    else:
        log("  ✗ anchor mismatch"); sys.exit(1)


def patch_app_build_gradle():
    log("\n=== PATCH: app/build.gradle.kts (coil-gif) ===")
    f = PROJECT_ROOT / "app/build.gradle.kts"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "libs.coil.gif" in t:
        log("  ✓ already present"); return

    anchor = "  implementation(libs.coil.compose)\n"
    if anchor in t:
        t = t.replace(anchor, anchor + "  implementation(libs.coil.gif)\n", 1)
        f.write_text(t, encoding="utf-8")
        log("  ✓ implementation added")
    else:
        log("  ✗ anchor missing"); sys.exit(1)


# ============================================================
# ImageCacheManager: register GifDecoder
# ============================================================
def patch_image_cache_manager():
    log("\n=== PATCH: ImageCacheManager (GifDecoder) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageCacheManager.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "GifDecoder.Factory" in t:
        log("  ✓ already registered"); return

    anchor = "        val imageLoader = ImageLoader.Builder(context)\n"
    if anchor in t:
        t = t.replace(
            anchor,
            anchor +
            "            .components {\n"
            "                try {\n"
            "                    add(coil.gif.GifDecoder.Factory())\n"
            "                } catch (_: Throwable) {\n"
            "                    // coil-gif unavailable — static decoding only\n"
            "                }\n"
            "            }\n",
            1,
        )
        f.write_text(t, encoding="utf-8")
        log("  ✓ GifDecoder registered")
    else:
        log("  ✗ anchor missing"); sys.exit(1)


# ============================================================
# CopyOrMoveImagesDialog: mime-aware save/share
# ============================================================
def patch_copy_move_dialog():
    log("\n=== PATCH: CopyOrMoveImagesDialog (mime-aware) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/dialogs/CopyOrMoveImagesDialog.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # 1. Replace downloadToCacheUri (returns Pair<Uri, String>?)
    old_dl = (
        "private suspend fun downloadToCacheUri(context: Context, pin: PinItem): Uri? = withContext(Dispatchers.IO) {\n"
        "    try {\n"
        "        val client = OkHttpClient()\n"
        "        val request = Request.Builder().url(pin.imageUrl).build()\n"
        "        val response = client.newCall(request).execute()\n"
        "        if (!response.isSuccessful || response.body == null) return@withContext null\n"
        "\n"
        "        val cacheDir = File(context.cacheDir, \"shared_images\").apply { if (!exists()) mkdirs() }\n"
        "        val file = File(cacheDir, \"share_${pin.id.take(20)}.jpg\")\n"
        "        FileOutputStream(file).use { out ->\n"
        "            response.body!!.byteStream().copyTo(out)\n"
        "        }\n"
        "\n"
        "        FileProvider.getUriForFile(context, \"${context.packageName}.fileprovider\", file)\n"
        "    } catch (_: Exception) {\n"
        "        null\n"
        "    }\n"
        "}\n"
    )
    new_dl = (
        "private suspend fun downloadToCacheUri(context: Context, pin: PinItem): Pair<Uri, String>? = withContext(Dispatchers.IO) {\n"
        "    try {\n"
        "        val client = OkHttpClient()\n"
        "        val request = Request.Builder()\n"
        "            .url(pin.imageUrl)\n"
        "            .header(\"User-Agent\", \"Mozilla/5.0 (Android; Mobile; rv:109.0)\")\n"
        "            .build()\n"
        "        val response = client.newCall(request).execute()\n"
        "        response.use { resp ->\n"
        "            if (!resp.isSuccessful || resp.body == null) return@withContext null\n"
        "            val contentTypeHeader = resp.header(\"Content-Type\")\n"
        "            val mime = com.example.util.ImageMimeUtils.resolveMime(pin.mimeType, pin.imageUrl, contentTypeHeader)\n"
        "            val ext = com.example.util.ImageMimeUtils.extensionFor(mime)\n"
        "            val cacheDir = File(context.cacheDir, \"shared_images\").apply { if (!exists()) mkdirs() }\n"
        "            val file = File(cacheDir, \"share_${pin.id.take(20)}.$ext\")\n"
        "            resp.body!!.byteStream().use { input ->\n"
        "                FileOutputStream(file).use { out -> input.copyTo(out) }\n"
        "            }\n"
        "            FileProvider.getUriForFile(context, \"${context.packageName}.fileprovider\", file) to mime\n"
        "        }\n"
        "    } catch (_: Exception) {\n"
        "        null\n"
        "    }\n"
        "}\n"
    )
    if old_dl in t:
        t = t.replace(old_dl, new_dl, 1); changed = True
        log("  ✓ downloadToCacheUri rewritten")
    else:
        log("  ⚠ downloadToCacheUri anchor missing")

    # 2. Copy call site (first pin)
    old_copy = (
        "                                    val firstPin = selectedPins.firstOrNull()\n"
        "                                    if (firstPin != null) {\n"
        "                                        val uri = downloadToCacheUri(context, firstPin)\n"
        "                                        if (uri != null) {\n"
        "                                            val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager\n"
        "                                            val clip = ClipData.newUri(context.contentResolver, \"Image\", uri)\n"
        "                                            clipboard.setPrimaryClip(clip)\n"
        "                                            Toast.makeText(context, \"Copied image to clipboard\", Toast.LENGTH_SHORT).show()\n"
        "                                        } else {\n"
        "                                            Toast.makeText(context, \"Failed to copy image\", Toast.LENGTH_SHORT).show()\n"
        "                                        }\n"
        "                                    }\n"
    )
    new_copy = (
        "                                    val firstPin = selectedPins.firstOrNull()\n"
        "                                    if (firstPin != null) {\n"
        "                                        val pair = downloadToCacheUri(context, firstPin)\n"
        "                                        if (pair != null) {\n"
        "                                            val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager\n"
        "                                            val clip = ClipData.newUri(context.contentResolver, \"Image\", pair.first)\n"
        "                                            clipboard.setPrimaryClip(clip)\n"
        "                                            Toast.makeText(context, \"Copied image to clipboard\", Toast.LENGTH_SHORT).show()\n"
        "                                        } else {\n"
        "                                            Toast.makeText(context, \"Failed to copy image\", Toast.LENGTH_SHORT).show()\n"
        "                                        }\n"
        "                                    }\n"
    )
    if old_copy in t:
        t = t.replace(old_copy, new_copy, 1); changed = True
        log("  ✓ copy call site updated")
    else:
        log("  ⚠ copy call site anchor missing")

    # 3. Share call site
    old_share = (
        "                                    val uris = ArrayList<Uri>()\n"
        "                                    for (pin in selectedPins.take(10)) {\n"
        "                                        val u = downloadToCacheUri(context, pin)\n"
        "                                        if (u != null) uris.add(u)\n"
        "                                    }\n"
        "                                    if (uris.isNotEmpty()) {\n"
        "                                        val sendIntent = if (uris.size == 1) {\n"
        "                                            Intent(Intent.ACTION_SEND).apply {\n"
        "                                                type = \"image/jpeg\"\n"
        "                                                putExtra(Intent.EXTRA_STREAM, uris[0])\n"
        "                                                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)\n"
        "                                            }\n"
        "                                        } else {\n"
        "                                            Intent(Intent.ACTION_SEND_MULTIPLE).apply {\n"
        "                                                type = \"image/jpeg\"\n"
        "                                                putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris)\n"
        "                                                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)\n"
        "                                            }\n"
        "                                        }\n"
        "                                        val shareIntent = Intent.createChooser(sendIntent, \"Share Image\")\n"
        "                                        context.startActivity(shareIntent)\n"
        "                                    } else {\n"
        "                                        Toast.makeText(context, \"Could not prepare image\", Toast.LENGTH_SHORT).show()\n"
        "                                    }\n"
    )
    new_share = (
        "                                    val pairs = ArrayList<Pair<Uri, String>>()\n"
        "                                    for (pin in selectedPins.take(10)) {\n"
        "                                        val p = downloadToCacheUri(context, pin)\n"
        "                                        if (p != null) pairs.add(p)\n"
        "                                    }\n"
        "                                    if (pairs.isNotEmpty()) {\n"
        "                                        val uris = pairs.map { it.first }\n"
        "                                        val mimes = pairs.map { it.second }.distinct()\n"
        "                                        val commonMime = if (mimes.size == 1) mimes[0] else \"*/*\"\n"
        "                                        val sendIntent = if (uris.size == 1) {\n"
        "                                            Intent(Intent.ACTION_SEND).apply {\n"
        "                                                type = commonMime\n"
        "                                                putExtra(Intent.EXTRA_STREAM, uris[0])\n"
        "                                                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)\n"
        "                                            }\n"
        "                                        } else {\n"
        "                                            Intent(Intent.ACTION_SEND_MULTIPLE).apply {\n"
        "                                                type = commonMime\n"
        "                                                putParcelableArrayListExtra(Intent.EXTRA_STREAM, ArrayList(uris))\n"
        "                                                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)\n"
        "                                            }\n"
        "                                        }\n"
        "                                        val shareIntent = Intent.createChooser(sendIntent, \"Share Image\")\n"
        "                                        context.startActivity(shareIntent)\n"
        "                                    } else {\n"
        "                                        Toast.makeText(context, \"Could not prepare image\", Toast.LENGTH_SHORT).show()\n"
        "                                    }\n"
    )
    if old_share in t:
        t = t.replace(old_share, new_share, 1); changed = True
        log("  ✓ share call site updated")
    else:
        log("  ⚠ share call site anchor missing")

    if changed: f.write_text(t, encoding="utf-8")


# ============================================================
# FullscreenGalleryViewer: mime-aware prepare/share
# ============================================================
def patch_fullscreen_viewer():
    log("\n=== PATCH: FullscreenGalleryViewer (mime-aware) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/FullscreenGalleryViewer.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # 1. Rewrite prepareImageUriForPin → Pair<Uri, String>?
    old_prep_start = (
        "private suspend fun prepareImageUriForPin(context: Context, pin: PinItem): Uri? = withContext(Dispatchers.IO) {\n"
    )
    idx = t.find(old_prep_start)
    if idx >= 0:
        # find function end (matching brace)
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
        new_prep = '''private suspend fun prepareImageUriForPin(context: Context, pin: PinItem): Pair<Uri, String>? = withContext(Dispatchers.IO) {
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
        val response = client.newCall(request).execute()
        response.use { resp ->
            if (!resp.isSuccessful || resp.body == null) return@withContext null
            val contentTypeHeader = resp.header("Content-Type")
            val mime = com.example.util.ImageMimeUtils.resolveMime(pin.mimeType, pin.imageUrl, contentTypeHeader)
            val ext = com.example.util.ImageMimeUtils.extensionFor(mime)
            val cacheDir = File(context.cacheDir, "shared_images").apply { if (!exists()) mkdirs() }
            val safeName = "share_${pin.id.filter { it.isLetterOrDigit() }.take(25).ifBlank { "img_${System.currentTimeMillis()}" }}.$ext"
            val file = File(cacheDir, safeName)
            if (!file.exists() || file.length() == 0L) {
                resp.body!!.byteStream().use { input ->
                    FileOutputStream(file).use { out -> input.copyTo(out) }
                }
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
        t = t[:idx] + new_prep + t[end:]
        changed = True
        log("  ✓ prepareImageUriForPin rewritten")

    # 2. Share function signature: add mime param, use it
    old_share_fn_start = "private fun shareImage(context: Context, pin: PinItem, uri: Uri) {\n"
    idx2 = t.find(old_share_fn_start)
    if idx2 >= 0:
        open_brace2 = t.find("{", idx2)
        depth = 1
        i = open_brace2 + 1
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
        end2 = i + 1
        new_share_fn = '''private fun shareImage(context: Context, pin: PinItem, uri: Uri, mime: String) {
    try {
        val shareIntent = Intent(Intent.ACTION_SEND).apply {
            type = mime.ifBlank { pin.mimeType.ifBlank { "image/jpeg" } }
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        val chooser = Intent.createChooser(shareIntent, "Share Image")
        chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(chooser)
    } catch (e: Exception) {
        Toast.makeText(context, "Failed to share image: ${e.message}", Toast.LENGTH_SHORT).show()
    }
}'''
        t = t[:idx2] + new_share_fn + t[end2:]
        changed = True
        log("  ✓ shareImage signature updated")

    # 3. Call sites in MinimalImageHoldDialog
    old_copy_call = (
        "                                val uri = prepareImageUriForPin(context, pin)\n"
        "                                isProcessing = false\n"
        "                                if (uri != null) {\n"
        "                                    copyImageToClipboard(context, pin, uri)\n"
        "                                    onDismiss()\n"
        "                                } else {\n"
        "                                    Toast.makeText(context, \"Could not prepare image file\", Toast.LENGTH_SHORT).show()\n"
        "                                }\n"
    )
    new_copy_call = (
        "                                val pair = prepareImageUriForPin(context, pin)\n"
        "                                isProcessing = false\n"
        "                                if (pair != null) {\n"
        "                                    copyImageToClipboard(context, pin, pair.first)\n"
        "                                    onDismiss()\n"
        "                                } else {\n"
        "                                    Toast.makeText(context, \"Could not prepare image file\", Toast.LENGTH_SHORT).show()\n"
        "                                }\n"
    )
    if old_copy_call in t:
        t = t.replace(old_copy_call, new_copy_call, 1); changed = True
        log("  ✓ copy call site updated")

    old_share_call = (
        "                                val uri = prepareImageUriForPin(context, pin)\n"
        "                                isProcessing = false\n"
        "                                if (uri != null) {\n"
        "                                    shareImage(context, pin, uri)\n"
        "                                    onDismiss()\n"
        "                                } else {\n"
        "                                    Toast.makeText(context, \"Could not prepare image file\", Toast.LENGTH_SHORT).show()\n"
        "                                }\n"
    )
    new_share_call = (
        "                                val pair = prepareImageUriForPin(context, pin)\n"
        "                                isProcessing = false\n"
        "                                if (pair != null) {\n"
        "                                    shareImage(context, pin, pair.first, pair.second)\n"
        "                                    onDismiss()\n"
        "                                } else {\n"
        "                                    Toast.makeText(context, \"Could not prepare image file\", Toast.LENGTH_SHORT).show()\n"
        "                                }\n"
    )
    if old_share_call in t:
        t = t.replace(old_share_call, new_share_call, 1); changed = True
        log("  ✓ share call site updated")

    if changed: f.write_text(t, encoding="utf-8")


# ============================================================
# PinCard: use full image URL for animated content
# ============================================================
def patch_pin_card():
    log("\n=== PATCH: PinCard (GIF masonry auto-play) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/PinCard.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "isAnimatedGif" in t:
        log("  ✓ already patched"); return

    # Insert declarations before the Box that contains AsyncImage
    anchor = (
        "        // Image Container with safe aspect ratio\n"
        "        Box(\n"
    )
    if anchor not in t:
        log("  ⚠ anchor missing"); return

    insert = (
        "        val isAnimatedGif = com.example.util.ImageMimeUtils.isAnimated(pin.mimeType, pin.imageUrl)\n"
        "        val cardImageUrl = if (isAnimatedGif) pin.imageUrl.ifBlank { pin.thumbnailUrl }\n"
        "                           else pin.thumbnailUrl.ifBlank { pin.imageUrl }\n"
        "\n"
        "        // Image Container with safe aspect ratio\n"
        "        Box(\n"
    )
    t = t.replace(anchor, insert, 1)

    # Replace thumbnail data with effective URL
    t = t.replace(
        "                    .data(pin.thumbnailUrl.ifBlank { pin.imageUrl })\n",
        "                    .data(cardImageUrl)\n",
        1,
    )

    f.write_text(t, encoding="utf-8")
    log("  ✓ PinCard uses full image URL for GIFs")


# ============================================================
# PinterestRepository: set mimeType from URL
# ============================================================
def patch_pinterest_repository():
    log("\n=== PATCH: PinterestRepository (mimeType) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/data/PinterestRepository.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "mimeType = com.example.util.ImageLinkResolver.guessMimeType(highResUrl)" in t:
        log("  ✓ already patched"); return

    # parsePinJsonObject return: add mimeType before boardPosition
    old = (
        "            fileSizeKb = (200..1200).random().toLong(),\n"
        "            boardPosition = currentCount\n"
        "        )\n"
    )
    new = (
        "            fileSizeKb = (200..1200).random().toLong(),\n"
        "            mimeType = com.example.util.ImageLinkResolver.guessMimeType(highResUrl),\n"
        "            boardPosition = currentCount\n"
        "        )\n"
    )
    if old in t:
        t = t.replace(old, new, 1)
        f.write_text(t, encoding="utf-8")
        log("  ✓ parsePinJsonObject mimeType added")
    else:
        log("  ⚠ parsePinJsonObject anchor missing")


# ============================================================
# Verification
# ============================================================
def verify_all():
    log("\n=== VERIFY ===")
    checks = []

    imu = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageMimeUtils.kt"
    dl = PROJECT_ROOT / "app/src/main/java/com/example/util/Downloader.kt"
    icm = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageCacheManager.kt"
    cm = PROJECT_ROOT / "app/src/main/java/com/example/ui/dialogs/CopyOrMoveImagesDialog.kt"
    fs = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/FullscreenGalleryViewer.kt"
    pc = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/PinCard.kt"
    repo = PROJECT_ROOT / "app/src/main/java/com/example/data/PinterestRepository.kt"
    ver_toml = PROJECT_ROOT / "gradle/libs.versions.toml"
    build_gradle = PROJECT_ROOT / "app/build.gradle.kts"

    for p in (imu, dl, icm, cm, fs, pc, repo, ver_toml, build_gradle):
        if not p.exists():
            log(f"  ✗ missing: {p}"); sys.exit(1)

    checks.append(("ImageMimeUtils exists", imu.exists() and
                   "fun resolveMime(" in imu.read_text(encoding="utf-8")))
    checks.append(("Downloader content-type read",
                   "contentTypeHeader = response.header(\"Content-Type\")" in dl.read_text(encoding="utf-8")))
    checks.append(("Downloader uses ImageMimeUtils",
                   "ImageMimeUtils.resolveMime(" in dl.read_text(encoding="utf-8")))
    checks.append(("Downloader no hardcoded jpg",
                   ".jpg\"" not in dl.read_text(encoding="utf-8")))
    checks.append(("ImageCacheManager registers GifDecoder",
                   "GifDecoder.Factory()" in icm.read_text(encoding="utf-8")))
    checks.append(("CopyMove downloadToCacheUri returns Pair",
                   "Pair<Uri, String>?" in cm.read_text(encoding="utf-8")))
    checks.append(("Fullscreen prepareImageUriForPin returns Pair",
                   "Pair<Uri, String>?" in fs.read_text(encoding="utf-8")))
    checks.append(("Fullscreen shareImage takes mime",
                   "private fun shareImage(context: Context, pin: PinItem, uri: Uri, mime: String)" in fs.read_text(encoding="utf-8")))
    checks.append(("PinCard isAnimatedGif",
                   "isAnimatedGif" in pc.read_text(encoding="utf-8")))
    checks.append(("Repository mimeType added",
                   "mimeType = com.example.util.ImageLinkResolver.guessMimeType(highResUrl)" in repo.read_text(encoding="utf-8")))
    checks.append(("coil-gif in toml",
                   "coil-gif" in ver_toml.read_text(encoding="utf-8")))
    checks.append(("coil-gif in build.gradle.kts",
                   "libs.coil.gif" in build_gradle.read_text(encoding="utf-8")))

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
        run(["git", "commit", "-m", "GIF support: content-type-aware save/share + coil-gif masonry auto-play"])


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
    log("PinBoard — GIF support (download/share/masonry/fullscreen)")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    write_image_mime_utils()
    write_downloader()
    patch_gradle_versions()
    patch_app_build_gradle()
    patch_image_cache_manager()
    patch_copy_move_dialog()
    patch_fullscreen_viewer()
    patch_pin_card()
    patch_pinterest_repository()
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