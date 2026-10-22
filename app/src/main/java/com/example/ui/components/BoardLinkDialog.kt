package com.example.ui.components

import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AddLink
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.ContentPaste
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Link
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
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

@Composable
fun BoardLinkDialog(
    isOpen: Boolean,
    boardHistory: List<BoardHistoryItem>,
    onDismiss: () -> Unit,
    onLoadBoard: (String) -> Unit,
    onRemoveHistoryItem: (String) -> Unit,
    onClearHistory: () -> Unit
) {
    if (!isOpen) return

    val context = LocalContext.current
    val focusManager = LocalFocusManager.current
    var urlInput by remember { mutableStateOf("") }

    val safeDismiss = {
        focusManager.clearFocus()
        onDismiss()
    }

    DisposableEffect(Unit) {
        onDispose {
            focusManager.clearFocus()
        }
    }

    AlertDialog(
        onDismissRequest = safeDismiss,
        title = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Default.AddLink,
                    contentDescription = null,
                    tint = PinterestRed,
                    modifier = Modifier.size(24.dp)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "Get Board from Link",
                    fontWeight = FontWeight.Bold,
                    fontSize = 18.sp
                )
            }
        },
        text = {
            Column(modifier = Modifier.fillMaxWidth()) {
                Text(
                    text = "Paste any Pinterest board URL (e.g., https://pinterest.com/username/boardname) or short link:",
                    style = MaterialTheme.typography.bodyMedium.copy(
                        color = PinterestTextSecondary,
                        fontSize = 13.sp
                    )
                )

                Spacer(modifier = Modifier.height(12.dp))

                OutlinedTextField(
                    value = urlInput,
                    onValueChange = { urlInput = it },
                    placeholder = { Text("https://pinterest.com/user/board", fontSize = 13.sp) },
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = PinterestRed,
                        cursorColor = PinterestRed
                    ),
                    shape = RoundedCornerShape(12.dp),
                    trailingIcon = {
                        IconButtonPaste(
                            onClick = {
                                val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
                                val clipText = clipboard?.primaryClip?.getItemAt(0)?.text?.toString()
                                if (!clipText.isNullOrBlank()) {
                                    urlInput = clipText.trim()
                                }
                            }
                        )
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("board_url_input_field")
                )

                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Quick Try Samples:",
                    style = MaterialTheme.typography.labelSmall.copy(
                        color = PinterestTextSecondary,
                        fontWeight = FontWeight.Bold,
                        fontSize = 11.sp
                    )
                )
                Spacer(modifier = Modifier.height(4.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    val sampleBoards = listOf(
                        "Holiday Decor" to "https://www.pinterest.com/pinterest/holiday-decor-ideas/",
                        "Visual Insp." to "https://www.pinterest.com/pinterest/visual-inspiration/",
                        "Manicures" to "https://www.pinterest.com/pinterest/try-a-new-holiday-manicure/"
                    )
                    sampleBoards.forEach { (label, url) ->
                        Surface(
                            onClick = { urlInput = url },
                            shape = RoundedCornerShape(12.dp),
                            color = PinterestPillGray,
                            modifier = Modifier.testTag("sample_board_${label.lowercase().replace(" ", "_").replace(".", "")}")
                        ) {
                            Text(
                                text = label,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Medium,
                                color = PinterestBlack,
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))
                HorizontalDivider()
                Spacer(modifier = Modifier.height(10.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = Icons.Default.History,
                            contentDescription = null,
                            tint = PinterestTextSecondary,
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(
                            text = "HISTORY OF BOARDS LINKS",
                            style = MaterialTheme.typography.labelSmall.copy(
                                fontWeight = FontWeight.Bold,
                                fontSize = 10.sp,
                                letterSpacing = 0.5.sp,
                                color = PinterestTextSecondary
                            )
                        )
                    }

                    val pinterestHistory = remember(boardHistory) {
                        boardHistory.filter { !it.isCustom && it.boardId != "board_my_save" && it.boardId != "board_favorites" && it.boardId != "board_dump" && !it.url.startsWith("custom://") }
                    }

                    if (pinterestHistory.isNotEmpty()) {
                        Text(
                            text = "Clear All",
                            fontSize = 11.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = PinterestRed,
                            modifier = Modifier
                                .clickable { onClearHistory() }
                                .padding(4.dp)
                                .testTag("clear_history_button")
                        )
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))

                val pinterestHistory = remember(boardHistory) {
                    boardHistory.filter { !it.isCustom && it.boardId != "board_my_save" && it.boardId != "board_favorites" && it.boardId != "board_dump" && !it.url.startsWith("custom://") }
                }

                if (pinterestHistory.isEmpty()) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 16.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = "No board history yet.\nPaste a Pinterest link above to load your first board.",
                            style = MaterialTheme.typography.bodySmall.copy(
                                color = PinterestTextSecondary,
                                fontSize = 12.sp,
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center
                            )
                        )
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(max = 220.dp)
                    ) {
                        items(
                            count = pinterestHistory.size,
                            key = { idx -> "${pinterestHistory[idx].url}_$idx" }
                        ) { idx ->
                            val historyItem = pinterestHistory[idx]
                            Surface(
                                shape = RoundedCornerShape(10.dp),
                                color = PinterestPillGray,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 3.dp)
                                    .clickable {
                                        urlInput = historyItem.url
                                    }
                                    .testTag("history_item_${historyItem.url.hashCode()}")
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp)
                                ) {
                                    val isFav = historyItem.boardId == "board_favorites" || historyItem.url.contains("favorites")
                                    val isMySave = historyItem.boardId == "board_my_save" || historyItem.url.contains("my_save")

                                    Icon(
                                        imageVector = when {
                                            isFav -> Icons.Default.Favorite
                                            isMySave -> Icons.Default.Bookmark
                                            else -> Icons.Default.Link
                                        },
                                        contentDescription = null,
                                        tint = PinterestRed,
                                        modifier = Modifier.size(16.dp)
                                    )
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(
                                            text = historyItem.title.ifBlank { "Pinterest Board" },
                                            fontSize = 13.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = PinterestBlack,
                                            maxLines = 1,
                                            overflow = TextOverflow.Ellipsis
                                        )
                                        Text(
                                            text = "${historyItem.ownerName.ifBlank { if (historyItem.isCustom) "Custom" else "Pinterest" }} • ${historyItem.pinCount} pins",
                                            fontSize = 11.sp,
                                            color = PinterestTextSecondary,
                                            maxLines = 1,
                                            overflow = TextOverflow.Ellipsis
                                        )
                                    }
                                    if (!isFav && !isMySave) {
                                        IconButton(
                                            onClick = { onRemoveHistoryItem(historyItem.url) },
                                            modifier = Modifier.size(28.dp)
                                        ) {
                                            Icon(
                                                imageVector = Icons.Default.Close,
                                                contentDescription = "Remove from history",
                                                tint = PinterestTextSecondary,
                                                modifier = Modifier.size(16.dp)
                                            )
                                        }
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
                    if (urlInput.isNotBlank()) {
                        focusManager.clearFocus()
                        onLoadBoard(urlInput.trim())
                        onDismiss()
                    }
                },
                enabled = urlInput.isNotBlank(),
                colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier.testTag("load_board_confirm_button")
            ) {
                Text("Load Board", color = Color.White, fontWeight = FontWeight.Bold)
            }
        },
        dismissButton = {
            TextButton(onClick = safeDismiss) {
                Text("Cancel", color = PinterestBlack)
            }
        },
        shape = RoundedCornerShape(20.dp)
    )
}

@Composable
private fun IconButtonPaste(onClick: () -> Unit) {
    IconButton(onClick = onClick) {
        Icon(
            imageVector = Icons.Default.ContentPaste,
            contentDescription = "Paste",
            tint = PinterestRed,
            modifier = Modifier.size(20.dp)
        )
    }
}
