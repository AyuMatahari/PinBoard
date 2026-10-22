package com.example.ui.dialogs

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Domain
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.SwapVert
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.model.PinterestBoard
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary

@Composable
fun EditCustomBoardDialog(
    isOpen: Boolean,
    board: PinterestBoard?,
    onDismiss: () -> Unit,
    onSaveBoard: (boardId: String, newName: String, domains: List<String>, isDefault: Boolean) -> Unit,
    onDeleteBoard: (PinterestBoard) -> Unit,
    onOpenReorderBoards: () -> Unit = {}
) {
    if (!isOpen || board == null) return

    var boardName by remember(board) { mutableStateOf(board.title) }
    var customDomains by remember(board) { mutableStateOf(board.customDomains.joinToString(", ")) }
    var isDefault by remember(board) { mutableStateOf(board.isDefault) }
    var showDeleteConfirm by remember { mutableStateOf(false) }

    if (showDeleteConfirm) {
        AlertDialog(
            onDismissRequest = { showDeleteConfirm = false },
            icon = {
                Icon(
                    imageVector = Icons.Default.Warning,
                    contentDescription = null,
                    tint = PinterestRed,
                    modifier = Modifier.size(28.dp)
                )
            },
            title = {
                Text(
                    text = "Delete \"${board.title}\"?",
                    fontWeight = FontWeight.Bold,
                    fontSize = 17.sp
                )
            },
            text = {
                Text(
                    text = "Are you sure you want to delete this custom board and all its images? You can undo this immediately from the toast message.",
                    fontSize = 13.sp,
                    color = PinterestTextSecondary
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        showDeleteConfirm = false
                        onDismiss()
                        onDeleteBoard(board)
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                    shape = RoundedCornerShape(16.dp),
                    modifier = Modifier.testTag("confirm_delete_custom_board_btn")
                ) {
                    Text("Delete Board", color = Color.White, fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteConfirm = false }) {
                    Text("Cancel", color = PinterestBlack)
                }
            },
            shape = RoundedCornerShape(20.dp)
        )
        return
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Default.Edit,
                    contentDescription = null,
                    tint = PinterestRed,
                    modifier = Modifier.size(24.dp)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "Edit Board",
                    fontWeight = FontWeight.Bold,
                    fontSize = 18.sp
                )
            }
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
            ) {
                // Name
                OutlinedTextField(
                    value = boardName,
                    onValueChange = { boardName = it },
                    label = { Text("Board Name", fontSize = 13.sp) },
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = PinterestRed,
                        cursorColor = PinterestRed
                    ),
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("edit_custom_board_name_field")
                )

                Spacer(modifier = Modifier.height(12.dp))

                // Custom Domains
                OutlinedTextField(
                    value = customDomains,
                    onValueChange = { customDomains = it },
                    label = { Text("Custom Web Domains", fontSize = 13.sp) },
                    placeholder = { Text("e.g. opu.com, unsplash.com", fontSize = 13.sp) },
                    supportingText = {
                        Text(
                            text = "Matching images added anywhere will automatically join this board without duplicates.",
                            fontSize = 11.sp,
                            color = PinterestTextSecondary
                        )
                    },
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = PinterestRed,
                        cursorColor = PinterestRed
                    ),
                    shape = RoundedCornerShape(12.dp),
                    trailingIcon = {
                        Icon(
                            imageVector = Icons.Default.Domain,
                            contentDescription = null,
                            tint = PinterestTextSecondary,
                            modifier = Modifier.size(20.dp)
                        )
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("edit_custom_board_domains_field")
                )

                Spacer(modifier = Modifier.height(10.dp))

                // Default Board Switch (not applicable to Favorites)
                if (board.id != "board_favorites") {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "Default Board for Saves",
                                fontWeight = FontWeight.SemiBold,
                                fontSize = 13.sp
                            )
                            Text(
                                text = if (isDefault) "Currently set as default" else "Images without board choice save here",
                                fontSize = 11.sp,
                                color = PinterestTextSecondary
                            )
                        }
                        Spacer(modifier = Modifier.width(8.dp))
                        Switch(
                            checked = isDefault,
                            onCheckedChange = { isDefault = it },
                            colors = SwitchDefaults.colors(
                                checkedThumbColor = Color.White,
                                checkedTrackColor = PinterestRed
                            )
                        )
                    }
                }

                // Reorder Boards Button (Requirement 6)
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = PinterestPillGray,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onOpenReorderBoards() }
                        .testTag("open_reorder_boards_btn")
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 12.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                imageVector = Icons.Default.SwapVert,
                                contentDescription = null,
                                tint = PinterestRed,
                                modifier = Modifier.size(18.dp)
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Column {
                                Text(
                                    text = "Reorder Boards",
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 13.sp,
                                    color = PinterestBlack
                                )
                                Text(
                                    text = "Custom drag/sort order & board type rules",
                                    fontSize = 11.sp,
                                    color = PinterestTextSecondary
                                )
                            }
                        }

                        Icon(
                            imageVector = Icons.Default.SwapVert,
                            contentDescription = null,
                            tint = PinterestTextSecondary,
                            modifier = Modifier.size(16.dp)
                        )
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))
                HorizontalDivider()
                Spacer(modifier = Modifier.height(12.dp))

                // Deletion Section
                if (board.isSpecialNonDeletable) {
                    Surface(
                        shape = RoundedCornerShape(10.dp),
                        color = PinterestPillGray,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.padding(10.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.Lock,
                                contentDescription = null,
                                tint = PinterestTextSecondary,
                                modifier = Modifier.size(16.dp)
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(
                                text = "System board (cannot be deleted)",
                                fontSize = 12.sp,
                                color = PinterestTextSecondary,
                                fontWeight = FontWeight.Medium
                            )
                        }
                    }
                } else {
                    OutlinedButton(
                        onClick = { showDeleteConfirm = true },
                        colors = ButtonDefaults.outlinedButtonColors(
                            contentColor = PinterestRed
                        ),
                        shape = RoundedCornerShape(16.dp),
                        modifier = Modifier
                            .fillMaxWidth()
                            .testTag("delete_custom_board_btn")
                    ) {
                        Icon(
                            imageVector = Icons.Default.Delete,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        Text("Delete Board", fontWeight = FontWeight.Bold)
                    }
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    if (boardName.isNotBlank()) {
                        val domainList = customDomains.split(",", "\n", " ")
                            .map { it.trim() }
                            .filter { it.isNotBlank() }
                        onSaveBoard(board.id, boardName.trim(), domainList, isDefault)
                        onDismiss()
                    }
                },
                enabled = boardName.isNotBlank(),
                colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier.testTag("save_custom_board_btn")
            ) {
                Text("Save Changes", color = Color.White, fontWeight = FontWeight.Bold)
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
