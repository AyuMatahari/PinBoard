package com.example.ui

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
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
import androidx.compose.material.icons.filled.Checklist
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
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.lifecycleScope
import com.example.data.local.AppDatabase
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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext


class ShareTargetActivity : ComponentActivity() {

    @Volatile
    private var autoSaveJob: Job? = null

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

        // Auto-save to default board immediately (async).
        autoSaveJob = lifecycleScope.launch(Dispatchers.IO) {
            autoSaveToDefaultBoardSync(sharedLinks, sharedImageUris)
        }

        setContent {
            MyApplicationTheme {
                FloatingShareDialog(
                    sharedLinks = sharedLinks,
                    sharedImageUris = sharedImageUris,
                    onClose = { finish() },
                    onSaveToBoards = { targetBoardIds, extractMultiple ->
                        saveToBoards(
                            targetBoardIds = targetBoardIds,
                            links = sharedLinks,
                            imageUris = sharedImageUris,
                            extractMultipleImages = extractMultiple
                        )
                    }
                )
            }
        }
    }

    private suspend fun autoSaveToDefaultBoardSync(links: List<String>, imageUris: List<Uri>) {
        try {
            val dao = AppDatabase.getDatabase(applicationContext).boardDao()
            ensureDefaultBoardsExist(dao)
            val allBoards = dao.getAllBoards()
            val defaultBoard = allBoards.firstOrNull { it.isDefault }
                ?: allBoards.firstOrNull { it.id == "board_dump" }
                ?: allBoards.firstOrNull() ?: return

            val resolvedPins = mutableListOf<PinItem>()
            for (link in links) resolvedPins.add(ImageLinkResolver.resolveLink(link, defaultBoard.title))
            for (uri in imageUris) {
                val s = uri.toString()
                resolvedPins.add(PinItem(
                    id = ImageLinkResolver.generateDeterministicPinId(s),
                    title = "Shared Photo", imageUrl = s, thumbnailUrl = s,
                    author = "Shared from device", sourceUrl = s,
                    dateAddedMillis = System.currentTimeMillis()
                ))
            }
            val existingIds = dao.getPinIdsForBoard(defaultBoard.id).toSet()
            val existingUrls = dao.getImageUrlsForBoard(defaultBoard.id).toSet()
            val toInsert = resolvedPins.filter {
                !existingIds.contains(it.id) && !existingUrls.contains(it.imageUrl)
            }
            if (toInsert.isNotEmpty()) {
                dao.insertPins(toInsert.mapIndexed { i, p -> PinEntity.fromPinItem(p, defaultBoard.id, i) })
            }
            withContext(Dispatchers.Main) {
                Toast.makeText(
                    this@ShareTargetActivity,
                    "Saved to ${defaultBoard.title}",
                    Toast.LENGTH_SHORT
                ).show()
            }
        } catch (t: Throwable) {
            t.printStackTrace()
        }
    }

    private fun saveToBoards(
        targetBoardIds: List<String>,
        links: List<String>,
        imageUris: List<Uri>,
        extractMultipleImages: Boolean
    ) {
        lifecycleScope.launch {
            try {
                autoSaveJob?.join()
                withContext(Dispatchers.IO) {
                    val appCtx = applicationContext
                    val dao = AppDatabase.getDatabase(appCtx).boardDao()
                    ensureDefaultBoardsExist(dao)
                    val allBoards = dao.getAllBoards()
                    val defaultBoard = allBoards.firstOrNull { it.isDefault }
                        ?: allBoards.firstOrNull { it.id == "board_dump" }
                        ?: allBoards.firstOrNull()

                    val chosenBoards = if (targetBoardIds.isEmpty()) {
                        listOfNotNull(defaultBoard)
                    } else {
                        allBoards.filter { targetBoardIds.contains(it.id) }
                    }

                    val resolvedPins = mutableListOf<PinItem>()
                    for (link in links) {
                        if (extractMultipleImages) {
                            resolvedPins.addAll(ImageLinkResolver.resolveMultipleLinks(link))
                        } else {
                            resolvedPins.add(ImageLinkResolver.resolveLink(link))
                        }
                    }
                    for (uri in imageUris) {
                        val s = uri.toString()
                        resolvedPins.add(PinItem(
                            id = ImageLinkResolver.generateDeterministicPinId(s),
                            title = "Shared Photo", imageUrl = s, thumbnailUrl = s,
                            author = "Shared from device", sourceUrl = s,
                            dateAddedMillis = System.currentTimeMillis()
                        ))
                    }

                    val matchedDomainBoards = allBoards.filter { b ->
                        b.isCustom && resolvedPins.any { pin ->
                            LinkExtractor.matchesAnyDomain(
                                pin.sourceUrl.ifBlank { pin.imageUrl },
                                b.customDomains.split(",")
                            )
                        }
                    }
                    val allTargets = (chosenBoards + matchedDomainBoards).distinctBy { it.id }
                    val defaultId = defaultBoard?.id

                    // If user explicitly picked boards that don't include default, remove from default
                    if (defaultId != null && targetBoardIds.isNotEmpty() && !targetBoardIds.contains(defaultId)) {
                        dao.deletePinsFromBoard(defaultId, resolvedPins.map { it.id })
                    }

                    for (target in allTargets) {
                        val existingIds = dao.getPinIdsForBoard(target.id).toSet()
                        val existingUrls = dao.getImageUrlsForBoard(target.id).toSet()
                        val toInsert = mutableListOf<PinEntity>()
                        resolvedPins.forEachIndexed { i, p ->
                            if (!existingIds.contains(p.id) && !existingUrls.contains(p.imageUrl)) {
                                toInsert.add(PinEntity.fromPinItem(p, target.id, i))
                            }
                        }
                        if (toInsert.isNotEmpty()) dao.insertPins(toInsert)
                    }
                }
                withContext(Dispatchers.Main) {
                    Toast.makeText(applicationContext, "Saved", Toast.LENGTH_SHORT).show()
                    finish()
                }
            } catch (t: Throwable) {
                t.printStackTrace()
                withContext(Dispatchers.Main) { finish() }
            }
        }
    }

    private suspend fun ensureDefaultBoardsExist(dao: com.example.data.local.BoardDao) {
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


@OptIn(ExperimentalLayoutApi::class, androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun FloatingShareDialog(
    sharedLinks: List<String>,
    sharedImageUris: List<Uri>,
    onClose: () -> Unit,
    onSaveToBoards: (targetBoardIds: List<String>, extractMultiple: Boolean) -> Unit
) {
    val context = androidx.compose.ui.platform.LocalContext.current
    var boards by remember { mutableStateOf<List<BoardEntity>>(emptyList()) }
    var isLoadingBoards by remember { mutableStateOf(true) }
    var isSelectMode by remember { mutableStateOf(false) }
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
            Column(modifier = Modifier.fillMaxWidth().padding(20.dp)) {
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
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IconButton(onClick = { isSelectMode = !isSelectMode }, modifier = Modifier.size(32.dp)) {
                            Icon(Icons.Default.Checklist, "Toggle multi-select",
                                tint = if (isSelectMode) PinterestRed else PinterestTextSecondary,
                                modifier = Modifier.size(20.dp))
                        }
                        IconButton(onClick = onClose, modifier = Modifier.size(32.dp)) {
                            Icon(Icons.Default.Close, "Close",
                                tint = PinterestTextSecondary, modifier = Modifier.size(18.dp))
                        }
                    }
                }

                Spacer(Modifier.height(10.dp))

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
                    if (isSelectMode) "Select multiple destination boards:"
                    else "Choose destination board (already saved to default):",
                    fontSize = 12.sp, color = PinterestTextSecondary
                )
                Spacer(Modifier.height(10.dp))

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
                                            if (isSelectMode) {
                                                if (isSelected) selectedBoardIds.remove(board.id)
                                                else selectedBoardIds.add(board.id)
                                            } else {
                                                selectedBoardIds.clear()
                                                selectedBoardIds.add(board.id)
                                                onSaveToBoards(listOf(board.id), extractMultipleImages)
                                            }
                                        },
                                        onLongClick = {
                                            isSelectMode = true
                                            if (isSelected) selectedBoardIds.remove(board.id)
                                            else selectedBoardIds.add(board.id)
                                        }
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
                    Text("X exits · already in default", fontSize = 11.sp, color = PinterestTextSecondary)
                    Button(
                        onClick = {
                            if (selectedBoardIds.isNotEmpty()) {
                                onSaveToBoards(selectedBoardIds.toList(), extractMultipleImages)
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
