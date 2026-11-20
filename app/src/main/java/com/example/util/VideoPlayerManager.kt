package com.example.util

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
