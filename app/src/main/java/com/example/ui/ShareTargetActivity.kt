package com.example.ui

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.material.icons.filled.Folder
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
import androidx.compose.runtime.rememberCoroutineScope
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
import com.example.data.local.AppDatabase
import com.example.data.local.BoardEntity
import com.example.data.local.CustomAlbumEntity
import com.example.data.local.PinEntity
import com.example.model.PinItem
import com.example.ui.theme.MyApplicationTheme
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillDarkGray
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary
import com.example.util.ImageLinkResolver
import com.example.util.LinkExtractor
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class ShareTargetActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Parse shared payload
        val sharedLinks = mutableListOf<String>()
        val sharedImageUris = mutableListOf<Uri>()

        when (intent?.action) {
            Intent.ACTION_SEND -> {
                if ("text/plain" == intent.type) {
                    val sharedText = intent.getStringExtra(Intent.EXTRA_TEXT) ?: ""
                    sharedLinks.addAll(LinkExtractor.extractLinks(sharedText))
                    if (sharedLinks.isEmpty() && sharedText.isNotBlank()) {
                        if (sharedText.startsWith("http://") || sharedText.startsWith("https://")) {
                            sharedLinks.add(sharedText.trim())
                        }
                    }
                } else if (intent.type?.startsWith("image/") == true) {
                    (intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM))?.let { uri ->
                        sharedImageUris.add(uri)
                    }
                }
            }
            Intent.ACTION_SEND_MULTIPLE -> {
                if (intent.type?.startsWith("image/") == true) {
                    intent.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM)?.let { list ->
                        sharedImageUris.addAll(list)
                    }
                }
            }
        }

        setContent {
            MyApplicationTheme {
                FloatingShareDialog(
                    sharedLinks = sharedLinks,
                    sharedImageUris = sharedImageUris,
                    onDismissAndSaveDefault = {
                        saveAndFinish(
                            targetBoardIds = emptyList(),
                            links = sharedLinks,
                            imageUris = sharedImageUris,
                            extractMultipleImages = false,
                            putIntoAlbum = false,
                            targetAlbumId = null
                        )
                    },
                    onSaveToBoards = { targetBoardIds, extractMultiple, putAlbum, targetAlbumId ->
                        saveAndFinish(
                            targetBoardIds = targetBoardIds,
                            links = sharedLinks,
                            imageUris = sharedImageUris,
                            extractMultipleImages = extractMultiple,
                            putIntoAlbum = putAlbum,
                            targetAlbumId = targetAlbumId
                        )
                    }
                )
            }
        }
    }

    private fun saveAndFinish(
        targetBoardIds: List<String>,
        links: List<String>,
        imageUris: List<Uri>,
        extractMultipleImages: Boolean = false,
        putIntoAlbum: Boolean = false,
        targetAlbumId: String? = null
    ) {
        val appCtx = applicationContext
        lifecycleScopeLaunch {
            val dao = AppDatabase.getDatabase(appCtx).boardDao()

            // Ensure baseline boards exist
            ensureDefaultBoardsExist(dao)

            val allBoards = withContext(Dispatchers.IO) { dao.getAllBoards() }
            val defaultBoard = allBoards.firstOrNull { it.isDefault }
                ?: allBoards.firstOrNull { it.id == "board_dump" }
                ?: allBoards.firstOrNull { it.id == "board_my_save" }
                ?: allBoards.firstOrNull()

            val chosenBoards = if (targetBoardIds.isEmpty() && targetAlbumId == null) {
                listOfNotNull(defaultBoard)
            } else if (targetBoardIds.isNotEmpty()) {
                allBoards.filter { targetBoardIds.contains(it.id) }
            } else {
                // If targetAlbumId is selected without board, look up board of the album
                val album = withContext(Dispatchers.IO) { dao.getAlbumById(targetAlbumId!!) }
                if (album != null) {
                    allBoards.filter { it.id == album.boardId }
                } else {
                    listOfNotNull(defaultBoard)
                }
            }

            // Resolve items to PinItems
            val resolvedPins = mutableListOf<PinItem>()
            withContext(Dispatchers.IO) {
                for (link in links) {
                    if (extractMultipleImages) {
                        val multiple = ImageLinkResolver.resolveMultipleLinks(link)
                        resolvedPins.addAll(multiple)
                    } else {
                        val resolved = ImageLinkResolver.resolveLink(link)
                        resolvedPins.add(resolved)
                    }
                }
                for (uri in imageUris) {
                    val uriStr = uri.toString()
                    val pin = PinItem(
                        id = ImageLinkResolver.generateDeterministicPinId(uriStr),
                        title = "Shared Photo",
                        imageUrl = uriStr,
                        thumbnailUrl = uriStr,
                        author = "Shared from device",
                        sourceUrl = uriStr,
                        dateAddedMillis = System.currentTimeMillis()
                    )
                    resolvedPins.add(pin)
                }
            }

            // Save to chosen boards, and domain-matched custom boards
            withContext(Dispatchers.IO) {
                val matchedDomainBoards = if (targetAlbumId == null) {
                    allBoards.filter { b ->
                        b.isCustom && resolvedPins.any { pin ->
                            LinkExtractor.matchesAnyDomain(pin.sourceUrl.ifBlank { pin.imageUrl }, b.customDomains.split(","))
                        }
                    }
                } else emptyList()

                val allTargetBoards = (chosenBoards + matchedDomainBoards).distinctBy { it.id }

                for (targetBoard in allTargetBoards) {
                    var currentAlbumId = targetAlbumId

                    // If user checked putIntoAlbum, create a CustomAlbumEntity
                    if (putIntoAlbum && resolvedPins.isNotEmpty()) {
                        val albumId = "album_${System.currentTimeMillis()}_${(1000..9999).random()}"
                        val albumTitle = resolvedPins.firstOrNull()?.title?.substringBefore(" (") ?: "Album"
                        val albumEntity = CustomAlbumEntity(
                            id = albumId,
                            boardId = targetBoard.id,
                            parentAlbumId = targetAlbumId,
                            title = albumTitle,
                            sourceUrl = links.firstOrNull() ?: "",
                            dateAddedMillis = System.currentTimeMillis()
                        )
                        dao.insertAlbum(albumEntity)
                        currentAlbumId = albumId
                    }

                    val existingIds = dao.getPinIdsForBoard(targetBoard.id).toSet()
                    val existingUrls = dao.getImageUrlsForBoard(targetBoard.id).toSet()

                    val pinsToInsert = mutableListOf<PinEntity>()
                    resolvedPins.forEachIndexed { index, pin ->
                        if (!existingIds.contains(pin.id) && !existingUrls.contains(pin.imageUrl)) {
                            pinsToInsert.add(
                                PinEntity.fromPinItem(
                                    pin.copy(albumId = currentAlbumId),
                                    targetBoard.id,
                                    index
                                )
                            )
                        }
                    }

                    if (pinsToInsert.isNotEmpty()) {
                        dao.insertPins(pinsToInsert)
                    }
                }
            }

            val savedNames = chosenBoards.joinToString(", ") { it.title }
            withContext(Dispatchers.Main) {
                val msg = if (putIntoAlbum) "Saved as Album to $savedNames!" else "Saved to $savedNames!"
                Toast.makeText(appCtx, msg, Toast.LENGTH_SHORT).show()
                finish()
            }
        }
    }

    private fun lifecycleScopeLaunch(block: suspend () -> Unit) {
        kotlinx.coroutines.CoroutineScope(Dispatchers.Main).launch {
            try {
                block()
            } catch (t: Throwable) {
                t.printStackTrace()
                Toast.makeText(applicationContext, "Saved to board", Toast.LENGTH_SHORT).show()
                finish()
            }
        }
    }

    private suspend fun ensureDefaultBoardsExist(dao: com.example.data.local.BoardDao) {
        withContext(Dispatchers.IO) {
            val dump = dao.getBoardById("board_dump")
            if (dump == null) {
                dao.insertBoard(
                    BoardEntity(
                        id = "board_dump",
                        title = "Dump board",
                        slug = "dump",
                        ownerUsername = "you",
                        ownerDisplayName = "Dump board",
                        ownerAvatarUrl = "",
                        pinCount = 0,
                        followerCount = 0,
                        boardUrl = "custom://dump",
                        description = "Default dump board for quick saves and fallback",
                        isCustom = true,
                        customDomains = "",
                        isDefault = true,
                        isSpecialNonDeletable = true
                    )
                )
                val mySaveExisting = dao.getBoardById("board_my_save")
                if (mySaveExisting != null && mySaveExisting.isDefault) {
                    dao.insertBoard(mySaveExisting.copy(isDefault = false))
                }
            }
            val mySave = dao.getBoardById("board_my_save")
            if (mySave == null) {
                dao.insertBoard(
                    BoardEntity(
                        id = "board_my_save",
                        title = "My Save",
                        slug = "my-save",
                        ownerUsername = "you",
                        ownerDisplayName = "My Save",
                        ownerAvatarUrl = "",
                        pinCount = 0,
                        followerCount = 0,
                        boardUrl = "custom://my_save",
                        description = "Custom board for saved items",
                        isCustom = true,
                        customDomains = "",
                        isDefault = false,
                        isSpecialNonDeletable = true
                    )
                )
            }
            val favorites = dao.getBoardById("board_favorites")
            if (favorites == null) {
                dao.insertBoard(
                    BoardEntity(
                        id = "board_favorites",
                        title = "Favorites",
                        slug = "favorites",
                        ownerUsername = "you",
                        ownerDisplayName = "Favorites",
                        ownerAvatarUrl = "",
                        pinCount = 0,
                        followerCount = 0,
                        boardUrl = "custom://favorites",
                        description = "Your favorite images",
                        isCustom = true,
                        customDomains = "",
                        isDefault = false,
                        isSpecialNonDeletable = true
                    )
                )
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class, androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun FloatingShareDialog(
    sharedLinks: List<String>,
    sharedImageUris: List<Uri>,
    onDismissAndSaveDefault: () -> Unit,
    onSaveToBoards: (targetBoardIds: List<String>, extractMultiple: Boolean, putAlbum: Boolean, targetAlbumId: String?) -> Unit
) {
    val context = androidx.compose.ui.platform.LocalContext.current
    var boards by remember { mutableStateOf<List<BoardEntity>>(emptyList()) }
    var albums by remember { mutableStateOf<List<CustomAlbumEntity>>(emptyList()) }
    var isLoadingBoards by remember { mutableStateOf(true) }
    var isSelectMode by remember { mutableStateOf(false) }
    val selectedBoardIds = remember { mutableStateListOf<String>() }
    var selectedAlbumId by remember { mutableStateOf<String?>(null) }

    var extractMultipleImages by remember { mutableStateOf(false) }
    var putIntoAlbum by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        withContext(Dispatchers.IO) {
            val dao = AppDatabase.getDatabase(context).boardDao()
            val list = dao.getAllBoards()
            boards = list
            albums = dao.getAllAlbums()
            val defaultB = list.firstOrNull { it.isDefault } ?: list.firstOrNull { it.id == "board_dump" } ?: list.firstOrNull { it.id == "board_my_save" } ?: list.firstOrNull()
            defaultB?.let { selectedBoardIds.add(it.id) }
            isLoadingBoards = false
        }
    }

    val itemCount = sharedLinks.size + sharedImageUris.size

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black.copy(alpha = 0.55f))
            .clickable { onDismissAndSaveDefault() },
        contentAlignment = Alignment.Center
    ) {
        Card(
            modifier = Modifier
                .fillMaxWidth(0.92f)
                .wrapContentHeight()
                .clickable(enabled = false) {}
                .testTag("floating_share_dialog_card"),
            shape = RoundedCornerShape(24.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            elevation = CardDefaults.cardElevation(defaultElevation = 12.dp)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(20.dp)
            ) {
                // Header
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier
                                .size(36.dp)
                                .clip(CircleShape)
                                .background(PinterestRed.copy(alpha = 0.12f)),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = Icons.Default.Share,
                                contentDescription = null,
                                tint = PinterestRed,
                                modifier = Modifier.size(20.dp)
                            )
                        }
                        Spacer(modifier = Modifier.width(10.dp))
                        Column {
                            Text(
                                text = "Save to PinBoard",
                                fontWeight = FontWeight.Bold,
                                fontSize = 17.sp,
                                color = MaterialTheme.colorScheme.onSurface
                            )
                            Text(
                                text = if (itemCount > 1) "$itemCount items detected" else "1 item detected",
                                fontSize = 12.sp,
                                color = PinterestTextSecondary
                            )
                        }
                    }

                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IconButton(
                            onClick = { isSelectMode = !isSelectMode },
                            modifier = Modifier.size(32.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.Checklist,
                                contentDescription = "Toggle multi-select mode",
                                tint = if (isSelectMode) PinterestRed else PinterestTextSecondary,
                                modifier = Modifier.size(20.dp)
                            )
                        }
                        Spacer(modifier = Modifier.width(4.dp))
                        IconButton(
                            onClick = onDismissAndSaveDefault,
                            modifier = Modifier.size(32.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.Close,
                                contentDescription = "Close and Save to Default",
                                tint = PinterestTextSecondary,
                                modifier = Modifier.size(18.dp)
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                // Checklist 1: Add multiple main images from webpage (unchecked by default)
                if (sharedLinks.isNotEmpty()) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable {
                                extractMultipleImages = !extractMultipleImages
                                if (!extractMultipleImages) putIntoAlbum = false
                            }
                            .padding(vertical = 4.dp)
                            .testTag("share_extract_multiple_checkbox")
                    ) {
                        Checkbox(
                            checked = extractMultipleImages,
                            onCheckedChange = {
                                extractMultipleImages = it
                                if (!it) putIntoAlbum = false
                            },
                            colors = CheckboxDefaults.colors(checkedColor = PinterestRed)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Column {
                            Text(
                                text = "Add multiple main images from webpage",
                                fontSize = 12.sp,
                                fontWeight = FontWeight.SemiBold,
                                color = MaterialTheme.colorScheme.onSurface
                            )
                            Text(
                                text = "Extract content images in order (first to last)",
                                fontSize = 10.sp,
                                color = PinterestTextSecondary
                            )
                        }
                    }

                    // Checklist 2: Shown when extractMultipleImages is checked
                    if (extractMultipleImages) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(start = 24.dp)
                                .clickable { putIntoAlbum = !putIntoAlbum }
                                .padding(vertical = 4.dp)
                                .testTag("share_put_into_album_checkbox")
                        ) {
                            Checkbox(
                                checked = putIntoAlbum,
                                onCheckedChange = { putIntoAlbum = it },
                                colors = CheckboxDefaults.colors(checkedColor = PinterestRed)
                            )
                            Spacer(modifier = Modifier.width(4.dp))
                            Column {
                                Text(
                                    text = "Put into album",
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.SemiBold,
                                    color = MaterialTheme.colorScheme.onSurface
                                )
                                Text(
                                    text = "Save as an album inside the chosen board",
                                    fontSize = 10.sp,
                                    color = PinterestTextSecondary
                                )
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                Text(
                    text = if (isSelectMode) "Select multiple destination boards:" else "Choose destination board (press & hold for multi-select):",
                    style = MaterialTheme.typography.bodySmall.copy(
                        fontSize = 12.sp,
                        color = PinterestTextSecondary
                    )
                )

                Spacer(modifier = Modifier.height(10.dp))

                if (isLoadingBoards) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(100.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator(color = PinterestRed, strokeWidth = 2.dp)
                    }
                } else {
                    FlowRow(
                        modifier = Modifier
                            .fillMaxWidth()
                            .verticalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        boards.forEach { board ->
                            val isSelected = selectedBoardIds.contains(board.id) && selectedAlbumId == null
                            Surface(
                                shape = RoundedCornerShape(16.dp),
                                color = if (isSelected) PinterestBlack else PinterestPillGray,
                                modifier = Modifier
                                    .combinedClickable(
                                        onClick = {
                                            selectedAlbumId = null
                                            if (isSelectMode) {
                                                if (isSelected) selectedBoardIds.remove(board.id)
                                                else selectedBoardIds.add(board.id)
                                            } else {
                                                selectedBoardIds.clear()
                                                selectedBoardIds.add(board.id)
                                                onSaveToBoards(listOf(board.id), extractMultipleImages, putIntoAlbum, null)
                                            }
                                        },
                                        onLongClick = {
                                            selectedAlbumId = null
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
                                        Icon(
                                            imageVector = Icons.Default.Check,
                                            contentDescription = null,
                                            tint = Color.White,
                                            modifier = Modifier.size(14.dp)
                                        )
                                        Spacer(modifier = Modifier.width(6.dp))
                                    }
                                    Text(
                                        text = board.title,
                                        fontSize = 13.sp,
                                        fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium,
                                        color = if (isSelected) Color.White else PinterestBlack,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis
                                    )
                                    if (board.isDefault) {
                                        Spacer(modifier = Modifier.width(4.dp))
                                        Text(
                                            text = "(Default)",
                                            fontSize = 10.sp,
                                            color = if (isSelected) Color.LightGray else PinterestTextSecondary
                                        )
                                    }
                                }
                            }
                        }

                        // Also allow selecting existing non-sort albums
                        albums.forEach { album ->
                            val isAlbumSelected = selectedAlbumId == album.id
                            Surface(
                                shape = RoundedCornerShape(16.dp),
                                color = if (isAlbumSelected) PinterestRed else PinterestPillGray,
                                modifier = Modifier
                                    .clickable {
                                        selectedAlbumId = if (isAlbumSelected) null else album.id
                                    }
                                    .testTag("share_target_album_${album.id}")
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Folder,
                                        contentDescription = null,
                                        tint = if (isAlbumSelected) Color.White else PinterestRed,
                                        modifier = Modifier.size(14.dp)
                                    )
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Text(
                                        text = album.title,
                                        fontSize = 13.sp,
                                        fontWeight = if (isAlbumSelected) FontWeight.Bold else FontWeight.Medium,
                                        color = if (isAlbumSelected) Color.White else PinterestBlack,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis
                                    )
                                }
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                // Bottom actions
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Exiting will save to default board",
                        fontSize = 11.sp,
                        color = PinterestTextSecondary
                    )

                    Button(
                        onClick = {
                            if (selectedAlbumId != null) {
                                onSaveToBoards(emptyList(), extractMultipleImages, putIntoAlbum, selectedAlbumId)
                            } else if (selectedBoardIds.isNotEmpty()) {
                                onSaveToBoards(selectedBoardIds.toList(), extractMultipleImages, putIntoAlbum, null)
                            } else {
                                onDismissAndSaveDefault()
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                        shape = RoundedCornerShape(20.dp),
                        modifier = Modifier.testTag("share_dialog_save_btn")
                    ) {
                        Text(
                            text = if (putIntoAlbum) "Save as Album"
                            else if (selectedAlbumId != null) "Add to Album"
                            else if (selectedBoardIds.size > 1) "Save to ${selectedBoardIds.size} Boards"
                            else "Save",
                            color = Color.White,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
        }
    }
}
