package com.example.ui.dialogs

import android.content.ClipboardManager
import android.content.Context
import androidx.compose.animation.AnimatedVisibility
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
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import com.example.model.PinterestBoard
import com.example.ui.theme.PinterestBlack
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

    val selectedBoardIds = remember(availableBoards, currentBoardId) {
        val initial = mutableStateListOf<String>()
        if (!currentBoardId.isNullOrBlank() && availableBoards.any { it.id == currentBoardId }) {
            initial.add(currentBoardId)
        } else {
            (availableBoards.firstOrNull { it.isDefault }?.id
                ?: availableBoards.firstOrNull()?.id)?.let { initial.add(it) }
        }
        initial
    }

    val extractedLinks = remember(textInput) { LinkExtractor.extractLinks(textInput) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.AddPhotoAlternate, null, tint = PinterestRed, modifier = Modifier.size(24.dp))
                Spacer(Modifier.width(8.dp))
                Text("Add Images Manually", fontWeight = FontWeight.Bold, fontSize = 18.sp)
            }
        },
        text = {
            Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
                Text("Paste image links or webpage URLs.",
                    color = PinterestTextSecondary, fontSize = 13.sp)
                if (!currentAlbumTitle.isNullOrBlank()) {
                    Spacer(Modifier.height(6.dp))
                    Text("Will be added to album: $currentAlbumTitle",
                        color = PinterestRed, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                }
                Spacer(Modifier.height(10.dp))

                OutlinedTextField(
                    value = textInput,
                    onValueChange = { textInput = it },
                    label = { Text("Links or Unstructured Text", fontSize = 13.sp) },
                    placeholder = { Text("Paste text or links here...", fontSize = 13.sp) },
                    minLines = 4, maxLines = 6,
                    supportingText = {
                        Text(
                            if (extractedLinks.isNotEmpty()) "Found ${extractedLinks.size} link(s)"
                            else "No links found yet",
                            fontSize = 11.sp,
                            fontWeight = if (extractedLinks.isNotEmpty()) FontWeight.Bold else FontWeight.Normal,
                            color = if (extractedLinks.isNotEmpty()) PinterestRed else PinterestTextSecondary
                        )
                    },
                    trailingIcon = {
                        IconButton(onClick = {
                            val cb = context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
                            val clipText = cb?.primaryClip?.getItemAt(0)?.text?.toString()
                            if (!clipText.isNullOrBlank()) {
                                textInput = if (textInput.isBlank()) clipText.trim()
                                else textInput + "\n" + clipText.trim()
                            }
                        }) {
                            Icon(Icons.Default.ContentPaste, "Paste", tint = PinterestRed, modifier = Modifier.size(20.dp))
                        }
                    },
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = PinterestRed, cursorColor = PinterestRed),
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.fillMaxWidth().testTag("manual_images_input_field")
                )

                Spacer(Modifier.height(10.dp))

                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth()
                        .clickable { extractMultipleImages = !extractMultipleImages }
                        .padding(vertical = 4.dp)
                        .testTag("extract_multiple_images_checkbox")
                ) {
                    Checkbox(
                        checked = extractMultipleImages,
                        onCheckedChange = { extractMultipleImages = it },
                        colors = CheckboxDefaults.colors(checkedColor = PinterestRed)
                    )
                    Spacer(Modifier.width(6.dp))
                    Column {
                        Text("Add multiple main images from webpage",
                            fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                        Text("Extract all content images from webpage in order",
                            fontSize = 11.sp, color = PinterestTextSecondary)
                    }
                }

                Spacer(Modifier.height(12.dp))

                Row(
                    modifier = Modifier.fillMaxWidth()
                        .clickable { boardsExpanded = !boardsExpanded }
                        .padding(vertical = 6.dp)
                        .testTag("boards_selector_toggle"),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        "Adding to: ${selectedBoardIds.size} board${if (selectedBoardIds.size != 1) "s" else ""}",
                        fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
                        color = PinterestTextSecondary,
                        modifier = Modifier.weight(1f)
                    )
                    Text(if (boardsExpanded) "▲" else "▼", fontSize = 11.sp, color = PinterestRed)
                }
                AnimatedVisibility(visible = boardsExpanded) {
                    Column {
                        Spacer(Modifier.height(6.dp))
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
                                            Icon(Icons.Default.Check, null, tint = Color.White, modifier = Modifier.size(14.dp))
                                            Spacer(Modifier.width(4.dp))
                                        }
                                        Text(board.title, fontSize = 12.sp,
                                            fontWeight = if (isChecked) FontWeight.Bold else FontWeight.Medium,
                                            color = if (isChecked) Color.White else PinterestBlack)
                                    }
                                }
                            }
                        }
                    }
                }

                Spacer(Modifier.height(8.dp))
                Text("Tip: Any custom boards with matching domains will also receive these images.",
                    fontSize = 11.sp, color = PinterestTextSecondary)
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    if (extractedLinks.isNotEmpty() && selectedBoardIds.isNotEmpty()) {
                        onAddImages(textInput.trim(), selectedBoardIds.toList(), extractMultipleImages)
                        onDismiss()
                    }
                },
                enabled = extractedLinks.isNotEmpty() && selectedBoardIds.isNotEmpty(),
                colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier.testTag("confirm_add_manual_images_btn")
            ) {
                Text("Add ${extractedLinks.size} Link${if (extractedLinks.size > 1) "s" else ""}",
                    color = Color.White, fontWeight = FontWeight.Bold)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel", color = PinterestBlack) }
        },
        shape = RoundedCornerShape(20.dp)
    )
}
