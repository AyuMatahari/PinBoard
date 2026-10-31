#!/usr/bin/env python3
"""
PinBoard Gallery — ShareTarget rewrite + multi-image order flip
"""
import os, re, sys, json, time, shutil, datetime, subprocess, urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
REPO_NAME = "PinBoard"; APP_NAME = "PinBoard"; ARTIFACT = "app-release"
PACKAGE_ID = "com.aistudio.pinboardgallery.kzwvpt"
KEYSTORE_FILE = "release.keystore"; KEYSTORE_ALIAS = "upload"
KEYSTORE_PASS = "PinBoardRelease2025"
KEYSTORE_DNAME = "CN=PinBoard Gallery, OU=PinBoard, O=PinBoard, L=Unknown, ST=Unknown, C=US"
KEYSTORE_VALIDITY = "10000"

WORKFLOW_YAML = """\
name: Build APK
on:
  workflow_dispatch:
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      JAVA_TOOL_OPTIONS: "-Djava.awt.headless=true"
      GRADLE_OPTS: "-Djava.awt.headless=true"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: '17' }
      - uses: android-actions/setup-android@v3
        with: { packages: '' }
      - run: yes | sdkmanager --licenses >/dev/null 2>&1 || true
      - run: sdkmanager --install "platforms;android-36" "build-tools;36.0.0" >/dev/null 2>&1 || true
      - name: Verify keystore
        run: |
          [ -f release.keystore ] || { echo "no keystore"; exit 1; }
          keytool -list -keystore release.keystore -storepass PinBoardRelease2025 2>/dev/null | grep -q upload
      - uses: gradle/actions/setup-gradle@v3
        with: { gradle-version: wrapper }
      - run: chmod +x ./gradlew
      - run: ./gradlew :app:assembleRelease --stacktrace --no-daemon
      - name: Verify APK
        run: |
          APK=$(find app/build/outputs/apk/release -name "*.apk" | head -1)
          [ -n "$APK" ] || exit 1
          BT=$(ls -d $ANDROID_HOME/build-tools/* | sort -V | tail -1)
          "$BT/apksigner" verify --verbose --print-certs "$APK"
      - uses: actions/upload-artifact@v4
        with: { name: app-release, path: app/build/outputs/apk/release/*.apk, if-no-files-found: error }
"""


def log(m): print(m, flush=True)


def run(cmd, cwd=None, check=True, capture=False):
    log(f"> {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    try:
        return subprocess.run(cmd, cwd=str(cwd or PROJECT_ROOT), check=check,
                              capture_output=capture, text=True, shell=isinstance(cmd, str))
    except subprocess.CalledProcessError as e:
        if e.stdout: log(f"  out: {e.stdout}")
        if e.stderr: log(f"  err: {e.stderr}")
        if check: raise


def tool_available(name):
    try:
        subprocess.run([name, "--version"], capture_output=True, check=True, timeout=5)
        return True
    except Exception: return False


# ============================================================
# NEW SHARE TARGET (full rewrite)
# ============================================================
NEW_SHARE_TARGET = r'''package com.example.ui

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.data.local.AppDatabase
import com.example.data.local.BoardDao
import com.example.data.local.BoardEntity
import com.example.data.local.PinEntity
import com.example.model.PinItem
import com.example.ui.theme.MyApplicationTheme
import com.example.ui.theme.PinterestBlack
import com.example.ui.theme.PinterestPillGray
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary
import com.example.util.ImageLinkResolver
import com.example.util.LinkExtractor
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext


class ShareTargetActivity : ComponentActivity() {

    companion object {
        /**
         * Process-scoped coroutine scope that survives activity destruction.
         * Auto-save and user-triggered saves continue here even if the
         * ShareTargetActivity finishes immediately (fixes unreliable auto-save).
         */
        private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    }

    @Volatile
    private var autoSaveJob: Job? = null

    @Volatile
    private var resolvedPinsForSave: List<PinItem>? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val sharedLinks = mutableListOf<String>()
        val sharedImageUris = mutableListOf<Uri>()

        when (intent?.action) {
            Intent.ACTION_SEND -> {
                if ("text/plain" == intent.type) {
                    val sharedText = intent.getStringExtra(Intent.EXTRA_TEXT) ?: ""
                    sharedLinks.addAll(LinkExtractor.extractLinks(sharedText))
                    if (sharedLinks.isEmpty() && sharedText.isNotBlank() &&
                        (sharedText.startsWith("http://") || sharedText.startsWith("https://"))) {
                        sharedLinks.add(sharedText.trim())
                    }
                } else if (intent.type?.startsWith("image/") == true) {
                    androidx.core.content.IntentCompat
                        .getParcelableExtra(intent, Intent.EXTRA_STREAM, Uri::class.java)
                        ?.let { sharedImageUris.add(it) }
                }
            }
            Intent.ACTION_SEND_MULTIPLE -> {
                if (intent.type?.startsWith("image/") == true) {
                    androidx.core.content.IntentCompat
                        .getParcelableArrayListExtra(intent, Intent.EXTRA_STREAM, Uri::class.java)
                        ?.let { sharedImageUris.addAll(it) }
                }
            }
        }

        // Auto-save to default board — runs on app scope so it survives finish().
        autoSaveJob = appScope.launch {
            try {
                val pins = resolveSharedItems(sharedLinks, sharedImageUris, false)
                resolvedPinsForSave = pins
                val appCtx = applicationContext
                val dao = AppDatabase.getDatabase(appCtx).boardDao()
                ensureDefaultBoardsExist(dao)
                val allBoards = dao.getAllBoards()
                val defaultBoard = allBoards.firstOrNull { it.isDefault }
                    ?: allBoards.firstOrNull { it.id == "board_dump" }
                    ?: allBoards.firstOrNull() ?: return@launch

                val existingIds = dao.getPinIdsForBoard(defaultBoard.id).toSet()
                val existingUrls = dao.getImageUrlsForBoard(defaultBoard.id).toSet()
                val toInsert = pins.filter {
                    !existingIds.contains(it.id) && !existingUrls.contains(it.imageUrl)
                }
                if (toInsert.isNotEmpty()) {
                    dao.insertPins(toInsert.mapIndexed { i, p -> PinEntity.fromPinItem(p, defaultBoard.id, i) })
                }
                withContext(Dispatchers.Main) {
                    Toast.makeText(appCtx, "Saved to ${defaultBoard.title}", Toast.LENGTH_SHORT).show()
                }
            } catch (t: Throwable) {
                t.printStackTrace()
            }
        }

        setContent {
            MyApplicationTheme {
                FloatingShareDialog(
                    sharedLinks = sharedLinks,
                    sharedImageUris = sharedImageUris,
                    onClose = { finish() },
                    onSaveToSelected = { boards, extractMultiple ->
                        performSaveToBoards(sharedLinks, sharedImageUris, boards, extractMultiple)
                        finish()
                    },
                    onHoldBoard = { boardId ->
                        performSaveToBoards(sharedLinks, sharedImageUris, listOf(boardId), false)
                        finish()
                    }
                )
            }
        }
    }

    private fun performSaveToBoards(
        links: List<String>,
        uris: List<Uri>,
        targetBoardIds: List<String>,
        extractMultiple: Boolean
    ) {
        appScope.launch {
            try {
                autoSaveJob?.join()
                val appCtx = applicationContext
                val dao = AppDatabase.getDatabase(appCtx).boardDao()
                val allBoards = dao.getAllBoards()
                val defaultBoard = allBoards.firstOrNull { it.isDefault }
                    ?: allBoards.firstOrNull { it.id == "board_dump" }
                    ?: allBoards.firstOrNull()

                val pins: List<PinItem> = if (extractMultiple) {
                    resolveSharedItems(links, uris, true)
                } else {
                    resolvedPinsForSave ?: resolveSharedItems(links, uris, false)
                }

                if (defaultBoard != null && targetBoardIds.isNotEmpty() &&
                    !targetBoardIds.contains(defaultBoard.id)) {
                    dao.deletePinsFromBoard(defaultBoard.id, pins.map { it.id })
                }

                for (boardId in targetBoardIds) {
                    val existingIds = dao.getPinIdsForBoard(boardId).toSet()
                    val existingUrls = dao.getImageUrlsForBoard(boardId).toSet()
                    val toInsert = pins.filter {
                        !existingIds.contains(it.id) && !existingUrls.contains(it.imageUrl)
                    }
                    if (toInsert.isNotEmpty()) {
                        dao.insertPins(toInsert.mapIndexed { i, p ->
                            PinEntity.fromPinItem(p.copy(albumId = null), boardId, i)
                        })
                    }
                }

                withContext(Dispatchers.Main) {
                    val names = allBoards.filter { targetBoardIds.contains(it.id) }
                        .joinToString(", ") { it.title }
                    Toast.makeText(appCtx, "Saved to $names", Toast.LENGTH_SHORT).show()
                }
            } catch (t: Throwable) {
                t.printStackTrace()
            }
        }
    }

    private suspend fun resolveSharedItems(
        links: List<String>,
        uris: List<Uri>,
        extractMultiple: Boolean
    ): List<PinItem> = withContext(Dispatchers.IO) {
        val pins = mutableListOf<PinItem>()
        for (link in links) {
            if (extractMultiple) {
                pins.addAll(ImageLinkResolver.resolveMultipleLinks(link))
            } else {
                pins.add(ImageLinkResolver.resolveLink(link))
            }
        }
        for (uri in uris) {
            val s = uri.toString()
            pins.add(PinItem(
                id = ImageLinkResolver.generateDeterministicPinId(s),
                title = "Shared Photo",
                imageUrl = s,
                thumbnailUrl = s,
                author = "Shared from device",
                sourceUrl = s,
                dateAddedMillis = System.currentTimeMillis()
            ))
        }
        pins
    }

    private suspend fun ensureDefaultBoardsExist(dao: BoardDao) {
        withContext(Dispatchers.IO) {
            if (dao.getBoardById("board_dump") == null) {
                dao.insertBoard(BoardEntity(
                    id = "board_dump", title = "Dump board", slug = "dump",
                    ownerUsername = "you", ownerDisplayName = "Dump board", ownerAvatarUrl = "",
                    pinCount = 0, followerCount = 0, boardUrl = "custom://dump",
                    description = "Default dump board", isCustom = true, customDomains = "",
                    isDefault = true, isSpecialNonDeletable = true
                ))
            }
            if (dao.getBoardById("board_my_save") == null) {
                dao.insertBoard(BoardEntity(
                    id = "board_my_save", title = "My Save", slug = "my-save",
                    ownerUsername = "you", ownerDisplayName = "My Save", ownerAvatarUrl = "",
                    pinCount = 0, followerCount = 0, boardUrl = "custom://my_save",
                    description = "Custom board for saved items", isCustom = true, customDomains = "",
                    isDefault = false, isSpecialNonDeletable = true
                ))
            }
            if (dao.getBoardById("board_favorites") == null) {
                dao.insertBoard(BoardEntity(
                    id = "board_favorites", title = "Favorites", slug = "favorites",
                    ownerUsername = "you", ownerDisplayName = "Favorites", ownerAvatarUrl = "",
                    pinCount = 0, followerCount = 0, boardUrl = "custom://favorites",
                    description = "Your favorite images", isCustom = true, customDomains = "",
                    isDefault = false, isSpecialNonDeletable = true
                ))
            }
        }
    }
}


@OptIn(ExperimentalLayoutApi::class, ExperimentalFoundationApi::class)
@Composable
private fun FloatingShareDialog(
    sharedLinks: List<String>,
    sharedImageUris: List<Uri>,
    onClose: () -> Unit,
    onSaveToSelected: (List<String>, Boolean) -> Unit,
    onHoldBoard: (String) -> Unit
) {
    val context = LocalContext.current
    var boards by remember { mutableStateOf<List<BoardEntity>>(emptyList()) }
    var isLoadingBoards by remember { mutableStateOf(true) }
    val selectedBoardIds = remember { mutableStateListOf<String>() }
    var extractMultipleImages by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        withContext(Dispatchers.IO) {
            val dao = AppDatabase.getDatabase(context).boardDao()
            val list = dao.getAllBoards()
            boards = list
            val def = list.firstOrNull { it.isDefault }
                ?: list.firstOrNull { it.id == "board_dump" }
                ?: list.firstOrNull { it.id == "board_my_save" }
                ?: list.firstOrNull()
            def?.let { selectedBoardIds.add(it.id) }
            isLoadingBoards = false
        }
    }

    val itemCount = sharedLinks.size + sharedImageUris.size

    Box(
        modifier = Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.55f)),
        contentAlignment = Alignment.Center
    ) {
        Card(
            modifier = Modifier.fillMaxWidth(0.92f).wrapContentHeight()
                .testTag("floating_share_dialog_card"),
            shape = RoundedCornerShape(24.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            elevation = CardDefaults.cardElevation(defaultElevation = 12.dp)
        ) {
            Column(Modifier.fillMaxWidth().padding(20.dp)) {
                // Header
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier.size(36.dp).clip(CircleShape)
                                .background(PinterestRed.copy(alpha = 0.12f)),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(Icons.Default.Share, null, tint = PinterestRed, modifier = Modifier.size(20.dp))
                        }
                        Spacer(Modifier.width(10.dp))
                        Column {
                            Text("Save to PinBoard", fontWeight = FontWeight.Bold, fontSize = 17.sp)
                            Text(
                                if (itemCount > 1) "$itemCount items detected" else "1 item detected",
                                fontSize = 12.sp, color = PinterestTextSecondary
                            )
                        }
                    }
                    IconButton(onClick = onClose, modifier = Modifier.size(32.dp)) {
                        Icon(Icons.Default.Close, "Close", tint = PinterestTextSecondary, modifier = Modifier.size(18.dp))
                    }
                }

                Spacer(Modifier.height(10.dp))

                // Extract-multiple checkbox
                if (sharedLinks.isNotEmpty()) {
                    Row(
                        modifier = Modifier.fillMaxWidth()
                            .combinedClickable(
                                onClick = { extractMultipleImages = !extractMultipleImages },
                                onLongClick = { extractMultipleImages = !extractMultipleImages }
                            )
                            .padding(vertical = 4.dp)
                            .testTag("share_extract_multiple_checkbox"),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Checkbox(
                            checked = extractMultipleImages,
                            onCheckedChange = { extractMultipleImages = it },
                            colors = CheckboxDefaults.colors(checkedColor = PinterestRed)
                        )
                        Spacer(Modifier.width(4.dp))
                        Column {
                            Text("Add multiple main images from webpage",
                                fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                            Text("Extract content images in order",
                                fontSize = 10.sp, color = PinterestTextSecondary)
                        }
                    }
                }

                Spacer(Modifier.height(10.dp))
                Text(
                    "Tap to select · Hold to save to that board and exit",
                    fontSize = 11.sp, color = PinterestTextSecondary
                )
                Spacer(Modifier.height(8.dp))

                if (isLoadingBoards) {
                    Box(Modifier.fillMaxWidth().height(100.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(color = PinterestRed, strokeWidth = 2.dp)
                    }
                } else {
                    FlowRow(
                        modifier = Modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        boards.forEach { board ->
                            val isSelected = selectedBoardIds.contains(board.id)
                            Surface(
                                shape = RoundedCornerShape(16.dp),
                                color = if (isSelected) PinterestBlack else PinterestPillGray,
                                modifier = Modifier
                                    .combinedClickable(
                                        onClick = {
                                            if (isSelected) selectedBoardIds.remove(board.id)
                                            else selectedBoardIds.add(board.id)
                                        },
                                        onLongClick = { onHoldBoard(board.id) }
                                    )
                                    .testTag("share_target_board_${board.id}")
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp)
                                ) {
                                    if (isSelected) {
                                        Icon(Icons.Default.Check, null, tint = Color.White, modifier = Modifier.size(14.dp))
                                        Spacer(Modifier.width(6.dp))
                                    }
                                    Text(
                                        board.title,
                                        fontSize = 13.sp,
                                        fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium,
                                        color = if (isSelected) Color.White else PinterestBlack,
                                        maxLines = 1, overflow = TextOverflow.Ellipsis
                                    )
                                    if (board.isDefault) {
                                        Spacer(Modifier.width(4.dp))
                                        Text("(Default)", fontSize = 10.sp,
                                            color = if (isSelected) Color.LightGray else PinterestTextSecondary)
                                    }
                                }
                            }
                        }
                    }
                }

                Spacer(Modifier.height(16.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        "Already in default board · change to move",
                        fontSize = 11.sp, color = PinterestTextSecondary
                    )
                    Button(
                        onClick = {
                            if (selectedBoardIds.isNotEmpty()) {
                                onSaveToSelected(selectedBoardIds.toList(), extractMultipleImages)
                            } else {
                                onClose()
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),
                        shape = RoundedCornerShape(20.dp),
                        modifier = Modifier.testTag("share_dialog_save_btn")
                    ) {
                        Text(
                            if (selectedBoardIds.size > 1) "Save to ${selectedBoardIds.size} Boards" else "Save",
                            color = Color.White, fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
        }
    }
}
'''


def patch_share_target():
    log("\n=== PATCH: ShareTargetActivity rewrite ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/ShareTargetActivity.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    f.write_text(NEW_SHARE_TARGET, encoding="utf-8")
    log("  ✓ rewritten (app-scoped auto-save, tap=toggle, hold=save+exit, no delay)")

    # Self-verify critical markers
    t = f.read_text(encoding="utf-8")
    required = [
        "private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)",
        "autoSaveJob = appScope.launch {",
        "onLongClick = { onHoldBoard(board.id) }",
        "onClick = {\n                                            if (isSelected) selectedBoardIds.remove(board.id)\n                                            else selectedBoardIds.add(board.id)\n                                        }",
        "performSaveToBoards(sharedLinks, sharedImageUris, boards, extractMultiple)\n                        finish()",
    ]
    for r in required:
        if r not in t:
            log(f"  ✗ MISSING marker: {r[:60]}...")
            sys.exit(1)
    log("  ✓ all markers verified")


# ============================================================
# Multi-image order flip
# ============================================================
def patch_flip_multi_order():
    log("\n=== PATCH: Flip multi-image order ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageLinkResolver.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "First image gets highest date" in t:
        log("  ✓ already patched"); return

    old = "                        dateAddedMillis = baseTime + (index * 10L), // Strictly increasing for stable sorting\n"
    new = "                        dateAddedMillis = baseTime + ((candidateList.size - index) * 10L), // First image gets highest date\n"
    if old not in t:
        log("  ✗ anchor missing"); sys.exit(1)
    t = t.replace(old, new, 1)
    f.write_text(t, encoding="utf-8")
    log("  ✓ multi-image date order flipped (first image now shows first)")


# ============================================================
# Standard pipeline
# ============================================================
def read_app_version():
    p = PROJECT_ROOT / "app/build.gradle.kts"
    if not p.exists(): return ("unknown", "0")
    x = p.read_text(encoding="utf-8")
    vn = re.search(r'versionName\s*=\s*"([^"]+)"', x)
    vc = re.search(r"versionCode\s*=\s*(\d+)", x)
    return (vn.group(1) if vn else "unknown", vc.group(1) if vc else "0")


def ensure_release_keystore():
    log("\n=== release.keystore ===")
    ks = PROJECT_ROOT / KEYSTORE_FILE
    if ks.exists() and ks.stat().st_size > 0:
        r = subprocess.run(["keytool", "-list", "-keystore", str(ks), "-storepass", KEYSTORE_PASS],
                           capture_output=True, text=True)
        if r.returncode == 0 and KEYSTORE_ALIAS in r.stdout:
            log("  ✓ OK"); return
        sys.exit(1)
    r = subprocess.run(["keytool", "-genkeypair", "-v", "-keystore", str(ks),
                        "-alias", KEYSTORE_ALIAS, "-keyalg", "RSA", "-keysize", "2048",
                        "-validity", KEYSTORE_VALIDITY, "-storepass", KEYSTORE_PASS,
                        "-keypass", KEYSTORE_PASS, "-dname", KEYSTORE_DNAME],
                       capture_output=True, text=True)
    if r.returncode != 0: sys.exit(1)


def find_braced(text, start):
    o = text.find("{", start)
    if o == -1: return None
    d, i = 1, o + 1
    while i < len(text) and d > 0:
        c = text[i]
        if c == '"':
            i += 1
            while i < len(text):
                if text[i] == "\\": i += 2; continue
                if text[i] == '"': break
                i += 1
        elif c == "{": d += 1
        elif c == "}":
            d -= 1
            if d == 0: return (o, i)
        i += 1
    return None


def patch_build_gradle():
    log("\n=== build.gradle.kts ===")
    p = PROJECT_ROOT / "app/build.gradle.kts"
    if not p.exists(): sys.exit(1)
    x = p.read_text(encoding="utf-8"); orig = x
    idx = x.find('create("release")')
    if idx == -1: sys.exit(1)
    span = find_braced(x, idx)
    if not span: sys.exit(1)
    ob, cb = span
    if f'storeFile = file("${{rootDir}}/{KEYSTORE_FILE}")' not in x[ob:cb]:
        nc = (f'\n      storeFile = file("${{rootDir}}/{KEYSTORE_FILE}")\n'
              f'      storePassword = "{KEYSTORE_PASS}"\n'
              f'      keyAlias = "{KEYSTORE_ALIAS}"\n'
              f'      keyPassword = "{KEYSTORE_PASS}"\n    ')
        x = x[:ob+1] + nc + x[cb:]
    if x != orig: p.write_text(x, encoding="utf-8")


def latest_gradle_version():
    try:
        req = urllib.request.Request("https://api.github.com/repos/gradle/gradle/releases/latest",
                                     headers={"User-Agent": "pinboard"})
        with urllib.request.urlopen(req, timeout=30) as r:
            tag = json.load(r).get("tag_name", "").lstrip("v")
            if tag: return tag
    except Exception: pass
    pr = PROJECT_ROOT / "gradle/wrapper/gradle-wrapper.properties"
    if pr.exists():
        m = re.search(r"gradle-([\d.]+)-bin\.zip", pr.read_text(encoding="utf-8"))
        if m: return m.group(1)
    return "9.3.1"


def ensure_gradle_wrapper():
    log("\n=== gradle wrapper ===")
    gw = PROJECT_ROOT / "gradlew"; gwb = PROJECT_ROOT / "gradlew.bat"
    jar = PROJECT_ROOT / "gradle/wrapper/gradle-wrapper.jar"
    if gw.exists() and gwb.exists() and jar.exists(): log("  ✓"); return
    ver = latest_gradle_version(); base = f"https://raw.githubusercontent.com/gradle/gradle/v{ver}"
    for url, dest in [(f"{base}/gradlew", gw), (f"{base}/gradlew.bat", gwb),
                      (f"{base}/gradle/wrapper/gradle-wrapper.jar", jar)]:
        if dest.exists() and dest.stat().st_size > 0: continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try: urllib.request.urlretrieve(url, dest)
        except Exception as e: log(e); sys.exit(1)
    try: os.chmod(gw, 0o755)
    except: pass


def write_workflow():
    log("\n=== workflow ===")
    wf = PROJECT_ROOT / ".github/workflows"; wf.mkdir(parents=True, exist_ok=True)
    (wf / "build.yml").write_text(WORKFLOW_YAML, encoding="utf-8")


def setup_git():
    log("\n=== git ===")
    if not (PROJECT_ROOT / ".git").exists():
        run(["git", "init"]); run(["git", "branch", "-M", "main"])
    if not subprocess.run(["git", "config", "--global", "user.name"], capture_output=True, text=True).stdout.strip():
        run(["git", "config", "--global", "user.name", "PinBoard Build"])
    if not subprocess.run(["git", "config", "--global", "user.email"], capture_output=True, text=True).stdout.strip():
        run(["git", "config", "--global", "user.email", "pinboard@build.local"])
    gi = PROJECT_ROOT / ".gitignore"
    req = ["build/", "*/build/", ".gradle/", "local.properties", "*.iml", ".idea/", ".cxx/",
           ".DS_Store", ".kotlin/", ".env", "_downloads/", "*.jks", "*.keystore",
           "!debug.keystore", "!release.keystore"]
    ex = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    merged = list(ex)
    for l in req:
        if l not in merged: merged.append(l)
    gi.write_text("\n".join(merged) + "\n", encoding="utf-8")
    run(["git", "add", "-A"])
    for n in (KEYSTORE_FILE, "debug.keystore"):
        if (PROJECT_ROOT / n).exists(): run(["git", "add", "-f", n], check=False)
    if subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip():
        run(["git", "commit", "-m", "Share: app-scoped auto-save, tap/hold gestures, no delay; flip multi-image order"])


def verify_keystore_tracked():
    r = subprocess.run(["git", "ls-files", "--error-unmatch", KEYSTORE_FILE],
                       capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    if r.returncode != 0:
        run(["git", "add", "-f", KEYSTORE_FILE])
        run(["git", "commit", "-m", "Add keystore"])


def gh_user():
    r = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip(): sys.exit(1)
    return r.stdout.strip()


def ensure_github_repo():
    log("\n=== GitHub repo ===")
    user = gh_user(); full = f"{user}/{REPO_NAME}"
    if subprocess.run(["gh", "repo", "view", full], capture_output=True).returncode != 0:
        subprocess.run(["gh", "repo", "create", REPO_NAME, "--public", "--source", ".",
                        "--remote", "origin", "--push"], capture_output=True, text=True)
    if subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True).returncode != 0:
        run(["git", "remote", "add", "origin", f"https://github.com/{full}.git"])
    r = subprocess.run(["git", "push", "-u", "origin", "main"], capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(["git", "push", "-u", "origin", "main", "--force"], capture_output=True, text=True)
    return full


def trigger_and_download(repo_full):
    log("\n=== CI ===")
    for _ in range(6):
        r = subprocess.run(["gh", "workflow", "run", "build.yml", "--ref", "main", "--repo", repo_full],
                           capture_output=True, text=True)
        if r.returncode == 0: break
        time.sleep(10)
    else: sys.exit(1)
    time.sleep(10)
    run_id = None
    for _ in range(20):
        r = subprocess.run(["gh", "run", "list", "--repo", repo_full, "--workflow", "build.yml",
                            "--limit", "1", "--json", "databaseId"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            try:
                runs = json.loads(r.stdout)
                if runs: run_id = runs[0]["databaseId"]; break
            except json.JSONDecodeError: pass
        time.sleep(5)
    if run_id is None: sys.exit(1)
    while True:
        r = subprocess.run(["gh", "run", "view", str(run_id), "--repo", repo_full,
                            "--json", "status,conclusion"], capture_output=True, text=True)
        if r.returncode != 0: time.sleep(15); continue
        try: info = json.loads(r.stdout)
        except: time.sleep(15); continue
        st, cc = info.get("status"), info.get("conclusion")
        log(f"  status={st} conclusion={cc}")
        if st == "completed":
            if cc != "success":
                subprocess.run(["gh", "run", "view", str(run_id), "--repo", repo_full, "--log-failed"])
                sys.exit(1)
            break
        time.sleep(20)
    dl = PROJECT_ROOT / "_downloads"
    if dl.exists(): shutil.rmtree(dl)
    dl.mkdir()
    subprocess.run(["gh", "run", "download", str(run_id), "--repo", repo_full,
                    "--name", ARTIFACT, "--dir", str(dl)], check=True)
    return dl


def move_apk(dl):
    log("\n=== Move APK ===")
    apks = list(dl.glob("*.apk"))
    if not apks: sys.exit(1)
    apk = apks[0]; vn, vc = read_app_version()
    log(f"  App: {vn} ({vc})")
    tf = PROJECT_ROOT / "Apk Directory.txt"
    target = Path(tf.read_text(encoding="utf-8").strip()) if tf.exists() else Path.home() / "Downloads"
    target.mkdir(parents=True, exist_ok=True)
    dest = target / f"{APP_NAME}-v{vn}-{vc}{apk.suffix}"
    if dest.exists():
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = target / f"{APP_NAME}-v{vn}-{vc}_{ts}{apk.suffix}"
    shutil.copy2(apk, dest)
    log(f"  ✓ {dest}")
    return dest


def find_apksigner():
    for sdk in [Path(os.environ.get("ANDROID_HOME", "")), Path(os.environ.get("ANDROID_SDK_ROOT", "")),
                Path(os.environ.get("LOCALAPPDATA", "")) / "Android/Sdk",
                Path.home() / "AppData/Local/Android/Sdk",
                Path.home() / "Library/Android/sdk", Path("/usr/local/lib/android/sdk")]:
        if not str(sdk).strip() or not sdk.exists(): continue
        bt = sdk / "build-tools"
        if not bt.exists(): continue
        for v in sorted([d for d in bt.iterdir() if d.is_dir()], key=lambda d: d.name, reverse=True):
            for n in ("apksigner.bat", "apksigner"):
                e = v / n
                if e.exists(): return str(e)
    return None


def verify_apk(apk):
    log("\n=== Verify APK ===")
    s = find_apksigner()
    if not s: log("  skip"); return
    r = subprocess.run([s, "verify", "--verbose", "--print-certs", str(apk)], capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    log("\n".join(f"  {l}" for l in out.splitlines()[:8]))
    if r.returncode != 0 or "Verifies" not in out: log("  ✗"); sys.exit(1)
    log("  ✓")


def find_adb():
    if tool_available("adb"): return "adb"
    for c in [Path(os.environ.get("LOCALAPPDATA", "")) / "Android/Sdk/platform-tools/adb.exe",
              Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe",
              Path.home() / "Library/Android/sdk/platform-tools/adb", Path("/usr/local/bin/adb")]:
        if c.exists(): return str(c)
    return None


def adb_device(adb):
    try:
        r = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=5)
        if r.returncode != 0: return False
        return any("\tdevice" in l or " device" in l for l in r.stdout.strip().splitlines()[1:])
    except: return False


def device_install(apk):
    log("\n=== Device install ===")
    adb = find_adb()
    if not adb or not adb_device(adb):
        log(f"  no device: adb uninstall {PACKAGE_ID}; adb install \"{apk}\"")
        return
    subprocess.run([adb, "uninstall", PACKAGE_ID], capture_output=True, timeout=60)
    r = subprocess.run([adb, "install", str(apk)], capture_output=True, text=True, timeout=300)
    out = (r.stdout + r.stderr).strip()
    log(f"  {out}")
    if "Success" in out: log("  ✓ Installed")


def main():
    log("=" * 70)
    log("PinBoard — ShareTarget rewrite + multi-image order flip")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    patch_share_target()
    patch_flip_multi_order()

    ensure_release_keystore()
    patch_build_gradle()
    ensure_gradle_wrapper()
    write_workflow()
    setup_git()
    verify_keystore_tracked()
    repo = ensure_github_repo()
    dl = trigger_and_download(repo)
    apk = move_apk(dl)
    verify_apk(apk)
    device_install(apk)
    log("\n" + "=" * 70)
    log(f"DONE -> {apk}")
    log("=" * 70)


if __name__ == "__main__":
    main()