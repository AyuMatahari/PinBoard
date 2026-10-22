package com.example.ui.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.wrapContentWidth
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarToday
import androidx.compose.material.icons.filled.UnfoldMore
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChange
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.model.PinItem
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestRed
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt

@Composable
fun ModernGalleryFastScroller(
    totalItems: Int,
    currentFirstVisibleIndex: Int,
    currentScrollOffset: Int = 0,
    canScrollForward: Boolean = true,
    canScrollBackward: Boolean = true,
    displayedPins: List<PinItem>,
    isScrolling: Boolean,
    onFastScrollTo: (Int) -> Unit,
    modifier: Modifier = Modifier
) {
    if (totalItems <= 6) return

    var isDragging by remember { mutableStateOf(false) }
    var dragProgress by remember { mutableFloatStateOf(0f) }
    var isVisibleByTimer by remember { mutableStateOf(false) }

    // Fade out after half second (500ms) of inactivity
    LaunchedEffect(isScrolling, isDragging) {
        if (isScrolling || isDragging) {
            isVisibleByTimer = true
        } else {
            delay(500)
            isVisibleByTimer = false
        }
    }

    // Continuous smooth sub-item scroll fraction from grid position and offset
    val rawScrollFraction by remember(currentFirstVisibleIndex, currentScrollOffset, totalItems, canScrollForward, canScrollBackward) {
        derivedStateOf {
            if (totalItems <= 1) 0f
            else if (!canScrollBackward) 0f
            else if (!canScrollForward) 1f
            else {
                val estimatedCardHeightPx = 400f
                val subItemOffset = (currentScrollOffset.toFloat() / estimatedCardHeightPx).coerceIn(0f, 1.5f)
                val smoothItemPos = currentFirstVisibleIndex.toFloat() + subItemOffset
                val total = (totalItems - 1).coerceAtLeast(1).toFloat()
                (smoothItemPos / total).coerceIn(0f, 1f)
            }
        }
    }

    // Keep dragProgress synchronized with rawScrollFraction whenever NOT dragging
    // This prevents any jumping when the user taps or holds the thumb!
    val currentRawFraction by rememberUpdatedState(rawScrollFraction)
    LaunchedEffect(rawScrollFraction, isDragging) {
        if (!isDragging) {
            dragProgress = currentRawFraction
        }
    }

    // Active fraction: direct 1:1 mapping when dragging or scrolling
    val rawActive = if (isDragging) dragProgress else rawScrollFraction
    val activeFraction = if (rawActive.isFinite()) rawActive.coerceIn(0f, 1f) else 0f
    val safeMaxIdx = (totalItems - 1).coerceAtLeast(0)
    val currentPinIndex = if (safeMaxIdx > 0) (activeFraction * safeMaxIdx).roundToInt().coerceIn(0, safeMaxIdx) else 0
    val currentPin = displayedPins.getOrNull(currentPinIndex)

    val dateLabel = remember(currentPin) {
        if (currentPin != null) {
            SimpleDateFormat("MMM yyyy", Locale.US).format(Date(currentPin.dateAddedMillis))
        } else ""
    }

    val currentTotalItems by rememberUpdatedState(totalItems)
    val onFastScrollToUpdated by rememberUpdatedState(onFastScrollTo)

    AnimatedVisibility(
        visible = isVisibleByTimer,
        enter = fadeIn(animationSpec = tween(150)),
        exit = fadeOut(animationSpec = tween(300)),
        modifier = modifier
    ) {
        BoxWithConstraints(
            modifier = Modifier
                .fillMaxHeight()
                .padding(vertical = 48.dp)
                .wrapContentWidth(Alignment.End)
                .testTag("gallery_fast_scroller")
        ) {
            val trackHeightPx = constraints.maxHeight.toFloat()
            val thumbDiameterDp = 36.dp
            val density = LocalDensity.current
            val thumbDiameterPx = with(density) { thumbDiameterDp.toPx() }
            val maxTravelPx = (trackHeightPx - thumbDiameterPx).coerceAtLeast(1f)
            val currentThumbY = (activeFraction * maxTravelPx).coerceIn(0f, maxTravelPx)

            val currentMaxTravelPx by rememberUpdatedState(maxTravelPx)

            // Date pill is shown ONLY when user taps/holds/drags the scrollbar
            androidx.compose.animation.AnimatedVisibility(
                visible = isDragging && dateLabel.isNotBlank(),
                enter = fadeIn(animationSpec = tween(120)) + scaleIn(initialScale = 0.85f),
                exit = fadeOut(animationSpec = tween(180)) + scaleOut(targetScale = 0.85f),
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .offset {
                        IntOffset(
                            x = -((thumbDiameterPx + 14.dp.toPx()).roundToInt()),
                            y = (currentThumbY - 2.dp.toPx()).roundToInt()
                        )
                    }
            ) {
                Surface(
                    shape = CircleShape,
                    color = Color.White,
                    shadowElevation = 6.dp,
                    border = androidx.compose.foundation.BorderStroke(1.dp, Color(0x1F000000))
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.CalendarToday,
                            contentDescription = null,
                            tint = PinterestRed,
                            modifier = Modifier.size(13.dp)
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(
                            text = if (dateLabel.isNotBlank()) "$dateLabel • Pin ${currentPinIndex + 1}/$totalItems" else "Pin ${currentPinIndex + 1} of $totalItems",
                            color = PinterestBlack,
                            fontWeight = FontWeight.Bold,
                            fontSize = 11.sp,
                            maxLines = 1,
                            softWrap = false
                        )
                    }
                }
            }

            // Interactive Scroller Track & Thumb Container
            // Captures gestures without jumpiness: touching near thumb anchors at current position
            Box(
                modifier = Modifier
                    .align(Alignment.CenterEnd)
                    .fillMaxHeight()
                    .width(48.dp)
                    .pointerInput(Unit) {
                        awaitEachGesture {
                            val down = awaitFirstDown(requireUnconsumed = false)
                            val maxPx = currentMaxTravelPx.coerceAtLeast(1f)
                            val thumbCenterY = currentRawFraction * maxPx + (thumbDiameterPx / 2f)
                            val distFromThumb = abs(down.position.y - thumbCenterY)

                            // If user touches near thumb (within 36dp), do NOT jump: anchor exactly at current position
                            val initialFraction = if (distFromThumb <= thumbDiameterPx) {
                                currentRawFraction.coerceIn(0f, 1f)
                            } else {
                                val touchY = down.position.y - (thumbDiameterPx / 2f)
                                (touchY / maxPx).coerceIn(0f, 1f)
                            }

                            dragProgress = initialFraction
                            var currentY = initialFraction * maxPx
                            isDragging = true

                            // Only trigger scroll jump if tapped away on the track, not when holding the thumb
                            if (distFromThumb > thumbDiameterPx) {
                                val total = currentTotalItems
                                val targetIdx = (initialFraction * (total - 1)).roundToInt().coerceIn(0, total - 1)
                                onFastScrollToUpdated(targetIdx)
                            }

                            val pointerId = down.id
                            while (true) {
                                val event = awaitPointerEvent()
                                val change = event.changes.firstOrNull { it.id == pointerId } ?: break
                                if (!change.pressed) {
                                    break
                                }
                                val deltaY = change.positionChange().y
                                if (deltaY != 0f) {
                                    change.consume()
                                    currentY = (currentY + deltaY).coerceIn(0f, maxPx)
                                    val newFraction = (currentY / maxPx).coerceIn(0f, 1f)
                                    dragProgress = newFraction
                                    val total = currentTotalItems
                                    val targetIdx = (newFraction * (total - 1)).roundToInt().coerceIn(0, total - 1)
                                    onFastScrollToUpdated(targetIdx)
                                }
                            }
                            isDragging = false
                        }
                    }
            ) {
                // Circular Scrollbar Thumb
                Box(
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .offset { IntOffset(x = -4.dp.toPx().roundToInt(), y = currentThumbY.roundToInt()) }
                        .size(thumbDiameterDp)
                        .shadow(elevation = 6.dp, shape = CircleShape)
                        .clip(CircleShape)
                        .background(Color.White)
                        .border(1.dp, Color(0x1F000000), CircleShape)
                        .testTag("fast_scroller_thumb"),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = Icons.Default.UnfoldMore,
                        contentDescription = "Scroll Scrubber",
                        tint = if (isDragging) PinterestRed else PinterestBlack,
                        modifier = Modifier.size(18.dp)
                    )
                }
            }
        }
    }
}
