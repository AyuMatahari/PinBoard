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

            val success = downloadSinglePinInternal(context, pin)
            if (success) {
                successCount++
            }
        }

        onProgress(
            DownloadProgress(
                current = total,
                total = total,
                currentPinTitle = "Done",
                isComplete = true
            )
        )

        successCount
    }

    suspend fun downloadSinglePin(context: Context, pin: PinItem): Boolean = withContext(Dispatchers.IO) {
        downloadSinglePinInternal(context, pin)
    }

    private fun downloadSinglePinInternal(context: Context, pin: PinItem): Boolean {
        try {
            val sanitizedTitle = pin.title
                .take(30)
                .replace(Regex("[^a-zA-Z0-9_-]"), "_")
                .trim('_')
                .ifBlank { "pin" }
            val fileName = "Pinterest_${sanitizedTitle}_${pin.id}.jpg"
            val mimeType = "image/jpeg"

            val candidateUrls = listOf(pin.imageUrl, pin.thumbnailUrl).filter { it.isNotBlank() }.distinct()
            var responseBody: okhttp3.ResponseBody? = null
            for (url in candidateUrls) {
                try {
                    val request = Request.Builder()
                        .url(url)
                        .header("User-Agent", "Mozilla/5.0 (Android; Mobile; rv:109.0)")
                        .build()
                    val response = client.newCall(request).execute()
                    if (response.isSuccessful && response.body != null) {
                        responseBody = response.body
                        break
                    }
                } catch (_: Exception) {}
            }
            if (responseBody == null) return false

            val inputStream: InputStream = responseBody.byteStream()

            return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                // Android 10+ MediaStore Downloads or Images
                val values = ContentValues().apply {
                    put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
                    put(MediaStore.MediaColumns.MIME_TYPE, mimeType)
                    put(
                        MediaStore.MediaColumns.RELATIVE_PATH,
                        "${Environment.DIRECTORY_DOWNLOADS}/$FOLDER_NAME"
                    )
                    put(MediaStore.MediaColumns.IS_PENDING, 1)
                }

                val resolver = context.contentResolver
                // Use MediaStore.Downloads on API 29+
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
                // Android 9 and below
                val downloadsDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                val targetDir = File(downloadsDir, FOLDER_NAME)
                if (!targetDir.exists()) {
                    targetDir.mkdirs()
                }
                val outputFile = File(targetDir, fileName)
                FileOutputStream(outputFile).use { outputStream ->
                    inputStream.copyTo(outputStream)
                }
                MediaScannerConnection.scanFile(
                    context,
                    arrayOf(outputFile.absolutePath),
                    arrayOf(mimeType),
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
