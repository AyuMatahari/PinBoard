package com.example.data.local

import android.content.Context
import android.os.Build
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(
    entities = [
        BoardEntity::class,
        PinEntity::class,
        PinterestScannedPinEntity::class,
        PinEventEntity::class,
        CustomAlbumEntity::class
    ],
    version = 5,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun boardDao(): BoardDao

    companion object {
        @Volatile
        private var INSTANCE: AppDatabase? = null

        private fun migrateToVersion5(db: androidx.sqlite.db.SupportSQLiteDatabase) {
            // 1. Ensure boards table exists
            db.execSQL("CREATE TABLE IF NOT EXISTS `boards` (`id` TEXT NOT NULL, `title` TEXT NOT NULL, `slug` TEXT NOT NULL, `ownerUsername` TEXT NOT NULL, `ownerDisplayName` TEXT NOT NULL, `ownerAvatarUrl` TEXT NOT NULL, `pinCount` INTEGER NOT NULL, `followerCount` INTEGER NOT NULL, `boardUrl` TEXT NOT NULL, `description` TEXT NOT NULL, `isCustom` INTEGER NOT NULL, `customDomains` TEXT NOT NULL, `isDefault` INTEGER NOT NULL, `isSpecialNonDeletable` INTEGER NOT NULL, `lastUpdatedMillis` INTEGER NOT NULL, PRIMARY KEY(`id`))")

            // 2. Ensure pins table exists
            db.execSQL("CREATE TABLE IF NOT EXISTS `pins` (`id` TEXT NOT NULL, `boardId` TEXT NOT NULL, `title` TEXT NOT NULL, `description` TEXT NOT NULL, `imageUrl` TEXT NOT NULL, `thumbnailUrl` TEXT NOT NULL, `author` TEXT NOT NULL, `boardName` TEXT NOT NULL, `sourceUrl` TEXT NOT NULL, `width` INTEGER NOT NULL, `height` INTEGER NOT NULL, `dominantColor` INTEGER NOT NULL, `dateAddedMillis` INTEGER NOT NULL, `savesCount` INTEGER NOT NULL, `likesCount` INTEGER NOT NULL, `fileSizeKb` INTEGER NOT NULL, `orderIndex` INTEGER NOT NULL, `boardPosition` INTEGER NOT NULL, `firstSeenAt` TEXT NOT NULL, `firstSeenAtMillis` INTEGER NOT NULL, `pinterestCreatedAt` TEXT, `deliveryStatus` TEXT NOT NULL, `deliveredAt` TEXT, `mimeType` TEXT NOT NULL, `sourceDomain` TEXT NOT NULL, `isBrokenOrUnreachable` INTEGER NOT NULL, `albumId` TEXT, PRIMARY KEY(`id`, `boardId`))")

            // Add any missing columns to pins if table already existed from older version
            val existingPinCols = mutableSetOf<String>()
            try {
                val cursor = db.query("PRAGMA table_info(pins)")
                while (cursor.moveToNext()) {
                    existingPinCols.add(cursor.getString(1).lowercase())
                }
                cursor.close()
            } catch (_: Throwable) {}

            if (!existingPinCols.contains("albumid")) {
                try { db.execSQL("ALTER TABLE `pins` ADD COLUMN `albumId` TEXT DEFAULT NULL") } catch (_: Throwable) {}
            }
            if (!existingPinCols.contains("deliverystatus")) {
                try { db.execSQL("ALTER TABLE `pins` ADD COLUMN `deliveryStatus` TEXT NOT NULL DEFAULT 'pending'") } catch (_: Throwable) {}
            }
            if (!existingPinCols.contains("deliveredat")) {
                try { db.execSQL("ALTER TABLE `pins` ADD COLUMN `deliveredAt` TEXT DEFAULT NULL") } catch (_: Throwable) {}
            }
            if (!existingPinCols.contains("mimetype")) {
                try { db.execSQL("ALTER TABLE `pins` ADD COLUMN `mimeType` TEXT NOT NULL DEFAULT 'image/jpeg'") } catch (_: Throwable) {}
            }
            if (!existingPinCols.contains("sourcedomain")) {
                try { db.execSQL("ALTER TABLE `pins` ADD COLUMN `sourceDomain` TEXT NOT NULL DEFAULT ''") } catch (_: Throwable) {}
            }
            if (!existingPinCols.contains("isbrokenorunreachable")) {
                try { db.execSQL("ALTER TABLE `pins` ADD COLUMN `isBrokenOrUnreachable` INTEGER NOT NULL DEFAULT 0") } catch (_: Throwable) {}
            }

            db.execSQL("CREATE INDEX IF NOT EXISTS `index_pins_boardId` ON `pins` (`boardId`)")
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_pins_orderIndex` ON `pins` (`orderIndex`)")
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_pins_boardPosition` ON `pins` (`boardPosition`)")
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_pins_imageUrl` ON `pins` (`imageUrl`)")
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_pins_albumId` ON `pins` (`albumId`)")

            // 3. Ensure pinterest_pins exists
            db.execSQL("CREATE TABLE IF NOT EXISTS `pinterest_pins` (`pin_id` TEXT NOT NULL, `board_url` TEXT NOT NULL, `board_position` INTEGER NOT NULL, `first_seen_at` TEXT NOT NULL, `pin_url` TEXT NOT NULL, `image_url` TEXT, `title` TEXT, `delivery_status` TEXT NOT NULL, `delivered_at` TEXT, `pinterest_created_at` TEXT, `first_seen_at_millis` INTEGER NOT NULL, `width` INTEGER NOT NULL, `height` INTEGER NOT NULL, `author` TEXT NOT NULL, `description` TEXT NOT NULL, `saves_count` INTEGER NOT NULL, `likes_count` INTEGER NOT NULL, PRIMARY KEY(`pin_id`, `board_url`))")
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_pinterest_pins_board_url` ON `pinterest_pins` (`board_url`)")
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_pinterest_pins_board_position` ON `pinterest_pins` (`board_position`)")
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_pinterest_pins_first_seen_at` ON `pinterest_pins` (`first_seen_at`)")
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_pinterest_pins_delivery_status` ON `pinterest_pins` (`delivery_status`)")

            // 4. Ensure pin_events exists
            db.execSQL("CREATE TABLE IF NOT EXISTS `pin_events` (`event_id` TEXT NOT NULL, `board_id` TEXT NOT NULL, `pin_id` TEXT NOT NULL, `event` TEXT NOT NULL, `board_url` TEXT NOT NULL, `board_position` INTEGER NOT NULL, `first_seen_at` TEXT NOT NULL, `pin_url` TEXT NOT NULL, `image_url` TEXT, `delivery_status` TEXT NOT NULL, `delivered_at` TEXT, `retry_count` INTEGER NOT NULL, `created_at_millis` INTEGER NOT NULL, PRIMARY KEY(`event_id`))")
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_pin_events_board_id` ON `pin_events` (`board_id`)")
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_pin_events_pin_id` ON `pin_events` (`pin_id`)")
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_pin_events_delivery_status` ON `pin_events` (`delivery_status`)")

            // 5. Ensure custom_albums exists
            db.execSQL("CREATE TABLE IF NOT EXISTS `custom_albums` (`id` TEXT NOT NULL, `boardId` TEXT NOT NULL, `parentAlbumId` TEXT, `title` TEXT NOT NULL, `sourceUrl` TEXT NOT NULL, `dateAddedMillis` INTEGER NOT NULL, `orderIndex` INTEGER NOT NULL, `isFavorite` INTEGER NOT NULL, PRIMARY KEY(`id`))")
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_custom_albums_boardId` ON `custom_albums` (`boardId`)")
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_custom_albums_parentAlbumId` ON `custom_albums` (`parentAlbumId`)")
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_custom_albums_dateAddedMillis` ON `custom_albums` (`dateAddedMillis`)")
        }

        val MIGRATION_1_5 = object : androidx.room.migration.Migration(1, 5) {
            override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) = migrateToVersion5(db)
        }
        val MIGRATION_2_5 = object : androidx.room.migration.Migration(2, 5) {
            override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) = migrateToVersion5(db)
        }
        val MIGRATION_3_5 = object : androidx.room.migration.Migration(3, 5) {
            override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) = migrateToVersion5(db)
        }
        val MIGRATION_4_5 = object : androidx.room.migration.Migration(4, 5) {
            override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) = migrateToVersion5(db)
        }

        fun getDatabase(context: Context): AppDatabase {
            return INSTANCE ?: synchronized(this) {
                val builder = Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "pinboard_gallery_database"
                )
                    .addMigrations(MIGRATION_1_5, MIGRATION_2_5, MIGRATION_3_5, MIGRATION_4_5)
                    .fallbackToDestructiveMigration(dropAllTables = true)
                    .fallbackToDestructiveMigrationOnDowngrade(dropAllTables = true)

                if (Build.FINGERPRINT != "robolectric") {
                    try {
                        builder.enableMultiInstanceInvalidation()
                    } catch (_: Throwable) {}
                }

                val instance = builder.build()
                INSTANCE = instance
                instance
            }
        }

        fun optimizeAndShrinkDatabase(context: Context) {
            try {
                val db = getDatabase(context)
                db.openHelper.writableDatabase.execSQL("PRAGMA wal_checkpoint(TRUNCATE)")
            } catch (_: Throwable) {}
        }
    }
}
