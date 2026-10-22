package com.example.ui.components

import androidx.compose.animation.AnimatedVisibility
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
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AddPhotoAlternate
import androidx.compose.material.icons.filled.BugReport
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.FilterList
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Sort
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.res.painterResource
import androidx.compose.foundation.Image
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import coil.compose.AsyncImage
import coil.request.ImageRequest
import com.example.R
import com.example.model.PinterestBoard
import com.example.model.SortOption
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillDarkGray
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary

@Composable
fun PinterestTopBar(
    currentColumns: Int,
    onColumnsChanged: (Int) -> Unit,
    currentSort: SortOption,
    onSortSelected: (SortOption) -> Unit,
    separateByDate: Boolean = false,
    onToggleSeparateByDate: () -> Unit = {},
    groupByAlbum: Boolean = false,
    onToggleGroupByAlbum: () -> Unit = {},
    searchQuery: String,
    onSearchQueryChanged: (String) -> Unit,
    isSelectionMode: Boolean,
    onToggleSelectionMode: () -> Unit,
    onOpenLinkDialog: () -> Unit,
    onOpenSettings: () -> Unit = {},
    onOpenAddImages: () -> Unit = {},
    isSyncing: Boolean = false,
    onSyncClicked: () -> Unit = {},
    isBrowserTestingVisible: Boolean = true,
    onToggleBrowserTesting: () -> Unit = {},
    isScanning: Boolean = false,
    currentBoard: PinterestBoard? = null,
    hasCrashLog: Boolean = false,
    onOpenCrashLogs: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    var sortMenuExpanded by remember { mutableStateOf(false) }
    var isSearchActive by remember { mutableStateOf(false) }
    val focusManager = LocalFocusManager.current
    val context = LocalContext.current

    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface)
            .statusBarsPadding()
            .padding(horizontal = 12.dp, vertical = 6.dp)
    ) {
        // Main Top Bar Row
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            // Profile photo of the board's owner (or Pinterest Logo when none)
            Box(
                modifier = Modifier
                    .size(36.dp)
                    .clip(CircleShape)
                    .clickable { onOpenLinkDialog() }
                    .testTag("pinterest_logo_badge"),
                contentAlignment = Alignment.Center
            ) {
                val avatarUrl = currentBoard?.ownerAvatarUrl
                if (!avatarUrl.isNullOrBlank()) {
                    AsyncImage(
                        model = ImageRequest.Builder(context)
                            .data(avatarUrl)
                            .crossfade(true)
                            .build(),
                        contentDescription = currentBoard.ownerDisplayName.ifBlank { "Board Owner" },
                        contentScale = ContentScale.Crop,
                        modifier = Modifier
                            .size(36.dp)
                            .clip(CircleShape)
                    )
                } else {
                    Image(
                        painter = painterResource(id = R.drawable.ic_pinterest_circle_logo),
                        contentDescription = "Pinterest Logo",
                        modifier = Modifier.size(36.dp)
                    )
                }
            }

            // Right Actions: Column Switcher, Sort, Select (Icon only), Settings
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                // Column Switcher Segmented Control (4, 3, 2 columns)
                ColumnSwitcher(
                    currentColumns = currentColumns,
                    onColumnsChanged = onColumnsChanged
                )

                // Sort Menu Icon Button
                Box {
                    Box(
                        modifier = Modifier
                            .size(28.dp)
                            .clip(CircleShape)
                            .clickable { sortMenuExpanded = true }
                            .testTag("sort_menu_button"),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            imageVector = Icons.Default.FilterList,
                            contentDescription = "Sort Pins",
                            tint = MaterialTheme.colorScheme.onSurface,
                            modifier = Modifier.size(16.dp)
                        )
                    }

                    DropdownMenu(
                        expanded = sortMenuExpanded,
                        onDismissRequest = { sortMenuExpanded = false }
                    ) {
                        val availableSortOptions = remember(currentBoard?.id) {
                            if (currentBoard?.id == "board_favorites") {
                                listOf(SortOption.FAVORITED_NEWEST, SortOption.FAVORITED_OLDEST) +
                                        SortOption.values().filter { it != SortOption.FAVORITED_NEWEST && it != SortOption.FAVORITED_OLDEST }
                            } else {
                                SortOption.values().filter { it != SortOption.FAVORITED_NEWEST && it != SortOption.FAVORITED_OLDEST }
                            }
                        }

                        availableSortOptions.forEach { option ->
                            DropdownMenuItem(
                                text = {
                                    Row(
                                        verticalAlignment = Alignment.CenterVertically,
                                        modifier = Modifier.fillMaxWidth()
                                    ) {
                                        Text(
                                            text = option.label,
                                            fontWeight = if (option == currentSort) FontWeight.Bold else FontWeight.Normal,
                                            color = if (option == currentSort) PinterestRed else MaterialTheme.colorScheme.onSurface,
                                            modifier = Modifier.weight(1f)
                                        )
                                        if (option == currentSort) {
                                            Icon(
                                                imageVector = Icons.Default.Check,
                                                contentDescription = "Selected",
                                                tint = PinterestRed,
                                                modifier = Modifier.size(16.dp)
                                            )
                                        }
                                    }
                                },
                                onClick = {
                                    onSortSelected(option)
                                    sortMenuExpanded = false
                                }
                            )
                        }

                        // Checklist at bottom to group into albums or separate images by date
                        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

                        DropdownMenuItem(
                            text = {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    Checkbox(
                                        checked = groupByAlbum,
                                        onCheckedChange = { onToggleGroupByAlbum() },
                                        colors = CheckboxDefaults.colors(
                                            checkedColor = PinterestRed,
                                            checkmarkColor = Color.White
                                        )
                                    )
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Column {
                                        Text(
                                            text = "Album",
                                            fontWeight = if (groupByAlbum) FontWeight.Bold else FontWeight.Normal,
                                            fontSize = 13.sp,
                                            color = if (groupByAlbum) PinterestRed else MaterialTheme.colorScheme.onSurface
                                        )
                                        Text(
                                            text = if (separateByDate) "Grouped by month" else "Grouped by day",
                                            fontSize = 11.sp,
                                            color = PinterestTextSecondary
                                        )
                                    }
                                }
                            },
                            onClick = {
                                onToggleGroupByAlbum()
                            }
                        )

                        DropdownMenuItem(
                            text = {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    Checkbox(
                                        checked = separateByDate,
                                        onCheckedChange = { onToggleSeparateByDate() },
                                        colors = CheckboxDefaults.colors(
                                            checkedColor = PinterestRed,
                                            checkmarkColor = Color.White
                                        )
                                    )
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Text(
                                        text = "Separate images by date",
                                        fontWeight = if (separateByDate) FontWeight.Bold else FontWeight.Normal,
                                        fontSize = 13.sp,
                                        color = if (separateByDate) PinterestRed else MaterialTheme.colorScheme.onSurface
                                    )
                                }
                            },
                            onClick = {
                                onToggleSeparateByDate()
                            }
                        )
                    }
                }

                // Add Images Manually Button
                Box(
                    modifier = Modifier
                        .size(28.dp)
                        .clip(CircleShape)
                        .background(PinterestPillGray)
                        .clickable { onOpenAddImages() }
                        .testTag("top_bar_add_images_button"),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = Icons.Default.AddPhotoAlternate,
                        contentDescription = "Add Images Manually",
                        tint = PinterestBlack,
                        modifier = Modifier.size(15.dp)
                    )
                }

                // Selection Mode Button (Compact Circle Proportional to Pill Icon)
                Box(
                    modifier = Modifier
                        .size(28.dp)
                        .clip(CircleShape)
                        .background(if (isSelectionMode) PinterestRed else PinterestPillGray)
                        .clickable { onToggleSelectionMode() }
                        .testTag("select_mode_button"),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = if (isSelectionMode) Icons.Default.Check else Icons.Outlined.CheckCircle,
                        contentDescription = if (isSelectionMode) "Done Selecting" else "Select",
                        tint = if (isSelectionMode) Color.White else PinterestBlack,
                        modifier = Modifier.size(15.dp)
                    )
                }



                // Crash / Error Log Alert Button (prominently visible if an error/crash was recorded)
                if (hasCrashLog) {
                    Box(
                        modifier = Modifier
                            .size(28.dp)
                            .clip(CircleShape)
                            .background(PinterestRed)
                            .clickable { onOpenCrashLogs() }
                            .testTag("crash_log_alert_button"),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            imageVector = Icons.Default.BugReport,
                            contentDescription = "View Error / Crash Log",
                            tint = Color.White,
                            modifier = Modifier.size(15.dp)
                        )
                    }
                }

                // Settings Button (Compact Circle Proportional to Pill Icon)
                Box(
                    modifier = Modifier
                        .size(28.dp)
                        .clip(CircleShape)
                        .background(PinterestPillGray)
                        .clickable { onOpenSettings() }
                        .testTag("settings_button"),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = Icons.Default.Settings,
                        contentDescription = "Settings",
                        tint = PinterestBlack,
                        modifier = Modifier.size(15.dp)
                    )
                }

                // Sync / Refresh Button (when currentBoard != null)
                if (currentBoard != null) {
                    Box(
                        modifier = Modifier
                            .size(28.dp)
                            .clip(CircleShape)
                            .background(PinterestPillGray)
                            .clickable(enabled = !isSyncing) { onSyncClicked() }
                            .testTag("sync_board_button"),
                        contentAlignment = Alignment.Center
                    ) {
                        if (isSyncing) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(14.dp),
                                color = PinterestRed,
                                strokeWidth = 2.dp
                            )
                        } else {
                            Icon(
                                imageVector = Icons.Default.Refresh,
                                contentDescription = "Sync Board Images",
                                tint = MaterialTheme.colorScheme.onSurface,
                                modifier = Modifier.size(15.dp)
                            )
                        }
                    }
                }
            }
        }

        // Inline Search / Filter Bar
        Spacer(modifier = Modifier.height(8.dp))
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(24.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant)
                .padding(horizontal = 12.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = Icons.Default.Search,
                contentDescription = "Search",
                tint = PinterestTextSecondary,
                modifier = Modifier.size(18.dp)
            )
            Spacer(modifier = Modifier.width(8.dp))
            BasicTextField(
                value = searchQuery,
                onValueChange = onSearchQueryChanged,
                singleLine = true,
                cursorBrush = SolidColor(PinterestRed),
                textStyle = MaterialTheme.typography.bodyMedium.copy(
                    color = MaterialTheme.colorScheme.onSurface,
                    fontSize = 13.sp
                ),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { focusManager.clearFocus() }),
                modifier = Modifier
                    .weight(1f)
                    .testTag("board_search_input"),
                decorationBox = { innerTextField ->
                    if (searchQuery.isEmpty()) {
                        Text(
                            text = "Filter pins by title, keyword, or creator...",
                            color = PinterestTextSecondary,
                            fontSize = 13.sp
                        )
                    }
                    innerTextField()
                }
            )
            if (searchQuery.isNotEmpty()) {
                IconButton(
                    onClick = {
                        onSearchQueryChanged("")
                        focusManager.clearFocus()
                    },
                    modifier = Modifier.size(24.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.Close,
                        contentDescription = "Clear",
                        tint = PinterestTextSecondary,
                        modifier = Modifier.size(16.dp)
                    )
                }
            }
        }
    }
}

/**
 * Segmented control for switching between 2, 3, and 4 columns
 */
@Composable
fun ColumnSwitcher(
    currentColumns: Int,
    onColumnsChanged: (Int) -> Unit
) {
    Surface(
        shape = RoundedCornerShape(14.dp),
        color = PinterestPillGray,
        modifier = Modifier.height(28.dp)
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.padding(2.dp)
        ) {
            listOf(2, 3, 4).forEach { count ->
                val isSelected = currentColumns == count
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(12.dp))
                        .background(if (isSelected) PinterestBlack else Color.Transparent)
                        .clickable { onColumnsChanged(count) }
                        .padding(horizontal = 7.dp, vertical = 2.dp)
                        .testTag("col_switch_$count"),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "${count}C",
                        fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium,
                        fontSize = 11.sp,
                        color = if (isSelected) Color.White else PinterestBlack
                    )
                }
            }
        }
    }
}
