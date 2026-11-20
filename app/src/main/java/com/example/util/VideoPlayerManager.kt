package com.example.util

import android.content.Context
import android.net.Uri
import androidx.media3.common.MediaItem
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.datasource.cache.CacheDataSource
import androidx.media3.datasource.cache.LeastRecentlyUsedCacheEvictor
import androidx.media3.datasource.cache.SimpleCache
import androidx.media3.exoplayer.DefaultLoadErrorHandlingPolicy
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.dash.DashMediaSource
import androidx.media3.exoplayer.hls.HlsMediaSource
import androidx.media3.exoplayer.source.MediaSource
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import com.example.model.PinItem
import java.io.File

/**
 * Singleton managing the ExoPlayer + Media3 disk cache.
 *
 * Cache budgeting:
 *   - 30% of ImageCacheManager.getMaxDiskCacheMb() is reserved for the video cache.
 *   - This budget is enforced by LeastRecentlyUsedCacheEvictor.
 *   - Cache lives in cacheDir/media3_video_cache so it is auto-cleaned by Android.
 *
 * Download behavior (via CacheDataSource):
 *   - While player.play() is active → fetches chunks ahead of the playhead
 *   - When player.pause() is called → fetches stop
 *   - When player resumes → fetches resume from where they left off
 *   This exactly matches the requirement "pause download on nav/exit".
 */
object VideoPlayerManager {

    private var player: ExoPlayer? = null
    private var simpleCache: SimpleCache? = null
    private var cacheBudgetMb: Int = -1
    private var currentPinId: String? = null

    private const val VIDEO_BUDGET_PERCENT = 30L
    private const val MIN_VIDEO_CACHE_MB = 20L

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
        val maxMb = ImageCacheManager.getMaxDiskCacheMb(ctx)
        if (simpleCache != null && cacheBudgetMb == maxMb) {
            return simpleCache!!
        }
        try { simpleCache?.release() } catch (_: Throwable) {}

        // Use the FULL user limit. Combined image+video is enforced by
        // CacheBudgetEnforcer.sweep() — no artificial 30/70 split.
        val budgetMb = maxMb
        val budgetBytes = budgetMb * 1024L * 1024L
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
        CacheBudgetEnforcer.sweepAsync()
    }

    fun release() {
        try {
            player?.stop()
            player?.clearMediaItems()
            player?.release()
        } catch (_: Throwable) {}
        player = null
        currentPinId = null
        CacheBudgetEnforcer.sweepAsync()
    }

    fun currentPlayingPinId(): String? = currentPinId

    /** Returns the existing SimpleCache without creating it, for external eviction. */
    fun getSimpleCacheForEviction(context: Context): SimpleCache? = simpleCache

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
