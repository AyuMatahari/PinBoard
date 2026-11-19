package com.example.util

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
        if (pin.isVideo) return downloadVideoInternal(context, pin)
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
    private fun downloadVideoInternal(context: Context, pin: PinItem): Boolean {
        try {
            val videoUrl = pin.videoUrl ?: pin.imageUrl
            if (videoUrl.isBlank()) return false
            val mime = pin.videoMimeType.ifBlank {
                ImageMimeUtils.videoMimeFromUrl(videoUrl) ?: "video/mp4"
            }
            val ext = when {
                mime.contains("webm") -> "webm"
                mime.contains("quicktime") || mime.contains("mov") -> "mov"
                mime.contains("matroska") -> "mkv"
                mime.contains("avi") -> "avi"
                mime.contains("ogg") -> "ogv"
                mime.contains("3gpp") -> "3gp"
                mime.contains("mp2t") || videoUrl.contains(".ts") -> "ts"
                else -> "mp4"
            }
            val sanitizedTitle = pin.title.take(30)
                .replace(Regex("[^a-zA-Z0-9_-]"), "_")
                .trim('_')
                .ifBlank { "video" }
            val fileName = "Pinterest_${sanitizedTitle}_${pin.id}.$ext"
            val request = Request.Builder()
                .url(videoUrl)
                .header("User-Agent", "Mozilla/5.0 (Android; Mobile; rv:109.0)")
                .build()
            val response = client.newCall(request).execute()
            if (!response.isSuccessful || response.body == null) return false
            val input = response.body!!.byteStream()
            return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val values = ContentValues().apply {
                    put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
                    put(MediaStore.MediaColumns.MIME_TYPE, mime)
                    put(MediaStore.MediaColumns.RELATIVE_PATH,
                        "${Environment.DIRECTORY_DOWNLOADS}/$FOLDER_NAME")
                    put(MediaStore.MediaColumns.IS_PENDING, 1)
                }
                val resolver = context.contentResolver
                val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                    ?: resolver.insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, values)
                if (uri != null) {
                    resolver.openOutputStream(uri)?.use { out: OutputStream -> input.copyTo(out) }
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
                FileOutputStream(outputFile).use { out -> input.copyTo(out) }
                MediaScannerConnection.scanFile(context,
                    arrayOf(outputFile.absolutePath), arrayOf(mime), null)
                true
            }
        } catch (e: Exception) {
            e.printStackTrace()
            return false
        }
    }

}
