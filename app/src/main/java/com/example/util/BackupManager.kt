package com.example.util

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.os.Environment
import com.example.data.local.AppDatabase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object BackupManager {

    private const val PREFS_NAME = "pinboard_backup_prefs"
    private const val KEY_BACKUP_ENABLED = "backup_enabled"
    private const val KEY_BACKUP_INTERVAL_MINUTES = "backup_interval_minutes"
    private const val KEY_MAX_BACKUP_FILES = "max_backup_files"
    private const val KEY_LAST_BACKUP_TIME = "last_backup_time"
    const val DEFAULT_MAX_BACKUP_FILES = 5
    /** Value 0 means unlimited: never prune old backup files. */
    const val UNLIMITED_MAX_BACKUP_FILES = 0

    val MAX_FILES_OPTIONS: List<Int> = listOf(0, 1, 2, 3, 5, 10, 15, 20, 30, 50)  // 0 = Unlimited

    val INTERVAL_OPTIONS: List<Pair<String, Long>> = listOf(
        "1 hour" to 60L,
        "3 hours" to 180L,
        "1 day" to 1440L,
        "3 days" to 4320L,
        "1 week" to 10080L,
        "2 weeks" to 20160L,
        "1 month" to 43200L,
        "3 months" to 129600L,
        "6 months" to 259200L,
        "1 year" to 525600L
    )

    /**
     * True when this app can read arbitrary files under shared Download/.
     * On Android 11+ this needs MANAGE_EXTERNAL_STORAGE, granted via
     * Settings -> Special app access -> All files access. Without it the
     * File API returns only files created by THIS installation, which is
     * why backups from previous installs disappear from the Restore list.
     */
    fun hasAllFilesAccess(): Boolean =
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) true
        else try { Environment.isExternalStorageManager() } catch (_: Throwable) { false }

    /** Opens the system All-files-access screen for this app. */
    fun requestAllFilesAccess(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return
        try {
            val intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION).apply {
                data = Uri.parse("package:" + context.packageName)
            }
            context.startActivity(intent)
            return
        } catch (_: Throwable) {}
        try { context.startActivity(Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)) } catch (_: Throwable) {}
    }

    fun isBackupEnabled(context: Context): Boolean {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getBoolean(KEY_BACKUP_ENABLED, true)
    }

    fun setBackupEnabled(context: Context, enabled: Boolean) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putBoolean(KEY_BACKUP_ENABLED, enabled).apply()
    }

    fun getBackupIntervalMinutes(context: Context): Long {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getLong(KEY_BACKUP_INTERVAL_MINUTES, 1440L) // default 1 day
    }

    fun setBackupIntervalMinutes(context: Context, minutes: Long) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putLong(KEY_BACKUP_INTERVAL_MINUTES, minutes).apply()
    }

    fun getMaxBackupFiles(context: Context): Int {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getInt(KEY_MAX_BACKUP_FILES, DEFAULT_MAX_BACKUP_FILES)
    }

    fun setMaxBackupFiles(context: Context, maxFiles: Int) {
        val clamped = maxFiles.coerceAtLeast(0)  // 0 = Unlimited
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putInt(KEY_MAX_BACKUP_FILES, clamped).apply()
        if (clamped > 0) {
            try {
                val dir = getBackupDirectory(context)
                pruneOldBackups(dir, clamped)
            } catch (_: Exception) {}
        }
    }

    fun getBackupDirectory(context: Context): File {
        val downloadDir = try {
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
        } catch (_: Exception) {
            null
        }
        val targetDir = if (downloadDir != null) {
            File(downloadDir, "PinterestViewerDownloads/Backup")
        } else {
            File(context.filesDir, "Download/PinterestViewerDownloads/Backup")
        }

        if (!targetDir.exists()) {
            targetDir.mkdirs()
        }

        if (targetDir.canWrite()) {
            return targetDir
        }

        val fallbackExternal = File(context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), "PinterestViewerDownloads/Backup").apply {
            if (!exists()) mkdirs()
        }
        if (fallbackExternal.canWrite()) {
            return fallbackExternal
        }

        // Clean up legacy internal filesDir backups to keep user data compact
        try {
            File(context.filesDir, "Download/PinterestViewerDownloads/Backup").takeIf { it.exists() }?.deleteRecursively()
        } catch (_: Throwable) {}

        // Store non-permanent backup data in cacheDir to keep User Data as tiny as possible
        val internalDir = File(context.cacheDir, "PinterestViewerDownloads/Backup").apply {
            if (!exists()) mkdirs()
        }
        return internalDir
    }

    fun getLastBackupTime(context: Context): Long {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getLong(KEY_LAST_BACKUP_TIME, 0L)
    }

    private fun setLastBackupTime(context: Context, time: Long) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putLong(KEY_LAST_BACKUP_TIME, time).apply()
    }

    fun checkAndPerformScheduledBackup(context: Context) {
        if (!isBackupEnabled(context)) return
        val intervalMinutes = getBackupIntervalMinutes(context)
        val lastBackup = getLastBackupTime(context)
        val now = System.currentTimeMillis()
        val intervalMillis = intervalMinutes * 60 * 1000L

        if (now - lastBackup >= intervalMillis) {
            performBackupAsync(context)
        }
    }

    fun performBackupAsync(context: Context) {
        kotlinx.coroutines.CoroutineScope(Dispatchers.IO).launch {
            try {
                performBackup(context)
            } catch (t: Throwable) {
                t.printStackTrace()
            }
        }
    }

    suspend fun performBackup(context: Context): Result<File> = withContext(Dispatchers.IO) {
        try {
            val db = AppDatabase.getDatabase(context)
            val dao = db.boardDao()

            val boards = dao.getAllBoards()
            val allPins = dao.getAllPins()

            val rootJson = JSONObject()
            rootJson.put("version", 1)
            rootJson.put("timestamp", System.currentTimeMillis())
            rootJson.put("created_at", SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).format(Date()))

            // Export all SharedPreferences settings
            val settingsObj = JSONObject()
            val appSettingsPrefs = context.getSharedPreferences("app_settings", Context.MODE_PRIVATE)
            appSettingsPrefs.all.forEach { (k, v) ->
                settingsObj.put(k, v ?: JSONObject.NULL)
            }
            rootJson.put("settings", settingsObj)

            // Board layout prefs (per-board columns and sort)
            try {
                val blPrefs = context.getSharedPreferences("board_layout_prefs", Context.MODE_PRIVATE)
                val blObj = JSONObject()
                blPrefs.all.forEach { (k, v) -> blObj.put(k, v ?: JSONObject.NULL) }
                rootJson.put("board_layout_prefs", blObj)
            } catch (_: Exception) {}

            // Image cache prefs
            try {
                val icPrefs = context.getSharedPreferences("image_cache_prefs", Context.MODE_PRIVATE)
                val icObj = JSONObject()
                icPrefs.all.forEach { (k, v) -> icObj.put(k, v ?: JSONObject.NULL) }
                rootJson.put("image_cache_prefs", icObj)
            } catch (_: Exception) {}

            // Backup prefs (excluding last_backup_time)
            try {
                val bPrefs = context.getSharedPreferences("pinboard_backup_prefs", Context.MODE_PRIVATE)
                val bObj = JSONObject()
                bPrefs.all.forEach { (k, v) ->
                    if (k != "last_backup_time") bObj.put(k, v ?: JSONObject.NULL)
                }
                rootJson.put("backup_prefs", bObj)
            } catch (_: Exception) {}

            // Export board history
            val historyPrefs = context.getSharedPreferences("pinterest_board_history", Context.MODE_PRIVATE)
            val historyJsonStr = historyPrefs.getString("history_json", null)
            if (historyJsonStr != null) {
                try {
                    rootJson.put("board_history", JSONArray(historyJsonStr))
                } catch (_: Exception) {
                    rootJson.put("board_history", historyJsonStr)
                }
            }

            // Export boards
            val boardsArray = JSONArray()
            boards.forEach { b ->
                val bObj = JSONObject().apply {
                    put("id", b.id)
                    put("title", b.title)
                    put("slug", b.slug)
                    put("ownerUsername", b.ownerUsername)
                    put("ownerDisplayName", b.ownerDisplayName)
                    put("ownerAvatarUrl", b.ownerAvatarUrl)
                    put("pinCount", b.pinCount)
                    put("followerCount", b.followerCount)
                    put("boardUrl", b.boardUrl)
                    put("description", b.description)
                    put("isCustom", b.isCustom)
                    put("customDomains", b.customDomains)
                    put("isDefault", b.isDefault)
                    put("isSpecialNonDeletable", b.isSpecialNonDeletable)
                    put("lastUpdatedMillis", b.lastUpdatedMillis)
                }
                boardsArray.put(bObj)
            }
            rootJson.put("boards", boardsArray)

            // Save to /Download/PinterestViewerDownloads
            val chosenBackupDir = getBackupDirectory(context)

            // Export pins metadata and info (excluding raw image binary data)
            // Requirement 1: Make sure to not delete data even if image itself is deleted from the app
            val archivedPinsMap = linkedMapOf<String, JSONObject>()
            val fullPinsList = mutableListOf<JSONObject>()

            // Load from existing master archive if available
            val archiveFile = File(chosenBackupDir, "master_pins_archive.json")
            if (archiveFile.exists()) {
                try {
                    val existingArchiveStr = archiveFile.readText()
                    val existingArray = JSONArray(existingArchiveStr)
                    for (i in 0 until existingArray.length()) {
                        val obj = existingArray.getJSONObject(i)
                        val key = obj.optString("id").ifBlank { obj.optString("imageUrl") }
                        if (key.isNotBlank()) {
                            archivedPinsMap[key] = obj
                        }
                    }
                } catch (_: Exception) {}
            }

            // Merge with all pins currently in database
            allPins.forEach { p ->
                val pObj = JSONObject().apply {
                    put("id", p.id)
                    put("boardId", p.boardId)
                    put("title", p.title)
                    put("description", p.description)
                    put("imageUrl", p.imageUrl)
                    put("thumbnailUrl", p.thumbnailUrl)
                    put("author", p.author)
                    put("boardName", p.boardName)
                    put("sourceUrl", p.sourceUrl)
                    put("width", p.width)
                    put("height", p.height)
                    put("dominantColor", p.dominantColor)
                    put("dateAddedMillis", p.dateAddedMillis)
                    put("savesCount", p.savesCount)
                    put("likesCount", p.likesCount)
                    put("fileSizeKb", p.fileSizeKb)
                    put("orderIndex", p.orderIndex)
                    put("boardPosition", p.boardPosition)
                    put("firstSeenAt", p.firstSeenAt)
                    put("firstSeenAtMillis", p.firstSeenAtMillis)
                    put("pinterestCreatedAt", p.pinterestCreatedAt ?: "")
                    put("mimeType", p.mimeType)
                    put("sourceDomain", p.sourceDomain)
                    put("isBrokenOrUnreachable", p.isBrokenOrUnreachable)
                    put("albumId", p.albumId ?: "")
                }
                val key = p.id.ifBlank { p.imageUrl }
                archivedPinsMap[key] = pObj
                fullPinsList.add(pObj)
            }

            // Archive: deduped by pin id (metadata preservation after deletion)
            val archivePinsArray = JSONArray()
            archivedPinsMap.values.forEach { archivePinsArray.put(it) }
            try {
                archiveFile.writeText(archivePinsArray.toString())
            } catch (_: Exception) {}

            // Backup pins: ALL (id, boardId) pairs, NO dedup — preserves pins
            // that live on multiple boards (Dump / My Save / Favorites / custom).
            val pinsArray = JSONArray()
            fullPinsList.forEach { pinsArray.put(it) }
            rootJson.put("pins", pinsArray)

            // Custom albums (non-sort albums created from multi-image links)
            try {
                val customAlbums = dao.getAllAlbums()
                val albumsArray = JSONArray()
                customAlbums.forEach { a ->
                    val aObj = JSONObject().apply {
                        put("id", a.id)
                        put("boardId", a.boardId)
                        put("parentAlbumId", a.parentAlbumId ?: "")
                        put("title", a.title)
                        put("sourceUrl", a.sourceUrl)
                        put("dateAddedMillis", a.dateAddedMillis)
                        put("orderIndex", a.orderIndex)
                        put("isFavorite", a.isFavorite)
                    }
                    albumsArray.put(aObj)
                }
                rootJson.put("custom_albums", albumsArray)
            rootJson.put("album_ordering_version", 2)
            } catch (_: Exception) {}

            val timestampStr = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
            val backupFileName = "pinboard_backup_$timestampStr.json"
            val targetFile = File(chosenBackupDir, backupFileName)

            // Always write latest backup to target and latest.json
            // Pretty-printed (indent = 2) for human readability; compact JSON
            // files can still be restored because JSONObject() accepts both.
            val jsonString = rootJson.toString(2)
            targetFile.writeText(jsonString)

            val latestFile = File(chosenBackupDir, "latest_backup.json")
            try {
                latestFile.writeText(jsonString)
            } catch (_: Exception) {}

            // Prune old backups to respect max backup files limit (Requirement 3)
            pruneOldBackups(chosenBackupDir, getMaxBackupFiles(context))

            setLastBackupTime(context, System.currentTimeMillis())
            Result.success(targetFile)
        } catch (t: Throwable) {
            t.printStackTrace()
            Result.failure(t)
        }
    }

    private fun pruneOldBackups(backupDir: File, maxCount: Int) {
        if (maxCount <= 0) return  // Unlimited: never delete old backups
        try {
            val backupFiles = backupDir.listFiles { file ->
                file.isFile && file.name.startsWith("pinboard_backup_") && file.name.endsWith(".json")
            } ?: return

            if (backupFiles.size > maxCount) {
                // Sort by last modified descending (newest first)
                val sorted = backupFiles.sortedByDescending { it.lastModified() }
                // Delete everything past maxCount
                for (i in maxCount until sorted.size) {
                    try {
                        sorted[i].delete()
                    } catch (t: Throwable) {
                        t.printStackTrace()
                    }
                }
            }
        } catch (t: Throwable) {
            t.printStackTrace()
        }
    }

    fun getAvailableBackups(context: Context): List<File> {
        // Return ALL .json files in the backup folder (and its parent
        // PinterestViewerDownloads folder, if any), so user-created or
        // manually-copied backups are listed. Compact and pretty JSON are
        // both supported by the restore path.
        val primaryDir = getBackupDirectory(context)
        val files = mutableListOf<File>()

        fun collectFrom(dir: File) {
            if (dir.exists() && dir.isDirectory) {
                dir.listFiles { f ->
                    f.isFile && f.extension.equals("json", ignoreCase = true) &&
                            f.name != "master_pins_archive.json"
                }?.let { files.addAll(it) }
            }
        }

        collectFrom(primaryDir)
        primaryDir.parentFile?.let { parent ->
            if (parent.name == "PinterestViewerDownloads") {
                collectFrom(parent)
            }
        }

        return files.distinctBy { it.absolutePath }
            .sortedByDescending { it.lastModified() }
    }

    data class RestoreSummary(
        val boardsCount: Int,
        val pinsCount: Int,
        val settingsRestored: Boolean
    )

    private fun restorePrefsObject(context: Context, prefsObj: JSONObject?, prefsName: String) {
        if (prefsObj == null) return
        try {
            val editor = context.getSharedPreferences(prefsName, Context.MODE_PRIVATE).edit()
            val keys = prefsObj.keys()
            while (keys.hasNext()) {
                val key = keys.next()
                when (val value = prefsObj.get(key)) {
                    is Boolean -> editor.putBoolean(key, value)
                    is Int -> editor.putInt(key, value)
                    is Long -> editor.putLong(key, value)
                    is Float -> editor.putFloat(key, value)
                    is Double -> editor.putFloat(key, value.toFloat())
                    is String -> editor.putString(key, value)
                }
            }
            editor.apply()
        } catch (_: Exception) {}
    }

    suspend fun restoreBackup(context: Context, backupFile: File): Result<RestoreSummary> = withContext(Dispatchers.IO) {
        try {
            if (!backupFile.exists() || !backupFile.canRead()) {
                return@withContext Result.failure(Exception("Backup file does not exist or cannot be read"))
            }

            // Tolerant: pretty or compact JSON, strips UTF-8 BOM, trims whitespace.
            val rawStr = backupFile.readText()
            val jsonStr = rawStr.trimStart('\uFEFF', ' ', '\t', '\r', '\n')
            if (jsonStr.isBlank()) {
                return@withContext Result.failure(Exception("Backup file is empty"))
            }
            val rootJson = try {
                JSONObject(jsonStr)
            } catch (t: Throwable) {
                return@withContext Result.failure(
                    Exception("Not a valid JSON backup: ${t.message ?: t.javaClass.simpleName}")
                )
            }

            val db = AppDatabase.getDatabase(context)
            val dao = db.boardDao()

            val hasBoards = rootJson.has("boards")
            val hasPins = rootJson.has("pins")
            val hasSettings = rootJson.has("settings")
            val hasHistory = rootJson.has("board_history")
            if (!hasBoards && !hasPins && !hasSettings && !hasHistory) {
                return@withContext Result.failure(
                    Exception("Not a PinBoard backup (missing boards/pins/settings)")
                )
            }

            var restoredBoardsCount = 0
            var restoredPinsCount = 0
            var settingsRestored = false

            // 1. Restore Boards
            val boardsArray = rootJson.optJSONArray("boards")
            if (boardsArray != null && boardsArray.length() > 0) {
                val boardEntities = mutableListOf<com.example.data.local.BoardEntity>()
                for (i in 0 until boardsArray.length()) {
                    val bObj = boardsArray.getJSONObject(i)
                    val id = bObj.optString("id")
                    if (id.isNotBlank()) {
                        boardEntities.add(
                            com.example.data.local.BoardEntity(
                                id = id,
                                title = bObj.optString("title", ""),
                                slug = bObj.optString("slug", ""),
                                ownerUsername = bObj.optString("ownerUsername", ""),
                                ownerDisplayName = bObj.optString("ownerDisplayName", ""),
                                ownerAvatarUrl = bObj.optString("ownerAvatarUrl", ""),
                                pinCount = bObj.optInt("pinCount", 0),
                                followerCount = bObj.optInt("followerCount", 0),
                                boardUrl = bObj.optString("boardUrl", ""),
                                description = bObj.optString("description", ""),
                                isCustom = bObj.optBoolean("isCustom", false),
                                customDomains = bObj.optString("customDomains", ""),
                                isDefault = bObj.optBoolean("isDefault", false),
                                isSpecialNonDeletable = bObj.optBoolean("isSpecialNonDeletable", false),
                                lastUpdatedMillis = bObj.optLong("lastUpdatedMillis", System.currentTimeMillis())
                            )
                        )
                    }
                }
                if (boardEntities.isNotEmpty()) {
                    dao.insertBoards(boardEntities)
                    restoredBoardsCount = boardEntities.size
                }
            }

            // 2. Restore Pins
            val pinsArray = rootJson.optJSONArray("pins")
            if (pinsArray != null && pinsArray.length() > 0) {
                val pinEntities = mutableListOf<com.example.data.local.PinEntity>()
                for (i in 0 until pinsArray.length()) {
                    val pObj = pinsArray.getJSONObject(i)
                    val id = pObj.optString("id")
                    val boardId = pObj.optString("boardId")
                    val imageUrl = pObj.optString("imageUrl")
                    if (id.isNotBlank() && imageUrl.isNotBlank()) {
                        pinEntities.add(
                            com.example.data.local.PinEntity(
                                id = id,
                                boardId = boardId.ifBlank { "board_dump" },
                                title = pObj.optString("title", ""),
                                description = pObj.optString("description", ""),
                                imageUrl = imageUrl,
                                thumbnailUrl = pObj.optString("thumbnailUrl", imageUrl),
                                author = pObj.optString("author", ""),
                                boardName = pObj.optString("boardName", ""),
                                sourceUrl = pObj.optString("sourceUrl", ""),
                                width = pObj.optInt("width", 0),
                                height = pObj.optInt("height", 0),
                                dominantColor = pObj.optLong("dominantColor", 0xFF333333L),
                                dateAddedMillis = pObj.optLong("dateAddedMillis", System.currentTimeMillis()),
                                savesCount = pObj.optInt("savesCount", 0),
                                likesCount = pObj.optInt("likesCount", 0),
                                fileSizeKb = pObj.optLong("fileSizeKb", 0L),
                                orderIndex = pObj.optInt("orderIndex", i),
                                boardPosition = pObj.optInt("boardPosition", i),
                                firstSeenAt = pObj.optString("firstSeenAt", ""),
                                firstSeenAtMillis = pObj.optLong("firstSeenAtMillis", 0L),
                                pinterestCreatedAt = pObj.optString("pinterestCreatedAt", "").ifBlank { null },
                                mimeType = pObj.optString("mimeType", "image/jpeg"),
                                sourceDomain = pObj.optString("sourceDomain", ""),
                                isBrokenOrUnreachable = pObj.optBoolean("isBrokenOrUnreachable", false),
                                albumId = pObj.optString("albumId", "").ifBlank { null }
                            )
                        )
                    }
                }
                if (pinEntities.isNotEmpty()) {
                    dao.upsertPinsSafely(pinEntities)
                    restoredPinsCount = pinEntities.size
                }
            }

            // 2b. Restore custom albums (non-sort albums from multi-image links)
            val albumsArray = rootJson.optJSONArray("custom_albums")
            if (albumsArray != null && albumsArray.length() > 0) {
                val albumEntities = mutableListOf<com.example.data.local.CustomAlbumEntity>()
                for (i in 0 until albumsArray.length()) {
                    val aObj = albumsArray.optJSONObject(i) ?: continue
                    val aId = aObj.optString("id")
                    if (aId.isBlank()) continue
                    albumEntities.add(
                        com.example.data.local.CustomAlbumEntity(
                            id = aId,
                            boardId = aObj.optString("boardId"),
                            parentAlbumId = aObj.optString("parentAlbumId", "").ifBlank { null },
                            title = aObj.optString("title", ""),
                            sourceUrl = aObj.optString("sourceUrl", ""),
                            dateAddedMillis = aObj.optLong("dateAddedMillis", System.currentTimeMillis()),
                            orderIndex = aObj.optInt("orderIndex", 0),
                            isFavorite = aObj.optBoolean("isFavorite", false)
                        )
                    )
                }
                if (albumEntities.isNotEmpty()) {
                    dao.insertAlbums(albumEntities)
                }
            }

            // Legacy album migration: if backup is v1 (no album_ordering_version),
            // reposition each album to the median of its pins' dateAddedMillis
            // so they intersperse naturally with pins instead of stacking on top.
            val albumOrderVer = rootJson.optInt("album_ordering_version", 1)
            if (albumOrderVer < 2) {
                try {
                    val allAlbums = dao.getAllAlbums()
                    for (album in allAlbums) {
                        val albumPins = dao.getPinsForAlbum(album.id)
                        if (albumPins.size > 1) {
                            val dates = albumPins.map { it.dateAddedMillis }.sorted()
                            val median = dates[dates.size / 2]
                            dao.updateAlbumDate(album.id, median)
                        }
                    }
                } catch (_: Throwable) {}
            }

            // 3. Restore App Settings SharedPreferences
            val settingsObj = rootJson.optJSONObject("settings")
            if (settingsObj != null) {
                val editor = context.getSharedPreferences("app_settings", Context.MODE_PRIVATE).edit()
                val keys = settingsObj.keys()
                while (keys.hasNext()) {
                    val key = keys.next()
                    when (val value = settingsObj.get(key)) {
                        is Boolean -> editor.putBoolean(key, value)
                        is Int -> editor.putInt(key, value)
                        is Long -> editor.putLong(key, value)
                        is Float -> editor.putFloat(key, value)
                        is Double -> editor.putFloat(key, value.toFloat())
                        is String -> editor.putString(key, value)
                        is JSONArray -> {
                            val set = mutableSetOf<String>()
                            for (j in 0 until value.length()) {
                                set.add(value.getString(j))
                            }
                            editor.putStringSet(key, set)
                        }
                    }
                }
                editor.apply()
                settingsRestored = true
            }

            // 3b. Restore board_layout_prefs
            restorePrefsObject(context, rootJson.optJSONObject("board_layout_prefs"), "board_layout_prefs")

            // 3c. Restore image_cache_prefs
            restorePrefsObject(context, rootJson.optJSONObject("image_cache_prefs"), "image_cache_prefs")

            // 3d. Restore backup_prefs (skip last_backup_time)
            run {
                val bPrefs = rootJson.optJSONObject("backup_prefs")
                if (bPrefs != null) {
                    val ed = context.getSharedPreferences("pinboard_backup_prefs", Context.MODE_PRIVATE).edit()
                    val ks = bPrefs.keys()
                    while (ks.hasNext()) {
                        val k = ks.next()
                        if (k == "last_backup_time") continue
                        when (val v = bPrefs.get(k)) {
                            is Boolean -> ed.putBoolean(k, v)
                            is Int -> ed.putInt(k, v)
                            is Long -> ed.putLong(k, v)
                            is Float -> ed.putFloat(k, v)
                            is String -> ed.putString(k, v)
                        }
                    }
                    ed.apply()
                }
            }

            // 4. Restore Board History
            val historyVal = rootJson.opt("board_history")
            if (historyVal != null) {
                val historyPrefs = context.getSharedPreferences("pinterest_board_history", Context.MODE_PRIVATE)
                historyPrefs.edit().putString("history_json", historyVal.toString()).apply()
            }

            Result.success(RestoreSummary(restoredBoardsCount, restoredPinsCount, settingsRestored))
        } catch (t: Throwable) {
            t.printStackTrace()
            Result.failure(Exception("Restore failed: ${t.message ?: t.javaClass.simpleName}"))
        }
    }
}
