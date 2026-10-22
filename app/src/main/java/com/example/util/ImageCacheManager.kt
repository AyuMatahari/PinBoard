package com.example.util

import android.content.Context
import coil.Coil
import coil.ImageLoader
import coil.disk.DiskCache
import coil.memory.MemoryCache
import java.io.File

object ImageCacheManager {
    private const val PREFS_NAME = "image_cache_prefs"
    private const val KEY_MAX_DISK_CACHE_MB = "max_disk_cache_mb"
    const val DEFAULT_MAX_DISK_CACHE_MB = 512
    const val MIN_CACHE_MB = 50
    const val MAX_CACHE_MB = 4096

    fun getMaxDiskCacheMb(context: Context): Int {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getInt(KEY_MAX_DISK_CACHE_MB, DEFAULT_MAX_DISK_CACHE_MB)
    }

    fun setMaxDiskCacheMb(context: Context, maxMb: Int) {
        val clamped = maxMb.coerceIn(MIN_CACHE_MB, MAX_CACHE_MB)
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putInt(KEY_MAX_DISK_CACHE_MB, clamped)
            .apply()

        applyImageLoader(context, clamped)
    }

    fun applyImageLoader(context: Context, maxMb: Int = getMaxDiskCacheMb(context)) {
        val cacheDirectory = context.cacheDir.resolve("image_cache")
        val imageLoader = ImageLoader.Builder(context)
            .diskCache {
                DiskCache.Builder()
                    .directory(cacheDirectory)
                    .maxSizeBytes(maxMb.toLong() * 1024L * 1024L)
                    .build()
            }
            .memoryCache {
                MemoryCache.Builder(context)
                    .maxSizePercent(0.25)
                    .build()
            }
            .crossfade(true)
            .build()

        Coil.setImageLoader(imageLoader)
    }

    fun getDiskCacheUsageBytes(context: Context): Long {
        val cacheDir = context.cacheDir.resolve("image_cache")
        if (!cacheDir.exists()) return 0L
        return getDirSize(cacheDir)
    }

    fun formatBytes(bytes: Long): String {
        if (bytes <= 0) return "0 MB"
        val mb = bytes.toDouble() / (1024.0 * 1024.0)
        return if (mb < 0.1) {
            val kb = bytes / 1024
            "$kb KB"
        } else {
            String.format(java.util.Locale.US, "%.1f MB", mb)
        }
    }

    private fun getDirSize(dir: File): Long {
        var size = 0L
        dir.listFiles()?.forEach { file ->
            size += if (file.isDirectory) getDirSize(file) else file.length()
        }
        return size
    }

    @OptIn(coil.annotation.ExperimentalCoilApi::class)
    fun clearCache(context: Context) {
        try {
            Coil.imageLoader(context).diskCache?.clear()
            Coil.imageLoader(context).memoryCache?.clear()
            val cacheDir = context.cacheDir.resolve("image_cache")
            if (cacheDir.exists()) {
                cacheDir.deleteRecursively()
            }
            cleanupNonPermanentUserData(context)
        } catch (e: Exception) {
            e.printStackTrace()
        }
        applyImageLoader(context)
    }

    fun cleanupNonPermanentUserData(context: Context) {
        try {
            // Clean up WebView disk caches that Chromium puts in app_webview dataDir (which inflate "User data")
            val dataDir = context.applicationInfo.dataDir?.let { java.io.File(it) } ?: context.filesDir.parentFile
            dataDir?.listFiles()?.forEach { file ->
                if (file.name.startsWith("app_webview")) {
                    val subDirs = listOf("Cache", "GPUCache", "Code Cache", "Media Cache", "blob_storage", "Service Worker")
                    subDirs.forEach { sub ->
                        try {
                            java.io.File(file, sub).takeIf { it.exists() }?.deleteRecursively()
                            java.io.File(file, "Default/$sub").takeIf { it.exists() }?.deleteRecursively()
                        } catch (_: Throwable) {}
                    }
                }
            }

            // Clean temporary files in filesDir
            try {
                java.io.File(context.filesDir, "temp").takeIf { it.exists() }?.deleteRecursively()
            } catch (_: Throwable) {}

            // Truncate SQLite WAL file to minimize Room database size on disk
            com.example.data.local.AppDatabase.optimizeAndShrinkDatabase(context)
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }
}
