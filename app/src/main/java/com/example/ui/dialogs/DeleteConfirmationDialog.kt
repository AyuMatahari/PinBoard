package com.example.ui.dialogs

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary

@Composable
fun DeleteFromAllConfirmationDialog(
    isOpen: Boolean,
    itemCount: Int,
    onDismiss: () -> Unit,
    onConfirmDeleteFromAll: () -> Unit
) {
    if (!isOpen) return

    AlertDialog(
        onDismissRequest = onDismiss,
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
                text = "Delete from All Boards?",
                fontWeight = FontWeight.Bold,
                fontSize = 17.sp
            )
        },
        text = {
            Text(
                text = "This will permanently remove the $itemCount selected image${if (itemCount > 1) "s" else ""} from every board they belong to across the app. Are you sure?",
                fontSize = 13.sp,
                color = PinterestTextSecondary
            )
        },
        confirmButton = {
            Button(
                onClick = {
                    onConfirmDeleteFromAll()
                    onDismiss()
                },
                colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                shape = RoundedCornerShape(16.dp),
                modifier = Modifier.testTag("confirm_delete_all_boards_btn")
            ) {
                Text("Delete From All", color = Color.White, fontWeight = FontWeight.Bold)
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
