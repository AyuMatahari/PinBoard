package com.example.ui.dialogs

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.material.icons.filled.DragHandle
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Link
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
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
import kotlin.math.roundToInt


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

    // Local mutable copy — the source of truth during the dialog lifetime
    var localBoards by remember(boards) { mutableStateOf(boards) }
    var draggedIndex by remember { mutableStateOf<Int?>(null) }
    var accumulatedDrag by remember { mutableFloatStateOf(0f) }

    val density = LocalDensity.current
    val itemHeightDp = 56.dp
    val itemHeightPx = with(density) { itemHeightDp.toPx() }

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
                localBoards.forEachIndexed { index, item ->
                    val isCurrent = currentBoardUrl?.trimEnd('/')
                        ?.equals(item.url.trimEnd('/'), ignoreCase = true) == true
                    val isDragged = draggedIndex == index

                    val isFav = item.boardId == "board_favorites" || item.url.contains("favorites")
                    val isMySave = item.boardId == "board_my_save" || item.url.contains("my_save")
                    val isDump = item.boardId == "board_dump" || item.url.contains("dump")

                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(itemHeightDp)
                            .padding(vertical = 2.dp)
                            .graphicsLayer {
                                if (isDragged) {
                                    translationY = accumulatedDrag
                                    shadowElevation = 12.dp.toPx()
                                    alpha = 0.95f
                                    scaleX = 1.02f
                                    scaleY = 1.02f
                                }
                            }
                            .zIndex(if (isDragged) 1f else 0f)
                            .pointerInput(item.url, localBoards.size) {
                                detectDragGesturesAfterLongPress(
                                    onDragStart = {
                                        draggedIndex = index
                                        accumulatedDrag = 0f
                                    },
                                    onDrag = { change, drag ->
                                        change.consume()
                                        accumulatedDrag += drag.dy
                                    },
                                    onDragEnd = {
                                        val offset = (accumulatedDrag / itemHeightPx).roundToInt()
                                        val targetIdx = (index + offset)
                                            .coerceIn(0, localBoards.size - 1)
                                        if (targetIdx != index) {
                                            val newList = localBoards.toMutableList()
                                            val moved = newList.removeAt(index)
                                            newList.add(targetIdx, moved)
                                            localBoards = newList
                                            onReorderBoards(newList)
                                        }
                                        draggedIndex = null
                                        accumulatedDrag = 0f
                                    },
                                    onDragCancel = {
                                        draggedIndex = null
                                        accumulatedDrag = 0f
                                    }
                                )
                            }
                    ) {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    if (draggedIndex == null) {
                                        onSelectBoard(item.url)
                                        onDismiss()
                                    }
                                }
                                .testTag("board_picker_pill_${item.url.hashCode()}")
                                .background(
                                    color = if (isCurrent) PinterestRed else PinterestPillGray,
                                    shape = RoundedCornerShape(24.dp)
                                )
                                .padding(horizontal = 14.dp, vertical = 12.dp),
                            contentAlignment = Alignment.CenterStart
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.Start
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
                                    modifier = Modifier.size(14.dp)
                                )
                                Spacer(Modifier.width(8.dp))
                                Text(
                                    text = item.title.ifBlank { "Board" },
                                    fontSize = 13.sp,
                                    fontWeight = if (isCurrent) FontWeight.Bold else FontWeight.Medium,
                                    color = if (isCurrent) Color.White else PinterestBlack,
                                    modifier = Modifier.weight(1f)
                                )
                                if (item.isCustom && !isFav && !isMySave && !isDump) {
                                    Text(
                                        text = "· Custom",
                                        fontSize = 10.sp,
                                        color = if (isCurrent) Color.White.copy(alpha = 0.7f) else PinterestTextSecondary
                                    )
                                    Spacer(Modifier.width(6.dp))
                                }
                                Icon(
                                    imageVector = Icons.Default.DragHandle,
                                    contentDescription = "Drag to reorder",
                                    tint = if (isCurrent) Color.White.copy(alpha = 0.7f) else PinterestTextSecondary,
                                    modifier = Modifier.size(16.dp)
                                )
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
