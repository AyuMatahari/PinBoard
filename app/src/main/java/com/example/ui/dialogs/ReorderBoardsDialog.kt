package com.example.ui.dialogs

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDownward
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.SwapVert
import androidx.compose.material.icons.filled.SortByAlpha
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.model.BoardHistoryItem
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary

enum class BoardSortPreset {
    NONE,
    ALPHABET_ASC,
    ALPHABET_DESC,
    DATE_NEWEST,
    DATE_OLDEST,
    ACTIVITY_HIGH,
    ACTIVITY_LOW
}

@Composable
fun ReorderBoardsDialog(
    isOpen: Boolean,
    boards: List<BoardHistoryItem>,
    forceBoardTypeOrder: Boolean,
    onDismiss: () -> Unit,
    onSaveReorderedBoards: (reorderedList: List<BoardHistoryItem>, forceTypeOrder: Boolean) -> Unit
) {
    if (!isOpen) return

    var forceTypeOrderState by remember(forceBoardTypeOrder) { mutableStateOf(forceBoardTypeOrder) }
    val currentList = remember(boards) { mutableStateListOf<BoardHistoryItem>().apply { addAll(boards) } }

    fun applyBoardTypeConstraints(input: List<BoardHistoryItem>): List<BoardHistoryItem> {
        if (!forceTypeOrderState) return input

        // Tier 1: Pinterest Boards
        val pinterest = input.filter {
            !it.isCustom && it.boardId != "board_dump" && it.boardId != "board_my_save" && it.boardId != "board_favorites" &&
                    !it.url.startsWith("custom://")
        }

        // Tier 2: Permanent custom boards strictly ordered: 1. Dump, 2. My Save, 3. Favorites
        val dump = input.firstOrNull { it.boardId == "board_dump" || it.url == "custom://dump" }
        val mySave = input.firstOrNull { it.boardId == "board_my_save" || it.url == "custom://my_save" }
        val fav = input.firstOrNull { it.boardId == "board_favorites" || it.url == "custom://favorites" }
        val permanent = listOfNotNull(dump, mySave, fav)

        // Tier 3: Other Custom Boards
        val custom = input.filter {
            it.isCustom && it.boardId != "board_dump" && it.boardId != "board_my_save" && it.boardId != "board_favorites" &&
                    it.url != "custom://dump" && it.url != "custom://my_save" && it.url != "custom://favorites"
        }

        return pinterest + permanent + custom
    }

    fun sortList(preset: BoardSortPreset) {
        val sorted = when (preset) {
            BoardSortPreset.NONE -> currentList.toList()
            BoardSortPreset.ALPHABET_ASC -> currentList.sortedBy { it.title.lowercase() }
            BoardSortPreset.ALPHABET_DESC -> currentList.sortedByDescending { it.title.lowercase() }
            BoardSortPreset.DATE_NEWEST -> currentList.sortedByDescending { it.timestamp }
            BoardSortPreset.DATE_OLDEST -> currentList.sortedBy { it.timestamp }
            BoardSortPreset.ACTIVITY_HIGH -> currentList.sortedByDescending { it.pinCount }
            BoardSortPreset.ACTIVITY_LOW -> currentList.sortedBy { it.pinCount }
        }
        val constrained = if (forceTypeOrderState) applyBoardTypeConstraints(sorted) else sorted
        currentList.clear()
        currentList.addAll(constrained)
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Default.SwapVert,
                    contentDescription = null,
                    tint = PinterestRed,
                    modifier = Modifier.size(24.dp)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "Reorder Boards",
                    fontWeight = FontWeight.Bold,
                    fontSize = 18.sp
                )
            }
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
            ) {
                Text(
                    text = "Rearrange the boards list order or sort them automatically.",
                    fontSize = 12.sp,
                    color = PinterestTextSecondary
                )

                Spacer(modifier = Modifier.height(10.dp))

                // Force Board Type Order Checklist (Requirement 6)
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = PinterestPillGray,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable {
                                forceTypeOrderState = !forceTypeOrderState
                                if (forceTypeOrderState) {
                                    val constrained = applyBoardTypeConstraints(currentList.toList())
                                    currentList.clear()
                                    currentList.addAll(constrained)
                                }
                            }
                            .padding(horizontal = 10.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Checkbox(
                            checked = forceTypeOrderState,
                            onCheckedChange = { checked ->
                                forceTypeOrderState = checked
                                if (checked) {
                                    val constrained = applyBoardTypeConstraints(currentList.toList())
                                    currentList.clear()
                                    currentList.addAll(constrained)
                                }
                            },
                            colors = CheckboxDefaults.colors(checkedColor = PinterestRed),
                            modifier = Modifier.testTag("force_board_type_order_checkbox")
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "Force boards type order",
                                fontWeight = FontWeight.Bold,
                                fontSize = 13.sp,
                                color = PinterestBlack
                            )
                            Text(
                                text = "Hold order: 1. Pinterest  2. Permanent (Dump, My Save, Favorites)  3. Custom boards",
                                fontSize = 10.sp,
                                color = PinterestTextSecondary,
                                lineHeight = 13.sp
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                // Sort Preset Quick Buttons
                Text(
                    text = "SORT BY PRESET",
                    style = MaterialTheme.typography.labelSmall.copy(
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 0.6.sp,
                        fontSize = 10.sp,
                        color = PinterestTextSecondary
                    )
                )

                Spacer(modifier = Modifier.height(6.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Surface(
                        shape = RoundedCornerShape(14.dp),
                        color = PinterestPillGray,
                        modifier = Modifier
                            .weight(1f)
                            .clickable { sortList(BoardSortPreset.ALPHABET_ASC) }
                            .testTag("sort_alphabet_asc_btn")
                    ) {
                        Text(
                            text = "A-Z",
                            fontSize = 11.sp,
                            fontWeight = FontWeight.SemiBold,
                            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                            modifier = Modifier.padding(vertical = 6.dp)
                        )
                    }

                    Surface(
                        shape = RoundedCornerShape(14.dp),
                        color = PinterestPillGray,
                        modifier = Modifier
                            .weight(1f)
                            .clickable { sortList(BoardSortPreset.ALPHABET_DESC) }
                            .testTag("sort_alphabet_desc_btn")
                    ) {
                        Text(
                            text = "Z-A",
                            fontSize = 11.sp,
                            fontWeight = FontWeight.SemiBold,
                            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                            modifier = Modifier.padding(vertical = 6.dp)
                        )
                    }

                    Surface(
                        shape = RoundedCornerShape(14.dp),
                        color = PinterestPillGray,
                        modifier = Modifier
                            .weight(1.3f)
                            .clickable { sortList(BoardSortPreset.DATE_NEWEST) }
                            .testTag("sort_date_newest_btn")
                    ) {
                        Text(
                            text = "Date (New)",
                            fontSize = 11.sp,
                            fontWeight = FontWeight.SemiBold,
                            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                            modifier = Modifier.padding(vertical = 6.dp)
                        )
                    }

                    Surface(
                        shape = RoundedCornerShape(14.dp),
                        color = PinterestPillGray,
                        modifier = Modifier
                            .weight(1.3f)
                            .clickable { sortList(BoardSortPreset.ACTIVITY_HIGH) }
                            .testTag("sort_activity_high_btn")
                    ) {
                        Text(
                            text = "Active",
                            fontSize = 11.sp,
                            fontWeight = FontWeight.SemiBold,
                            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                            modifier = Modifier.padding(vertical = 6.dp)
                        )
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))
                HorizontalDivider()
                Spacer(modifier = Modifier.height(8.dp))

                // Board items list with manual move Up / Down
                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 240.dp)
                ) {
                    itemsIndexed(
                        items = currentList,
                        key = { idx, item -> "${item.url}_$idx" }
                    ) { index, item ->
                        val isPermanent = item.boardId == "board_dump" || item.boardId == "board_my_save" || item.boardId == "board_favorites"
                        Surface(
                            shape = RoundedCornerShape(10.dp),
                            color = PinterestPillGray,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 2.dp)
                                .testTag("reorder_board_item_$index")
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(horizontal = 8.dp, vertical = 6.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "${index + 1}.",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = PinterestTextSecondary,
                                    modifier = Modifier.width(22.dp)
                                )

                                Icon(
                                    imageVector = when {
                                        item.boardId == "board_favorites" -> Icons.Default.Favorite
                                        item.boardId == "board_my_save" -> Icons.Default.Bookmark
                                        item.boardId == "board_dump" -> Icons.Default.Folder
                                        item.isCustom -> Icons.Default.Folder
                                        else -> Icons.Default.Link
                                    },
                                    contentDescription = null,
                                    tint = PinterestRed,
                                    modifier = Modifier.size(14.dp)
                                )

                                Spacer(modifier = Modifier.width(6.dp))

                                Column(modifier = Modifier.weight(1f)) {
                                    Text(
                                        text = item.title,
                                        fontWeight = FontWeight.SemiBold,
                                        fontSize = 12.sp,
                                        color = PinterestBlack,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis
                                    )
                                    Text(
                                        text = if (isPermanent) "Permanent" else if (item.isCustom) "Custom" else "Pinterest",
                                        fontSize = 10.sp,
                                        color = PinterestTextSecondary
                                    )
                                }

                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    IconButton(
                                        onClick = {
                                            if (index > 0) {
                                                val moved = currentList.removeAt(index)
                                                currentList.add(index - 1, moved)
                                                if (forceTypeOrderState) {
                                                    val constrained = applyBoardTypeConstraints(currentList.toList())
                                                    currentList.clear()
                                                    currentList.addAll(constrained)
                                                }
                                            }
                                        },
                                        enabled = index > 0,
                                        modifier = Modifier.size(28.dp)
                                    ) {
                                        Icon(
                                            imageVector = Icons.Default.KeyboardArrowUp,
                                            contentDescription = "Move Up",
                                            tint = if (index > 0) PinterestBlack else Color.LightGray,
                                            modifier = Modifier.size(18.dp)
                                        )
                                    }

                                    IconButton(
                                        onClick = {
                                            if (index < currentList.size - 1) {
                                                val moved = currentList.removeAt(index)
                                                currentList.add(index + 1, moved)
                                                if (forceTypeOrderState) {
                                                    val constrained = applyBoardTypeConstraints(currentList.toList())
                                                    currentList.clear()
                                                    currentList.addAll(constrained)
                                                }
                                            }
                                        },
                                        enabled = index < currentList.size - 1,
                                        modifier = Modifier.size(28.dp)
                                    ) {
                                        Icon(
                                            imageVector = Icons.Default.KeyboardArrowDown,
                                            contentDescription = "Move Down",
                                            tint = if (index < currentList.size - 1) PinterestBlack else Color.LightGray,
                                            modifier = Modifier.size(18.dp)
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val finalResult = if (forceTypeOrderState) applyBoardTypeConstraints(currentList.toList()) else currentList.toList()
                    onSaveReorderedBoards(finalResult, forceTypeOrderState)
                    onDismiss()
                },
                colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier.testTag("save_reorder_boards_btn")
            ) {
                Text("Save Order", color = Color.White, fontWeight = FontWeight.Bold)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel", color = PinterestBlack)
            }
        },
        shape = RoundedCornerShape(20.dp)
    )
}
