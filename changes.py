#!/usr/bin/env python3
"""
PinBoard Gallery — fix transfer (DB source) + banner dedupe
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


def find_function_end(t, start_marker):
    idx = t.find(start_marker)
    if idx < 0: return -1
    open_brace = t.find("{", idx + len(start_marker) - 1)
    if open_brace < 0: return -1
    depth = 1
    i = open_brace + 1
    while i < len(t) and depth > 0:
        c = t[i]
        if c == '"':
            i += 1
            while i < len(t):
                if t[i] == "\\": i += 2; continue
                if t[i] == '"': break
                i += 1
        elif c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0: return i + 1
        i += 1
    return -1


# ============================================================
# THE FIX
# ============================================================
def patch_transfer_bugs():
    log("\n=== PATCH: transfer (DB source) + banner dedupe ===")
    vm_f = PROJECT_ROOT / "app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt"
    ps_f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not vm_f.exists(): log("  ✗ VM missing"); sys.exit(1)
    if not ps_f.exists(): log("  ✗ Screen missing"); sys.exit(1)

    # ---------- ViewModel ----------
    t = vm_f.read_text(encoding="utf-8")
    vm_changed = False

    # 1) executeAlbumTransfer — fetch from DB
    if "// DB-source pins" in t and "fun executeAlbumTransfer(targetAlbum: DateAlbum, targetBoardId: String)" in t:
        log("  ✓ executeAlbumTransfer already patched")
    else:
        marker = "    fun executeAlbumTransfer(targetAlbum: DateAlbum, targetBoardId: String) {"
        idx = t.find(marker)
        if idx < 0:
            log("  ⚠ executeAlbumTransfer marker not found")
        else:
            end_idx = find_function_end(t, marker)
            if end_idx < 0:
                log("  ⚠ could not find executeAlbumTransfer end")
            else:
                new_fn = """    fun executeAlbumTransfer(targetAlbum: DateAlbum, targetBoardId: String) {
        val transfer = _pendingAlbumTransfer.value ?: return
        val ctx = appContext ?: return
        viewModelScope.launch {
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            // DB-source pins — safe when user navigates away from source board
            val sourcePins = withContext(Dispatchers.IO) {
                dao.getPinsForBoard(transfer.sourceBoardId)
                    .filter { transfer.pinIds.contains(it.id) }
                    .map { it.toPinItem() }
            }
            if (sourcePins.isEmpty()) {
                _pendingAlbumTransfer.value = null
                _snackbarMessage.value = "No images to transfer"
                return@launch
            }
            val albumId = targetAlbum.id
            if (transfer.sourceBoardId == targetBoardId) {
                withContext(Dispatchers.IO) {
                    sourcePins.forEach { pin -> dao.movePinsToAlbum(listOf(pin.id), albumId) }
                }
            } else {
                val existingUrls = withContext(Dispatchers.IO) { dao.getImageUrlsForBoard(targetBoardId).toSet() }
                val toAdd = sourcePins.filter { !existingUrls.contains(it.imageUrl) }
                    .map { it.copy(albumId = albumId) }
                withContext(Dispatchers.IO) {
                    if (toAdd.isNotEmpty()) {
                        dao.upsertPinsSafely(toAdd.mapIndexed { i, p ->
                            PinEntity.fromPinItem(p, targetBoardId, i)
                        })
                    }
                    if (transfer.mode == AlbumTransferMode.MOVE) {
                        dao.deletePinsFromBoard(transfer.sourceBoardId, transfer.pinIds.toList())
                    }
                }
            }
            val curr = _currentBoard.value
            if (curr != null && (curr.id == targetBoardId || curr.id == transfer.sourceBoardId)) {
                val refreshed = withContext(Dispatchers.IO) {
                    dao.getPinsForBoard(curr.id).map { it.toPinItem() }
                }
                withContext(Dispatchers.Main) {
                    _rawPins.value = refreshed
                    _currentBoard.value = curr.copy(pins = refreshed, pinCount = refreshed.size)
                    updateDisplayedPins()
                }
            }
            _pendingAlbumTransfer.value = null
            withContext(Dispatchers.Main) {
                clearSelection()
                _snackbarMessage.value = "${if (transfer.mode == AlbumTransferMode.MOVE) "Moved" else "Copied"} ${sourcePins.size} image(s) to ${targetAlbum.title}"
            }
        }
    }
"""
                t = t[:idx] + new_fn + t[end_idx:]
                vm_changed = True
                log("  ✓ executeAlbumTransfer rewritten (DB-sourced)")

    # 2) moveToTopInternal — take sourceBoardId param
    old_marker = "    private suspend fun moveToTopInternal(pinIds: Set<String>, albumIds: Set<String>, dao: BoardDao) {"
    new_marker = "    private suspend fun moveToTopInternal(sourceBoardId: String, pinIds: Set<String>, albumIds: Set<String>, dao: BoardDao) {"
    if new_marker in t:
        log("  ✓ moveToTopInternal already patched")
    elif old_marker in t:
        end_idx = find_function_end(t, old_marker)
        if end_idx > 0:
            idx = t.find(old_marker)
            new_fn = """    private suspend fun moveToTopInternal(sourceBoardId: String, pinIds: Set<String>, albumIds: Set<String>, dao: BoardDao) {
        val allPins = withContext(Dispatchers.IO) {
            dao.getPinsForBoard(sourceBoardId).map { it.toPinItem() }
        }
        val allAlbums = withContext(Dispatchers.IO) { dao.getAlbumsForBoard(sourceBoardId) }
        val maxPinDate = allPins.maxOfOrNull { it.dateAddedMillis } ?: 0L
        val maxAlbumDate = allAlbums.maxOfOrNull { it.dateAddedMillis } ?: 0L
        var nextDate = maxOf(maxPinDate, maxAlbumDate) + 60_000L

        val affectedAlbumIds = mutableSetOf<String>()
        val updatedPins = allPins.map { p ->
            if (pinIds.contains(p.id)) {
                p.albumId?.let { affectedAlbumIds.add(it) }
                p.copy(albumId = null, dateAddedMillis = nextDate).also { nextDate += 1000L }
            } else p
        }

        val updatedAlbums = allAlbums.map { a ->
            if (albumIds.contains(a.id)) {
                a.copy(dateAddedMillis = nextDate).also { nextDate += 1000L }
            } else a
        }

        val nonEmptyAlbumIds = updatedPins.mapNotNull { it.albumId }.toSet()
        val dissolvedAlbumIds = affectedAlbumIds - nonEmptyAlbumIds
        val finalAlbums = updatedAlbums.filterNot { it.id in dissolvedAlbumIds }

        withContext(Dispatchers.IO) {
            dao.upsertPinsSafely(updatedPins.mapIndexed { i, p -> PinEntity.fromPinItem(p, sourceBoardId, i) })
            updatedAlbums.filter { it.id in albumIds }.forEach { dao.insertAlbum(it) }
            dissolvedAlbumIds.forEach { dao.deleteAlbum(it) }
        }

        val curr = _currentBoard.value
        if (curr != null && curr.id == sourceBoardId) {
            withContext(Dispatchers.Main) {
                _rawPins.value = updatedPins
                _customAlbums.value = finalAlbums
                _currentBoard.value = curr.copy(pins = updatedPins, pinCount = updatedPins.size)
                updateDisplayedPins(resetLimit = true)
            }
        }
    }
"""
            t = t[:idx] + new_fn + t[end_idx:]
            vm_changed = True
            log("  ✓ moveToTopInternal rewritten (sourceBoardId param)")
        else:
            log("  ⚠ could not find moveToTopInternal end")
    else:
        log("  ⚠ moveToTopInternal marker not found")

    # 3) executeAlbumTransferToCurrentBoard — fetch from DB, new moveToTopInternal call
    marker_cb = "    fun executeAlbumTransferToCurrentBoard() {"
    if "// DB-source pins — safe when navigating to another board" in t:
        log("  ✓ executeAlbumTransferToCurrentBoard already patched")
    elif marker_cb in t:
        end_idx = find_function_end(t, marker_cb)
        if end_idx > 0:
            idx = t.find(marker_cb)
            new_fn = """    fun executeAlbumTransferToCurrentBoard() {
        val transfer = _pendingAlbumTransfer.value ?: return
        val currentBoard = _currentBoard.value ?: return
        viewModelScope.launch {
            val ctx = appContext ?: return@launch
            val dao = AppDatabase.getDatabase(ctx).boardDao()
            // DB-source pins — safe when navigating to another board
            val sourcePins = withContext(Dispatchers.IO) {
                dao.getPinsForBoard(transfer.sourceBoardId)
                    .filter { transfer.pinIds.contains(it.id) }
                    .map { it.toPinItem() }
            }
            if (sourcePins.isEmpty()) {
                _pendingAlbumTransfer.value = null
                _snackbarMessage.value = "No images to transfer"
                return@launch
            }
            if (currentBoard.id == transfer.sourceBoardId) {
                if (transfer.mode == AlbumTransferMode.MOVE) {
                    moveToTopInternal(transfer.sourceBoardId, sourcePins.map { it.id }.toSet(), emptySet(), dao)
                    _snackbarMessage.value = "Moved ${sourcePins.size} to top of board"
                } else {
                    _snackbarMessage.value = "Already on this board"
                }
            } else {
                val existingUrls = withContext(Dispatchers.IO) { dao.getImageUrlsForBoard(currentBoard.id).toSet() }
                val baseDate = System.currentTimeMillis()
                val toAdd = sourcePins.filter { !existingUrls.contains(it.imageUrl) }
                    .mapIndexed { i, p -> p.copy(albumId = null, dateAddedMillis = baseDate + i * 1000L) }
                withContext(Dispatchers.IO) {
                    if (toAdd.isNotEmpty()) {
                        dao.upsertPinsSafely(toAdd.mapIndexed { i, p ->
                            PinEntity.fromPinItem(p, currentBoard.id, i)
                        })
                    }
                    if (transfer.mode == AlbumTransferMode.MOVE) {
                        dao.deletePinsFromBoard(transfer.sourceBoardId, transfer.pinIds.toList())
                    }
                }
                val refreshed = withContext(Dispatchers.IO) {
                    dao.getPinsForBoard(currentBoard.id).map { it.toPinItem() }
                }
                withContext(Dispatchers.Main) {
                    _rawPins.value = refreshed
                    _currentBoard.value = currentBoard.copy(pins = refreshed, pinCount = refreshed.size)
                    updateDisplayedPins()
                }
                _snackbarMessage.value = "${if (transfer.mode == AlbumTransferMode.MOVE) "Moved" else "Copied"} ${toAdd.size} to ${currentBoard.title}"
            }
            _pendingAlbumTransfer.value = null
            withContext(Dispatchers.Main) { clearSelection() }
        }
    }
"""
            t = t[:idx] + new_fn + t[end_idx:]
            vm_changed = True
            log("  ✓ executeAlbumTransferToCurrentBoard rewritten (DB-sourced)")
        else:
            log("  ⚠ could not find executeAlbumTransferToCurrentBoard end")
    else:
        log("  ⚠ executeAlbumTransferToCurrentBoard marker not found")

    if vm_changed:
        vm_f.write_text(t, encoding="utf-8")

    # ---------- Banner dedupe ----------
    ps_t = ps_f.read_text(encoding="utf-8")
    start_marker = "    // Pending album transfer banner"
    end_marker = "\n    // Album position dialog"
    start_idx = ps_t.find(start_marker)
    if start_idx < 0:
        log("  ⚠ banner start marker not found")
    else:
        end_idx = ps_t.find(end_marker, start_idx)
        if end_idx < 0:
            log("  ⚠ banner end marker not found")
        else:
            clean_banner = """    // Pending album transfer banner (single, canonical)
    androidx.compose.foundation.layout.Box(modifier = Modifier.fillMaxSize()) {
        pendingAlbumTransfer?.let { transfer ->
            androidx.compose.material3.Surface(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = 16.dp, start = 12.dp, end = 12.dp)
                    .fillMaxWidth()
                    .testTag("pending_album_transfer_banner"),
                shape = RoundedCornerShape(16.dp),
                color = PinterestBlack,
                shadowElevation = 8.dp
            ) {
                androidx.compose.foundation.layout.Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    androidx.compose.material3.IconButton(
                        onClick = { viewModel.cancelAlbumTransferAndRestore() },
                        modifier = Modifier.testTag("album_transfer_back_btn")
                    ) {
                        androidx.compose.material3.Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Back to selection",
                            tint = Color.White
                        )
                    }
                    Text(
                        text = "Tap an album to ${if (transfer.mode == com.example.viewmodel.AlbumTransferMode.MOVE) "move" else "copy"} ${transfer.pinIds.size} image${if (transfer.pinIds.size > 1) "s" else ""}",
                        color = Color.White,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Medium,
                        modifier = Modifier.weight(1f)
                    )
                    androidx.compose.material3.TextButton(
                        onClick = { viewModel.executeAlbumTransferToCurrentBoard() },
                        modifier = Modifier.testTag("album_transfer_here_btn")
                    ) {
                        Text(
                            text = if (transfer.mode == com.example.viewmodel.AlbumTransferMode.MOVE) "Move here" else "Copy here",
                            color = Color(0xFF64B5F6),
                            fontWeight = FontWeight.Bold,
                            fontSize = 12.sp
                        )
                    }
                }
            }
        }
    }
"""
            ps_t = ps_t[:start_idx] + clean_banner + ps_t[end_idx:]
            ps_f.write_text(ps_t, encoding="utf-8")
            log("  ✓ banner replaced (canonical — single button)")

    # ---------- Self-verify ----------
    log("\n=== Self-verify ===")
    t_v = vm_f.read_text(encoding="utf-8")
    t_p = ps_f.read_text(encoding="utf-8")

    checks = [
        ("executeAlbumTransfer DB-sourced", "// DB-source pins" in t_v),
        ("executeAlbumTransferToCurrentBoard DB-sourced", "// DB-source pins — safe when navigating to another board" in t_v),
        ("moveToTopInternal sourceBoardId", "private suspend fun moveToTopInternal(sourceBoardId: String" in t_v),
        ("Banner single button", t_p.count('testTag("album_transfer_here_btn")') == 1),
        ("Banner back button", "album_transfer_back_btn" in t_p),
        ("moveToTopInternal call updated", "moveToTopInternal(transfer.sourceBoardId, sourcePins.map { it.id }.toSet(), emptySet(), dao)" in t_v),
    ]
    all_ok = True
    for label, ok in checks:
        log(f"  {'✓' if ok else '✗'} {label}")
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
        run(["git", "commit", "-m", "Fix transfer: DB-source pins + single banner button"])


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
    log("PinBoard — transfer DB-source fix + banner dedupe")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    patch_transfer_bugs()

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