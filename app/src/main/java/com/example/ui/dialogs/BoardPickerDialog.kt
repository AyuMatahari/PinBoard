package com.example.ui.dialogs

// v3-pill-drag
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Link
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.PointerInputChange
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.zIndex
import com.example.model.BoardHistoryItem
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary


@OptIn(ExperimentalLayoutApi::class, ExperimentalFoundationApi::class)
@Composable
fun BoardPickerDialog(
    isOpen: Boolean,
    boards: List<BoardHistoryItem>,
    currentBoardUrl: String?,
    onDismiss: () -> Unit,
    onSelectBoard: (String) -> Unit,
    onReorderBoards: (List<BoardHistoryItem>) -> Unit = {}
) {
    if (!isOpen) return

    var localBoards by remember(boards) { mutableStateOf(boards) }
    var draggedUrl by remember { mutableStateOf<String?>(null) }
    var dragOffset by remember { mutableStateOf(Offset.Zero) }
    var suppressClickUntil by remember { mutableStateOf(0L) }
    val itemBounds = remember { mutableMapOf<String, Rect>() }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Column {
                Text("Switch board", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                Spacer(Modifier.height(4.dp))
                Text(
                    "Tap to open · Hold to drag reorder",
                    fontSize = 11.sp,
                    color = PinterestTextSecondary
                )
            }
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 500.dp)
                    .verticalScroll(rememberScrollState())
            ) {
                FlowRow(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    localBoards.forEach { item ->
                        val isCurrent = currentBoardUrl?.trimEnd('/')
                            ?.equals(item.url.trimEnd('/'), ignoreCase = true) == true
                        val isDragged = draggedUrl == item.url

                        val isFav = item.boardId == "board_favorites" || item.url.contains("favorites")
                        val isMySave = item.boardId == "board_my_save" || item.url.contains("my_save")
                        val isDump = item.boardId == "board_dump" || item.url.contains("dump")

                        Surface(
                            shape = RoundedCornerShape(20.dp),
                            color = if (isCurrent) PinterestRed else PinterestPillGray,
                            modifier = Modifier
                                .onGloballyPositioned { coords ->
                                    itemBounds[item.url] = coords.boundsInRoot()
                                }
                                .graphicsLayer {
                                    if (isDragged) {
                                        translationX = dragOffset.x
                                        translationY = dragOffset.y
                                        shadowElevation = 12.dp.toPx()
                                        scaleX = 1.06f
                                        scaleY = 1.06f
                                        alpha = 0.95f
                                    }
                                }
                                .zIndex(if (isDragged) 1f else 0f)
                                .pointerInput(item.url, localBoards.size) {
                                    detectDragGesturesAfterLongPress(
                                        onDragStart = {
                                            draggedUrl = item.url
                                            dragOffset = Offset.Zero
                                        },
                                        onDrag = { change: PointerInputChange, amount: Offset ->
                                            change.consume()
                                            dragOffset += amount
                                        },
                                        onDragEnd = {
                                            val current = draggedUrl
                                            draggedUrl = null
                                            suppressClickUntil = System.currentTimeMillis() + 250
                                            if (current != null) {
                                                val draggedBounds = itemBounds[current]
                                                if (draggedBounds != null && dragOffset.getDistance() > 8f) {
                                                    val finalCenter = draggedBounds.center + dragOffset
                                                    val target = itemBounds.entries
                                                        .filter { it.key != current }
                                                        .minByOrNull { (it.value.center - finalCenter).getDistance() }
                                                    if (target != null) {
                                                        val fromIdx = localBoards.indexOfFirst { it.url == current }
                                                        val toIdx = localBoards.indexOfFirst { it.url == target.key }
                                                        if (fromIdx >= 0 && toIdx >= 0 && fromIdx != toIdx) {
                                                            val newList = localBoards.toMutableList()
                                                            val moved = newList.removeAt(fromIdx)
                                                            newList.add(toIdx, moved)
                                                            localBoards = newList
                                                            onReorderBoards(newList)
                                                        }
                                                    }
                                                }
                                            }
                                            dragOffset = Offset.Zero
                                        },
                                        onDragCancel = {
                                            draggedUrl = null
                                            dragOffset = Offset.Zero
                                            suppressClickUntil = System.currentTimeMillis() + 250
                                        }
                                    )
                                }
                                .clickable {
                                    if (System.currentTimeMillis() > suppressClickUntil) {
                                        onSelectBoard(item.url)
                                        onDismiss()
                                    }
                                }
                                .testTag("board_picker_pill_${item.url.hashCode()}")
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp)
                            ) {
                                Icon(
                                    imageVector = when {
                                        isFav -> Icons.Default.Favorite
                                        isMySave -> Icons.Default.Bookmark
                                        isDump -> Icons.Default.Folder
                                        item.isCustom -> Icons.Default.Folder
                                        else -> Icons.Default.Link
                                    },
                                    contentDescription = null,
                                    tint = if (isCurrent) Color.White else PinterestRed,
                                    modifier = Modifier.size(13.dp)
                                )
                                Spacer(Modifier.width(6.dp))
                                Text(
                                    text = item.title.ifBlank { "Board" },
                                    fontSize = 13.sp,
                                    fontWeight = if (isCurrent) FontWeight.Bold else FontWeight.Medium,
                                    color = if (isCurrent) Color.White else PinterestBlack
                                )
                                if (item.isCustom && !isFav && !isMySave && !isDump) {
                                    Spacer(Modifier.width(4.dp))
                                    Text(
                                        text = "· Custom",
                                        fontSize = 10.sp,
                                        color = if (isCurrent) Color.White.copy(alpha = 0.7f) else PinterestTextSecondary
                                    )
                                }
                            }
                        }
                    }
                }

                if (localBoards.isEmpty()) {
                    Spacer(Modifier.height(12.dp))
                    Text("No boards available.", fontSize = 12.sp, color = PinterestTextSecondary)
                }
            }
        },
        confirmButton = {},
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Close", color = PinterestBlack) }
        },
        shape = RoundedCornerShape(20.dp)
    )
}
