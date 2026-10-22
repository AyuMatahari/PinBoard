package com.example.ui.components

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import coil.request.ImageRequest
import com.example.model.DateAlbum
import com.example.model.PinItem
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.math.roundToInt

/**
 * Album card displaying a stacked card effect for date-grouped collections.
 *
 * Stacked card effect:
 * - Top layer: First image in album (upright in center foreground)
 * - Second / Left layer: Middle image in album (tilted diagonally left)
 * - Third / Right layer: Last image in album (tilted diagonally right)
 * - Subtle drop shadows separating each layer, no white borders.
 *
 * Gestures:
 * - Tap: opens the collection of images in the album
 * - Hold: adds/toggles album in favorites
 * - Swipe left/right: opens the screen-fitting preview of ~18 images
 */
@Composable
fun AlbumCard(
    album: DateAlbum,
    columnCount: Int,
    isFavorite: Boolean,
    isPortrait: Boolean = false,
    onClick: () -> Unit,
    onLongClick: () -> Unit,
    onSwipePreview: () -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val pins = album.pins
    val allAlbumPins = if (pins.isNotEmpty()) pins else album.subAlbums.flatMap { it.pins }
    val topPin = allAlbumPins.firstOrNull()
    val leftPin = if (allAlbumPins.size >= 2) allAlbumPins[allAlbumPins.size / 2] else null
    val rightPin = if (allAlbumPins.size >= 3) allAlbumPins.last() else null

    Box(
        modifier = modifier
            .fillMaxWidth()
            .testTag("album_card_${album.id}")
            .pointerInput(album.id) {
                awaitEachGesture {
                    val down = awaitFirstDown(requireUnconsumed = false)
                    val startPos = down.position
                    var isHorizontalSwipe = false
                    var isVerticalScroll = false
                    var longPressed = false
                    var totalDragX = 0f

                    val timeoutResult = withTimeoutOrNull(420L) {
                        while (true) {
                            val event = awaitPointerEvent()
                            val change = event.changes.firstOrNull() ?: break
                            val diffX = change.position.x - startPos.x
                            val diffY = change.position.y - startPos.y

                            if (kotlin.math.abs(diffY) > 20f && kotlin.math.abs(diffY) > kotlin.math.abs(diffX)) {
                                isVerticalScroll = true
                                return@withTimeoutOrNull true
                            }
                            if (kotlin.math.abs(diffX) > 25f && kotlin.math.abs(diffX) > kotlin.math.abs(diffY) * 1.2f) {
                                isHorizontalSwipe = true
                                totalDragX = diffX
                                return@withTimeoutOrNull true
                            }
                            if (!change.pressed) {
                                return@withTimeoutOrNull false
                            }
                        }
                    }

                    if (isVerticalScroll) {
                        return@awaitEachGesture
                    }

                    if (timeoutResult == null && !isHorizontalSwipe) {
                        longPressed = true
                        down.consume()
                        onLongClick()
                        do {
                            val event = awaitPointerEvent()
                            event.changes.forEach { it.consume() }
                        } while (event.changes.any { it.pressed })
                        return@awaitEachGesture
                    }

                    if (isHorizontalSwipe) {
                        do {
                            val event = awaitPointerEvent()
                            val change = event.changes.firstOrNull()
                            if (change != null) {
                                totalDragX = change.position.x - startPos.x
                                change.consume()
                            }
                        } while (event.changes.any { it.pressed })

                        if (kotlin.math.abs(totalDragX) > 30f) {
                            onSwipePreview()
                        }
                    } else if (timeoutResult == false && !longPressed) {
                        onClick()
                    }
                }
            }
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 10.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            // Stacked Cards Thumbnail Container (Three square images layered with slight diagonal offset)
            BoxWithConstraints(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 4.dp, vertical = 4.dp),
                contentAlignment = Alignment.Center
            ) {
                val cardWidth = maxWidth * 0.74f
                val cardHeight = if (isPortrait) cardWidth * 1.38f else cardWidth
                val containerHeight = cardHeight + 16.dp

                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(containerHeight),
                    contentAlignment = Alignment.Center
                ) {
                    // 1. Left Background Card (middle image, tilted diagonally left)
                    if (leftPin != null) {
                        Box(
                            modifier = Modifier
                                .size(width = cardWidth, height = cardHeight)
                                .graphicsLayer {
                                    rotationZ = -10f
                                    translationX = -cardWidth.toPx() * 0.16f
                                    translationY = 5.dp.toPx()
                                }
                                .shadow(
                                    elevation = 5.dp,
                                    shape = RoundedCornerShape(14.dp),
                                    clip = false
                                )
                                .clip(RoundedCornerShape(14.dp))
                                .background(Color(0xFF222222))
                        ) {
                            AsyncImage(
                                model = ImageRequest.Builder(context)
                                    .data(leftPin.imageUrl)
                                    .crossfade(true)
                                    .build(),
                                contentDescription = null,
                                contentScale = ContentScale.Crop,
                                modifier = Modifier.fillMaxSize()
                            )
                        }
                    }

                    // 2. Right Background Card (last image, tilted diagonally right)
                    if (rightPin != null) {
                        Box(
                            modifier = Modifier
                                .size(width = cardWidth, height = cardHeight)
                                .graphicsLayer {
                                    rotationZ = 10f
                                    translationX = cardWidth.toPx() * 0.16f
                                    translationY = 5.dp.toPx()
                                }
                                .shadow(
                                    elevation = 5.dp,
                                    shape = RoundedCornerShape(14.dp),
                                    clip = false
                                )
                                .clip(RoundedCornerShape(14.dp))
                                .background(Color(0xFF222222))
                        ) {
                            AsyncImage(
                                model = ImageRequest.Builder(context)
                                    .data(rightPin.imageUrl)
                                    .crossfade(true)
                                    .build(),
                                contentDescription = null,
                                contentScale = ContentScale.Crop,
                                modifier = Modifier.fillMaxSize()
                            )
                        }
                    }

                    // 3. Top Foreground Card (first image, upright with rounded corners and drop shadow)
                    if (topPin != null) {
                        Box(
                            modifier = Modifier
                                .size(width = cardWidth, height = cardHeight)
                                .shadow(
                                    elevation = 8.dp,
                                    shape = RoundedCornerShape(14.dp),
                                    clip = false
                                )
                                .clip(RoundedCornerShape(14.dp))
                                .background(Color(0xFF1E1E1E))
                        ) {
                            AsyncImage(
                                model = ImageRequest.Builder(context)
                                    .data(topPin.imageUrl)
                                    .crossfade(true)
                                    .build(),
                                contentDescription = album.title,
                                contentScale = ContentScale.Crop,
                                modifier = Modifier.fillMaxSize()
                            )

                            // Heart Badge if favorited
                            if (isFavorite) {
                                Surface(
                                    shape = CircleShape,
                                    color = Color.Black.copy(alpha = 0.65f),
                                    modifier = Modifier
                                        .align(Alignment.TopEnd)
                                        .padding(6.dp)
                                        .size(24.dp)
                                ) {
                                    Box(contentAlignment = Alignment.Center) {
                                        Icon(
                                            imageVector = Icons.Default.Favorite,
                                            contentDescription = "Favorited Album",
                                            tint = PinterestRed,
                                            modifier = Modifier.size(14.dp)
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(6.dp))

            // Album Metadata: Center aligned date and image count (no swipe icon)
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 4.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    text = album.title,
                    style = MaterialTheme.typography.bodyMedium.copy(
                        fontWeight = FontWeight.Bold,
                        fontSize = 13.sp,
                        color = MaterialTheme.colorScheme.onSurface
                    ),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center
                )

                Spacer(modifier = Modifier.height(2.dp))

                val totalCount = pins.size + album.subAlbums.sumOf { it.pins.size }
                Text(
                    text = if (album.subAlbums.isNotEmpty() && pins.isEmpty())
                        "${album.subAlbums.size} album${if (album.subAlbums.size > 1) "s" else ""} • $totalCount images"
                    else
                        "$totalCount image${if (totalCount > 1) "s" else ""}",
                    style = MaterialTheme.typography.bodySmall.copy(
                        fontSize = 11.sp,
                        color = PinterestTextSecondary
                    ),
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center
                )
            }
        }
    }
}

/**
 * Fullscreen Quick Preview Overlay.
 *
 * User requirement:
 * - Shows by swiping left/right on an Album
 * - Displays preview of overall album showing ~18 images fitting on screen without wasting space
 * - Does not show only top/latest images; samples evenly from top to bottom
 * - Shows no interface other than images (press back or tap to exit)
 */
@Composable
fun AlbumPreviewOverlay(
    album: DateAlbum,
    onDismiss: () -> Unit
) {
    val context = LocalContext.current

    BackHandler {
        onDismiss()
    }

    // Sample ~18 images distributed evenly from top to bottom
    val sampledPins = remember(album) {
        val all = album.pins
        if (all.size <= 18) {
            all
        } else {
            val count = 18
            val step = (all.size - 1).toDouble() / (count - 1).toDouble()
            (0 until count).map { i ->
                val idx = (i * step).roundToInt().coerceIn(0, all.size - 1)
                all[idx]
            }
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black)
            .clickable { onDismiss() }
            .testTag("album_preview_overlay")
    ) {
        BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
            val isLandscape = maxWidth > maxHeight
            val cols = if (isLandscape) 6 else 3
            val rows = if (isLandscape) 3 else 6
            val cellWidth = maxWidth / cols
            val cellHeight = maxHeight / rows

            Column(modifier = Modifier.fillMaxSize()) {
                for (r in 0 until rows) {
                    Row(modifier = Modifier.fillMaxWidth()) {
                        for (c in 0 until cols) {
                            val index = r * cols + c
                            val pin = sampledPins.getOrNull(index)
                            Box(
                                modifier = Modifier
                                    .width(cellWidth)
                                    .height(cellHeight)
                                    .padding(0.75.dp)
                                    .background(Color(0xFF161616)),
                                contentAlignment = Alignment.Center
                            ) {
                                if (pin != null) {
                                    AsyncImage(
                                        model = ImageRequest.Builder(context)
                                            .data(pin.imageUrl)
                                            .crossfade(true)
                                            .build(),
                                        contentDescription = null,
                                        contentScale = ContentScale.Crop,
                                        modifier = Modifier.fillMaxSize()
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
