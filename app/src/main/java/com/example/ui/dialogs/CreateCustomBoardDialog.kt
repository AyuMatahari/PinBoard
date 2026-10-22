package com.example.ui.dialogs

import android.content.ClipboardManager
import android.content.Context
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
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ContentPaste
import androidx.compose.material.icons.filled.Domain
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.ViewCarousel
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary
import com.example.util.LinkExtractor

@Composable
fun CreateCustomBoardDialog(
    isOpen: Boolean,
    onDismiss: () -> Unit,
    onCreateBoard: (name: String, domains: List<String>, unstructuredLinksText: String, isDefault: Boolean) -> Unit
) {
    if (!isOpen) return

    val context = LocalContext.current
    var boardName by remember { mutableStateOf("") }
    var customDomains by remember { mutableStateOf("") }
    var unstructuredLinks by remember { mutableStateOf("") }
    var isDefault by remember { mutableStateOf(false) }

    val detectedLinksCount = remember(unstructuredLinks) {
        LinkExtractor.extractLinks(unstructuredLinks).size
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Default.ViewCarousel,
                    contentDescription = null,
                    tint = PinterestRed,
                    modifier = Modifier.size(24.dp)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "New Custom Board",
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
                    text = "Create a custom board to organize your own direct image links.",
                    style = MaterialTheme.typography.bodyMedium.copy(
                        color = PinterestTextSecondary,
                        fontSize = 13.sp
                    )
                )

                Spacer(modifier = Modifier.height(12.dp))

                // 1. Board Name (Required)
                OutlinedTextField(
                    value = boardName,
                    onValueChange = { boardName = it },
                    label = { Text("Board Name *", fontSize = 13.sp) },
                    placeholder = { Text("e.g. Wallpapers, Design Ideas", fontSize = 13.sp) },
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = PinterestRed,
                        cursorColor = PinterestRed
                    ),
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("create_custom_board_name_field")
                )

                Spacer(modifier = Modifier.height(12.dp))

                // 2. Custom Web Domains (Optional)
                OutlinedTextField(
                    value = customDomains,
                    onValueChange = { customDomains = it },
                    label = { Text("Custom Web Domains (Optional)", fontSize = 13.sp) },
                    placeholder = { Text("e.g. opu.com, unsplash.com", fontSize = 13.sp) },
                    supportingText = {
                        Text(
                            text = "When new links are added anywhere matching these domains, images will automatically be saved to this board without duplicates.",
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
                        .testTag("create_custom_board_domains_field")
                )

                Spacer(modifier = Modifier.height(10.dp))

                // 3. Initial Image Links / Unstructured text (Optional)
                OutlinedTextField(
                    value = unstructuredLinks,
                    onValueChange = { unstructuredLinks = it },
                    label = { Text("Add Image Links (Optional)", fontSize = 13.sp) },
                    placeholder = { Text("Paste text with one or more image links...", fontSize = 13.sp) },
                    minLines = 3,
                    maxLines = 5,
                    supportingText = {
                        if (detectedLinksCount > 0) {
                            Text(
                                text = "Found $detectedLinksCount link${if (detectedLinksCount > 1) "s" else ""}",
                                fontSize = 11.sp,
                                color = PinterestRed,
                                fontWeight = FontWeight.Bold
                            )
                        } else {
                            Text(
                                text = "Accepts free-form text containing multiple URLs",
                                fontSize = 11.sp,
                                color = PinterestTextSecondary
                            )
                        }
                    },
                    trailingIcon = {
                        IconButton(
                            onClick = {
                                val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
                                val clipText = clipboard?.primaryClip?.getItemAt(0)?.text?.toString()
                                if (!clipText.isNullOrBlank()) {
                                    unstructuredLinks = if (unstructuredLinks.isBlank()) clipText.trim()
                                    else unstructuredLinks + "\n" + clipText.trim()
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
                        .testTag("create_custom_board_links_field")
                )

                Spacer(modifier = Modifier.height(8.dp))

                // 4. Default Board Switch
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Set as Default Board",
                            fontWeight = FontWeight.SemiBold,
                            fontSize = 13.sp
                        )
                        Text(
                            text = "Images shared from other apps will default to this board",
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
        },
        confirmButton = {
            Button(
                onClick = {
                    if (boardName.isNotBlank()) {
                        val domainList = customDomains.split(",", "\n", " ")
                            .map { it.trim() }
                            .filter { it.isNotBlank() }
                        onCreateBoard(boardName.trim(), domainList, unstructuredLinks.trim(), isDefault)
                        onDismiss()
                    }
                },
                enabled = boardName.isNotBlank(),
                colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier.testTag("create_custom_board_confirm_btn")
            ) {
                Text("Create Board", color = Color.White, fontWeight = FontWeight.Bold)
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
