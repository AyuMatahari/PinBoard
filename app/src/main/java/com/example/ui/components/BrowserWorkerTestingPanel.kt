package com.example.ui.components

import android.view.ViewGroup
import android.webkit.WebView
import android.widget.FrameLayout
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BugReport
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.Height
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.automirrored.filled.Login
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Security
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material.icons.automirrored.filled.Sort
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.SwapVert
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.example.scanner.PinterestScanner
import com.example.scanner.ScanDiagnostics
import com.example.scanner.ScannerState
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestRed

@Composable
fun BrowserWorkerTestingPanel(
    scanner: PinterestScanner,
    scannerState: ScannerState,
    diagnostics: ScanDiagnostics,
    boardUrl: String,
    onStartScan: () -> Unit,
    onReorderPins: () -> Unit = {},
    isCustomBoard: Boolean = false,
    modifier: Modifier = Modifier
) {
    var isExpanded by remember { mutableStateOf(true) }
    var isWebViewVisible by remember { mutableStateOf(true) }
    var isStatusVisible by remember { mutableStateOf(true) }
    var browserHeightDp by remember { mutableStateOf(720.dp) }

    Card(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp, vertical = 6.dp)
            .testTag("browser_worker_testing_panel"),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f)
        ),
        border = CardDefaults.outlinedCardBorder().copy(
            brush = androidx.compose.ui.graphics.SolidColor(
                if (scannerState.isScanning) PinterestRed.copy(alpha = 0.6f)
                else MaterialTheme.colorScheme.outline.copy(alpha = 0.25f)
            )
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp)
        ) {
            // Header Bar
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { isExpanded = !isExpanded },
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Box(
                        modifier = Modifier
                            .size(10.dp)
                            .clip(CircleShape)
                            .background(
                                when {
                                    scannerState.isScanning && !scannerState.isPaused -> Color(0xFF4CAF50)
                                    scannerState.isPaused -> Color(0xFFFF9800)
                                    else -> Color.Gray
                                }
                            )
                    )

                    Text(
                        text = "Browser Worker (Testing)",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold
                    )

                    // Image Blocking Status Badge
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = if (diagnostics.isImageBlockingEnabled) Color(0xFF1E88E5).copy(alpha = 0.15f) else Color(0xFF4CAF50).copy(alpha = 0.15f)
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(4.dp)
                        ) {
                            Icon(
                                imageVector = if (diagnostics.isImageBlockingEnabled) Icons.Default.Shield else Icons.Default.Image,
                                contentDescription = "Image Mode",
                                modifier = Modifier.size(12.dp),
                                tint = if (diagnostics.isImageBlockingEnabled) Color(0xFF1976D2) else Color(0xFF2E7D32)
                            )
                            Text(
                                text = if (diagnostics.isImageBlockingEnabled) "Images: Blocked (${diagnostics.blockedImageRequests})" else "Images: Allowed",
                                fontSize = 11.sp,
                                fontWeight = FontWeight.SemiBold,
                                color = if (diagnostics.isImageBlockingEnabled) Color(0xFF1976D2) else Color(0xFF2E7D32)
                            )
                        }
                    }
                }

                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (scannerState.isLoggedIn) {
                        Surface(
                            shape = RoundedCornerShape(12.dp),
                            color = Color(0xFF4CAF50).copy(alpha = 0.15f),
                            modifier = Modifier.padding(end = 4.dp)
                        ) {
                            Text(
                                text = "Session Active",
                                fontSize = 11.sp,
                                fontWeight = FontWeight.SemiBold,
                                color = Color(0xFF2E7D32),
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }
                    }

                    Icon(
                        imageVector = if (isExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                        contentDescription = if (isExpanded) "Collapse" else "Expand",
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            AnimatedVisibility(
                visible = isExpanded,
                enter = expandVertically() + fadeIn(),
                exit = shrinkVertically() + fadeOut()
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 10.dp)
                ) {
                    if (isCustomBoard) {
                        Surface(
                            shape = RoundedCornerShape(10.dp),
                            color = MaterialTheme.colorScheme.surfaceVariant,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(bottom = 8.dp)
                        ) {
                            Row(
                                modifier = Modifier.padding(10.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Security,
                                    contentDescription = null,
                                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                                    modifier = Modifier.size(16.dp)
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    text = "Debug Panel is visible, but Browser Worker is disabled for Custom Boards. (Custom boards store direct image links).",
                                    fontSize = 11.sp,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    }

                    // Diagnostics HUD Chips (Brief Section 21)
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .horizontalScroll(rememberScrollState())
                            .padding(bottom = 8.dp),
                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        DiagnosticChip(
                            label = "Unique Pins",
                            value = "${diagnostics.uniquePins}",
                            highlight = diagnostics.uniquePins > 0
                        )
                        DiagnosticChip(
                            label = "Feed Responses",
                            value = "${diagnostics.responseCount}"
                        )
                        DiagnosticChip(
                            label = "Blocked Images",
                            value = "${diagnostics.blockedImageRequests} (0 KB)"
                        )
                        DiagnosticChip(
                            label = "Scrolls",
                            value = "${diagnostics.scrollIterations} / 300"
                        )
                        DiagnosticChip(
                            label = "Doc Height",
                            value = "${diagnostics.documentHeight}px"
                        )
                        DiagnosticChip(
                            label = "Duration",
                            value = "${diagnostics.scanDurationSeconds}s"
                        )
                        if (diagnostics.lastBookmark.isNotBlank()) {
                            DiagnosticChip(
                                label = "Bookmark",
                                value = diagnostics.lastBookmark.take(8) + "..."
                            )
                        }
                    }

                    // Worker Control Buttons
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // Scan Action Button
                        if (!scannerState.isScanning) {
                            Button(
                                onClick = onStartScan,
                                enabled = !isCustomBoard,
                                colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                                shape = RoundedCornerShape(10.dp),
                                modifier = Modifier.height(36.dp).testTag("start_scan_worker_btn")
                            ) {
                                Icon(Icons.Default.PlayArrow, contentDescription = null, modifier = Modifier.size(16.dp))
                                Spacer(modifier = Modifier.width(4.dp))
                                Text("Scan Board", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            }
                        } else {
                            if (scannerState.isPaused) {
                                Button(
                                    onClick = { scanner.resumeScan() },
                                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF4CAF50)),
                                    shape = RoundedCornerShape(10.dp),
                                    modifier = Modifier.height(36.dp)
                                ) {
                                    Icon(Icons.Default.PlayArrow, contentDescription = null, modifier = Modifier.size(16.dp))
                                    Spacer(modifier = Modifier.width(4.dp))
                                    Text("Resume", fontSize = 12.sp)
                                }
                            } else {
                                OutlinedButton(
                                    onClick = { scanner.pauseScan() },
                                    shape = RoundedCornerShape(10.dp),
                                    modifier = Modifier.height(36.dp)
                                ) {
                                    Icon(Icons.Default.Pause, contentDescription = null, modifier = Modifier.size(16.dp))
                                    Spacer(modifier = Modifier.width(4.dp))
                                    Text("Pause", fontSize = 12.sp)
                                }
                            }

                            Button(
                                onClick = { scanner.stopScan() },
                                colors = ButtonDefaults.buttonColors(containerColor = PinterestBlack),
                                shape = RoundedCornerShape(10.dp),
                                modifier = Modifier.height(36.dp)
                            ) {
                                Icon(Icons.Default.Stop, contentDescription = null, modifier = Modifier.size(16.dp))
                                Spacer(modifier = Modifier.width(4.dp))
                                Text("Stop", fontSize = 12.sp)
                            }
                        }

                        // Reorder Pins After Scan Button
                        OutlinedButton(
                            onClick = onReorderPins,
                            enabled = !isCustomBoard,
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier.height(36.dp).testTag("reorder_pins_btn")
                        ) {
                            Icon(Icons.AutoMirrored.Filled.Sort, contentDescription = null, modifier = Modifier.size(16.dp), tint = if (!isCustomBoard) PinterestRed else Color.Gray)
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Reorder Pins", fontSize = 12.sp, color = if (!isCustomBoard) PinterestRed else Color.Gray, fontWeight = FontWeight.Bold)
                        }

                        // Manual Scroll Step button
                        OutlinedButton(
                            onClick = { scanner.stepScroll() },
                            enabled = !isCustomBoard,
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier.height(36.dp)
                        ) {
                            Icon(Icons.Default.SwapVert, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Step (+900px)", fontSize = 12.sp)
                        }

                        // Login Button
                        OutlinedButton(
                            onClick = { scanner.login() },
                            enabled = !isCustomBoard,
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier.height(36.dp)
                        ) {
                            Icon(Icons.AutoMirrored.Filled.Login, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Pinterest Login", fontSize = 12.sp)
                        }

                        // Toggle Image Blocking Button (Disabled by default)
                        OutlinedButton(
                            onClick = { scanner.setImageBlockingEnabled(!scannerState.isImageBlockingEnabled) },
                            enabled = !isCustomBoard,
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier.height(36.dp)
                        ) {
                            Icon(
                                imageVector = if (scannerState.isImageBlockingEnabled) Icons.Default.Shield else Icons.Default.Image,
                                contentDescription = null,
                                modifier = Modifier.size(16.dp),
                                tint = if (scannerState.isImageBlockingEnabled) Color(0xFF1976D2) else Color(0xFF2E7D32)
                            )
                            Spacer(modifier = Modifier.width(4.dp))
                            Text(
                                text = if (scannerState.isImageBlockingEnabled) "Images: Blocked" else "Images: Allowed",
                                fontSize = 12.sp
                            )
                        }

                        // Adjust Height Button
                        OutlinedButton(
                            onClick = {
                                browserHeightDp = when (browserHeightDp) {
                                    500.dp -> 720.dp
                                    720.dp -> 900.dp
                                    else -> 500.dp
                                }
                            },
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier.height(36.dp)
                        ) {
                            Icon(Icons.Default.Height, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text(
                                text = "Height: ${browserHeightDp.value.toInt()}dp",
                                fontSize = 12.sp
                            )
                        }

                        // Toggle Status Visibility Button
                        OutlinedButton(
                            onClick = { isStatusVisible = !isStatusVisible },
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier
                                .height(36.dp)
                                .testTag("toggle_status_button")
                        ) {
                            Icon(
                                imageVector = if (isStatusVisible) Icons.Default.VisibilityOff else Icons.Default.Visibility,
                                contentDescription = null,
                                modifier = Modifier.size(16.dp)
                            )
                            Spacer(modifier = Modifier.width(4.dp))
                            Text(
                                text = if (isStatusVisible) "Hide Status" else "Show Status",
                                fontSize = 12.sp
                            )
                        }

                        // Toggle WebView Visibility
                        OutlinedButton(
                            onClick = { isWebViewVisible = !isWebViewVisible },
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier.height(36.dp)
                        ) {
                            Text(
                                if (isWebViewVisible) "Hide Browser" else "Show Browser",
                                fontSize = 12.sp
                            )
                        }
                    }

                    // Live Isolated WebView Viewport (for Testing Purposes)
                    if (isWebViewVisible) {
                        Spacer(modifier = Modifier.height(8.dp))
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(browserHeightDp)
                                .clip(RoundedCornerShape(12.dp))
                                .border(
                                    width = 1.dp,
                                    color = MaterialTheme.colorScheme.outline.copy(alpha = 0.3f),
                                    shape = RoundedCornerShape(12.dp)
                                )
                                .background(Color.White)
                        ) {
                            AndroidView(
                                factory = { ctx ->
                                    FrameLayout(ctx).apply {
                                        layoutParams = ViewGroup.LayoutParams(
                                            ViewGroup.LayoutParams.MATCH_PARENT,
                                            ViewGroup.LayoutParams.MATCH_PARENT
                                        )
                                        val wv = scanner.getWebView()
                                        if (wv != null) {
                                            (wv.parent as? ViewGroup)?.removeView(wv)
                                            addView(
                                                wv,
                                                ViewGroup.LayoutParams(
                                                    ViewGroup.LayoutParams.MATCH_PARENT,
                                                    ViewGroup.LayoutParams.MATCH_PARENT
                                                )
                                            )
                                        }
                                    }
                                },
                                update = { container ->
                                    val wv = scanner.getWebView()
                                    if (wv != null && wv.parent != container) {
                                        (wv.parent as? ViewGroup)?.removeView(wv)
                                        container.removeAllViews()
                                        container.addView(
                                            wv,
                                            ViewGroup.LayoutParams(
                                                ViewGroup.LayoutParams.MATCH_PARENT,
                                                ViewGroup.LayoutParams.MATCH_PARENT
                                            )
                                        )
                                    }
                                },
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(browserHeightDp)
                                    .testTag("testing_webview_container")
                            )

                            // Status Overlay at bottom of WebView with full information and hide button
                            if (isStatusVisible) {
                                Surface(
                                    modifier = Modifier
                                        .align(Alignment.BottomCenter)
                                        .fillMaxWidth(),
                                    color = Color(0xDD000000)
                                ) {
                                    Row(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .padding(start = 12.dp, end = 6.dp, top = 6.dp, bottom = 6.dp),
                                        verticalAlignment = Alignment.CenterVertically,
                                        horizontalArrangement = Arrangement.SpaceBetween
                                    ) {
                                        Column(
                                            modifier = Modifier.weight(1f)
                                        ) {
                                            Text(
                                                text = scannerState.statusMessage,
                                                fontSize = 12.sp,
                                                color = Color.White,
                                                fontWeight = FontWeight.Medium
                                            )
                                            if (scannerState.currentBoardUrl.isNotBlank()) {
                                                Spacer(modifier = Modifier.height(2.dp))
                                                Text(
                                                    text = scannerState.currentBoardUrl,
                                                    fontSize = 10.sp,
                                                    color = Color(0xFFB0BEC5),
                                                    fontWeight = FontWeight.Normal
                                                )
                                            }
                                        }
                                        IconButton(
                                            onClick = { isStatusVisible = false },
                                            modifier = Modifier.size(28.dp)
                                        ) {
                                            Icon(
                                                imageVector = Icons.Default.Close,
                                                contentDescription = "Hide Status",
                                                tint = Color.White.copy(alpha = 0.8f),
                                                modifier = Modifier.size(16.dp)
                                            )
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // Explanatory note matching user request
                    Spacer(modifier = Modifier.height(6.dp))
                    Text(
                        text = "ℹ️ Browser worker is isolated. Image blocking saves network bandwidth during scan. Pins are displayed with full images below on the app board.",
                        fontSize = 11.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f),
                        lineHeight = 14.sp
                    )
                }
            }
        }
    }
}

@Composable
private fun DiagnosticChip(
    label: String,
    value: String,
    highlight: Boolean = false
) {
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = if (highlight) PinterestRed.copy(alpha = 0.12f) else MaterialTheme.colorScheme.surface,
        border = CardDefaults.outlinedCardBorder().copy(
            brush = androidx.compose.ui.graphics.SolidColor(
                if (highlight) PinterestRed.copy(alpha = 0.4f) else MaterialTheme.colorScheme.outline.copy(alpha = 0.15f)
            )
        )
    ) {
        Column(modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)) {
            Text(
                text = label,
                fontSize = 9.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text(
                text = value,
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                fontFamily = FontFamily.Monospace,
                color = if (highlight) PinterestRed else MaterialTheme.colorScheme.onSurface
            )
        }
    }
}
