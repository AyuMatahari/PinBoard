package com.example.ui.dialogs

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.FolderOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import com.example.ui.theme.PinterestTextSecondary


@Composable
fun DeleteSelectionDialog(
    isOpen: Boolean,
    pinCount: Int,
    albumCount: Int,
    onDismiss: () -> Unit,
    onDissolve: () -> Unit,
    onDeleteAll: () -> Unit
) {
    if (!isOpen) return

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(
                text = "Choose how to delete selected albums:",
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp
            )
        },
        text = {
            Column(Modifier.fillMaxWidth()) {
                Text(
                    text = if (pinCount > 0)
                        "$albumCount album(s) + $pinCount image(s) selected"
                    else
                        "$albumCount album(s) selected",
                    fontSize = 12.sp,
                    color = PinterestTextSecondary
                )
                Spacer(Modifier.height(12.dp))

                // Option A: Dissolve
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = PinterestPillGray,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onDissolve() }
                        .testTag("delete_option_dissolve")
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Box(
                            modifier = Modifier
                                .size(32.dp)
                                .clip(CircleShape)
                                .background(Color(0xFFE3F2FD)),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = Icons.Default.FolderOff,
                                contentDescription = null,
                                tint = Color(0xFF1976D2),
                                modifier = Modifier.size(18.dp)
                            )
                        }
                        Spacer(Modifier.width(10.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                "Dissolve album, keep inside images",
                                fontWeight = FontWeight.SemiBold,
                                fontSize = 13.sp,
                                color = PinterestBlack
                            )
                            Text(
                                "Images stay on the board as loose pins.",
                                fontSize = 11.sp,
                                color = PinterestTextSecondary
                            )
                        }
                    }
                }

                Spacer(Modifier.height(8.dp))

                // Option B: Delete album + contents
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = PinterestPillGray,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onDeleteAll() }
                        .testTag("delete_option_with_contents")
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Box(
                            modifier = Modifier
                                .size(32.dp)
                                .clip(CircleShape)
                                .background(PinterestRed.copy(alpha = 0.15f)),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = Icons.Default.DeleteOutline,
                                contentDescription = null,
                                tint = PinterestRed,
                                modifier = Modifier.size(18.dp)
                            )
                        }
                        Spacer(Modifier.width(10.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                "Delete album + images inside",
                                fontWeight = FontWeight.SemiBold,
                                fontSize = 13.sp,
                                color = PinterestBlack
                            )
                            Text(
                                "Images are permanently removed. Undo is available.",
                                fontSize = 11.sp,
                                color = PinterestTextSecondary
                            )
                        }
                    }
                }

                if (pinCount > 0) {
                    Spacer(Modifier.height(10.dp))
                    Text(
                        "Explicitly selected images are deleted regardless of choice above.",
                        fontSize = 11.sp,
                        color = PinterestTextSecondary
                    )
                }
            }
        },
        confirmButton = {},
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel", color = PinterestBlack)
            }
        },
        shape = RoundedCornerShape(20.dp)
    )
}
