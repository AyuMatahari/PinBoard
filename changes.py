#!/usr/bin/env python3
"""
PinBoard Gallery — Rewrite AlbumCard.kt cleanly
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
# NEW ALBUMCARD.KT (full replacement)
# ============================================================
NEW_ALBUM_CARD = r'''package com.example.ui.components

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
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
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
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
import com.example.ui.theme.PinterestRed
import com.example.ui.theme.PinterestTextSecondary
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.math.abs
import kotlin.math.roundToInt


@Composable
fun AlbumCard(
    album: DateAlbum,
    columnCount: Int,
    isFavorite: Boolean,
    isPortrait: Boolean = false,
    isSelected: Boolean = false,
    isSelectionMode: Boolean = false,
    onClick: () -> Unit,
    onLongClick: () -> Unit,
    onSelectToggle: () -> Unit = {},
    onSwipePreview: () -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val currentOnClick by rememberUpdatedState(onClick)
    val currentOnLongClick by rememberUpdatedState(onLongClick)
    val currentOnSelectToggle by rememberUpdatedState(onSelectToggle)
    val currentOnSwipePreview by rememberUpdatedState(onSwipePreview)

    val pins = album.pins
    val allAlbumPins = if (pins.isNotEmpty()) pins else album.subAlbums.flatMap { it.pins }
    val topPin = allAlbumPins.firstOrNull()
    val leftPin = if (allAlbumPins.size >= 2) allAlbumPins[allAlbumPins.size / 2] else null
    val rightPin = if (allAlbumPins.size >= 3) allAlbumPins.last() else null

    Box(
        modifier = modifier
            .fillMaxWidth()
            .testTag("album_card_${album.id}")
            .pointerInput(album.id, isSelectionMode) {
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

                            if (abs(diffY) > 20f && abs(diffY) > abs(diffX)) {
                                isVerticalScroll = true
                                return@withTimeoutOrNull true
                            }
                            if (abs(diffX) > 25f && abs(diffX) > abs(diffY) * 1.2f) {
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
                        // Select mode: open album. Normal: toggle favorite.
                        if (isSelectionMode) currentOnClick() else currentOnLongClick()
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

                        if (abs(totalDragX) > 30f) {
                            currentOnSwipePreview()
                        }
                    } else if (timeoutResult == false && !longPressed) {
                        // Select mode: toggle selection. Normal: open album.
                        if (isSelectionMode) currentOnSelectToggle() else currentOnClick()
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
                    if (leftPin != null) {
                        Box(
                            modifier = Modifier
                                .size(width = cardWidth, height = cardHeight)
                                .graphicsLayer {
                                    rotationZ = -10f
                                    translationX = -cardWidth.toPx() * 0.16f
                                    translationY = 5.dp.toPx()
                                }
                                .shadow(elevation = 5.dp, shape = RoundedCornerShape(14.dp), clip = false)
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

                    if (rightPin != null) {
                        Box(
                            modifier = Modifier
                                .size(width = cardWidth, height = cardHeight)
                                .graphicsLayer {
                                    rotationZ = 10f
                                    translationX = cardWidth.toPx() * 0.16f
                                    translationY = 5.dp.toPx()
                                }
                                .shadow(elevation = 5.dp, shape = RoundedCornerShape(14.dp), clip = false)
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

                    if (topPin != null) {
                        Box(
                            modifier = Modifier
                                .size(width = cardWidth, height = cardHeight)
                                .shadow(elevation = 8.dp, shape = RoundedCornerShape(14.dp), clip = false)
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

                            if (isSelectionMode) {
                                Box(
                                    modifier = Modifier
                                        .fillMaxSize()
                                        .background(
                                            if (isSelected) PinterestRed.copy(alpha = 0.28f)
                                            else Color.Black.copy(alpha = 0.10f)
                                        )
                                )
                                Box(
                                    modifier = Modifier
                                        .align(Alignment.TopEnd)
                                        .padding(8.dp)
                                        .size(28.dp)
                                        .clip(CircleShape)
                                        .background(if (isSelected) PinterestRed else Color.Black.copy(alpha = 0.45f))
                                        .border(2.dp, Color.White, CircleShape),
                                    contentAlignment = Alignment.Center
                                ) {
                                    if (isSelected) {
                                        Icon(
                                            imageVector = Icons.Default.Check,
                                            contentDescription = "Album Selected",
                                            tint = Color.White,
                                            modifier = Modifier.size(18.dp)
                                        )
                                    }
                                }
                            }

                            if (isFavorite && !isSelectionMode) {
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


@Composable
fun AlbumPreviewOverlay(
    album: DateAlbum,
    onDismiss: () -> Unit
) {
    val context = LocalContext.current

    BackHandler {
        onDismiss()
    }

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
'''


def verify_album_card_fix():
    """Confirm the rewrite contains all required elements."""
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/AlbumCard.kt"
    if not f.exists():
        log("  ✗ file missing"); return False
    t = f.read_text(encoding="utf-8")
    required = [
        "import androidx.compose.runtime.getValue",
        "import androidx.compose.runtime.rememberUpdatedState",
        "val currentOnClick by rememberUpdatedState(onClick)",
        "val currentOnLongClick by rememberUpdatedState(onLongClick)",
        "val currentOnSelectToggle by rememberUpdatedState(onSelectToggle)",
        "val currentOnSwipePreview by rememberUpdatedState(onSwipePreview)",
        "if (isSelectionMode) currentOnClick() else currentOnLongClick()",
        "if (isSelectionMode) currentOnSelectToggle() else currentOnClick()",
    ]
    for r in required:
        if r not in t:
            log(f"  ✗ MISSING: {r}")
            return False
    log("  ✓ all required elements present")
    return True


def patch_album_card_rewrite():
    log("\n=== PATCH: Rewrite AlbumCard.kt ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/AlbumCard.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    f.write_text(NEW_ALBUM_CARD, encoding="utf-8")
    log("  ✓ file rewritten")
    if not verify_album_card_fix():
        log("  ✗ VERIFICATION FAILED"); sys.exit(1)


def harden_headless():
    """Add more headless props to gradle.properties (KSP AWT NPE mitigation)."""
    log("\n=== gradle.properties hardening ===")
    gp = PROJECT_ROOT / "gradle.properties"
    if not gp.exists(): log("  skip (no file)"); return
    g = gp.read_text(encoding="utf-8")
    changed = False
    for line in [
        "systemProp.java.awt.headless=true",
        "kotlin.daemon.jvmargs=-Xmx2g -Djava.awt.headless=true -Dfile.encoding=UTF-8",
        "kapt.use.worker.api=true",
    ]:
        key = line.split("=")[0]
        if key not in g:
            g += "\n" + line + "\n"
            changed = True
    if changed:
        gp.write_text(g, encoding="utf-8")
        log("  ✓ props added")
    else:
        log("  ✓ already present")


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
        run(["git", "commit", "-m", "Rewrite AlbumCard.kt with correct delegate imports"])


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
    log("PinBoard — AlbumCard rewrite + headless hardening")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    patch_album_card_rewrite()
    harden_headless()

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