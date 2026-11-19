package com.example.util

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
