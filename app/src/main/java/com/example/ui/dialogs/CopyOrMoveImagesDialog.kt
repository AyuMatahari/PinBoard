package com.example.ui.dialogs

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.Toast
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
import androidx.compose.material.icons.automirrored.filled.DriveFileMove
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import com.example.model.PinItem
import com.example.model.PinterestBoard
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream

enum class BoardTransferMode {
    COPY,
    MOVE
}

@Composable
fun CopyOrMoveImagesDialog(
    isOpen: Boolean,
    mode: BoardTransferMode,
    selectedPins: List<PinItem> = emptyList(),
    selectedCount: Int,
    availableBoards: List<PinterestBoard>,
    currentBoardId: String?,
    onDismiss: () -> Unit,
    onConfirm: (targetBoardIds: List<String>) -> Unit
) {
    if (!isOpen) return

    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()

    val selectableBoards = remember(availableBoards, currentBoardId, mode) {
        if (mode == BoardTransferMode.MOVE && !currentBoardId.isNullOrBlank()) {
            availableBoards.filter { it.id != currentBoardId }
        } else {
            availableBoards
        }
    }

    val selectedBoardIds = remember { mutableStateListOf<String>() }

    val isMove = mode == BoardTransferMode.MOVE
    val actionVerb = if (isMove) "Move" else "Copy"
    val icon = if (isMove) Icons.AutoMirrored.Filled.DriveFileMove else Icons.Default.ContentCopy

    AlertDialog(
        onDismissRequest = onDismiss,
        icon = {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = PinterestRed,
                modifier = Modifier.size(28.dp)
            )
        },
        title = {
            Text(
                text = "$actionVerb $selectedCount Image${if (selectedCount > 1) "s" else ""}",
                fontWeight = FontWeight.Bold,
                fontSize = 18.sp
            )
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
            ) {
                // Top quick actions for Copy mode (User requirement 2)
                if (mode == BoardTransferMode.COPY && selectedPins.isNotEmpty()) {
                    Text(
                        text = "QUICK ACTIONS",
                        style = MaterialTheme.typography.labelSmall.copy(
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 0.8.sp,
                            fontSize = 10.sp,
                            color = PinterestTextSecondary
                        )
                    )

                    Spacer(modifier = Modifier.height(6.dp))

                    // 1. Copy links of images
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = PinterestPillGray,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 3.dp)
                            .clickable {
                                val links = selectedPins.map { it.imageUrl.ifBlank { it.sourceUrl } }.filter { it.isNotBlank() }
                                val text = links.joinToString("\n")
                                val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                                val clip = ClipData.newPlainText("Image Links", text)
                                clipboard.setPrimaryClip(clip)
                                Toast.makeText(context, "Copied ${links.size} link(s) to clipboard", Toast.LENGTH_SHORT).show()
                                onDismiss()
                            }
                            .testTag("action_copy_links")
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 12.dp, vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                imageVector = Icons.Default.Link,
                                contentDescription = null,
                                tint = PinterestRed,
                                modifier = Modifier.size(18.dp)
                            )
                            Spacer(modifier = Modifier.width(10.dp))
                            Text(
                                text = "Copy links of images",
                                fontWeight = FontWeight.SemiBold,
                                fontSize = 13.sp,
                                color = PinterestBlack
                            )
                        }
                    }

                    // 2. Copy the image(s) itself to clipboard
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = PinterestPillGray,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 3.dp)
                            .clickable {
                                coroutineScope.launch {
                                    Toast.makeText(context, "Copying image to clipboard...", Toast.LENGTH_SHORT).show()
                                    val firstPin = selectedPins.firstOrNull()
                                    if (firstPin != null) {
                                        val uri = downloadToCacheUri(context, firstPin)
                                        if (uri != null) {
                                            val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                                            val clip = ClipData.newUri(context.contentResolver, "Image", uri)
                                            clipboard.setPrimaryClip(clip)
                                            Toast.makeText(context, "Copied image to clipboard", Toast.LENGTH_SHORT).show()
                                        } else {
                                            Toast.makeText(context, "Failed to copy image", Toast.LENGTH_SHORT).show()
                                        }
                                    }
                                    onDismiss()
                                }
                            }
                            .testTag("action_copy_image_itself")
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 12.dp, vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                imageVector = Icons.Default.Image,
                                contentDescription = null,
                                tint = PinterestRed,
                                modifier = Modifier.size(18.dp)
                            )
                            Spacer(modifier = Modifier.width(10.dp))
                            Text(
                                text = "Copy the images itself",
                                fontWeight = FontWeight.SemiBold,
                                fontSize = 13.sp,
                                color = PinterestBlack
                            )
                        }
                    }

                    // 3. Share the images links
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = PinterestPillGray,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 3.dp)
                            .clickable {
                                val links = selectedPins.map { it.imageUrl.ifBlank { it.sourceUrl } }.filter { it.isNotBlank() }
                                val text = links.joinToString("\n")
                                val sendIntent = Intent(Intent.ACTION_SEND).apply {
                                    type = "text/plain"
                                    putExtra(Intent.EXTRA_TEXT, text)
                                }
                                val shareIntent = Intent.createChooser(sendIntent, "Share Image Links")
                                context.startActivity(shareIntent)
                                onDismiss()
                            }
                            .testTag("action_share_links")
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 12.dp, vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                imageVector = Icons.Default.Share,
                                contentDescription = null,
                                tint = PinterestRed,
                                modifier = Modifier.size(18.dp)
                            )
                            Spacer(modifier = Modifier.width(10.dp))
                            Text(
                                text = "Share the images links",
                                fontWeight = FontWeight.SemiBold,
                                fontSize = 13.sp,
                                color = PinterestBlack
                            )
                        }
                    }

                    // 4. Share the image itself
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = PinterestPillGray,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 3.dp)
                            .clickable {
                                coroutineScope.launch {
                                    Toast.makeText(context, "Preparing images to share...", Toast.LENGTH_SHORT).show()
                                    val uris = ArrayList<Uri>()
                                    for (pin in selectedPins.take(10)) {
                                        val u = downloadToCacheUri(context, pin)
                                        if (u != null) uris.add(u)
                                    }
                                    if (uris.isNotEmpty()) {
                                        val sendIntent = if (uris.size == 1) {
                                            Intent(Intent.ACTION_SEND).apply {
                                                type = "image/jpeg"
                                                putExtra(Intent.EXTRA_STREAM, uris[0])
                                                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                            }
                                        } else {
                                            Intent(Intent.ACTION_SEND_MULTIPLE).apply {
                                                type = "image/jpeg"
                                                putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris)
                                                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                            }
                                        }
                                        val shareIntent = Intent.createChooser(sendIntent, "Share Image")
                                        context.startActivity(shareIntent)
                                    } else {
                                        Toast.makeText(context, "Could not prepare image", Toast.LENGTH_SHORT).show()
                                    }
                                    onDismiss()
                                }
                            }
                            .testTag("action_share_image_itself")
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 12.dp, vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                imageVector = Icons.Default.Share,
                                contentDescription = null,
                                tint = PinterestRed,
                                modifier = Modifier.size(18.dp)
                            )
                            Spacer(modifier = Modifier.width(10.dp))
                            Text(
                                text = "Share the image itself",
                                fontWeight = FontWeight.SemiBold,
                                fontSize = 13.sp,
                                color = PinterestBlack
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(12.dp))
                    HorizontalDivider()
                    Spacer(modifier = Modifier.height(12.dp))
                }

                Text(
                    text = if (isMove) {
                        "Select one or more destination boards. Images will be transferred to selected boards and removed from the current board."
                    } else {
                        "Select one or more destination boards to copy these images into."
                    },
                    style = MaterialTheme.typography.bodyMedium.copy(
                        color = PinterestTextSecondary,
                        fontSize = 13.sp
                    )
                )

                Spacer(modifier = Modifier.height(14.dp))

                Text(
                    text = "TARGET BOARDS",
                    style = MaterialTheme.typography.labelSmall.copy(
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 0.8.sp,
                        fontSize = 10.sp,
                        color = PinterestTextSecondary
                    )
                )

                Spacer(modifier = Modifier.height(8.dp))

                if (selectableBoards.isEmpty()) {
                    Text(
                        text = "No other boards available. Create a custom board first.",
                        fontSize = 12.sp,
                        color = PinterestTextSecondary
                    )
                } else {
                    selectableBoards.forEach { board ->
                        val isChecked = selectedBoardIds.contains(board.id)
                        Surface(
                            shape = RoundedCornerShape(12.dp),
                            color = if (isChecked) PinterestRed.copy(alpha = 0.1f) else PinterestPillGray,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 3.dp)
                                .clickable {
                                    if (isChecked) selectedBoardIds.remove(board.id)
                                    else selectedBoardIds.add(board.id)
                                }
                                .testTag("transfer_board_item_${board.id}")
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(horizontal = 12.dp, vertical = 10.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    modifier = Modifier.weight(1f)
                                ) {
                                    Text(
                                        text = board.title,
                                        fontWeight = if (isChecked) FontWeight.Bold else FontWeight.Medium,
                                        fontSize = 13.sp,
                                        color = if (isChecked) PinterestRed else PinterestBlack
                                    )
                                    if (board.isCustom) {
                                        Spacer(modifier = Modifier.width(6.dp))
                                        Surface(
                                            shape = RoundedCornerShape(6.dp),
                                            color = PinterestRed.copy(alpha = 0.15f)
                                        ) {
                                            Text(
                                                text = "Custom",
                                                color = PinterestRed,
                                                fontSize = 9.sp,
                                                fontWeight = FontWeight.Bold,
                                                modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                                            )
                                        }
                                    }
                                }

                                if (isChecked) {
                                    Icon(
                                        imageVector = Icons.Default.Check,
                                        contentDescription = "Selected",
                                        tint = PinterestRed,
                                        modifier = Modifier.size(18.dp)
                                    )
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
                    if (selectedBoardIds.isNotEmpty()) {
                        onConfirm(selectedBoardIds.toList())
                        onDismiss()
                    }
                },
                enabled = selectedBoardIds.isNotEmpty(),
                colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier.testTag("confirm_transfer_btn")
            ) {
                Text(
                    text = "$actionVerb to ${selectedBoardIds.size} Board${if (selectedBoardIds.size > 1) "s" else ""}",
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

private suspend fun downloadToCacheUri(context: Context, pin: PinItem): Uri? = withContext(Dispatchers.IO) {
    try {
        val client = OkHttpClient()
        val request = Request.Builder().url(pin.imageUrl).build()
        val response = client.newCall(request).execute()
        if (!response.isSuccessful || response.body == null) return@withContext null

        val cacheDir = File(context.cacheDir, "shared_images").apply { if (!exists()) mkdirs() }
        val file = File(cacheDir, "share_${pin.id.take(20)}.jpg")
        FileOutputStream(file).use { out ->
            response.body!!.byteStream().copyTo(out)
        }

        FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    } catch (_: Exception) {
        null
    }
}
