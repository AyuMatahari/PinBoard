package com.example.ui.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.DriveFileMove
import androidx.compose.material.icons.filled.CheckBox
import androidx.compose.material.icons.filled.CheckBoxOutlineBlank
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.CreateNewFolder
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.VerticalAlignTop
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed

@Composable
fun MultiSelectBottomBar(
    isVisible: Boolean,
    selectedPinCount: Int = 0,
    selectedAlbumCount: Int = 0,
    totalCount: Int,
    onSelectAll: () -> Unit,
    onDeselectAll: () -> Unit = {},
    onClearSelection: () -> Unit,
    onDownloadSelected: () -> Unit,
    onMoveToTop: () -> Unit = {},
    onDeleteSelected: () -> Unit = {},
    onCopySelected: () -> Unit = {},
    onMoveSelected: () -> Unit = {},
    onCreateAlbum: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    AnimatedVisibility(
        visible = isVisible,
        enter = slideInVertically(initialOffsetY = { it }),
        exit = slideOutVertically(targetOffsetY = { it }),
        modifier = modifier
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 6.dp)
                .navigationBarsPadding(),
            shape = RoundedCornerShape(20.dp),
            color = MaterialTheme.colorScheme.surface,
            shadowElevation = 8.dp,
            tonalElevation = 3.dp
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 10.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                // Left: Selected count & Clear button
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconButton(
                        onClick = onClearSelection,
                        modifier = Modifier.size(28.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Close,
                            contentDescription = "Exit Selection",
                            tint = MaterialTheme.colorScheme.onSurface,
                            modifier = Modifier.size(16.dp)
                        )
                    }

                    Spacer(modifier = Modifier.width(4.dp))

                    Text(
                        text = if (selectedPinCount > 0 && selectedAlbumCount > 0)
                            "${selectedPinCount + selectedAlbumCount} itm"
                        else if (selectedPinCount > 0) "$selectedPinCount img"
                        else if (selectedAlbumCount > 0) "$selectedAlbumCount alb"
                        else "0",
                        style = MaterialTheme.typography.titleSmall.copy(
                            fontWeight = FontWeight.Bold,
                            fontSize = 12.sp
                        ),
                        color = MaterialTheme.colorScheme.onSurface
                    )
                }

                // Center / Right actions: Select All Toggle, Copy, Move, Put at Top, Delete, Download
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(3.dp)
                ) {
                    val allSelected = (selectedPinCount + selectedAlbumCount) > 0 && (selectedPinCount + selectedAlbumCount) >= totalCount
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = if (allSelected) PinterestRed.copy(alpha = 0.12f) else PinterestPillGray,
                        modifier = Modifier
                            .clip(RoundedCornerShape(12.dp))
                            .clickable {
                                if (allSelected) onDeselectAll() else onSelectAll()
                            }
                            .testTag("select_all_toggle_btn")
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.padding(horizontal = 7.dp, vertical = 5.dp),
                            horizontalArrangement = Arrangement.spacedBy(3.dp)
                        ) {
                            Icon(
                                imageVector = if (allSelected) Icons.Default.CheckBox else Icons.Default.CheckBoxOutlineBlank,
                                contentDescription = if (allSelected) "Deselect All" else "Select All",
                                tint = PinterestRed,
                                modifier = Modifier.size(14.dp)
                            )
                            Text(
                                text = if (allSelected) "Deselect" else "Select All",
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                color = PinterestRed
                            )
                        }
                    }

                    // Copy to other boards action (User requirement)
                    IconButton(
                        onClick = onCopySelected,
                        enabled = (selectedPinCount + selectedAlbumCount) > 0,
                        modifier = Modifier
                            .size(32.dp)
                            .testTag("multi_select_copy_btn")
                    ) {
                        Icon(
                            imageVector = Icons.Default.ContentCopy,
                            contentDescription = "Copy to boards",
                            tint = if ((selectedPinCount + selectedAlbumCount) > 0) MaterialTheme.colorScheme.onSurface else Color.Gray,
                            modifier = Modifier.size(17.dp)
                        )
                    }

                    // Move to other boards action (User requirement)
                    IconButton(
                        onClick = onMoveSelected,
                        enabled = (selectedPinCount + selectedAlbumCount) > 0,
                        modifier = Modifier
                            .size(32.dp)
                            .testTag("multi_select_move_btn")
                    ) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.DriveFileMove,
                            contentDescription = "Move to boards",
                            tint = if ((selectedPinCount + selectedAlbumCount) > 0) MaterialTheme.colorScheme.onSurface else Color.Gray,
                            modifier = Modifier.size(18.dp)
                        )
                    }

                    // Put at Top action (User requirement)
                    IconButton(
                        onClick = onMoveToTop,
                        enabled = selectedPinCount > 0,
                        modifier = Modifier
                            .size(32.dp)
                            .testTag("multi_select_move_to_top_btn")
                    ) {
                        Icon(
                            imageVector = Icons.Default.VerticalAlignTop,
                            contentDescription = "Put images at top",
                            tint = if ((selectedPinCount + selectedAlbumCount) > 0) MaterialTheme.colorScheme.onSurface else Color.Gray,
                            modifier = Modifier.size(18.dp)
                        )
                    }

                    // Delete action (User requirement)
                    IconButton(
                        onClick = onDeleteSelected,
                        enabled = (selectedPinCount + selectedAlbumCount) > 0,
                        modifier = Modifier
                            .size(32.dp)
                            .testTag("multi_select_delete_btn")
                    ) {
                        Icon(
                            imageVector = Icons.Default.DeleteOutline,
                            contentDescription = "Delete selected images",
                            tint = if ((selectedPinCount + selectedAlbumCount) > 0) PinterestRed else Color.Gray,
                            modifier = Modifier.size(18.dp)
                        )
                    }

                    // Create Album button (pins only, >=2)
                    if (selectedPinCount >= 2) {
                        IconButton(
                            onClick = onCreateAlbum,
                            modifier = Modifier
                                .size(32.dp)
                                .testTag("multi_select_create_album_btn")
                        ) {
                            Icon(
                                imageVector = Icons.Default.CreateNewFolder,
                                contentDescription = "Create album from selected images",
                                tint = PinterestRed,
                                modifier = Modifier.size(18.dp)
                            )
                        }
                    }

                    // Download Button
                    Button(
                        onClick = onDownloadSelected,
                        enabled = selectedPinCount > 0,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = PinterestRed,
                            disabledContainerColor = PinterestPillGray
                        ),
                        shape = RoundedCornerShape(16.dp),
                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                        modifier = Modifier
                            .height(34.dp)
                            .testTag("download_selected_button")
                    ) {
                        Icon(
                            imageVector = Icons.Default.Download,
                            contentDescription = null,
                            tint = if ((selectedPinCount + selectedAlbumCount) > 0) Color.White else Color.Gray,
                            modifier = Modifier.size(14.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(
                            text = "Save",
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            color = if ((selectedPinCount + selectedAlbumCount) > 0) Color.White else Color.Gray
                        )
                    }
                }
            }
        }
    }
}
