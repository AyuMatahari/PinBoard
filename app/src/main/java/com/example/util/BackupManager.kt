package com.example.util

import android.content.Context
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

    val MAX_FILES_OPTIONS: List<Int> = listOf(1, 2, 3, 5, 10, 15, 20, 30, 50)

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
        val clamped = maxFiles.coerceAtLeast(1)
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putInt(KEY_MAX_BACKUP_FILES, clamped).apply()
        try {
            val dir = getBackupDirectory(context)
            pruneOldBackups(dir, clamped)
        } catch (_: Exception) {}
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
                }
                val key = p.id.ifBlank { p.imageUrl }
                archivedPinsMap[key] = pObj
            }

            val pinsArray = JSONArray()
            archivedPinsMap.values.forEach { pinsArray.put(it) }
            rootJson.put("pins", pinsArray)

            try {
                archiveFile.writeText(pinsArray.toString())
            } catch (_: Exception) {}

            val timestampStr = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
            val backupFileName = "pinboard_backup_$timestampStr.json"
            val targetFile = File(chosenBackupDir, backupFileName)

            // Always write latest backup to target and latest.json
            val jsonString = rootJson.toString()
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
        val primaryDir = getBackupDirectory(context)
        val files = mutableListOf<File>()

        fun collectFrom(dir: File) {
            if (dir.exists() && dir.isDirectory) {
                dir.listFiles { f ->
                    f.isFile && f.extension.equals("json", ignoreCase = true) &&
                            (f.name.startsWith("pinboard_backup_") || f.name == "latest_backup.json")
                }?.let { files.addAll(it) }
            }
        }

        collectFrom(primaryDir)
        // Also check parent folder in case previous backups were placed there
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

    suspend fun restoreBackup(context: Context, backupFile: File): Result<RestoreSummary> = withContext(Dispatchers.IO) {
        try {
            if (!backupFile.exists() || !backupFile.canRead()) {
                return@withContext Result.failure(Exception("Backup file does not exist or cannot be read"))
            }

            val jsonStr = backupFile.readText()
            val rootJson = JSONObject(jsonStr)

            val db = AppDatabase.getDatabase(context)
            val dao = db.boardDao()

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
                                isBrokenOrUnreachable = pObj.optBoolean("isBrokenOrUnreachable", false)
                            )
                        )
                    }
                }
                if (pinEntities.isNotEmpty()) {
                    dao.upsertPinsSafely(pinEntities)
                    restoredPinsCount = pinEntities.size
                }
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

            // 4. Restore Board History
            val historyVal = rootJson.opt("board_history")
            if (historyVal != null) {
                val historyPrefs = context.getSharedPreferences("pinterest_board_history", Context.MODE_PRIVATE)
                historyPrefs.edit().putString("history_json", historyVal.toString()).apply()
            }

            Result.success(RestoreSummary(restoredBoardsCount, restoredPinsCount, settingsRestored))
        } catch (t: Throwable) {
            t.printStackTrace()
            Result.failure(t)
        }
    }
}
