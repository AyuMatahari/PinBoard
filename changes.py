#!/usr/bin/env python3
"""
PinBoard Gallery — rebuild PinCard + FullscreenGalleryViewer signature/call
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
          [ -f release.keystore ] || exit 1
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
# Canonical PinCard.kt (rewrite)
# ============================================================
NEW_PIN_CARD = r'''package com.example.ui.components

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
'''


def rewrite_pin_card():
    log("\n=== PATCH: rewrite PinCard.kt ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/PinCard.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    if "// v2-video" in t and "effectiveImageModel" in t and "pin_video_badge_" in t and "cardImageUrl" not in t:
        log("  ✓ already v2"); return
    f.write_text(NEW_PIN_CARD, encoding="utf-8")
    log("  ✓ rewritten (canonical)")


def find_balanced_parens(t, start_idx):
    """Given index of '(', return index of matching ')'."""
    depth = 0
    i = start_idx
    while i < len(t):
        c = t[i]
        if c == '"':
            i += 1
            while i < len(t):
                if t[i] == "\\": i += 2; continue
                if t[i] == '"': break
                i += 1
        elif c == "'":
            i += 1
            while i < len(t):
                if t[i] == "\\": i += 2; continue
                if t[i] == "'": break
                i += 1
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def rebuild_fullscreen_signature():
    log("\n=== PATCH: FullscreenGalleryViewer signature (rebuild) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/FullscreenGalleryViewer.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    marker = "fun FullscreenGalleryViewer("
    idx = t.find(marker)
    if idx < 0: log("  ✗ marker not found"); sys.exit(1)

    open_paren = t.find("(", idx)
    close_paren = find_balanced_parens(t, open_paren)
    if close_paren < 0: log("  ✗ unbalanced"); sys.exit(1)

    current_params = t[open_paren:close_paren + 1]
    if "onPlayVideo:" in current_params and "refreshCounters:" in current_params:
        log("  ✓ signature already complete"); return

    new_params = """(
    pins: List<PinItem>,
    initialIndex: Int,
    isFavorite: (PinItem) -> Boolean = { false },
    onToggleFavorite: (PinItem) -> Unit = {},
    onMoveToTop: (PinItem) -> Unit = {},
    onDeleteSingle: (PinItem) -> Unit = {},
    onClose: () -> Unit,
    onDownloadSingle: (PinItem) -> Unit,
    onPlayVideo: (PinItem) -> Unit = {},
    disableArrowNavigation: Boolean = false,
    refreshCounters: Map<String, Int> = emptyMap(),
    onRefreshImage: (PinItem) -> Unit = {},
    modifier: Modifier = Modifier
)"""

    t = t[:open_paren] + new_params + t[close_paren + 1:]
    f.write_text(t, encoding="utf-8")
    log("  ✓ signature rebuilt with onPlayVideo")


def rebuild_screen_call_site():
    log("\n=== PATCH: PinBoardGalleryScreen FullscreenGalleryViewer call (rebuild) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    marker = "FullscreenGalleryViewer("
    idx = t.find(marker)
    if idx < 0: log("  ✗ call not found"); sys.exit(1)

    open_paren = t.find("(", idx)
    close_paren = find_balanced_parens(t, open_paren)
    if close_paren < 0: log("  ✗ unbalanced"); sys.exit(1)

    # Get indentation of the call line
    line_start = t.rfind("\n", 0, idx) + 1
    base_indent = t[line_start:idx]
    arg_indent = base_indent + "    "

    new_call = (
        base_indent + "FullscreenGalleryViewer(\n" +
        arg_indent + "refreshCounters = imageRefreshCounters,\n" +
        arg_indent + "onRefreshImage = { p -> viewModel.refreshImage(p.id) },\n" +
        arg_indent + "onPlayVideo = { p -> viewModel.playVideo(context, p) },\n" +
        arg_indent + "pins = fullScreenPins,\n" +
        arg_indent + "initialIndex = initialIndex,\n" +
        arg_indent + "disableArrowNavigation = disableArrowNavigation,\n" +
        arg_indent + "isFavorite = { pin -> favoritePinKeys.contains(pin.id) || favoritePinKeys.contains(pin.imageUrl) },\n" +
        arg_indent + "onToggleFavorite = { pin -> viewModel.toggleFavorite(pin) },\n" +
        arg_indent + "onMoveToTop = { pin -> viewModel.movePinToTop(pin) },\n" +
        arg_indent + "onDeleteSingle = { pin -> viewModel.deleteSinglePin(pin) },\n" +
        arg_indent + "onClose = { viewModel.closeFullscreen() },\n" +
        arg_indent + "onDownloadSingle = { pin -> viewModel.downloadSingle(context, pin) }\n" +
        base_indent + ")"
    )

    t = t[:idx] + new_call + t[close_paren + 1:]
    f.write_text(t, encoding="utf-8")
    log("  ✓ call site rebuilt")


def verify_all():
    log("\n=== VERIFY ===")
    ps = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    fs = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/FullscreenGalleryViewer.kt"
    pc = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/PinCard.kt"

    for p in (ps, fs, pc):
        if not p.exists(): log(f"  ✗ missing {p}"); sys.exit(1)

    def strip(text):
        out, i = [], 0
        while i < len(text):
            c = text[i]
            if c == '"':
                i += 1
                while i < len(text):
                    if text[i] == "\\": i += 2; continue
                    if text[i] == '"': i += 1; break
                    i += 1
            elif c == "'":
                i += 1
                while i < len(text):
                    if text[i] == "\\": i += 2; continue
                    if text[i] == "'": i += 1; break
                    i += 1
            elif c == "/" and i + 1 < len(text) and text[i + 1] == "/":
                while i < len(text) and text[i] != "\n": i += 1
            elif c == "/" and i + 1 < len(text) and text[i + 1] == "*":
                i += 2
                while i + 1 < len(text):
                    if text[i] == "*" and text[i + 1] == "/":
                        i += 2; break
                    i += 1
            else:
                out.append(c); i += 1
        return "".join(out)

    checks = []

    pst = ps.read_text(encoding="utf-8")
    fst = fs.read_text(encoding="utf-8")
    pct = pc.read_text(encoding="utf-8")

    checks.append(("FullscreenGalleryViewer has onPlayVideo param",
                   "onPlayVideo: (PinItem) -> Unit = {}," in fst))
    checks.append(("FullscreenGalleryViewer has refreshCounters param",
                   "refreshCounters: Map<String, Int> = emptyMap()," in fst))
    checks.append(("FullscreenGalleryViewer has onRefreshImage param",
                   "onRefreshImage: (PinItem) -> Unit = {}," in fst))
    checks.append(("Screen call site has onPlayVideo",
                   "onPlayVideo = { p -> viewModel.playVideo(context, p) }," in pst))
    checks.append(("Screen call site has onRefreshImage",
                   "onRefreshImage = { p -> viewModel.refreshImage(p.id) }," in pst))
    checks.append(("Screen call site has refreshCounters",
                   "refreshCounters = imageRefreshCounters," in pst))

    checks.append(("PinCard v2-video marker", "// v2-video" in pct))
    checks.append(("PinCard has effectiveImageModel", "effectiveImageModel" in pct))
    checks.append(("PinCard has video badge", "pin_video_badge_" in pct))
    checks.append(("PinCard has PlayArrow import",
                   "import androidx.compose.material.icons.filled.PlayArrow" in pct))
    checks.append(("PinCard no orphan cardImageUrl", "cardImageUrl" not in pct))

    # Bracket balance on all three files
    for label, path, content in [
        ("Screen", ps, pst),
        ("Fullscreen", fs, fst),
        ("PinCard", pc, pct),
    ]:
        s = strip(content)
        po, pcnt = s.count("("), s.count(")")
        bo, bc = s.count("{"), s.count("}")
        checks.append((f"{label} paren balance ({po}/{pcnt})", po == pcnt))
        checks.append((f"{label} brace balance ({bo}/{bc})", bo == bc))

    all_ok = True
    for name, ok in checks:
        log(f"  {'✓' if ok else '✗'} {name}")
        if not ok: all_ok = False

    if not all_ok:
        log("\n✗ VERIFICATION FAILED"); sys.exit(1)


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


def patch_build_gradle_keystore():
    log("\n=== build.gradle.kts (keystore) ===")
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
        x = x[:ob + 1] + nc + x[cb:]
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
        run(["git", "commit", "-m", "Fix PinCard + FullscreenGalleryViewer signature/call (canonical rebuild)"])


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
    log("PinBoard — fix PinCard + FullscreenGalleryViewer signature")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    rewrite_pin_card()
    rebuild_fullscreen_signature()
    rebuild_screen_call_site()
    verify_all()

    ensure_release_keystore()
    patch_build_gradle_keystore()
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