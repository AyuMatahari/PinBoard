package com.example.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import kotlinx.coroutines.flow.Flow

@Dao
interface BoardDao {
    @Query("SELECT * FROM boards WHERE (id = :id AND :id != '') OR (boardUrl = :url AND :url != '') LIMIT 1")
    suspend fun getBoardByIdOrUrl(id: String, url: String): BoardEntity?

    @Query("SELECT * FROM boards WHERE (boardUrl = :url AND :url != '') OR (slug = :slug AND :slug != '') LIMIT 1")
    suspend fun getBoardByUrlOrSlug(url: String, slug: String): BoardEntity?

    @Query("SELECT * FROM boards WHERE id = :id LIMIT 1")
    suspend fun getBoardById(id: String): BoardEntity?

    @Query("SELECT * FROM boards ORDER BY lastUpdatedMillis DESC")
    suspend fun getAllBoards(): List<BoardEntity>

    @Query("SELECT * FROM boards WHERE isCustom = 1 ORDER BY lastUpdatedMillis DESC")
    suspend fun getCustomBoards(): List<BoardEntity>

    @Query("SELECT * FROM boards WHERE isDefault = 1 LIMIT 1")
    suspend fun getDefaultBoard(): BoardEntity?

    @Query("UPDATE boards SET isDefault = 0")
    suspend fun clearDefaultBoardFlags()

    @Query("UPDATE boards SET isDefault = 1 WHERE id = :boardId")
    suspend fun setDefaultBoard(boardId: String)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertBoard(board: BoardEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertBoards(boards: List<BoardEntity>)

    @Query("DELETE FROM boards WHERE id = :boardId")
    suspend fun deleteBoard(boardId: String)

    @Query("SELECT * FROM pins WHERE boardId = :boardId ORDER BY dateAddedMillis DESC, orderIndex ASC, id ASC")
    suspend fun getPinsForBoard(boardId: String): List<PinEntity>

    @Query("SELECT * FROM pins WHERE boardId = :boardId ORDER BY dateAddedMillis DESC, orderIndex ASC, id ASC")
    fun observePinsForBoard(boardId: String): Flow<List<PinEntity>>

    @Query("SELECT * FROM pins")
    suspend fun getAllPins(): List<PinEntity>

    @Query("SELECT id FROM pins WHERE boardId = :boardId")
    suspend fun getPinIdsForBoard(boardId: String): List<String>

    @Query("SELECT imageUrl FROM pins WHERE boardId = :boardId")
    suspend fun getImageUrlsForBoard(boardId: String): List<String>

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insertPins(pins: List<PinEntity>): List<Long>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertPins(pins: List<PinEntity>)

    @Query("DELETE FROM pins WHERE boardId = :boardId")
    suspend fun deletePinsForBoard(boardId: String)

    @Query("DELETE FROM pins WHERE boardId = :boardId AND id IN (:pinIds)")
    suspend fun deletePinsFromBoard(boardId: String, pinIds: List<String>)

    @Query("DELETE FROM pins WHERE id IN (:pinIds) OR imageUrl IN (:imageUrls)")
    suspend fun deletePinsFromAllBoards(pinIds: List<String>, imageUrls: List<String>)

    @Query("SELECT id FROM pins WHERE boardId = :boardId")
    suspend fun getFavoritesPinIds(boardId: String = "board_favorites"): List<String>

    @Query("SELECT imageUrl FROM pins WHERE boardId = :boardId")
    suspend fun getFavoritesImageUrls(boardId: String = "board_favorites"): List<String>

    @Query("DELETE FROM pins WHERE boardId = :boardId AND (id = :pinId OR imageUrl = :imageUrl)")
    suspend fun removePinFromFavorites(boardId: String = "board_favorites", pinId: String, imageUrl: String)

    @Transaction
    suspend fun saveFullBoard(board: BoardEntity, pins: List<PinEntity>) {
        insertBoard(board)
        deletePinsForBoard(board.id)
        pins.chunked(50).forEach { batch ->
            upsertPins(batch)
        }
    }

    @Transaction
    suspend fun prependNewPins(board: BoardEntity, newPins: List<PinEntity>, existingPins: List<PinEntity>) {
        insertBoard(board)
        val combined = (newPins + existingPins).distinctBy { it.id }.mapIndexed { index, pin ->
            pin.copy(
                orderIndex = index,
                boardPosition = index
            )
        }
        deletePinsForBoard(board.id)
        combined.chunked(50).forEach { batch ->
            upsertPins(batch)
        }
    }

    @Transaction
    suspend fun upsertPinsSafely(pins: List<PinEntity>) {
        pins.chunked(50).forEach { batch ->
            upsertPins(batch)
        }
    }

    @Transaction
    suspend fun updateBoardDefaultState(boardId: String) {
        clearDefaultBoardFlags()
        setDefaultBoard(boardId)
    }

    // --- Implementation Brief Sections 15 & 18 Queries (pinterest_pins & pin_events) ---

    @Query("SELECT * FROM pinterest_pins WHERE board_url = :boardUrl ORDER BY board_position ASC")
    fun observeScannedPins(boardUrl: String): Flow<List<PinterestScannedPinEntity>>

    @Query("SELECT * FROM pinterest_pins WHERE board_url = :boardUrl ORDER BY board_position ASC")
    suspend fun getScannedPinsForBoard(boardUrl: String): List<PinterestScannedPinEntity>

    @Query("SELECT pin_id FROM pinterest_pins WHERE board_url = :boardUrl")
    suspend fun getScannedPinIds(boardUrl: String): List<String>

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insertScannedPin(pin: PinterestScannedPinEntity): Long

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insertScannedPins(pins: List<PinterestScannedPinEntity>): List<Long>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertScannedPins(pins: List<PinterestScannedPinEntity>)

    // --- Outbox Queue Queries (Sections 18 & 20) ---

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun queuePinEvent(event: PinEventEntity): Long

    @Query("SELECT * FROM pin_events WHERE delivery_status = 'pending' ORDER BY created_at_millis ASC LIMIT 50")
    suspend fun getPendingEvents(): List<PinEventEntity>

    @Query("UPDATE pin_events SET delivery_status = :status, delivered_at = :deliveredAt WHERE event_id = :eventId")
    suspend fun markEventDelivered(eventId: String, status: String = "delivered", deliveredAt: String)

    @Query("SELECT * FROM pin_events ORDER BY created_at_millis DESC LIMIT 30")
    fun observeRecentEvents(): Flow<List<PinEventEntity>>

    @Query("DELETE FROM pin_events WHERE delivery_status = 'delivered' OR created_at_millis < :cutoff")
    suspend fun pruneOldPinEvents(cutoff: Long = System.currentTimeMillis() - 86400000L)

    @Query("DELETE FROM pin_events WHERE event_id NOT IN (SELECT event_id FROM pin_events ORDER BY created_at_millis DESC LIMIT 50)")
    suspend fun trimEventsToMax50()

    // --- Custom Album Queries ---

    @Query("SELECT * FROM custom_albums WHERE boardId = :boardId ORDER BY dateAddedMillis DESC, orderIndex ASC")
    suspend fun getAlbumsForBoard(boardId: String): List<CustomAlbumEntity>

    @Query("SELECT * FROM custom_albums WHERE boardId = :boardId ORDER BY dateAddedMillis DESC, orderIndex ASC")
    fun observeAlbumsForBoard(boardId: String): Flow<List<CustomAlbumEntity>>

    @Query("SELECT * FROM custom_albums WHERE id = :albumId LIMIT 1")
    suspend fun getAlbumById(albumId: String): CustomAlbumEntity?

    @Query("SELECT * FROM custom_albums")
    suspend fun getAllAlbums(): List<CustomAlbumEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAlbum(album: CustomAlbumEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAlbums(albums: List<CustomAlbumEntity>)

    @Query("DELETE FROM custom_albums WHERE id = :albumId")
    suspend fun deleteAlbum(albumId: String)

    @Query("UPDATE pins SET albumId = NULL WHERE albumId = :albumId")
    suspend fun detachPinsFromAlbum(albumId: String)

    @Transaction
    suspend fun deleteAlbumAndDetachPins(albumId: String) {
        detachPinsFromAlbum(albumId)
        deleteAlbum(albumId)
    }

    @Query("UPDATE custom_albums SET dateAddedMillis = :date WHERE id = :albumId")
    suspend fun updateAlbumDate(albumId: String, date: Long)

    @Query("DELETE FROM custom_albums WHERE boardId = :boardId")
    suspend fun deleteAlbumsForBoard(boardId: String)

    @Query("SELECT * FROM pins WHERE albumId = :albumId ORDER BY orderIndex ASC, dateAddedMillis ASC")
    suspend fun getPinsForAlbum(albumId: String): List<PinEntity>

    @Query("UPDATE pins SET albumId = :newAlbumId WHERE id IN (:pinIds)")
    suspend fun movePinsToAlbum(pinIds: List<String>, newAlbumId: String?)

    @Query("UPDATE custom_albums SET parentAlbumId = :parentAlbumId WHERE id = :albumId")
    suspend fun setAlbumParent(albumId: String, parentAlbumId: String?)
}
