package com.example.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.ui.theme.PinterestTextSecondary
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

@Composable
fun DateSectionHeader(
    dateLabel: String,
    count: Int,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(start = 10.dp, end = 10.dp, top = 14.dp, bottom = 4.dp)
            .testTag("date_section_header_$dateLabel"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = dateLabel,
            fontWeight = FontWeight.SemiBold,
            fontSize = 13.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        Text(
            text = if (count == 1) "1 image" else "$count images",
            fontSize = 11.sp,
            fontWeight = FontWeight.Normal,
            color = PinterestTextSecondary
        )
    }
}

/**
 * Formats a timestamp into a gallery-style date section label (e.g. Today, Yesterday, Sep 22, 2026, Sep 2026).
 */
fun formatPinDateGroup(millis: Long): String {
    val now = System.currentTimeMillis()
    val calPin = Calendar.getInstance().apply { timeInMillis = millis }
    val calNow = Calendar.getInstance().apply { timeInMillis = now }

    val sameYear = calPin.get(Calendar.YEAR) == calNow.get(Calendar.YEAR)
    val sameDayOfYear = sameYear && calPin.get(Calendar.DAY_OF_YEAR) == calNow.get(Calendar.DAY_OF_YEAR)
    val yesterday = sameYear && calPin.get(Calendar.DAY_OF_YEAR) == calNow.get(Calendar.DAY_OF_YEAR) - 1

    return when {
        sameDayOfYear -> "Today"
        yesterday -> "Yesterday"
        sameYear -> SimpleDateFormat("MMM d, yyyy", Locale.getDefault()).format(Date(millis))
        else -> SimpleDateFormat("MMM yyyy", Locale.getDefault()).format(Date(millis))
    }
}
