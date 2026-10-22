package com.example.ui.components

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import com.example.util.LinkExtractor
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.calculatePan
import androidx.compose.foundation.gestures.calculateZoom
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.ui.input.pointer.positionChanged
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.filled.VerticalAlignTop
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
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
import com.example.model.PinItem
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillDarkGray
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.io.File
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.launch

@OptIn(ExperimentalLayoutApi::class, ExperimentalFoundationApi::class)
@Composable
fun FullscreenGalleryViewer(
    pins: List<PinItem>,
    initialIndex: Int,
    isFavorite: (PinItem) -> Boolean = { false },
    onToggleFavorite: (PinItem) -> Unit = {},
    onMoveToTop: (PinItem) -> Unit = {},
    onDeleteSingle: (PinItem) -> Unit = {},
    onClose: () -> Unit,
    onDownloadSingle: (PinItem) -> Unit,
    disableArrowNavigation: Boolean = false,
    modifier: Modifier = Modifier
) {
    if (pins.isEmpty()) {
        onClose()
        return
    }

    val context = LocalContext.current
    val safeInitial = initialIndex.coerceIn(0, pins.size - 1)
    val isRotary = pins.size > 1
    val rotaryMultiplier = 10_000
    val virtualPageCount = if (isRotary) pins.size * rotaryMultiplier else pins.size
    val virtualStartIndex = if (isRotary) (rotaryMultiplier / 2) * pins.size + safeInitial else safeInitial

    val pagerState = rememberPagerState(
        initialPage = virtualStartIndex,
        pageCount = { virtualPageCount }
    )

    var showControls by remember { mutableStateOf(false) }
    var isCurrentPageZoomed by remember { mutableStateOf(false) }
    var pinForImageHoldDialog by remember { mutableStateOf<PinItem?>(null) }

    BackHandler {
        onClose()
    }

    val currentActualIndex = if (isRotary) (pagerState.currentPage % pins.size) else pagerState.currentPage
    val currentPin = pins.getOrElse(currentActualIndex) { pins[0] }
    val pinIsFavorite = isFavorite(currentPin)

    val coroutineScope = androidx.compose.runtime.rememberCoroutineScope()

    // Always ensure scrolling is unlocked on page transitions
    LaunchedEffect(pagerState.currentPage) {
        isCurrentPageZoomed = false
    }

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(Color.Black)
            .testTag("fullscreen_gallery_viewer")
    ) {
        // Main Horizontal Pager with rotary wrap-around support (Requirement 8)
        HorizontalPager(
            state = pagerState,
            userScrollEnabled = !isCurrentPageZoomed,
            modifier = Modifier.fillMaxSize(),
            key = { index -> "${pins[if (isRotary) index % pins.size else index].id}_$index" }
        ) { pageIndex ->
            val actualPinIndex = if (isRotary) pageIndex % pins.size else pageIndex
            val pin = pins[actualPinIndex]
            var scale by remember { mutableFloatStateOf(1f) }
            var offsetX by remember { mutableFloatStateOf(0f) }
            var offsetY by remember { mutableFloatStateOf(0f) }

            // Reset zoom when navigating away to another page
            LaunchedEffect(currentActualIndex) {
                if (currentActualIndex != actualPinIndex) {
                    scale = 1f
                    offsetX = 0f
                    offsetY = 0f
                    isCurrentPageZoomed = false
                }
            }

            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .pointerInput(actualPinIndex) {
                        detectTapGestures(
                            onTap = {
                                showControls = !showControls
                            },
                            onDoubleTap = { tapOffset ->
                                if (scale > 1.05f) {
                                    scale = 1f
                                    offsetX = 0f
                                    offsetY = 0f
                                    isCurrentPageZoomed = false
                                } else {
                                    scale = 2.5f
                                    isCurrentPageZoomed = true
                                    val centerX = size.width / 2f
                                    val centerY = size.height / 2f
                                    val maxOffsetX = (size.width * 1.5f) / 2f
                                    val maxOffsetY = (size.height * 1.5f) / 2f
                                    offsetX = ((centerX - tapOffset.x) * 1.5f).coerceIn(-maxOffsetX, maxOffsetX)
                                    offsetY = ((centerY - tapOffset.y) * 1.5f).coerceIn(-maxOffsetY, maxOffsetY)
                                }
                            },
                            onLongPress = {
                                pinForImageHoldDialog = pin
                            }
                        )
                    }
                    .pointerInput(actualPinIndex) {
                        awaitEachGesture {
                            awaitFirstDown(requireUnconsumed = false)
                            do {
                                val event = awaitPointerEvent()
                                val pressedList = event.changes.filter { it.pressed }
                                val pointerCount = pressedList.size

                                if (pointerCount >= 2 || scale > 1.05f) {
                                    val zoom = event.calculateZoom()
                                    val pan = event.calculatePan()

                                    val newScale = (scale * zoom).coerceIn(1f, 5f)
                                    scale = newScale
                                    if (newScale > 1.05f) {
                                        isCurrentPageZoomed = true
                                        val maxOffsetX = (size.width * (newScale - 1f)) / 2f
                                        val maxOffsetY = (size.height * (newScale - 1f)) / 2f
                                        offsetX = (offsetX + pan.x).coerceIn(-maxOffsetX, maxOffsetX)
                                        offsetY = (offsetY + pan.y).coerceIn(-maxOffsetY, maxOffsetY)
                                    } else {
                                        scale = 1f
                                        offsetX = 0f
                                        offsetY = 0f
                                        isCurrentPageZoomed = false
                                    }

                                    event.changes.forEach {
                                        if (it.positionChanged()) {
                                            it.consume()
                                        }
                                    }
                                }
                            } while (event.changes.any { it.pressed })

                            // When fingers are lifted, if scale <= 1.05f, ensure fully reset so pager can scroll
                            if (scale <= 1.05f) {
                                scale = 1f
                                offsetX = 0f
                                offsetY = 0f
                                isCurrentPageZoomed = false
                            }
                        }
                    },
                contentAlignment = Alignment.Center
            ) {
                AsyncImage(
                    model = ImageRequest.Builder(context)
                        .data(pin.imageUrl)
                        .crossfade(true)
                        .build(),
                    contentDescription = pin.title,
                    contentScale = ContentScale.Fit,
                    modifier = Modifier
                        .fillMaxSize()
                        .graphicsLayer {
                            scaleX = scale
                            scaleY = scale
                            translationX = offsetX
                            translationY = offsetY
                        }
                )
            }
        }


        // Top Navigation & Action Bar Overlay
        AnimatedVisibility(
            visible = showControls,
            enter = fadeIn(),
            exit = fadeOut(),
            modifier = Modifier.align(Alignment.TopCenter)
        ) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Color.Black.copy(alpha = 0.65f))
                    .statusBarsPadding()
                    .padding(horizontal = 8.dp, vertical = 6.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    IconButton(
                        onClick = onClose,
                        modifier = Modifier.size(40.dp)
                    ) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Back",
                            tint = Color.White
                        )
                    }

                    // Page Index Indicator
                    Surface(
                        shape = RoundedCornerShape(16.dp),
                        color = PinterestPillDarkGray.copy(alpha = 0.8f)
                    ) {
                        Text(
                            text = "${currentActualIndex + 1} / ${pins.size}",
                            color = Color.White,
                            fontWeight = FontWeight.Bold,
                            fontSize = 13.sp,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 4.dp)
                        )
                    }

                    // Action Buttons Row: Put at Top, Favorite, Delete, Share, Save
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        // Put at Top action (User requirement)
                        IconButton(
                            onClick = { onMoveToTop(currentPin) },
                            modifier = Modifier
                                .size(38.dp)
                                .testTag("fullscreen_put_at_top_button")
                        ) {
                            Icon(
                                imageVector = Icons.Default.VerticalAlignTop,
                                contentDescription = "Put image at top",
                                tint = Color.White
                            )
                        }

                        // Favorite toggle button (User requirement)
                        IconButton(
                            onClick = { onToggleFavorite(currentPin) },
                            modifier = Modifier
                                .size(38.dp)
                                .testTag("fullscreen_favorite_button")
                        ) {
                            Icon(
                                imageVector = if (pinIsFavorite) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                                contentDescription = "Toggle favorite",
                                tint = if (pinIsFavorite) PinterestRed else Color.White
                            )
                        }

                        // Delete button
                        IconButton(
                            onClick = { onDeleteSingle(currentPin) },
                            modifier = Modifier
                                .size(38.dp)
                                .testTag("fullscreen_delete_button")
                        ) {
                            Icon(
                                imageVector = Icons.Default.DeleteOutline,
                                contentDescription = "Delete from board",
                                tint = Color.White
                            )
                        }

                        // Share button
                        IconButton(
                            onClick = {
                                val shareIntent = Intent(Intent.ACTION_SEND).apply {
                                    type = "text/plain"
                                    putExtra(Intent.EXTRA_SUBJECT, currentPin.title)
                                    putExtra(Intent.EXTRA_TEXT, "${currentPin.title}\n${currentPin.imageUrl}")
                                }
                                context.startActivity(Intent.createChooser(shareIntent, "Share Pin"))
                            },
                            modifier = Modifier.size(38.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.Share,
                                contentDescription = "Share",
                                tint = Color.White
                            )
                        }

                        // Download button
                        IconButton(
                            onClick = { onDownloadSingle(currentPin) },
                            modifier = Modifier
                                .size(38.dp)
                                .testTag("fullscreen_download_button")
                        ) {
                            Icon(
                                imageVector = Icons.Default.Download,
                                contentDescription = "Save to Downloads",
                                tint = Color.White
                            )
                        }
                    }
                }
            }
        }

        // Navigation Arrow Buttons on left and right edges for quick navigation
        if (pins.size > 1 && !disableArrowNavigation) {
            AnimatedVisibility(
                visible = showControls,
                enter = fadeIn(),
                exit = fadeOut(),
                modifier = Modifier
                    .align(Alignment.CenterStart)
                    .padding(start = 12.dp)
            ) {
                IconButton(
                    onClick = {
                        coroutineScope.launch {
                            val target = (pagerState.currentPage - 1).coerceAtLeast(0)
                            pagerState.animateScrollToPage(target)
                        }
                    },
                    modifier = Modifier
                        .size(44.dp)
                        .background(Color.Black.copy(alpha = 0.5f), CircleShape)
                        .testTag("fullscreen_prev_button")
                ) {
                    Icon(
                        imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                        contentDescription = "Previous image",
                        tint = Color.White,
                        modifier = Modifier.size(24.dp)
                    )
                }
            }

            AnimatedVisibility(
                visible = showControls,
                enter = fadeIn(),
                exit = fadeOut(),
                modifier = Modifier
                    .align(Alignment.CenterEnd)
                    .padding(end = 12.dp)
            ) {
                IconButton(
                    onClick = {
                        coroutineScope.launch {
                            val target = (pagerState.currentPage + 1).coerceAtMost(virtualPageCount - 1)
                            pagerState.animateScrollToPage(target)
                        }
                    },
                    modifier = Modifier
                        .size(44.dp)
                        .background(Color.Black.copy(alpha = 0.5f), CircleShape)
                        .testTag("fullscreen_next_button")
                ) {
                    Icon(
                        imageVector = Icons.AutoMirrored.Filled.ArrowForward,
                        contentDescription = "Next image",
                        tint = Color.White,
                        modifier = Modifier.size(24.dp)
                    )
                }
            }
        }

        // Bottom Info & Media Panel Overlay
        AnimatedVisibility(
            visible = showControls,
            enter = fadeIn(),
            exit = fadeOut(),
            modifier = Modifier.align(Alignment.BottomCenter)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Color.Black.copy(alpha = 0.75f))
                    .navigationBarsPadding()
                    .padding(horizontal = 16.dp, vertical = 12.dp)
            ) {
                // Title
                Text(
                    text = currentPin.title,
                    style = MaterialTheme.typography.titleMedium.copy(
                        fontWeight = FontWeight.Bold,
                        fontSize = 16.sp,
                        color = Color.White
                    ),
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis
                )

                // Author / Host Domain
                val subline = currentPin.author.ifBlank { currentPin.displayDomain }
                if (subline.isNotBlank()) {
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = subline,
                        style = MaterialTheme.typography.bodySmall.copy(
                            fontWeight = FontWeight.Medium,
                            fontSize = 13.sp,
                            color = Color(0xFFDDDDDD)
                        ),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }

                Spacer(modifier = Modifier.height(8.dp))

                // Media Metadata Pills
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    if (currentPin.boardName.isNotBlank()) {
                        MetadataPill(text = currentPin.boardName)
                    }
                    MetadataPill(text = currentPin.formattedDimensions)
                    MetadataPill(text = currentPin.formattedFileSize)
                    if (currentPin.mimeType.isNotBlank()) {
                        MetadataPill(text = currentPin.mimeType)
                    }
                    if (currentPin.displayDomain.isNotBlank()) {
                        MetadataPill(text = currentPin.displayDomain)
                    }
                    if (currentPin.isBrokenOrUnreachable) {
                        MetadataPill(text = "⚠ Unreachable link", isWarning = true)
                    }
                    if (pinIsFavorite) {
                        MetadataPill(text = "♥ Favorited", isRed = true)
                    }

                    // Webpage link pill/tag (User requirement 2)
                    // If sourceUrl is a webpage link, show pill; tap to open in external browser
                    val webpageLink = currentPin.sourceUrl.trim().ifBlank {
                        if (currentPin.imageUrl.startsWith("http") && !currentPin.imageUrl.endsWith(".jpg") && !currentPin.imageUrl.endsWith(".png") && !currentPin.imageUrl.endsWith(".webp")) {
                            currentPin.imageUrl
                        } else ""
                    }
                    if (webpageLink.isNotBlank() && (webpageLink.startsWith("http://", ignoreCase = true) || webpageLink.startsWith("https://", ignoreCase = true))) {
                        val hostLabel = LinkExtractor.extractHost(webpageLink).ifBlank { "Webpage" }
                        var showLinkOptionsDialog by remember { mutableStateOf(false) }

                        MetadataPill(
                            text = "🔗 $hostLabel ↗",
                            isLink = true,
                            onClick = {
                                try {
                                    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(webpageLink)).apply {
                                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                                    }
                                    context.startActivity(intent)
                                } catch (_: Exception) {
                                    Toast.makeText(context, "Could not open browser", Toast.LENGTH_SHORT).show()
                                }
                            },
                            onLongClick = {
                                showLinkOptionsDialog = true
                            },
                            testTag = "webpage_link_pill"
                        )

                        if (showLinkOptionsDialog) {
                            AlertDialog(
                                onDismissRequest = { showLinkOptionsDialog = false },
                                title = {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Icon(
                                            imageVector = Icons.Default.Share,
                                            contentDescription = null,
                                            tint = PinterestRed,
                                            modifier = Modifier.size(20.dp)
                                        )
                                        Spacer(modifier = Modifier.width(8.dp))
                                        Text(
                                            text = hostLabel.ifBlank { "Webpage Link" },
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 16.sp
                                        )
                                    }
                                },
                                text = {
                                    Column(modifier = Modifier.fillMaxWidth()) {
                                        Text(
                                            text = webpageLink,
                                            fontSize = 12.sp,
                                            color = PinterestTextSecondary,
                                            maxLines = 2,
                                            overflow = TextOverflow.Ellipsis
                                        )

                                        Spacer(modifier = Modifier.height(14.dp))

                                        // Option 1: Copy
                                        Surface(
                                            shape = RoundedCornerShape(10.dp),
                                            color = PinterestPillGray,
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .clickable {
                                                    showLinkOptionsDialog = false
                                                    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                                                    val clip = ClipData.newPlainText("Webpage Link", webpageLink)
                                                    clipboard.setPrimaryClip(clip)
                                                    Toast.makeText(context, "Copied link to clipboard", Toast.LENGTH_SHORT).show()
                                                }
                                                .testTag("link_option_copy")
                                        ) {
                                            Row(
                                                modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
                                                verticalAlignment = Alignment.CenterVertically
                                            ) {
                                                Icon(
                                                    imageVector = Icons.Default.ContentCopy,
                                                    contentDescription = "Copy",
                                                    tint = PinterestRed,
                                                    modifier = Modifier.size(18.dp)
                                                )
                                                Spacer(modifier = Modifier.width(10.dp))
                                                Text(
                                                    text = "Copy",
                                                    fontWeight = FontWeight.SemiBold,
                                                    fontSize = 14.sp,
                                                    color = PinterestBlack
                                                )
                                            }
                                        }

                                        Spacer(modifier = Modifier.height(8.dp))

                                        // Option 2: Share
                                        Surface(
                                            shape = RoundedCornerShape(10.dp),
                                            color = PinterestPillGray,
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .clickable {
                                                    showLinkOptionsDialog = false
                                                    val shareIntent = Intent(Intent.ACTION_SEND).apply {
                                                        type = "text/plain"
                                                        putExtra(Intent.EXTRA_SUBJECT, currentPin.title)
                                                        putExtra(Intent.EXTRA_TEXT, webpageLink)
                                                    }
                                                    context.startActivity(Intent.createChooser(shareIntent, "Share Webpage Link"))
                                                }
                                                .testTag("link_option_share")
                                        ) {
                                            Row(
                                                modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
                                                verticalAlignment = Alignment.CenterVertically
                                            ) {
                                                Icon(
                                                    imageVector = Icons.Default.Share,
                                                    contentDescription = "Share",
                                                    tint = PinterestRed,
                                                    modifier = Modifier.size(18.dp)
                                                )
                                                Spacer(modifier = Modifier.width(10.dp))
                                                Text(
                                                    text = "Share",
                                                    fontWeight = FontWeight.SemiBold,
                                                    fontSize = 14.sp,
                                                    color = PinterestBlack
                                                )
                                            }
                                        }
                                    }
                                },
                                confirmButton = {},
                                dismissButton = {
                                    TextButton(onClick = { showLinkOptionsDialog = false }) {
                                        Text("Cancel", color = PinterestTextSecondary)
                                    }
                                }
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                Button(
                    onClick = { onDownloadSingle(currentPin) },
                    colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                    shape = RoundedCornerShape(24.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(44.dp)
                        .testTag("fullscreen_save_to_downloads_button")
                ) {
                    Icon(
                        imageVector = Icons.Default.Download,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp),
                        tint = Color.White
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "Save to Downloads",
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp,
                        color = Color.White
                    )
                }
            }
        }

        pinForImageHoldDialog?.let { pin ->
            MinimalImageHoldDialog(
                pin = pin,
                onDismiss = { pinForImageHoldDialog = null }
            )
        }
    }
}

@Composable
private fun MinimalImageHoldDialog(
    pin: PinItem,
    onDismiss: () -> Unit
) {
    val context = LocalContext.current
    val coroutineScope = androidx.compose.runtime.rememberCoroutineScope()
    var isProcessing by remember { mutableStateOf(false) }

    Dialog(
        onDismissRequest = {
            if (!isProcessing) onDismiss()
        },
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            shape = RoundedCornerShape(24.dp),
            color = MaterialTheme.colorScheme.surface,
            tonalElevation = 6.dp,
            modifier = Modifier
                .fillMaxWidth(0.88f)
                .widthIn(max = 380.dp)
                .testTag("minimal_image_hold_dialog")
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(20.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                // 1. Image Preview
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(200.dp)
                        .clip(RoundedCornerShape(16.dp))
                        .background(Color.Black.copy(alpha = 0.08f)),
                    contentAlignment = Alignment.Center
                ) {
                    AsyncImage(
                        model = ImageRequest.Builder(context)
                            .data(pin.imageUrl)
                            .crossfade(true)
                            .build(),
                        contentDescription = pin.title,
                        contentScale = ContentScale.Crop,
                        modifier = Modifier
                            .fillMaxSize()
                            .clip(RoundedCornerShape(16.dp))
                    )
                }

                Spacer(modifier = Modifier.height(14.dp))

                // 2. Image Name
                Text(
                    text = pin.title.ifBlank { "Image" },
                    style = MaterialTheme.typography.titleMedium.copy(
                        fontWeight = FontWeight.Bold,
                        fontSize = 15.sp,
                        color = MaterialTheme.colorScheme.onSurface
                    ),
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("image_hold_dialog_title")
                )

                Spacer(modifier = Modifier.height(16.dp))

                // 3. Option 1: Copy Image itself (not link)
                Surface(
                    shape = RoundedCornerShape(14.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .clickable(enabled = !isProcessing) {
                            isProcessing = true
                            coroutineScope.launch {
                                val uri = prepareImageUriForPin(context, pin)
                                isProcessing = false
                                if (uri != null) {
                                    copyImageToClipboard(context, pin, uri)
                                    onDismiss()
                                } else {
                                    Toast.makeText(context, "Could not prepare image file", Toast.LENGTH_SHORT).show()
                                }
                            }
                        }
                        .testTag("image_hold_option_copy")
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 13.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = Icons.Default.ContentCopy,
                            contentDescription = "Copy Image",
                            tint = PinterestRed,
                            modifier = Modifier.size(20.dp)
                        )
                        Spacer(modifier = Modifier.width(12.dp))
                        Text(
                            text = "Copy Image",
                            fontWeight = FontWeight.SemiBold,
                            fontSize = 14.sp,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                // 4. Option 2: Share Image itself (not link)
                Surface(
                    shape = RoundedCornerShape(14.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .clickable(enabled = !isProcessing) {
                            isProcessing = true
                            coroutineScope.launch {
                                val uri = prepareImageUriForPin(context, pin)
                                isProcessing = false
                                if (uri != null) {
                                    shareImage(context, pin, uri)
                                    onDismiss()
                                } else {
                                    Toast.makeText(context, "Could not prepare image file", Toast.LENGTH_SHORT).show()
                                }
                            }
                        }
                        .testTag("image_hold_option_share")
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 13.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = Icons.Default.Share,
                            contentDescription = "Share Image",
                            tint = PinterestRed,
                            modifier = Modifier.size(20.dp)
                        )
                        Spacer(modifier = Modifier.width(12.dp))
                        Text(
                            text = "Share Image",
                            fontWeight = FontWeight.SemiBold,
                            fontSize = 14.sp,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                    }
                }

                if (isProcessing) {
                    Spacer(modifier = Modifier.height(12.dp))
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.Center
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(18.dp),
                            color = PinterestRed,
                            strokeWidth = 2.dp
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "Preparing image file...",
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                TextButton(
                    onClick = onDismiss,
                    enabled = !isProcessing,
                    modifier = Modifier
                        .align(Alignment.End)
                        .testTag("image_hold_dialog_cancel")
                ) {
                    Text(
                        text = "Cancel",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontWeight = FontWeight.Medium
                    )
                }
            }
        }
    }
}

private suspend fun prepareImageUriForPin(context: Context, pin: PinItem): Uri? = withContext(Dispatchers.IO) {
    try {
        if (pin.imageUrl.startsWith("content://")) {
            return@withContext Uri.parse(pin.imageUrl)
        }
        if (pin.imageUrl.startsWith("file://")) {
            val f = File(Uri.parse(pin.imageUrl).path ?: "")
            if (f.exists()) {
                return@withContext FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", f)
            }
        }

        val cacheDir = File(context.cacheDir, "shared_images").apply { if (!exists()) mkdirs() }
        val safeName = "share_${pin.id.filter { it.isLetterOrDigit() }.take(25).ifBlank { "img_${System.currentTimeMillis()}" }}.jpg"
        val file = File(cacheDir, safeName)

        if (!file.exists() || file.length() == 0L) {
            val client = okhttp3.OkHttpClient.Builder()
                .connectTimeout(10, java.util.concurrent.TimeUnit.SECONDS)
                .readTimeout(15, java.util.concurrent.TimeUnit.SECONDS)
                .build()
            val request = okhttp3.Request.Builder().url(pin.imageUrl).build()
            val response = client.newCall(request).execute()
            if (response.isSuccessful && response.body != null) {
                FileOutputStream(file).use { out ->
                    response.body!!.byteStream().copyTo(out)
                }
            }
        }

        if (file.exists() && file.length() > 0L) {
            FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        } else {
            null
        }
    } catch (e: Exception) {
        android.util.Log.e("FullscreenGalleryViewer", "prepareImageUriForPin error", e)
        null
    }
}

private fun copyImageToClipboard(context: Context, pin: PinItem, uri: Uri) {
    try {
        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clip = ClipData.newUri(context.contentResolver, pin.title.ifBlank { "Image" }, uri)
        clipboard.setPrimaryClip(clip)
        Toast.makeText(context, "Image copied to clipboard", Toast.LENGTH_SHORT).show()
    } catch (e: Exception) {
        Toast.makeText(context, "Failed to copy image: ${e.message}", Toast.LENGTH_SHORT).show()
    }
}

private fun shareImage(context: Context, pin: PinItem, uri: Uri) {
    try {
        val shareIntent = Intent(Intent.ACTION_SEND).apply {
            type = pin.mimeType.ifBlank { "image/jpeg" }
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        val chooser = Intent.createChooser(shareIntent, "Share Image")
        chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(chooser)
    } catch (e: Exception) {
        Toast.makeText(context, "Failed to share image: ${e.message}", Toast.LENGTH_SHORT).show()
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun MetadataPill(
    text: String,
    isWarning: Boolean = false,
    isRed: Boolean = false,
    isLink: Boolean = false,
    onClick: (() -> Unit)? = null,
    onLongClick: (() -> Unit)? = null,
    testTag: String? = null
) {
    val clickModifier = if (onClick != null && onLongClick != null) {
        Modifier.combinedClickable(
            onClick = onClick,
            onLongClick = onLongClick
        )
    } else if (onClick != null) {
        Modifier.clickable(onClick = onClick)
    } else Modifier

    val baseModifier = Modifier
        .height(26.dp)
        .clip(RoundedCornerShape(13.dp))
        .then(if (testTag != null) Modifier.testTag(testTag) else Modifier)
        .then(clickModifier)

    Surface(
        shape = RoundedCornerShape(13.dp),
        color = if (isRed) PinterestRed.copy(alpha = 0.35f)
        else if (isWarning) Color(0xFF5C1D1D)
        else if (isLink) Color(0xFF162B47)
        else Color(0xFF262626),
        border = if (isLink) androidx.compose.foundation.BorderStroke(1.dp, Color(0xFF4A90E2).copy(alpha = 0.6f)) else null,
        modifier = baseModifier
    ) {
        Box(
            modifier = Modifier.padding(horizontal = 9.dp),
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = text,
                color = if (isRed) PinterestRed
                else if (isWarning) Color(0xFFFFB4AB)
                else if (isLink) Color(0xFF90CAF9)
                else Color(0xFFE0E0E0),
                fontSize = 11.sp,
                fontWeight = if (isLink) FontWeight.SemiBold else FontWeight.Medium
            )
        }
    }
}
