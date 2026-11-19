package com.example.ui.components

// v2-video
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BrokenImage
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import coil.request.ImageRequest
import com.example.model.PinItem
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary
import java.io.File


@OptIn(ExperimentalFoundationApi::class)
@Composable
fun PinCard(
    pin: PinItem,
    columnCount: Int,
    isSelected: Boolean,
    isSelectionMode: Boolean,
    isFavorite: Boolean = false,
    hideTitleAndAuthor: Boolean = false,
    isNew: Boolean = false,
    refreshCounter: Int = 0,
    onClick: () -> Unit,
    onLongClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val cardShape = RoundedCornerShape(16.dp)

    // Video thumbnail extraction state
    var extractedVideoThumb by remember(pin.id) { mutableStateOf<File?>(null) }
    var videoThumbFailed by remember(pin.id) { mutableStateOf(false) }
    LaunchedEffect(pin.id, pin.isVideo, pin.hasSeparateThumbnail) {
        if (pin.isVideo && !pin.hasSeparateThumbnail && extractedVideoThumb == null && !videoThumbFailed) {
            val f = com.example.util.VideoThumbnailCache.getOrExtract(context, pin)
            if (f == null) videoThumbFailed = true else extractedVideoThumb = f
        }
    }

    val isAnimatedGif = !pin.isVideo && com.example.util.ImageMimeUtils.isAnimated(pin.mimeType, pin.imageUrl)
    val effectiveImageModel: Any? = when {
        pin.isVideo && pin.hasSeparateThumbnail -> pin.thumbnailUrl.ifBlank { pin.imageUrl }
        pin.isVideo -> extractedVideoThumb
        isAnimatedGif -> pin.imageUrl.ifBlank { pin.thumbnailUrl }
        else -> pin.thumbnailUrl.ifBlank { pin.imageUrl }
    }

    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(cardShape)
            .combinedClickable(
                onClick = onClick,
                onLongClick = onLongClick
            )
            .testTag("pin_card_${pin.id}")
            .padding(bottom = if (hideTitleAndAuthor) 6.dp else 12.dp)
    ) {
        val safeRatio = remember(pin.aspectRatio) {
            val r = pin.aspectRatio
            if (r.isFinite() && r > 0.1f) r.coerceIn(0.45f, 2.0f) else 0.75f
        }
        val cardBg = remember(pin.dominantColor) {
            try {
                if (pin.dominantColor != 0L) {
                    val raw = (pin.dominantColor and 0xFFFFFFFFL).toInt()
                    val argb = if ((raw and -0x1000000) == 0) (raw or -0x1000000) else raw
                    Color(color = argb)
                } else PinterestPillGray
            } catch (_: Throwable) {
                PinterestPillGray
            }
        }

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .clip(cardShape)
                .background(cardBg)
                .aspectRatio(safeRatio)
        ) {
            if (effectiveImageModel != null) {
                AsyncImage(
                    model = ImageRequest.Builder(context)
                        .data(effectiveImageModel)
                        .apply {
                            if (refreshCounter > 0) {
                                memoryCacheKey("pin-thumb:${pin.id}:r$refreshCounter")
                                diskCacheKey("pin-thumb:${pin.id}:r$refreshCounter")
                            }
                        }
                        .crossfade(true)
                        .build(),
                    contentDescription = pin.title,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier
                        .matchParentSize()
                        .clip(cardShape)
                )
            } else {
                // Video without extractable thumbnail — placeholder
                Box(
                    modifier = Modifier
                        .matchParentSize()
                        .background(PinterestPillGray),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = Icons.Default.PlayArrow,
                        contentDescription = "Video",
                        tint = PinterestTextSecondary,
                        modifier = Modifier.size(36.dp)
                    )
                }
            }

            // Video play icon — top-left, masonry-only indicator
            if (pin.isVideo && !isSelectionMode) {
                Box(
                    modifier = Modifier
                        .align(Alignment.TopStart)
                        .padding(6.dp)
                        .size(28.dp)
                        .clip(CircleShape)
                        .background(Color.Black.copy(alpha = 0.55f))
                        .border(1.5.dp, Color.White, CircleShape)
                        .testTag("pin_video_badge_${pin.id}"),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = Icons.Default.PlayArrow,
                        contentDescription = "Video",
                        tint = Color.White,
                        modifier = Modifier.size(15.dp)
                    )
                }
            }

            // Selection indicator
            if (isSelectionMode) {
                Box(
                    modifier = Modifier
                        .matchParentSize()
                        .background(
                            if (isSelected) PinterestRed.copy(alpha = 0.25f)
                            else Color.Black.copy(alpha = 0.15f)
                        )
                )
                Box(
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(8.dp)
                        .size(28.dp)
                        .clip(CircleShape)
                        .background(
                            if (isSelected) PinterestRed else Color.Black.copy(alpha = 0.45f)
                        )
                        .border(width = 2.dp, color = Color.White, shape = CircleShape),
                    contentAlignment = Alignment.Center
                ) {
                    if (isSelected) {
                        Icon(
                            imageVector = Icons.Default.Check,
                            contentDescription = "Selected",
                            tint = Color.White,
                            modifier = Modifier.size(18.dp)
                        )
                    }
                }
            } else {
                if (isFavorite) {
                    Box(
                        modifier = Modifier
                            .align(Alignment.TopEnd)
                            .padding(6.dp)
                            .size(28.dp)
                            .clip(CircleShape)
                            .background(PinterestRed)
                            .border(width = 1.5.dp, color = Color.White, shape = CircleShape)
                            .testTag("pin_favorite_badge_${pin.id}"),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            imageVector = Icons.Default.Favorite,
                            contentDescription = "Favorited",
                            tint = Color.White,
                            modifier = Modifier.size(15.dp)
                        )
                    }
                }
                if (isNew) {
                    Surface(
                        color = PinterestRed,
                        shape = RoundedCornerShape(6.dp),
                        shadowElevation = 3.dp,
                        modifier = Modifier
                            .padding(8.dp)
                            .align(Alignment.TopStart)
                            .testTag("pin_new_badge_${pin.id}")
                    ) {
                        Text(
                            text = "NEW",
                            color = Color.White,
                            fontWeight = FontWeight.ExtraBold,
                            fontSize = 9.sp,
                            letterSpacing = 0.6.sp,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }
            }

            if (pin.isBrokenOrUnreachable) {
                Surface(
                    color = Color.Black.copy(alpha = 0.7f),
                    shape = RoundedCornerShape(6.dp),
                    modifier = Modifier
                        .align(Alignment.BottomStart)
                        .padding(6.dp)
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 3.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.BrokenImage,
                            contentDescription = "Broken link",
                            tint = Color(0xFFFFB4AB),
                            modifier = Modifier.size(12.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(
                            text = "Unavailable",
                            color = Color(0xFFFFB4AB),
                            fontSize = 9.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
        }

        if (!hideTitleAndAuthor && columnCount <= 3 && pin.title.isNotBlank()) {
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = pin.title,
                style = MaterialTheme.typography.bodyMedium.copy(
                    fontWeight = FontWeight.SemiBold,
                    fontSize = if (columnCount == 2) 13.sp else 11.sp,
                    lineHeight = if (columnCount == 2) 17.sp else 14.sp
                ),
                maxLines = if (columnCount == 2) 2 else 1,
                overflow = TextOverflow.Ellipsis,
                color = MaterialTheme.colorScheme.onSurface,
                modifier = Modifier.padding(horizontal = 4.dp)
            )

            if (columnCount == 2) {
                Spacer(modifier = Modifier.height(2.dp))
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.padding(horizontal = 4.dp)
                ) {
                    Text(
                        text = pin.author.ifBlank { pin.displayDomain },
                        style = MaterialTheme.typography.labelSmall.copy(
                            fontSize = 11.sp,
                            color = PinterestTextSecondary
                        ),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }
        }
    }
}
