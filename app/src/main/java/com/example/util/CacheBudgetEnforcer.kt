package com.example.util

import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.File

/**
 * Enforces the user's total cache limit across IMAGE and VIDEO caches.
 *
 * Rationale:
 *   - Coil (image) and Media3 (video) each have their own LRU evictors that
 *     only know about their own caches. If both use the full limit, combined
 *     size can reach 2x the user's intent.
 *   - This object periodically sweeps. If combined > limit, it evicts the
 *     oldest completed VIDEO spans first (video is easier to evict than
 *     Coil's disk cache). If video is exhausted and combined is still over,
 *     images are simply left alone — Coil's own LRU will evict them on its
 *     next write when it exceeds the limit by itself.
 *
 * Net effect: combined stays under the user's limit in steady state, with
 * both categories able to grow into whatever the other isn't using.
 */
object CacheBudgetEnforcer {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var appContext: Context? = null
    private var monitorJob: Job? = null

    fun init(context: Context) {
        if (appContext != null) return
        appContext = context.applicationContext
        monitorJob = scope.launch {
            while (isActive) {
                delay(60_000L)
                try { sweep() } catch (_: Throwable) {}
            }
        }
    }

    fun sweepAsync() {
        scope.launch {
            try {
                delay(500L)  // let any in-flight write settle
                sweep()
            } catch (_: Throwable) {}
        }
    }

    fun sweep() {
        val ctx = appContext ?: return
        val limit = ImageCacheManager.getMaxDiskCacheMb(ctx).toLong() * 1024L * 1024L
        val imageSize = getImageCacheBytes(ctx)
        val videoSize = VideoPlayerManager.getCacheSizeBytes(ctx)
        val total = imageSize + videoSize
        if (total <= limit) return

        var toEvict = total - limit
        val cache = VideoPlayerManager.getSimpleCacheForEviction(ctx) ?: return
        try {
            val spans = cache.keys().asSequence()
                .flatMap { key ->
                    try { cache.getCachedSpans(key).asSequence() } catch (_: Throwable) { emptySequence() }
                }
                .filter { it.file != null }
                .sortedBy { it.lastTouchTimestamp }
                .toList()

            for (span in spans) {
                if (toEvict <= 0L) break
                try {
                    if (cache.removeSpan(span)) {
                        toEvict -= span.length
                    }
                } catch (_: Throwable) {}
            }
        } catch (_: Throwable) {}
    }

    private fun getImageCacheBytes(context: Context): Long {
        val dir = File(context.cacheDir, "image_cache")
        if (!dir.exists()) return 0L
        return dirSize(dir)
    }

    private fun dirSize(dir: File): Long {
        var total = 0L
        dir.listFiles()?.forEach { f ->
            total += if (f.isDirectory) dirSize(f) else f.length()
        }
        return total
    }
}
