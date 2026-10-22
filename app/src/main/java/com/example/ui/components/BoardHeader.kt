package com.example.ui.components

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AddLink
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.ViewCarousel
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import coil.request.ImageRequest
import com.example.model.BoardHistoryItem
import com.example.model.PinterestBoard
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun BoardHeader(
    board: PinterestBoard,
    boardHistory: List<BoardHistoryItem>,
    currentPinCount: Int,
    onHistoryItemSelected: (String) -> Unit,
    onCustomBoardPillLongClick: (BoardHistoryItem) -> Unit = {},
    onOpenLinkDialog: () -> Unit,
    onOpenCreateCustomBoard: () -> Unit = {},
    onEditCurrentCustomBoard: () -> Unit = {},
    boardsListScrollState: LazyListState = rememberLazyListState(),
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current

    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(top = 4.dp, bottom = 10.dp)
    ) {
        // Board Title & Metadata
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.Center
            ) {
                Text(
                    text = board.title,
                    style = MaterialTheme.typography.headlineSmall.copy(
                        fontWeight = FontWeight.ExtraBold,
                        fontSize = 22.sp
                    ),
                    color = MaterialTheme.colorScheme.onSurface,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis
                )

                if (board.isCustom) {
                    Spacer(modifier = Modifier.width(6.dp))
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = PinterestRed.copy(alpha = 0.12f),
                        modifier = Modifier
                            .clickable { onEditCurrentCustomBoard() }
                            .testTag("edit_board_badge_btn")
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.Edit,
                                contentDescription = "Edit board",
                                tint = PinterestRed,
                                modifier = Modifier.size(12.dp)
                            )
                            Spacer(modifier = Modifier.width(3.dp))
                            Text(
                                text = if (board.isDefault) "Default" else "Custom",
                                fontSize = 10.sp,
                                fontWeight = FontWeight.Bold,
                                color = PinterestRed
                            )
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(6.dp))

            // Owner Details Row
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.Center
            ) {
                if (board.ownerAvatarUrl.isNotBlank()) {
                    AsyncImage(
                        model = ImageRequest.Builder(context)
                            .data(board.ownerAvatarUrl)
                            .crossfade(true)
                            .build(),
                        contentDescription = board.ownerDisplayName,
                        contentScale = ContentScale.Crop,
                        modifier = Modifier
                            .size(24.dp)
                            .clip(CircleShape)
                            .background(PinterestPillGray)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                }

                Text(
                    text = board.ownerDisplayName.ifBlank { if (board.isCustom) "Custom Board" else "Pinterest Board" },
                    style = MaterialTheme.typography.bodyMedium.copy(
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 13.sp
                    ),
                    color = MaterialTheme.colorScheme.onSurface
                )

                Spacer(modifier = Modifier.width(8.dp))

                Box(
                    modifier = Modifier
                        .size(3.dp)
                        .clip(CircleShape)
                        .background(PinterestTextSecondary)
                )

                Spacer(modifier = Modifier.width(8.dp))

                Text(
                    text = "$currentPinCount Images",
                    style = MaterialTheme.typography.bodySmall.copy(
                        fontWeight = FontWeight.Medium,
                        color = PinterestRed
                    )
                )
            }

            if (board.customDomains.isNotEmpty()) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Auto-matches: ${board.customDomains.joinToString(", ")}",
                    style = MaterialTheme.typography.bodySmall.copy(
                        color = PinterestTextSecondary,
                        fontSize = 11.sp
                    ),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }

            val isDuplicateAutomatch = board.description.contains("auto-match", ignoreCase = true) ||
                    board.description.contains("automatch", ignoreCase = true) ||
                    (board.customDomains.isNotEmpty() && board.description.contains("match", ignoreCase = true))

            if (board.description.isNotBlank() && !isDuplicateAutomatch) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = board.description,
                    style = MaterialTheme.typography.bodySmall.copy(
                        color = PinterestTextSecondary,
                        fontSize = 12.sp
                    ),
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis
                )
            }

            Spacer(modifier = Modifier.height(10.dp))

            // Action Buttons Row
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                // New Custom Board
                Button(
                    onClick = onOpenCreateCustomBoard,
                    colors = ButtonDefaults.buttonColors(containerColor = PinterestBlack),
                    shape = RoundedCornerShape(24.dp),
                    contentPadding = PaddingValues(horizontal = 14.dp, vertical = 6.dp),
                    modifier = Modifier.testTag("create_custom_board_hero_button")
                ) {
                    Icon(
                        imageVector = Icons.Default.Add,
                        contentDescription = null,
                        modifier = Modifier.size(15.dp),
                        tint = Color.White
                    )
                    Spacer(modifier = Modifier.width(5.dp))
                    Text(
                        text = "New Board",
                        fontSize = 12.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = Color.White
                    )
                }

                // Pinterest Board Link
                Button(
                    onClick = onOpenLinkDialog,
                    colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                    shape = RoundedCornerShape(24.dp),
                    contentPadding = PaddingValues(horizontal = 14.dp, vertical = 6.dp),
                    modifier = Modifier.testTag("enter_board_link_hero_button")
                ) {
                    Icon(
                        imageVector = Icons.Default.AddLink,
                        contentDescription = null,
                        modifier = Modifier.size(15.dp),
                        tint = Color.White
                    )
                    Spacer(modifier = Modifier.width(5.dp))
                    Text(
                        text = "Pinterest Link",
                        fontSize = 12.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = Color.White
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        // History / List of Boards Carousel
        if (boardHistory.isNotEmpty()) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
            ) {
                Icon(
                    imageVector = Icons.Default.History,
                    contentDescription = null,
                    tint = PinterestTextSecondary,
                    modifier = Modifier.size(14.dp)
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    text = "BOARDS (HOLD CUSTOM TO EDIT)",
                    style = MaterialTheme.typography.labelSmall.copy(
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 0.8.sp,
                        fontSize = 10.sp,
                        color = PinterestTextSecondary
                    )
                )
            }

            LazyRow(
                state = boardsListScrollState,
                contentPadding = PaddingValues(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                items(
                    count = boardHistory.size,
                    key = { idx -> boardHistory[idx].url.ifBlank { "${boardHistory[idx].boardId}_$idx" } }
                ) { idx ->
                    val historyItem = boardHistory[idx]
                    val isSelected = historyItem.url.equals(board.boardUrl, ignoreCase = true)
                    Surface(
                        shape = RoundedCornerShape(20.dp),
                        color = if (isSelected) PinterestBlack else MaterialTheme.colorScheme.surfaceVariant,
                        modifier = Modifier
                            .then(
                                if (historyItem.isCustom) {
                                    Modifier.combinedClickable(
                                        onClick = {
                                            if (!isSelected) {
                                                onHistoryItemSelected(historyItem.url)
                                            }
                                        },
                                        onLongClick = {
                                            onCustomBoardPillLongClick(historyItem)
                                        }
                                    )
                                } else {
                                    Modifier.clickable {
                                        if (!isSelected) {
                                            onHistoryItemSelected(historyItem.url)
                                        }
                                    }
                                }
                            )
                            .testTag("board_history_chip_${historyItem.url.hashCode()}")
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp)
                        ) {
                            val isFav = historyItem.boardId == "board_favorites" || historyItem.url.contains("favorites")
                            val isMySave = historyItem.boardId == "board_my_save" || historyItem.url.contains("my_save")
                            val isDump = historyItem.boardId == "board_dump" || historyItem.url.contains("dump")

                            if (isFav) {
                                Icon(
                                    imageVector = Icons.Default.Favorite,
                                    contentDescription = null,
                                    tint = if (isSelected) Color.White else PinterestRed,
                                    modifier = Modifier.size(13.dp)
                                )
                                Spacer(modifier = Modifier.width(5.dp))
                            } else if (isMySave) {
                                Icon(
                                    imageVector = Icons.Default.Bookmark,
                                    contentDescription = null,
                                    tint = if (isSelected) Color.White else PinterestRed,
                                    modifier = Modifier.size(13.dp)
                                )
                                Spacer(modifier = Modifier.width(5.dp))
                            } else if (isDump) {
                                Icon(
                                    imageVector = Icons.Default.Folder,
                                    contentDescription = null,
                                    tint = if (isSelected) Color.White else PinterestRed,
                                    modifier = Modifier.size(13.dp)
                                )
                                Spacer(modifier = Modifier.width(5.dp))
                            }

                            Text(
                                text = historyItem.title.ifBlank { "Board" },
                                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium,
                                fontSize = 12.sp,
                                color = if (isSelected) Color.White else MaterialTheme.colorScheme.onSurface
                            )
                            if (historyItem.isCustom && !isFav && !isMySave && !isDump) {
                                Spacer(modifier = Modifier.width(4.dp))
                                Box(
                                    modifier = Modifier
                                        .size(5.dp)
                                        .clip(CircleShape)
                                        .background(if (isSelected) PinterestRed else PinterestTextSecondary)
                                )
                            }
                        }
                    }
                }

                // Add Custom Board Chip
                item {
                    Surface(
                        shape = RoundedCornerShape(20.dp),
                        color = PinterestPillGray,
                        modifier = Modifier
                            .clickable { onOpenCreateCustomBoard() }
                            .testTag("board_history_add_custom_chip")
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.Add,
                                contentDescription = null,
                                tint = PinterestBlack,
                                modifier = Modifier.size(14.dp)
                            )
                            Spacer(modifier = Modifier.width(4.dp))
                            Text(
                                text = "New Board",
                                fontWeight = FontWeight.SemiBold,
                                fontSize = 12.sp,
                                color = PinterestBlack
                            )
                        }
                    }
                }
            }
        }
    }
}
