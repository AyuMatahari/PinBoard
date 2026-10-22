package com.example.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BugReport
import androidx.compose.material.icons.filled.CleaningServices
import androidx.compose.material.icons.filled.DeleteSweep
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Storage
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import kotlinx.coroutines.launch
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillDarkGray
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary
import com.example.util.ImageCacheManager
import kotlin.math.roundToInt

@Composable
fun SettingsDialog(
    isOpen: Boolean,
    rememberPerBoardSettings: Boolean = true,
    onToggleRememberPerBoard: (Boolean) -> Unit = {},
    hidePinTitlesAndAuthors: Boolean = false,
    onToggleHidePinTitlesAndAuthors: (Boolean) -> Unit = {},
    portraitAlbumCards: Boolean = false,
    onTogglePortraitAlbumCards: (Boolean) -> Unit = {},
    disableArrowNavigation: Boolean = false,
    onToggleDisableArrowNavigation: (Boolean) -> Unit = {},
    isBrowserTestingVisible: Boolean = false,
    onToggleBrowserTesting: (Boolean) -> Unit = {},
    onOpenCrashLogs: () -> Unit = {},
    onRestoreBackup: ((java.io.File, (Result<com.example.util.BackupManager.RestoreSummary>) -> Unit) -> Unit)? = null,
    onDismiss: () -> Unit,
    onCacheSizeSaved: (Int) -> Unit
) {
    if (!isOpen) return

    val context = LocalContext.current
    val focusManager = LocalFocusManager.current
    val coroutineScope = rememberCoroutineScope()
    val currentSavedMb = remember { ImageCacheManager.getMaxDiskCacheMb(context) }
    var currentCacheUsageBytes by remember { mutableLongStateOf(0L) }

    var sliderValue by remember { mutableFloatStateOf(currentSavedMb.toFloat()) }
    var textValue by remember { mutableStateOf(currentSavedMb.toString()) }
    var isInputError by remember { mutableStateOf(false) }

    var isBackupEnabled by remember { mutableStateOf(com.example.util.BackupManager.isBackupEnabled(context)) }
    var backupIntervalMinutes by remember { mutableLongStateOf(com.example.util.BackupManager.getBackupIntervalMinutes(context)) }
    var showIntervalDropdown by remember { mutableStateOf(false) }
    var maxBackupFiles by remember { mutableIntStateOf(com.example.util.BackupManager.getMaxBackupFiles(context)) }
    var showMaxFilesDropdown by remember { mutableStateOf(false) }
    var backupStatusText by remember { mutableStateOf<String?>(null) }
    var showRestoreDialog by remember { mutableStateOf(false) }
    var availableBackups by remember { mutableStateOf<List<java.io.File>>(emptyList()) }
    var selectedBackupFile by remember { mutableStateOf<java.io.File?>(null) }
    var isRestoring by remember { mutableStateOf(false) }
    var restoreConfirmTarget by remember { mutableStateOf<java.io.File?>(null) }

    val safeDismiss = {
        focusManager.clearFocus()
        onDismiss()
    }

    DisposableEffect(Unit) {
        onDispose {
            focusManager.clearFocus()
        }
    }

    LaunchedEffect(isOpen) {
        currentCacheUsageBytes = ImageCacheManager.getDiskCacheUsageBytes(context)
    }

    val presets = listOf(256, 512, 1024, 2048)

    AlertDialog(
        onDismissRequest = safeDismiss,
        title = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Default.Settings,
                    contentDescription = null,
                    tint = PinterestRed,
                    modifier = Modifier.size(24.dp)
                )
                Spacer(modifier = Modifier.width(10.dp))
                Text(
                    text = "Settings",
                    fontWeight = FontWeight.Bold,
                    fontSize = 20.sp
                )
            }
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .padding(vertical = 4.dp)
            ) {
                // Clean Masonry Layout: Hide Image Name & Author
                Card(
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = PinterestPillGray),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 12.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(
                            modifier = Modifier
                                .weight(1f)
                                .padding(end = 8.dp)
                        ) {
                            Text(
                                text = "Hide Image Name & Author",
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold,
                                color = PinterestBlack
                            )
                            Spacer(modifier = Modifier.height(2.dp))
                            Text(
                                text = if (hidePinTitlesAndAuthors)
                                    "Clean layout active: Names and author labels are hidden for a seamless photo gallery."
                                else
                                    "Captions visible: Image names and authors appear below cards.",
                                fontSize = 11.sp,
                                color = PinterestTextSecondary,
                                lineHeight = 15.sp
                            )
                        }

                        Switch(
                            checked = hidePinTitlesAndAuthors,
                            onCheckedChange = { onToggleHidePinTitlesAndAuthors(it) },
                            colors = SwitchDefaults.colors(
                                checkedThumbColor = Color.White,
                                checkedTrackColor = PinterestRed,
                                uncheckedThumbColor = Color.White,
                                uncheckedTrackColor = Color.LightGray
                            ),
                            modifier = Modifier.testTag("hide_titles_authors_switch")
                        )
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Per-Board Layout Settings Toggle
                Card(
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = PinterestPillGray),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 12.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(
                            modifier = Modifier
                                .weight(1f)
                                .padding(end = 8.dp)
                        ) {
                            Text(
                                text = "Per-Board Layout Settings",
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold,
                                color = PinterestBlack
                            )
                            Spacer(modifier = Modifier.height(2.dp))
                            Text(
                                text = if (rememberPerBoardSettings)
                                    "Enabled: Columns (2-4) and sorting are saved individually for each board."
                                else
                                    "Disabled (Global): All boards share the exact same columns and sorting.",
                                fontSize = 11.sp,
                                color = PinterestTextSecondary,
                                lineHeight = 15.sp
                            )
                        }

                        Switch(
                            checked = rememberPerBoardSettings,
                            onCheckedChange = { onToggleRememberPerBoard(it) },
                            colors = SwitchDefaults.colors(
                                checkedThumbColor = Color.White,
                                checkedTrackColor = PinterestRed,
                                uncheckedThumbColor = Color.White,
                                uncheckedTrackColor = Color.LightGray
                            ),
                            modifier = Modifier.testTag("remember_per_board_switch")
                        )
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Regular Backup Settings Card (User requirement 1 & 3)
                Card(
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = PinterestPillGray),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 12.dp, vertical = 12.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Column(
                                modifier = Modifier
                                    .weight(1f)
                                    .padding(end = 8.dp)
                            ) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(
                                        imageVector = Icons.Default.Storage,
                                        contentDescription = null,
                                        tint = PinterestRed,
                                        modifier = Modifier.size(16.dp)
                                    )
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Text(
                                        text = "Regular JSON Backup",
                                        fontSize = 13.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = PinterestBlack
                                    )
                                }
                                Spacer(modifier = Modifier.height(2.dp))
                                Text(
                                    text = "Backs up all settings, board data, and image info (excluding image files) to /Download/PinterestViewerDownloads/Backup. Data is never lost even if images are deleted from the app.",
                                    fontSize = 11.sp,
                                    color = PinterestTextSecondary,
                                    lineHeight = 15.sp
                                )
                            }

                            Switch(
                                checked = isBackupEnabled,
                                onCheckedChange = {
                                    isBackupEnabled = it
                                    com.example.util.BackupManager.setBackupEnabled(context, it)
                                    if (it) {
                                        com.example.util.BackupManager.checkAndPerformScheduledBackup(context)
                                    }
                                },
                                colors = SwitchDefaults.colors(
                                    checkedThumbColor = Color.White,
                                    checkedTrackColor = PinterestRed,
                                    uncheckedThumbColor = Color.White,
                                    uncheckedTrackColor = Color.LightGray
                                ),
                                modifier = Modifier.testTag("enable_backup_switch")
                            )
                        }

                        if (isBackupEnabled) {
                            Spacer(modifier = Modifier.height(10.dp))
                            HorizontalDivider()
                            Spacer(modifier = Modifier.height(10.dp))

                            val currentIntervalLabel = com.example.util.BackupManager.INTERVAL_OPTIONS
                                .firstOrNull { it.second == backupIntervalMinutes }?.first ?: "$backupIntervalMinutes min"

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(
                                    text = "Backup Frequency:",
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.SemiBold,
                                    color = PinterestBlack
                                )

                                Surface(
                                    shape = RoundedCornerShape(16.dp),
                                    color = MaterialTheme.colorScheme.surface,
                                    modifier = Modifier
                                        .clickable {
                                            showIntervalDropdown = !showIntervalDropdown
                                            showMaxFilesDropdown = false
                                        }
                                        .testTag("backup_interval_selector")
                                ) {
                                    Text(
                                        text = "Every $currentIntervalLabel ▾",
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = PinterestRed,
                                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp)
                                    )
                                }
                            }

                            if (showIntervalDropdown) {
                                Spacer(modifier = Modifier.height(8.dp))
                                Column(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(12.dp))
                                        .padding(6.dp)
                                ) {
                                    com.example.util.BackupManager.INTERVAL_OPTIONS.forEach { (label, minutes) ->
                                        val isSelected = minutes == backupIntervalMinutes
                                        Row(
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .clickable {
                                                    backupIntervalMinutes = minutes
                                                    com.example.util.BackupManager.setBackupIntervalMinutes(context, minutes)
                                                    showIntervalDropdown = false
                                                }
                                                .padding(horizontal = 10.dp, vertical = 8.dp),
                                            verticalAlignment = Alignment.CenterVertically,
                                            horizontalArrangement = Arrangement.SpaceBetween
                                        ) {
                                            Text(
                                                text = "Every $label",
                                                fontSize = 12.sp,
                                                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
                                                color = if (isSelected) PinterestRed else PinterestBlack
                                            )
                                            if (isSelected) {
                                                Text("✓", color = PinterestRed, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                                            }
                                        }
                                    }
                                }
                            }

                            Spacer(modifier = Modifier.height(10.dp))

                            // Maximum Backup Files Setting (User requirement 3)
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(
                                    text = "Max Backup Files:",
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.SemiBold,
                                    color = PinterestBlack
                                )

                                Surface(
                                    shape = RoundedCornerShape(16.dp),
                                    color = MaterialTheme.colorScheme.surface,
                                    modifier = Modifier
                                        .clickable {
                                            showMaxFilesDropdown = !showMaxFilesDropdown
                                            showIntervalDropdown = false
                                        }
                                        .testTag("max_backup_files_selector")
                                ) {
                                    Text(
                                        text = if (maxBackupFiles == 0) "Unlimited ▾" else "$maxBackupFiles files ▾",
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = PinterestRed,
                                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp)
                                    )
                                }
                            }

                            if (showMaxFilesDropdown) {
                                Spacer(modifier = Modifier.height(8.dp))
                                Column(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(12.dp))
                                        .padding(6.dp)
                                ) {
                                    com.example.util.BackupManager.MAX_FILES_OPTIONS.forEach { count ->
                                        val isSelected = count == maxBackupFiles
                                        Row(
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .clickable {
                                                    maxBackupFiles = count
                                                    com.example.util.BackupManager.setMaxBackupFiles(context, count)
                                                    showMaxFilesDropdown = false
                                                }
                                                .padding(horizontal = 10.dp, vertical = 8.dp),
                                            verticalAlignment = Alignment.CenterVertically,
                                            horizontalArrangement = Arrangement.SpaceBetween
                                        ) {
                                            Text(
                                                text = if (count == 0) "Unlimited" else "$count file${if (count > 1) "s" else ""}",
                                                fontSize = 12.sp,
                                                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
                                                color = if (isSelected) PinterestRed else PinterestBlack
                                            )
                                            if (isSelected) {
                                                Text("✓", color = PinterestRed, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                                            }
                                        }
                                    }
                                }
                            }

                            Spacer(modifier = Modifier.height(10.dp))

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                val lastTime = com.example.util.BackupManager.getLastBackupTime(context)
                                val lastTimeText = if (lastTime > 0) {
                                    java.text.SimpleDateFormat("MMM dd, HH:mm", java.util.Locale.getDefault()).format(java.util.Date(lastTime))
                                } else "Never"

                                Text(
                                    text = "Last: $lastTimeText",
                                    fontSize = 11.sp,
                                    color = PinterestTextSecondary
                                )

                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Button(
                                        onClick = {
                                            coroutineScope.launch {
                                                backupStatusText = "Backing up..."
                                                val res = com.example.util.BackupManager.performBackup(context)
                                                backupStatusText = if (res.isSuccess) {
                                                    "Saved to /Download/PinterestViewerDownloads/Backup!"
                                                } else {
                                                    "Backup failed: ${res.exceptionOrNull()?.message}"
                                                }
                                            }
                                        },
                                        colors = ButtonDefaults.buttonColors(containerColor = PinterestBlack),
                                        shape = RoundedCornerShape(16.dp),
                                        contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                                        modifier = Modifier.testTag("backup_now_button")
                                    ) {
                                        Text("Backup Now", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Color.White)
                                    }

                                    androidx.compose.material3.OutlinedButton(
                                        onClick = {
                                            availableBackups = com.example.util.BackupManager.getAvailableBackups(context)
                                            selectedBackupFile = availableBackups.firstOrNull()
                                            showRestoreDialog = true
                                        },
                                        shape = RoundedCornerShape(16.dp),
                                        contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                                        modifier = Modifier.testTag("restore_backup_button")
                                    ) {
                                        Text("Restore", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = PinterestBlack)
                                    }
                                }
                            }

                            backupStatusText?.let { status ->
                                Spacer(modifier = Modifier.height(6.dp))
                                Text(
                                    text = status,
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Medium,
                                    color = if (status.startsWith("Saved") || status.startsWith("Restored")) Color(0xFF2E7D32) else PinterestRed
                                )
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Current Cache Usage Card
                Card(
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = PinterestPillGray),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 12.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                imageVector = Icons.Default.Storage,
                                contentDescription = null,
                                tint = PinterestRed,
                                modifier = Modifier.size(20.dp)
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Column {
                                Text(
                                    text = "Current Disk Cache",
                                    fontSize = 12.sp,
                                    color = PinterestTextSecondary,
                                    fontWeight = FontWeight.Medium
                                )
                                Text(
                                    text = ImageCacheManager.formatBytes(currentCacheUsageBytes),
                                    fontSize = 14.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = PinterestBlack
                                )
                            }
                        }

                        Button(
                            onClick = {
                                ImageCacheManager.clearCache(context)
                                currentCacheUsageBytes = 0L
                            },
                            colors = ButtonDefaults.buttonColors(
                                containerColor = MaterialTheme.colorScheme.surface,
                                contentColor = PinterestRed
                            ),
                            shape = RoundedCornerShape(16.dp),
                            elevation = ButtonDefaults.buttonElevation(defaultElevation = 1.dp),
                            modifier = Modifier.testTag("clear_cache_button")
                        ) {
                            Icon(
                                imageVector = Icons.Default.DeleteSweep,
                                contentDescription = null,
                                modifier = Modifier.size(16.dp)
                            )
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Clear", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }



                Spacer(modifier = Modifier.height(16.dp))
                HorizontalDivider()
                Spacer(modifier = Modifier.height(14.dp))

                Text(
                    text = "MAX IMAGE CACHE SIZE",
                    style = MaterialTheme.typography.labelSmall.copy(
                        fontWeight = FontWeight.Bold,
                        fontSize = 11.sp,
                        letterSpacing = 0.5.sp,
                        color = PinterestTextSecondary
                    )
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Decide the maximum disk space (MB) used to store image cache for fast loading:",
                    style = MaterialTheme.typography.bodySmall.copy(
                        fontSize = 12.sp,
                        color = PinterestTextSecondary
                    )
                )

                Spacer(modifier = Modifier.height(12.dp))

                // Text Field Input for exact MB
                OutlinedTextField(
                    value = textValue,
                    onValueChange = { input ->
                        val filtered = input.filter { it.isDigit() }
                        textValue = filtered
                        val parsed = filtered.toIntOrNull()
                        if (parsed != null && parsed in ImageCacheManager.MIN_CACHE_MB..ImageCacheManager.MAX_CACHE_MB) {
                            isInputError = false
                            sliderValue = parsed.toFloat()
                        } else {
                            isInputError = filtered.isNotEmpty()
                        }
                    },
                    label = { Text("Cache Size (MB)") },
                    suffix = { Text("MB", fontWeight = FontWeight.Bold) },
                    singleLine = true,
                    isError = isInputError,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = PinterestRed,
                        cursorColor = PinterestRed,
                        focusedLabelColor = PinterestRed
                    ),
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("cache_size_text_input")
                )

                if (isInputError) {
                    Text(
                        text = "Enter a value between ${ImageCacheManager.MIN_CACHE_MB} and ${ImageCacheManager.MAX_CACHE_MB} MB",
                        color = MaterialTheme.colorScheme.error,
                        fontSize = 11.sp,
                        modifier = Modifier.padding(start = 4.dp, top = 2.dp)
                    )
                }

                Spacer(modifier = Modifier.height(10.dp))

                // Slider Input
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "${ImageCacheManager.MIN_CACHE_MB} MB",
                        fontSize = 11.sp,
                        color = PinterestTextSecondary
                    )
                    Text(
                        text = "${sliderValue.toInt()} MB",
                        fontSize = 13.sp,
                        fontWeight = FontWeight.ExtraBold,
                        color = PinterestRed
                    )
                    Text(
                        text = "${ImageCacheManager.MAX_CACHE_MB} MB",
                        fontSize = 11.sp,
                        color = PinterestTextSecondary
                    )
                }

                Slider(
                    value = sliderValue,
                    onValueChange = { value ->
                        sliderValue = value
                        textValue = value.toInt().toString()
                        isInputError = false
                    },
                    valueRange = ImageCacheManager.MIN_CACHE_MB.toFloat()..ImageCacheManager.MAX_CACHE_MB.toFloat(),
                    colors = SliderDefaults.colors(
                        thumbColor = PinterestRed,
                        activeTrackColor = PinterestRed,
                        inactiveTrackColor = PinterestPillGray
                    ),
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("cache_size_slider")
                )

                Spacer(modifier = Modifier.height(8.dp))

                // Quick Preset Chips
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    presets.forEach { presetMb ->
                        val isSelected = sliderValue.toInt() == presetMb
                        Surface(
                            shape = RoundedCornerShape(16.dp),
                            color = if (isSelected) PinterestBlack else PinterestPillGray,
                            modifier = Modifier
                                .weight(1f)
                                .clickable {
                                    sliderValue = presetMb.toFloat()
                                    textValue = presetMb.toString()
                                    isInputError = false
                                }
                        ) {
                            Box(
                                contentAlignment = Alignment.Center,
                                modifier = Modifier.padding(vertical = 6.dp)
                            ) {
                                Text(
                                    text = if (presetMb >= 1024) "${presetMb / 1024} GB" else "$presetMb M",
                                    fontSize = 11.sp,
                                    fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium,
                                    color = if (isSelected) Color.White else PinterestBlack
                                )
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))
                HorizontalDivider(color = PinterestPillDarkGray.copy(alpha = 0.5f))
                Spacer(modifier = Modifier.height(12.dp))

                // Crash & Error Diagnostics
                Card(
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = PinterestPillGray),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { onOpenCrashLogs() }
                            .padding(horizontal = 12.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(
                                    imageVector = Icons.Default.BugReport,
                                    contentDescription = null,
                                    tint = PinterestRed,
                                    modifier = Modifier.size(16.dp)
                                )
                                Spacer(modifier = Modifier.width(6.dp))
                                Text(
                                    text = "Crash & Error Diagnostics",
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 13.sp,
                                    color = PinterestBlack
                                )
                            }
                            Spacer(modifier = Modifier.height(2.dp))
                            Text(
                                text = "View captured crash stacktraces, breadcrumbs, and error logs",
                                fontSize = 11.sp,
                                color = PinterestTextSecondary,
                                lineHeight = 14.sp
                            )
                        }
                        Button(
                            onClick = onOpenCrashLogs,
                            colors = ButtonDefaults.buttonColors(containerColor = Color.White),
                            shape = RoundedCornerShape(16.dp),
                            modifier = Modifier
                                .height(32.dp)
                                .testTag("open_crash_logs_button")
                        ) {
                            Text("View", fontSize = 12.sp, color = PinterestBlack, fontWeight = FontWeight.Bold)
                        }
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Browser Worker Debug Panel Toggle (Bottom of Settings)
                Card(
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = PinterestPillGray),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 12.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(
                            modifier = Modifier
                                .weight(1f)
                                .padding(end = 8.dp)
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(
                                    imageVector = Icons.Default.BugReport,
                                    contentDescription = null,
                                    tint = if (isBrowserTestingVisible) PinterestRed else PinterestBlack,
                                    modifier = Modifier.size(16.dp)
                                )
                                Spacer(modifier = Modifier.width(6.dp))
                                Text(
                                    text = "Browser Worker Debug Panel",
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 13.sp,
                                    color = PinterestBlack
                                )
                            }
                            Spacer(modifier = Modifier.height(2.dp))
                            Text(
                                text = "Show live browser worker viewport and test controls on the gallery screen",
                                fontSize = 11.sp,
                                color = PinterestTextSecondary,
                                lineHeight = 14.sp
                            )
                        }
                        Switch(
                            checked = isBrowserTestingVisible,
                            onCheckedChange = { onToggleBrowserTesting(it) },
                            colors = SwitchDefaults.colors(
                                checkedThumbColor = Color.White,
                                checkedTrackColor = PinterestRed,
                                uncheckedThumbColor = Color.White,
                                uncheckedTrackColor = Color.LightGray
                            ),
                            modifier = Modifier.testTag("browser_worker_debug_switch")
                        )
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Portrait Album Cards Toggle (Bottom of Settings)
                Card(
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = PinterestPillGray),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 12.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(
                            modifier = Modifier
                                .weight(1f)
                                .padding(end = 8.dp)
                        ) {
                            Text(
                                text = "Portrait Album Cards",
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold,
                                color = PinterestBlack
                            )
                            Spacer(modifier = Modifier.height(2.dp))
                            Text(
                                text = if (portraitAlbumCards)
                                    "Portrait cards: Album layers are displayed in taller portrait ratio."
                                else
                                    "Square cards: Album layers are displayed in standard square ratio.",
                                fontSize = 11.sp,
                                color = PinterestTextSecondary,
                                lineHeight = 15.sp
                            )
                        }

                        Switch(
                            checked = portraitAlbumCards,
                            onCheckedChange = { onTogglePortraitAlbumCards(it) },
                            colors = SwitchDefaults.colors(
                                checkedThumbColor = Color.White,
                                checkedTrackColor = PinterestRed,
                                uncheckedThumbColor = Color.White,
                                uncheckedTrackColor = Color.LightGray
                            ),
                            modifier = Modifier.testTag("portrait_album_cards_switch")
                        )
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Disable Next / Previous Arrow Navigation Toggle (Bottom of Settings)
                Card(
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = PinterestPillGray),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 12.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(
                            modifier = Modifier
                                .weight(1f)
                                .padding(end = 8.dp)
                        ) {
                            Text(
                                text = "Disable Arrow Navigation (Next/Prev)",
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold,
                                color = PinterestBlack
                            )
                            Spacer(modifier = Modifier.height(2.dp))
                            Text(
                                text = if (disableArrowNavigation)
                                    "Arrows disabled: Left and right next/prev arrow buttons are hidden in fullscreen view."
                                else
                                    "Arrows enabled: Navigation buttons appear on screen edges in fullscreen view.",
                                fontSize = 11.sp,
                                color = PinterestTextSecondary,
                                lineHeight = 15.sp
                            )
                        }

                        Switch(
                            checked = disableArrowNavigation,
                            onCheckedChange = { onToggleDisableArrowNavigation(it) },
                            colors = SwitchDefaults.colors(
                                checkedThumbColor = Color.White,
                                checkedTrackColor = PinterestRed,
                                uncheckedThumbColor = Color.White,
                                uncheckedTrackColor = Color.LightGray
                            ),
                            modifier = Modifier.testTag("disable_arrow_nav_switch")
                        )
                    }
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    focusManager.clearFocus()
                    val finalMb = textValue.toIntOrNull() ?: sliderValue.toInt()
                    val clamped = finalMb.coerceIn(ImageCacheManager.MIN_CACHE_MB, ImageCacheManager.MAX_CACHE_MB)
                    ImageCacheManager.setMaxDiskCacheMb(context, clamped)
                    onCacheSizeSaved(clamped)

                    onDismiss()
                },
                colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier.testTag("save_cache_settings_button")
            ) {
                Text("Save", color = Color.White, fontWeight = FontWeight.Bold)
            }
        },
        dismissButton = {
            TextButton(onClick = safeDismiss) {
                Text("Cancel", color = PinterestBlack)
            }
        },
        shape = RoundedCornerShape(20.dp)
    )

    if (showRestoreDialog) {
        if (availableBackups.isEmpty()) {
            AlertDialog(
                onDismissRequest = { showRestoreDialog = false },
                title = { Text("No Backups Found", fontWeight = FontWeight.Bold, fontSize = 16.sp) },
                text = {
                    Text(
                        "No .json backup files found in /Download/PinterestViewerDownloads/Backup. Tap 'Backup Now' to create one first.",
                        fontSize = 13.sp,
                        color = PinterestTextSecondary
                    )
                },
                confirmButton = {
                    Button(
                        onClick = { showRestoreDialog = false },
                        colors = ButtonDefaults.buttonColors(containerColor = PinterestBlack)
                    ) {
                        Text("OK")
                    }
                }
            )
        } else {
            AlertDialog(
                onDismissRequest = { if (!isRestoring) showRestoreDialog = false },
                title = {
                    Text("Restore from Backup", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                },
                text = {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .verticalScroll(rememberScrollState())
                    ) {
                        Text(
                            "Select a backup from /Download/PinterestViewerDownloads/Backup to restore:",
                            fontSize = 12.sp,
                            color = PinterestTextSecondary
                        )
                        Spacer(modifier = Modifier.height(10.dp))

                        // Android 11+ needs All Files Access so backups written by
                        // previous installs in Download/… become visible here.
                        if (!com.example.util.BackupManager.hasAllFilesAccess()) {
                            androidx.compose.material3.Surface(
                                shape = RoundedCornerShape(12.dp),
                                color = PinterestPillGray,
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Column(modifier = Modifier.padding(10.dp)) {
                                    Text(
                                        text = "All Files Access is needed to see every .json in the backup folder, including backups from previous app installs.",
                                        fontSize = 11.sp,
                                        color = PinterestBlack,
                                        fontWeight = FontWeight.SemiBold
                                    )
                                    Spacer(modifier = Modifier.height(6.dp))
                                    androidx.compose.material3.Button(
                                        onClick = {
                                            com.example.util.BackupManager.requestAllFilesAccess(context)
                                        },
                                        colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                                        shape = RoundedCornerShape(14.dp),
                                        contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 12.dp, vertical = 4.dp),
                                        modifier = Modifier.testTag("backup_all_files_access_btn")
                                    ) {
                                        Text("Grant All Files Access", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                                    }
                                }
                            }
                            Spacer(modifier = Modifier.height(10.dp))
                        }

                        // Refresh the list when the app resumes (i.e. after the
                        // user toggles All Files Access in system Settings).
                        val backupLifecycleOwner = androidx.lifecycle.compose.LocalLifecycleOwner.current
                        DisposableEffect(backupLifecycleOwner, showRestoreDialog) {
                            val obs = androidx.lifecycle.LifecycleEventObserver { _, event ->
                                if (event == androidx.lifecycle.Lifecycle.Event.ON_RESUME && showRestoreDialog) {
                                    val refreshed = com.example.util.BackupManager.getAvailableBackups(context)
                                    if (refreshed.isNotEmpty()) {
                                        availableBackups = refreshed
                                        if (selectedBackupFile == null ||
                                            refreshed.none { it.absolutePath == selectedBackupFile?.absolutePath }
                                        ) {
                                            selectedBackupFile = refreshed.firstOrNull()
                                        }
                                    }
                                }
                            }
                            backupLifecycleOwner.lifecycle.addObserver(obs)
                            onDispose { backupLifecycleOwner.lifecycle.removeObserver(obs) }
                        }

                        availableBackups.forEach { file ->
                            val isSelected = selectedBackupFile?.absolutePath == file.absolutePath
                            val fileDate = java.text.SimpleDateFormat("MMM dd, yyyy HH:mm", java.util.Locale.getDefault()).format(java.util.Date(file.lastModified()))
                            val fileSizeKb = (file.length() / 1024L).coerceAtLeast(1L)

                            Surface(
                                shape = RoundedCornerShape(10.dp),
                                color = if (isSelected) PinterestPillDarkGray else PinterestPillGray,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable { selectedBackupFile = file }
                                    .padding(vertical = 3.dp)
                            ) {
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(horizontal = 10.dp, vertical = 8.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    androidx.compose.material3.RadioButton(
                                        selected = isSelected,
                                        onClick = { selectedBackupFile = file },
                                        colors = androidx.compose.material3.RadioButtonDefaults.colors(
                                            selectedColor = PinterestRed,
                                            unselectedColor = Color.Gray
                                        )
                                    )
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(
                                            text = file.name,
                                            fontSize = 12.sp,
                                            fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium,
                                            color = PinterestBlack,
                                            maxLines = 1,
                                            overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis
                                        )
                                        Text(
                                            text = "$fileDate • $fileSizeKb KB",
                                            fontSize = 10.sp,
                                            color = PinterestTextSecondary
                                        )
                                    }
                                }
                            }
                        }
                    }
                },
                confirmButton = {
                    Button(
                        onClick = {
                            restoreConfirmTarget = selectedBackupFile
                        },
                        enabled = selectedBackupFile != null && !isRestoring,
                        colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                        modifier = Modifier.testTag("confirm_select_restore_button")
                    ) {
                        Text(if (isRestoring) "Restoring..." else "Restore", color = Color.White)
                    }
                },
                dismissButton = {
                    TextButton(
                        onClick = { showRestoreDialog = false },
                        enabled = !isRestoring
                    ) {
                        Text("Cancel", color = PinterestBlack)
                    }
                }
            )
        }
    }

    restoreConfirmTarget?.let { targetFile ->
        AlertDialog(
            onDismissRequest = { if (!isRestoring) restoreConfirmTarget = null },
            title = { Text("Confirm Restore", fontWeight = FontWeight.Bold, fontSize = 16.sp) },
            text = {
                Text(
                    "Are you sure you want to restore boards, pins, and settings from \"${targetFile.name}\"? Existing boards and data will be merged/restored.",
                    fontSize = 13.sp
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        isRestoring = true
                        if (onRestoreBackup != null) {
                            onRestoreBackup(targetFile) { result ->
                                isRestoring = false
                                restoreConfirmTarget = null
                                showRestoreDialog = false
                                if (result.isSuccess) {
                                    val summary = result.getOrNull()
                                    backupStatusText = "Restored: ${summary?.boardsCount ?: 0} boards, ${summary?.pinsCount ?: 0} images!"
                                } else {
                                    backupStatusText = "Restore failed: ${result.exceptionOrNull()?.message}"
                                }
                            }
                        } else {
                            coroutineScope.launch {
                                val result = com.example.util.BackupManager.restoreBackup(context, targetFile)
                                isRestoring = false
                                restoreConfirmTarget = null
                                showRestoreDialog = false
                                if (result.isSuccess) {
                                    val summary = result.getOrNull()
                                    backupStatusText = "Restored: ${summary?.boardsCount ?: 0} boards, ${summary?.pinsCount ?: 0} images!"
                                } else {
                                    backupStatusText = "Restore failed: ${result.exceptionOrNull()?.message}"
                                }
                            }
                        }
                    },
                    enabled = !isRestoring,
                    colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                    modifier = Modifier.testTag("confirm_restore_final_button")
                ) {
                    Text(if (isRestoring) "Restoring..." else "Confirm Restore", color = Color.White)
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { restoreConfirmTarget = null },
                    enabled = !isRestoring
                ) {
                    Text("Cancel", color = PinterestBlack)
                }
            }
        )
    }
}
