package com.example.ui.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestRed

@Composable
fun ModernGalleryScroller(
    isScrolling: Boolean,
    currentVisibleIndex: Int,
    totalCount: Int,
    onScrollToTop: () -> Unit,
    modifier: Modifier = Modifier
) {
    Box(modifier = modifier) {
        // Modern Floating "Back to Top" Action Button
        AnimatedVisibility(
            visible = currentVisibleIndex > 8,
            enter = fadeIn() + scaleIn(),
            exit = fadeOut() + scaleOut(),
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(bottom = 80.dp, end = 16.dp)
        ) {
            FloatingActionButton(
                onClick = onScrollToTop,
                containerColor = MaterialTheme.colorScheme.surface,
                contentColor = PinterestRed,
                shape = CircleShape,
                modifier = Modifier
                    .size(46.dp)
                    .shadow(6.dp, CircleShape)
                    .testTag("scroll_to_top_button")
            ) {
                Icon(
                    imageVector = Icons.Default.KeyboardArrowUp,
                    contentDescription = "Scroll to top",
                    modifier = Modifier.size(24.dp)
                )
            }
        }
    }
}
