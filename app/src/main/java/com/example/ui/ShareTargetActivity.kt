package com.example.ui

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.data.local.AppDatabase
import com.example.data.local.BoardDao
import com.example.data.local.BoardEntity
import com.example.data.local.PinEntity
import com.example.model.PinItem
import com.example.ui.theme.MyApplicationTheme
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary
import com.example.util.ImageLinkResolver
import com.example.util.LinkExtractor
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext


class ShareTargetActivity : ComponentActivity() {

    companion object {
        /**
         * Process-scoped coroutine scope that survives activity destruction.
         * Auto-save and user-triggered saves continue here even if the
         * ShareTargetActivity finishes immediately (fixes unreliable auto-save).
         */
        private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    }

    @Volatile
    private var autoSaveJob: Job? = null

    @Volatile
    private var resolvedPinsForSave: List<PinItem>? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val sharedLinks = mutableListOf<String>()
        val sharedImageUris = mutableListOf<Uri>()

        when (intent?.action) {
            Intent.ACTION_SEND -> {
                if ("text/plain" == intent.type) {
                    val sharedText = intent.getStringExtra(Intent.EXTRA_TEXT) ?: ""
                    sharedLinks.addAll(LinkExtractor.extractLinks(sharedText))
                    if (sharedLinks.isEmpty() && sharedText.isNotBlank() &&
                        (sharedText.startsWith("http://") || sharedText.startsWith("https://"))) {
                        sharedLinks.add(sharedText.trim())
                    }
                } else if (intent.type?.startsWith("image/") == true) {
                    androidx.core.content.IntentCompat
                        .getParcelableExtra(intent, Intent.EXTRA_STREAM, Uri::class.java)
                        ?.let { sharedImageUris.add(it) }
                }
            }
            Intent.ACTION_SEND_MULTIPLE -> {
                if (intent.type?.startsWith("image/") == true) {
                    androidx.core.content.IntentCompat
                        .getParcelableArrayListExtra(intent, Intent.EXTRA_STREAM, Uri::class.java)
                        ?.let { sharedImageUris.addAll(it) }
                }
            }
        }

        // Auto-save to default board — runs on app scope so it survives finish().
        autoSaveJob = appScope.launch {
            try {
                val pins = resolveSharedItems(sharedLinks, sharedImageUris, false)
                resolvedPinsForSave = pins
                val appCtx = applicationContext
                val dao = AppDatabase.getDatabase(appCtx).boardDao()
                ensureDefaultBoardsExist(dao)
                val allBoards = dao.getAllBoards()
                val defaultBoard = allBoards.firstOrNull { it.isDefault }
                    ?: allBoards.firstOrNull { it.id == "board_dump" }
                    ?: allBoards.firstOrNull() ?: return@launch

                val existingIds = dao.getPinIdsForBoard(defaultBoard.id).toSet()
                val existingUrls = dao.getImageUrlsForBoard(defaultBoard.id).toSet()
                val toInsert = pins.filter {
                    !existingIds.contains(it.id) && !existingUrls.contains(it.imageUrl)
                }
                if (toInsert.isNotEmpty()) {
                    dao.upsertPinsSafely(toInsert.mapIndexed { i, p ->
                        PinEntity.fromPinItem(p.copy(albumId = null), defaultBoard.id, i)
                    })
                }
                withContext(Dispatchers.Main) {
                    Toast.makeText(appCtx, "Saved to ${defaultBoard.title}", Toast.LENGTH_SHORT).show()
                }
            } catch (t: Throwable) {
                t.printStackTrace()
            }
        }

        setContent {
            MyApplicationTheme {
                FloatingShareDialog(
                    sharedLinks = sharedLinks,
                    sharedImageUris = sharedImageUris,
                    onClose = { finish() },
                    onSaveToSelected = { boards, extractMultiple ->
                        finish()
                        performSaveToBoards(sharedLinks, sharedImageUris, boards, extractMultiple)
                    },
                    onHoldBoard = { boardId, extractMultiple ->
                        finish()
                        performSaveToBoards(sharedLinks, sharedImageUris, listOf(boardId), extractMultiple)
                    }
                )
            }
        }
    }

    private fun performSaveToBoards(
        links: List<String>,
        uris: List<Uri>,
        targetBoardIds: List<String>,
        extractMultiple: Boolean
    ) {
        appScope.launch {
            try {
                autoSaveJob?.join()
                val appCtx = applicationContext
                val dao = AppDatabase.getDatabase(appCtx).boardDao()
                val allBoards = dao.getAllBoards()
                val defaultBoard = allBoards.firstOrNull { it.isDefault }
                    ?: allBoards.firstOrNull { it.id == "board_dump" }
                    ?: allBoards.firstOrNull()

                val pins: List<PinItem> = if (extractMultiple) {
                    resolveSharedItems(links, uris, true)
                } else {
                    resolvedPinsForSave ?: resolveSharedItems(links, uris, false)
                }

                if (defaultBoard != null && targetBoardIds.isNotEmpty() &&
                    !targetBoardIds.contains(defaultBoard.id)) {
                    dao.deletePinsFromBoard(defaultBoard.id, pins.map { it.id })
                }

                for (boardId in targetBoardIds) {
                    val existingIds = dao.getPinIdsForBoard(boardId).toSet()
                    val existingUrls = dao.getImageUrlsForBoard(boardId).toSet()
                    val toInsert = pins.filter {
                        !existingIds.contains(it.id) && !existingUrls.contains(it.imageUrl)
                    }
                    if (toInsert.isNotEmpty()) {
                        dao.upsertPinsSafely(toInsert.mapIndexed { i, p ->
                            PinEntity.fromPinItem(p.copy(albumId = null), boardId, i)
                        })
                    }
                }

                withContext(Dispatchers.Main) {
                    val names = allBoards.filter { targetBoardIds.contains(it.id) }
                        .joinToString(", ") { it.title }
                    Toast.makeText(appCtx, "Saved to $names", Toast.LENGTH_SHORT).show()
                }
            } catch (t: Throwable) {
                t.printStackTrace()
            }
        }
    }

    private suspend fun resolveSharedItems(
        links: List<String>,
        uris: List<Uri>,
        extractMultiple: Boolean
    ): List<PinItem> = withContext(Dispatchers.IO) {
        val pins = mutableListOf<PinItem>()
        for (link in links) {
            if (extractMultiple) {
                pins.addAll(ImageLinkResolver.resolveMultipleLinks(link))
            } else {
                pins.add(ImageLinkResolver.resolveLink(link))
            }
        }
        for (uri in uris) {
            val s = uri.toString()
            pins.add(PinItem(
                id = ImageLinkResolver.generateDeterministicPinId(s),
                title = "Shared Photo",
                imageUrl = s,
                thumbnailUrl = s,
                author = "Shared from device",
                sourceUrl = s,
                dateAddedMillis = System.currentTimeMillis()
            ))
        }
        pins
    }

    private suspend fun ensureDefaultBoardsExist(dao: BoardDao) {
        withContext(Dispatchers.IO) {
            if (dao.getBoardById("board_dump") == null) {
                dao.insertBoard(BoardEntity(
                    id = "board_dump", title = "Dump board", slug = "dump",
                    ownerUsername = "you", ownerDisplayName = "Dump board", ownerAvatarUrl = "",
                    pinCount = 0, followerCount = 0, boardUrl = "custom://dump",
                    description = "Default dump board", isCustom = true, customDomains = "",
                    isDefault = true, isSpecialNonDeletable = true
                ))
            }
            if (dao.getBoardById("board_my_save") == null) {
                dao.insertBoard(BoardEntity(
                    id = "board_my_save", title = "My Save", slug = "my-save",
                    ownerUsername = "you", ownerDisplayName = "My Save", ownerAvatarUrl = "",
                    pinCount = 0, followerCount = 0, boardUrl = "custom://my_save",
                    description = "Custom board for saved items", isCustom = true, customDomains = "",
                    isDefault = false, isSpecialNonDeletable = true
                ))
            }
            if (dao.getBoardById("board_favorites") == null) {
                dao.insertBoard(BoardEntity(
                    id = "board_favorites", title = "Favorites", slug = "favorites",
                    ownerUsername = "you", ownerDisplayName = "Favorites", ownerAvatarUrl = "",
                    pinCount = 0, followerCount = 0, boardUrl = "custom://favorites",
                    description = "Your favorite images", isCustom = true, customDomains = "",
                    isDefault = false, isSpecialNonDeletable = true
                ))
            }
        }
    }
}


@OptIn(ExperimentalLayoutApi::class, ExperimentalFoundationApi::class)
@Composable
private fun FloatingShareDialog(
    sharedLinks: List<String>,
    sharedImageUris: List<Uri>,
    onClose: () -> Unit,
    onSaveToSelected: (List<String>, Boolean) -> Unit,
    onHoldBoard: (String, Boolean) -> Unit
) {
    val context = LocalContext.current
    var boards by remember { mutableStateOf<List<BoardEntity>>(emptyList()) }
    var isLoadingBoards by remember { mutableStateOf(true) }
    val selectedBoardIds = remember { mutableStateListOf<String>() }
    var extractMultipleImages by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        withContext(Dispatchers.IO) {
            val dao = AppDatabase.getDatabase(context).boardDao()
            val list = dao.getAllBoards()
            boards = list
            val def = list.firstOrNull { it.isDefault }
                ?: list.firstOrNull { it.id == "board_dump" }
                ?: list.firstOrNull { it.id == "board_my_save" }
                ?: list.firstOrNull()
            def?.let { selectedBoardIds.add(it.id) }
            isLoadingBoards = false
        }
    }

    val itemCount = sharedLinks.size + sharedImageUris.size

    Box(
        modifier = Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.55f)),
        contentAlignment = Alignment.Center
    ) {
        Card(
            modifier = Modifier.fillMaxWidth(0.92f).wrapContentHeight()
                .testTag("floating_share_dialog_card"),
            shape = RoundedCornerShape(24.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            elevation = CardDefaults.cardElevation(defaultElevation = 12.dp)
        ) {
            Column(Modifier.fillMaxWidth().padding(20.dp)) {
                // Header
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier.size(36.dp).clip(CircleShape)
                                .background(PinterestRed.copy(alpha = 0.12f)),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(Icons.Default.Share, null, tint = PinterestRed, modifier = Modifier.size(20.dp))
                        }
                        Spacer(Modifier.width(10.dp))
                        Column {
                            Text("Save to PinBoard", fontWeight = FontWeight.Bold, fontSize = 17.sp)
                            Text(
                                if (itemCount > 1) "$itemCount items detected" else "1 item detected",
                                fontSize = 12.sp, color = PinterestTextSecondary
                            )
                        }
                    }
                    IconButton(onClick = onClose, modifier = Modifier.size(32.dp)) {
                        Icon(Icons.Default.Close, "Close", tint = PinterestTextSecondary, modifier = Modifier.size(18.dp))
                    }
                }

                Spacer(Modifier.height(10.dp))

                // Extract-multiple checkbox
                if (sharedLinks.isNotEmpty()) {
                    Row(
                        modifier = Modifier.fillMaxWidth()
                            .combinedClickable(
                                onClick = { extractMultipleImages = !extractMultipleImages },
                                onLongClick = { extractMultipleImages = !extractMultipleImages }
                            )
                            .padding(vertical = 4.dp)
                            .testTag("share_extract_multiple_checkbox"),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Checkbox(
                            checked = extractMultipleImages,
                            onCheckedChange = { extractMultipleImages = it },
                            colors = CheckboxDefaults.colors(checkedColor = PinterestRed)
                        )
                        Spacer(Modifier.width(4.dp))
                        Column {
                            Text("Add multiple main images from webpage",
                                fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                            Text("Extract content images in order",
                                fontSize = 10.sp, color = PinterestTextSecondary)
                        }
                    }
                }

                Spacer(Modifier.height(10.dp))
                Text(
                    "Tap to select · Hold to save to that board and exit",
                    fontSize = 11.sp, color = PinterestTextSecondary
                )
                Spacer(Modifier.height(8.dp))

                if (isLoadingBoards) {
                    Box(Modifier.fillMaxWidth().height(100.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(color = PinterestRed, strokeWidth = 2.dp)
                    }
                } else {
                    FlowRow(
                        modifier = Modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        boards.forEach { board ->
                            val isSelected = selectedBoardIds.contains(board.id)
                            Surface(
                                shape = RoundedCornerShape(16.dp),
                                color = if (isSelected) PinterestBlack else PinterestPillGray,
                                modifier = Modifier
                                    .combinedClickable(
                                        onClick = {
                                            if (isSelected) selectedBoardIds.remove(board.id)
                                            else selectedBoardIds.add(board.id)
                                        },
                                        onLongClick = { onHoldBoard(board.id, extractMultipleImages) }
                                    )
                                    .testTag("share_target_board_${board.id}")
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp)
                                ) {
                                    if (isSelected) {
                                        Icon(Icons.Default.Check, null, tint = Color.White, modifier = Modifier.size(14.dp))
                                        Spacer(Modifier.width(6.dp))
                                    }
                                    Text(
                                        board.title,
                                        fontSize = 13.sp,
                                        fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium,
                                        color = if (isSelected) Color.White else PinterestBlack,
                                        maxLines = 1, overflow = TextOverflow.Ellipsis
                                    )
                                    if (board.isDefault) {
                                        Spacer(Modifier.width(4.dp))
                                        Text("(Default)", fontSize = 10.sp,
                                            color = if (isSelected) Color.LightGray else PinterestTextSecondary)
                                    }
                                }
                            }
                        }
                    }
                }

                Spacer(Modifier.height(16.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        "Already in default board · change to move",
                        fontSize = 11.sp, color = PinterestTextSecondary
                    )
                    Button(
                        onClick = {
                            if (selectedBoardIds.isNotEmpty()) {
                                onSaveToSelected(selectedBoardIds.toList(), extractMultipleImages)
                            } else {
                                onClose()
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                        shape = RoundedCornerShape(20.dp),
                        modifier = Modifier.testTag("share_dialog_save_btn")
                    ) {
                        Text(
                            if (selectedBoardIds.size > 1) "Save to ${selectedBoardIds.size} Boards" else "Save",
                            color = Color.White, fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
        }
    }
}
