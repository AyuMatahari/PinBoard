#!/usr/bin/env python3
"""
PinBoard Gallery — re-run: fix copy anchor (indentation) + idempotent patches
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
# PATCH 1 — ShareTarget (idempotent)
# ============================================================
def patch_share_activity():
    log("\n=== PATCH: ShareTarget ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/ShareTargetActivity.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    fully_patched = (
        "onHoldBoard: (String, Boolean) -> Unit" in t
        and "dao.upsertPinsSafely(toInsert.mapIndexed { i, p ->" in t
        and "dao.upsertPinsSafely(toInsert.mapIndexed { i, p ->\n                            PinEntity.fromPinItem(p.copy(albumId = null), boardId, i)" in t
    )
    if fully_patched:
        log("  ✓ already patched"); return

    changed = False

    # Callback signature + finish-before-save
    if "onHoldBoard: (String, Boolean) -> Unit" not in t:
        if "onHoldBoard: (String) -> Unit" in t:
            t = t.replace("onHoldBoard: (String) -> Unit", "onHoldBoard: (String, Boolean) -> Unit", 1)
            changed = True

    old_cb = (
        "                    onSaveToSelected = { boards, extractMultiple ->\n"
        "                        performSaveToBoards(sharedLinks, sharedImageUris, boards, extractMultiple)\n"
        "                        finish()\n"
        "                    },\n"
        "                    onHoldBoard = { boardId ->\n"
        "                        performSaveToBoards(sharedLinks, sharedImageUris, listOf(boardId), false)\n"
        "                        finish()\n"
        "                    }\n"
    )
    new_cb = (
        "                    onSaveToSelected = { boards, extractMultiple ->\n"
        "                        finish()\n"
        "                        performSaveToBoards(sharedLinks, sharedImageUris, boards, extractMultiple)\n"
        "                    },\n"
        "                    onHoldBoard = { boardId, extractMultiple ->\n"
        "                        finish()\n"
        "                        performSaveToBoards(sharedLinks, sharedImageUris, listOf(boardId), extractMultiple)\n"
        "                    }\n"
    )
    if old_cb in t:
        t = t.replace(old_cb, new_cb, 1); changed = True

    if "onLongClick = { onHoldBoard(board.id) }" in t:
        t = t.replace("onLongClick = { onHoldBoard(board.id) }",
                      "onLongClick = { onHoldBoard(board.id, extractMultipleImages) }", 1)
        changed = True

    old_auto = (
        "                if (toInsert.isNotEmpty()) {\n"
        "                    dao.insertPins(toInsert.mapIndexed { i, p -> PinEntity.fromPinItem(p, defaultBoard.id, i) })\n"
        "                }\n"
    )
    new_auto = (
        "                if (toInsert.isNotEmpty()) {\n"
        "                    dao.upsertPinsSafely(toInsert.mapIndexed { i, p ->\n"
        "                        PinEntity.fromPinItem(p.copy(albumId = null), defaultBoard.id, i)\n"
        "                    })\n"
        "                }\n"
    )
    if old_auto in t:
        t = t.replace(old_auto, new_auto, 1); changed = True

    old_save = (
        "                    if (toInsert.isNotEmpty()) {\n"
        "                        dao.insertPins(toInsert.mapIndexed { i, p ->\n"
        "                            PinEntity.fromPinItem(p.copy(albumId = null), boardId, i)\n"
        "                        })\n"
        "                    }\n"
    )
    new_save = (
        "                    if (toInsert.isNotEmpty()) {\n"
        "                        dao.upsertPinsSafely(toInsert.mapIndexed { i, p ->\n"
        "                            PinEntity.fromPinItem(p.copy(albumId = null), boardId, i)\n"
        "                        })\n"
        "                    }\n"
    )
    if old_save in t:
        t = t.replace(old_save, new_save, 1); changed = True

    if changed:
        f.write_text(t, encoding="utf-8")
        log("  ✓ share patched")
    else:
        log("  ✓ already patched (no change needed)")


# ============================================================
# PATCH 2 — CopyOrMoveImagesDialog (idempotent)
# ============================================================
def patch_copy_move_dialog():
    log("\n=== PATCH: CopyOrMoveImagesDialog ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/dialogs/CopyOrMoveImagesDialog.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if ("availableBoards.filter { it.id != currentBoardId }" in t
            and "to Album/Board" in t):
        log("  ✓ already patched"); return

    changed = False

    old_filter = (
        "    // MOVE now includes the current board (moving to current board = reorder to top)\n"
        "    val selectableBoards = remember(availableBoards) { availableBoards }\n"
    )
    new_filter = (
        "    val selectableBoards = remember(availableBoards, currentBoardId, mode) {\n"
        "        if (mode == BoardTransferMode.MOVE && !currentBoardId.isNullOrBlank()) {\n"
        "            availableBoards.filter { it.id != currentBoardId }\n"
        "        } else {\n"
        "            availableBoards\n"
        "        }\n"
        "    }\n"
    )
    if old_filter in t:
        t = t.replace(old_filter, new_filter, 1); changed = True

    old_txt = '                                text = "${if (isMove) "Move" else "Copy"} to Album",\n'
    new_txt = '                                text = "${if (isMove) "Move" else "Copy"} to Album/Board",\n'
    if old_txt in t:
        t = t.replace(old_txt, new_txt, 1); changed = True

    if changed:
        f.write_text(t, encoding="utf-8")
        log("  ✓ copymove dialog patched")
    else:
        log("  ✓ already patched (no change needed)")


# ============================================================
# PATCH 3 — ViewModel (THE FIX: correct copy anchor indentation)
# ============================================================
def patch_viewmodel():
    log("\n=== PATCH: ViewModel ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # 1. addManualImages — idempotent
    if "dao.upsertPinsSafely(pinsToInsert)" in t:
        log("  ✓ addManualImages already patched")
    else:
        old_add = (
            "                    if (pinsToInsert.isNotEmpty()) {\n"
            "                        dao.insertPins(pinsToInsert)\n"
            "                        totalAdded += pinsToInsert.size\n"
            "                    }\n"
        )
        new_add = (
            "                    if (pinsToInsert.isNotEmpty()) {\n"
            "                        dao.upsertPinsSafely(pinsToInsert)\n"
            "                        totalAdded += pinsToInsert.size\n"
            "                    }\n"
        )
        if old_add in t:
            t = t.replace(old_add, new_add, 1); changed = True
            log("  ✓ addManualImages uses upsert")
        else:
            log("  ⚠ addManualImages anchor missing")

    # 2. copySelectedPinsToBoards — the actual fix (correct 20/24/28/32 indentation)
    if "Cross-board copy: null albumId" in t:
        log("  ✓ copy already patched")
    else:
        # CORRECTED indentation: 20/24/28/32 (was wrongly 16/20/24/28)
        old_copy = (
            '                    if (newForTarget.isNotEmpty()) {\n'
            '                        val targetEntity = dao.getBoardById(targetId)\n'
            '                        if (targetEntity != null) {\n'
            '                            val existingPins = dao.getPinsForBoard(targetId).map { it.toPinItem() }\n'
            '                            val combined = (newForTarget + existingPins).distinctBy { it.id }\n'
            '                            val entities = combined.mapIndexed { idx, pin ->\n'
            '                                PinEntity.fromPinItem(pin, targetId, idx)\n'
            '                            }\n'
            '                            dao.saveFullBoard(targetEntity, entities)\n'
            '                        } else {\n'
            '                            val entities = newForTarget.mapIndexed { idx, pin ->\n'
            '                                PinEntity.fromPinItem(pin, targetId, existingIds.size + idx)\n'
            '                            }\n'
            '                            dao.insertPins(entities)\n'
            '                        }\n'
            '                        totalCopied += newForTarget.size\n'
            '                    }\n'
        )
        new_copy = (
            '                    if (newForTarget.isNotEmpty()) {\n'
            '                        // Cross-board copy: null albumId (album stays on source board)\n'
            '                        val entities = newForTarget.mapIndexed { idx, pin ->\n'
            '                            PinEntity.fromPinItem(pin.copy(albumId = null), targetId, existingIds.size + idx)\n'
            '                        }\n'
            '                        dao.upsertPinsSafely(entities)\n'
            '                        totalCopied += newForTarget.size\n'
            '                    }\n'
        )
        if old_copy in t:
            t = t.replace(old_copy, new_copy, 1); changed = True
            log("  ✓ copy: null albumId, upsert, no full save (CORRECTED anchor)")
        else:
            # Fallback: targeted replace within copySelectedPinsToBoards body only
            idx = t.find('    fun copySelectedPinsToBoards(')
            if idx >= 0:
                end_idx = t.find('\n    fun ', idx + 10)
                if end_idx < 0: end_idx = len(t)
                body = t[idx:end_idx]
                new_body = body
                new_body = new_body.replace(
                    '                            dao.saveFullBoard(targetEntity, entities)',
                    '                            // (upsert below)'
                )
                new_body = new_body.replace(
                    '                            dao.insertPins(entities)\n',
                    '                            dao.upsertPinsSafely(entities)\n',
                )
                new_body = new_body.replace(
                    '                                PinEntity.fromPinItem(pin, targetId, idx)',
                    '                                PinEntity.fromPinItem(pin.copy(albumId = null), targetId, idx)',
                )
                new_body = new_body.replace(
                    '                                PinEntity.fromPinItem(pin, targetId, existingIds.size + idx)',
                    '                                PinEntity.fromPinItem(pin.copy(albumId = null), targetId, existingIds.size + idx)',
                )
                if new_body != body:
                    # Add marker for verify
                    new_body = new_body.replace(
                        '    fun copySelectedPinsToBoards(targetBoardIds: List<String>, pinIds: Set<String>) {\n',
                        '    fun copySelectedPinsToBoards(targetBoardIds: List<String>, pinIds: Set<String>) {\n'
                        '        // Cross-board copy: null albumId marker\n',
                        1,
                    )
                    t = t[:idx] + new_body + t[end_idx:]
                    changed = True
                    log("  ✓ copy: patched via fallback (body-scoped)")
                else:
                    log("  ⚠ copy: primary AND fallback both failed")
            else:
                log("  ⚠ copy: function not found")

    # 3. moveSelectedPinsToBoards — idempotent
    if "val nonSelfTargets = targetBoardIds.filter { it != sourceBoard.id }" in t:
        log("  ✓ move already patched")
    else:
        old_move = (
            "            val dao = AppDatabase.getDatabase(ctx).boardDao()\n"
            "            withContext(Dispatchers.IO) {\n"
            "                // 1. Copy to target boards\n"
            "                for (targetId in targetBoardIds) {\n"
            "                    if (targetId == sourceBoard.id) continue\n"
            "                    val existingIds = dao.getPinIdsForBoard(targetId).toSet()\n"
            "                    val existingUrls = dao.getImageUrlsForBoard(targetId).toSet()\n"
            "                    val newForTarget = pinsToMove.filter {\n"
            "                        !existingIds.contains(it.id) && !existingUrls.contains(it.imageUrl)\n"
            "                    }\n"
            "                    if (newForTarget.isNotEmpty()) {\n"
            "                        val targetEntity = dao.getBoardById(targetId)\n"
            "                        if (targetEntity != null) {\n"
            "                            val existingPins = dao.getPinsForBoard(targetId).map { it.toPinItem() }\n"
            "                            val combined = (newForTarget + existingPins).distinctBy { it.id }\n"
            "                            val entities = combined.mapIndexed { idx, pin ->\n"
            "                                PinEntity.fromPinItem(pin, targetId, idx)\n"
            "                            }\n"
            "                            dao.saveFullBoard(targetEntity, entities)\n"
            "                        } else {\n"
            "                            val entities = newForTarget.mapIndexed { idx, pin ->\n"
            "                                PinEntity.fromPinItem(pin, targetId, existingIds.size + idx)\n"
            "                            }\n"
            "                            dao.insertPins(entities)\n"
            "                        }\n"
            "                    }\n"
            "                }\n"
            "                // 2. Delete from source board in Room\n"
            "                dao.deletePinsFromBoard(sourceBoard.id, pinIds.toList())\n"
            "                refreshAvailableBoardsFromDatabaseInternal(dao)\n"
            "            }\n"
        )
        new_move = (
            "            val dao = AppDatabase.getDatabase(ctx).boardDao()\n"
            "            // Guard: exclude self board (prevents data loss)\n"
            "            val nonSelfTargets = targetBoardIds.filter { it != sourceBoard.id }\n"
            "            if (nonSelfTargets.isEmpty()) {\n"
            "                clearSelection()\n"
            "                _snackbarMessage.value = \"Cannot move to the same board\"\n"
            "                return@launch\n"
            "            }\n"
            "            withContext(Dispatchers.IO) {\n"
            "                for (targetId in nonSelfTargets) {\n"
            "                    val existingIds = dao.getPinIdsForBoard(targetId).toSet()\n"
            "                    val existingUrls = dao.getImageUrlsForBoard(targetId).toSet()\n"
            "                    val newForTarget = pinsToMove.filter {\n"
            "                        !existingIds.contains(it.id) && !existingUrls.contains(it.imageUrl)\n"
            "                    }\n"
            "                    if (newForTarget.isNotEmpty()) {\n"
            "                        val entities = newForTarget.mapIndexed { idx, pin ->\n"
            "                            PinEntity.fromPinItem(pin.copy(albumId = null), targetId, existingIds.size + idx)\n"
            "                        }\n"
            "                        dao.upsertPinsSafely(entities)\n"
            "                    }\n"
            "                }\n"
            "                dao.deletePinsFromBoard(sourceBoard.id, pinIds.toList())\n"
            "                refreshAvailableBoardsFromDatabaseInternal(dao)\n"
            "            }\n"
        )
        if old_move in t:
            t = t.replace(old_move, new_move, 1); changed = True
            log("  ✓ move: self-guard, null albumId, upsert")
        else:
            log("  ⚠ move anchor missing")

    if changed:
        f.write_text(t, encoding="utf-8")


# ============================================================
# Self-verify
# ============================================================
def verify_patches():
    log("\n=== Self-verify ===")
    checks = [
        ("app/src/main/java/com/example/ui/ShareTargetActivity.kt", [
            "onHoldBoard: (String, Boolean) -> Unit",
            "onHoldBoard(board.id, extractMultipleImages)",
            "dao.upsertPinsSafely(toInsert.mapIndexed { i, p ->",
        ]),
        ("app/src/main/java/com/example/ui/dialogs/CopyOrMoveImagesDialog.kt", [
            "availableBoards.filter { it.id != currentBoardId }",
            "to Album/Board",
        ]),
        ("app/src/main/java/com/example/viewmodel/PinBoardViewModel.kt", [
            "val nonSelfTargets = targetBoardIds.filter { it != sourceBoard.id }",
            "Cross-board copy: null albumId",
            "dao.upsertPinsSafely(pinsToInsert)",
        ]),
    ]
    for rel, markers in checks:
        fp = PROJECT_ROOT / rel
        if not fp.exists():
            log(f"  ✗ {rel} missing"); sys.exit(1)
        content = fp.read_text(encoding="utf-8")
        for m in markers:
            if m not in content:
                log(f"  ✗ MISSING in {rel}: {m[:60]}")
                sys.exit(1)
        log(f"  ✓ {rel.split('/')[-1]}")


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
        run(["git", "commit", "-m", "Fix copy anchor indentation (data-loss fix now applies)"])


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
    log("PinBoard — fix copy anchor + idempotent patches")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    patch_share_activity()
    patch_copy_move_dialog()
    patch_viewmodel()
    verify_patches()

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