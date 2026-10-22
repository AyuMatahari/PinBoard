package com.example.ui.dialogs

import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
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
import androidx.compose.material.icons.filled.AddPhotoAlternate
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.ContentPaste
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.model.DateAlbum
import com.example.model.PinterestBoard
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillDarkGray
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary
import com.example.util.LinkExtractor

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun AddManualImagesDialog(
    isOpen: Boolean,
    availableBoards: List<PinterestBoard>,
    currentBoardId: String?,
    currentAlbumTitle: String? = null,
    onDismiss: () -> Unit,
    onAddImages: (rawText: String, targetBoardIds: List<String>, extractMultipleImages: Boolean) -> Unit
) {
    if (!isOpen) return

    val context = LocalContext.current
    var textInput by remember { mutableStateOf("") }
    var extractMultipleImages by remember { mutableStateOf(false) }
    var boardsExpanded by remember { mutableStateOf(false) }

    // Selected boards (defaults to active board or default board)
    val selectedBoardIds = remember(availableBoards, currentBoardId) {
        val initial = mutableStateListOf<String>()
        if (!currentBoardId.isNullOrBlank() && availableBoards.any { it.id == currentBoardId }) {
            initial.add(currentBoardId)
        } else {
            availableBoards.firstOrNull { it.isDefault }?.id?.let { initial.add(it) }
                ?: availableBoards.firstOrNull()?.id?.let { initial.add(it) }
        }
        initial
    }

    val extractedLinks = remember(textInput) {
        LinkExtractor.extractLinks(textInput)
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Default.AddPhotoAlternate,
                    contentDescription = null,
                    tint = PinterestRed,
                    modifier = Modifier.size(24.dp)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "Add Images Manually",
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
                Text(
                    text = "Paste image links or webpage URLs (news sites, articles, blogs, image boards). The app extracts images and preserves source links.",
                    style = MaterialTheme.typography.bodyMedium.copy(
                        color = PinterestTextSecondary,
                        fontSize = 13.sp
                    )
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = textInput,
                    onValueChange = { textInput = it },
                    label = { Text("Links or Unstructured Text", fontSize = 13.sp) },
                    placeholder = { Text("Paste text or links here...", fontSize = 13.sp) },
                    minLines = 4,
                    maxLines = 6,
                    supportingText = {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = if (extractedLinks.isNotEmpty()) "Found ${extractedLinks.size} link(s)"
                                else "No links found yet",
                                fontSize = 11.sp,
                                fontWeight = if (extractedLinks.isNotEmpty()) FontWeight.Bold else FontWeight.Normal,
                                color = if (extractedLinks.isNotEmpty()) PinterestRed else PinterestTextSecondary
                            )
                        }
                    },
                    trailingIcon = {
                        IconButton(
                            onClick = {
                                val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
                                val clipText = clipboard?.primaryClip?.getItemAt(0)?.text?.toString()
                                if (!clipText.isNullOrBlank()) {
                                    textInput = if (textInput.isBlank()) clipText.trim()
                                    else textInput + "\n" + clipText.trim()
                                }
                            }
                        ) {
                            Icon(
                                imageVector = Icons.Default.ContentPaste,
                                contentDescription = "Paste from Clipboard",
                                tint = PinterestRed,
                                modifier = Modifier.size(20.dp)
                            )
                        }
                    },
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = PinterestRed,
                        cursorColor = PinterestRed
                    ),
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("manual_images_input_field")
                )

                Spacer(modifier = Modifier.height(10.dp))

                // Checklist 1: Add multiple main image in one webpage (unchecked by default)
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable {
                            extractMultipleImages = !extractMultipleImages
                            if (!extractMultipleImages) putIntoAlbum = false
                        }
                        .padding(vertical = 4.dp)
                        .testTag("extract_multiple_images_checkbox")
                ) {
                    Checkbox(
                        checked = extractMultipleImages,
                        onCheckedChange = {
                            extractMultipleImages = it
                            if (!it) putIntoAlbum = false
                        },
                        colors = CheckboxDefaults.colors(checkedColor = PinterestRed)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Column {
                        Text(
                            text = "Add multiple main images from webpage",
                            fontSize = 13.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = PinterestBlack
                        )
                        Text(
                            text = "Extract all content images from webpage in order (first to last).",
                            fontSize = 11.sp,
                            color = PinterestTextSecondary
                        )
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { boardsExpanded = !boardsExpanded }
                        .padding(vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Adding to: ${selectedBoardIds.size} board${if (selectedBoardIds.size != 1) "s" else ""}",
                        fontSize = 12.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = PinterestTextSecondary,
                        modifier = Modifier.weight(1f)
                    )
                    Text(
                        text = if (boardsExpanded) "▲" else "▼",
                        fontSize = 11.sp,
                        color = PinterestRed
                    )
                }
                androidx.compose.animation.AnimatedVisibility(visible = boardsExpanded) {
                    Column {
                        Spacer(modifier = Modifier.height(6.dp))

                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    availableBoards.forEach { board ->
                        val isChecked = selectedBoardIds.contains(board.id)
                        Surface(
                            shape = RoundedCornerShape(16.dp),
                            color = if (isChecked) PinterestBlack else PinterestPillGray,
                            modifier = Modifier
                                .clickable {
                                    if (isChecked) selectedBoardIds.remove(board.id)
                                    else selectedBoardIds.add(board.id)
                                }
                                .testTag("select_target_board_${board.id}")
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp)
                            ) {
                                if (isChecked) {
                                    Icon(
                                        imageVector = Icons.Default.Check,
                                        contentDescription = null,
                                        tint = Color.White,
                                        modifier = Modifier.size(14.dp)
                                    )
                                    Spacer(modifier = Modifier.width(4.dp))
                                }
                                Text(
                                    text = board.title,
                                    fontSize = 12.sp,
                                    fontWeight = if (isChecked) FontWeight.Bold else FontWeight.Medium,
                                    color = if (isChecked) Color.White else PinterestBlack
                                )
                            }
                        }
                    }
                }

                    }
                }
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Tip: Any other custom boards with matching domains will also receive the images automatically.",
                    fontSize = 11.sp,
                    color = PinterestTextSecondary
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    if (extractedLinks.isNotEmpty() && selectedBoardIds.isNotEmpty()) {
                        onAddImages(
                            textInput.trim(),
                            selectedBoardIds.toList(),
                            extractMultipleImages
                        )
                        onDismiss()
                    }
                },
                enabled = extractedLinks.isNotEmpty() && selectedBoardIds.isNotEmpty(),
                colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier.testTag("confirm_add_manual_images_btn")
            ) {
                Text(
                    text = "Add ${extractedLinks.size} Link${if (extractedLinks.size > 1) "s" else ""}",
                    color = Color.White,
                    fontWeight = FontWeight.Bold
                )
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
