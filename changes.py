#!/usr/bin/env python3
"""
PinBoard Gallery — fix onClose anchor + unified cache budget
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
# PATCH 1 — fix onClose anchor (regex, handles comma variants)
# ============================================================
def patch_onclose_release():
    log("\n=== PATCH: onClose release (regex, comma-tolerant) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "com.example.util.VideoPlayerManager.release()" in t:
        log("  ✓ already patched"); return

    pattern = re.compile(r'([ \t]*)onClose = \{ viewModel\.closeFullscreen\(\) \}(,?)')

    def repl(m):
        indent = m.group(1)
        inner = indent + "    "
        return (
            f"{indent}onClose = {{\n"
            f"{inner}com.example.util.VideoPlayerManager.release()\n"
            f"{inner}viewModel.closeFullscreen()\n"
            f"{indent}}},"
        )

    t_new, n = pattern.subn(repl, t, count=1)
    if n == 0:
        log("  ✗ onClose not matched even with regex"); sys.exit(1)

    f.write_text(t_new, encoding="utf-8")
    log("  ✓ onClose now releases player (comma handled)")


# ============================================================
# PATCH 2 — VideoPlayerManager: full limit + getSimpleCacheForEviction
# ============================================================
def patch_video_player_manager():
    log("\n=== PATCH: VideoPlayerManager (full limit + evict hook) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/VideoPlayerManager.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")
    changed = False

    # 2a. Switch from 30% budget to full limit
    old_budget = (
        "        val budgetMb = maxOf(MIN_VIDEO_CACHE_MB,\n"
        "            (maxMb * VIDEO_BUDGET_PERCENT) / 100L)\n"
        "        val budgetBytes = budgetMb * 1024L * 1024L\n"
    )
    new_budget = (
        "        // Use the FULL user limit. Combined image+video is enforced by\n"
        "        // CacheBudgetEnforcer.sweep() — no artificial 30/70 split.\n"
        "        val budgetMb = maxMb\n"
        "        val budgetBytes = budgetMb * 1024L * 1024L\n"
    )
    if old_budget in t:
        t = t.replace(old_budget, new_budget, 1)
        changed = True
        log("  ✓ video cache uses full limit (was 30%)")
    elif "val budgetMb = maxMb\n" in t:
        log("  ✓ already uses full limit")

    # 2b. Add getSimpleCacheForEviction
    if "fun getSimpleCacheForEviction(" not in t:
        anchor = "    fun getCacheSizeBytes(context: Context): Long {\n"
        add = (
            "    /** Returns the existing SimpleCache without creating it, for external eviction. */\n"
            "    fun getSimpleCacheForEviction(context: Context): SimpleCache? = simpleCache\n"
            "\n"
            "    fun getCacheSizeBytes(context: Context): Long {\n"
        )
        if anchor in t:
            t = t.replace(anchor, add, 1)
            changed = True
            log("  ✓ getSimpleCacheForEviction added")
        else:
            log("  ⚠ getCacheSizeBytes anchor missing")

    # 2c. Pause should trigger sweep (delayed)
    old_pause = (
        "    fun pause() {\n"
        "        try { player?.pause() } catch (_: Throwable) {}\n"
        "    }\n"
    )
    new_pause = (
        "    fun pause() {\n"
        "        try { player?.pause() } catch (_: Throwable) {}\n"
        "        CacheBudgetEnforcer.sweepAsync()\n"
        "    }\n"
    )
    if old_pause in t:
        t = t.replace(old_pause, new_pause, 1)
        changed = True
        log("  ✓ pause → sweepAsync")
    elif "CacheBudgetEnforcer.sweepAsync()" in t and "fun pause()" in t:
        log("  ✓ pause already calls sweep")

    # 2d. Release should trigger sweep
    old_release = (
        "        player = null\n"
        "        currentPinId = null\n"
        "    }\n"
    )
    new_release = (
        "        player = null\n"
        "        currentPinId = null\n"
        "        CacheBudgetEnforcer.sweepAsync()\n"
        "    }\n"
    )
    if old_release in t and "CacheBudgetEnforcer.sweepAsync()" not in t.split("fun release()")[1][:200] if "fun release()" in t else True:
        t = t.replace(old_release, new_release, 1)
        changed = True
        log("  ✓ release → sweepAsync")

    if changed:
        f.write_text(t, encoding="utf-8")


# ============================================================
# NEW: CacheBudgetEnforcer.kt
# ============================================================
NEW_CACHE_BUDGET_ENFORCER = r'''package com.example.util

import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.File

/**
 * Enforces the user's total cache limit across IMAGE and VIDEO caches.
 *
 * Rationale:
 *   - Coil (image) and Media3 (video) each have their own LRU evictors that
 *     only know about their own caches. If both use the full limit, combined
 *     size can reach 2x the user's intent.
 *   - This object periodically sweeps. If combined > limit, it evicts the
 *     oldest completed VIDEO spans first (video is easier to evict than
 *     Coil's disk cache). If video is exhausted and combined is still over,
 *     images are simply left alone — Coil's own LRU will evict them on its
 *     next write when it exceeds the limit by itself.
 *
 * Net effect: combined stays under the user's limit in steady state, with
 * both categories able to grow into whatever the other isn't using.
 */
object CacheBudgetEnforcer {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var appContext: Context? = null
    private var monitorJob: Job? = null

    fun init(context: Context) {
        if (appContext != null) return
        appContext = context.applicationContext
        monitorJob = scope.launch {
            while (isActive) {
                delay(60_000L)
                try { sweep() } catch (_: Throwable) {}
            }
        }
    }

    fun sweepAsync() {
        scope.launch {
            try {
                delay(500L)  // let any in-flight write settle
                sweep()
            } catch (_: Throwable) {}
        }
    }

    fun sweep() {
        val ctx = appContext ?: return
        val limit = ImageCacheManager.getMaxDiskCacheMb(ctx).toLong() * 1024L * 1024L
        val imageSize = getImageCacheBytes(ctx)
        val videoSize = VideoPlayerManager.getCacheSizeBytes(ctx)
        val total = imageSize + videoSize
        if (total <= limit) return

        var toEvict = total - limit
        val cache = VideoPlayerManager.getSimpleCacheForEviction(ctx) ?: return
        try {
            val spans = cache.keys().asSequence()
                .flatMap { key ->
                    try { cache.getCachedSpans(key).asSequence() } catch (_: Throwable) { emptySequence() }
                }
                .filter { it.file != null }
                .sortedBy { it.lastTouchTimestamp }
                .toList()

            for (span in spans) {
                if (toEvict <= 0L) break
                try {
                    if (cache.removeSpan(span)) {
                        toEvict -= span.length
                    }
                } catch (_: Throwable) {}
            }
        } catch (_: Throwable) {}
    }

    private fun getImageCacheBytes(context: Context): Long {
        val dir = File(context.cacheDir, "image_cache")
        if (!dir.exists()) return 0L
        return dirSize(dir)
    }

    private fun dirSize(dir: File): Long {
        var total = 0L
        dir.listFiles()?.forEach { f ->
            total += if (f.isDirectory) dirSize(f) else f.length()
        }
        return total
    }
}
'''


def write_cache_budget_enforcer():
    log("\n=== PATCH: new CacheBudgetEnforcer.kt ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/CacheBudgetEnforcer.kt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(NEW_CACHE_BUDGET_ENFORCER, encoding="utf-8")
    log("  ✓ created")


# ============================================================
# PATCH 3 — PinBoardApplication: init CacheBudgetEnforcer
# ============================================================
def patch_pinboard_application():
    log("\n=== PATCH: PinBoardApplication (init enforcer) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/PinBoardApplication.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    if "CacheBudgetEnforcer.init(" in t:
        log("  ✓ already patched"); return

    anchor = '        com.example.util.CrashMonitor.init(this)\n'
    if anchor in t:
        t = t.replace(
            anchor,
            anchor + "        com.example.util.CacheBudgetEnforcer.init(this)\n",
            1,
        )
        f.write_text(t, encoding="utf-8")
        log("  ✓ CacheBudgetEnforcer.init called")
    else:
        log("  ⚠ CrashMonitor.init anchor missing")


# ============================================================
# PATCH 4 — ImageCacheManager: video cache is NOT separate anymore
#           (but getDiskCacheUsageBytes and clearCache still combine them)
# ============================================================
def patch_image_cache_manager_comment():
    log("\n=== PATCH: ImageCacheManager (comment update) ===")
    f = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageCacheManager.kt"
    if not f.exists(): log("  ✗ not found"); sys.exit(1)
    t = f.read_text(encoding="utf-8")

    # Just ensure VideoPlayerManager calls still work — no code change needed.
    # The comment update is cosmetic; skip if already there.
    if "CacheBudgetEnforcer" in t:
        log("  ✓ already referenced"); return

    # Add explanatory comment above getDiskCacheUsageBytes
    old = (
        "    fun getDiskCacheUsageBytes(context: Context): Long {\n"
    )
    new = (
        "    /** Combined image + video cache size. Enforced as a single budget by CacheBudgetEnforcer. */\n"
        "    fun getDiskCacheUsageBytes(context: Context): Long {\n"
    )
    if old in t:
        t = t.replace(old, new, 1)
        f.write_text(t, encoding="utf-8")
        log("  ✓ comment added")


# ============================================================
# Verify
# ============================================================
def verify_all():
    log("\n=== VERIFY ===")
    checks = []

    ps = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    vpm = PROJECT_ROOT / "app/src/main/java/com/example/util/VideoPlayerManager.kt"
    cbe = PROJECT_ROOT / "app/src/main/java/com/example/util/CacheBudgetEnforcer.kt"
    pa = PROJECT_ROOT / "app/src/main/java/com/example/PinBoardApplication.kt"
    icm = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageCacheManager.kt"

    for p in (ps, vpm, cbe, pa, icm):
        if not p.exists(): log(f"  ✗ missing: {p}"); sys.exit(1)

    ps_t = ps.read_text(encoding="utf-8")
    vpm_t = vpm.read_text(encoding="utf-8")
    cbe_t = cbe.read_text(encoding="utf-8")
    pa_t = pa.read_text(encoding="utf-8")
    icm_t = icm.read_text(encoding="utf-8")

    checks.append(("Screen onClose releases player",
                   "com.example.util.VideoPlayerManager.release()" in ps_t))
    checks.append(("Screen onClose pattern correct",
                   "onClose = {\n" in ps_t and "com.example.util.VideoPlayerManager.release()" in ps_t))
    checks.append(("Screen no leftover one-line onClose",
                   "onClose = { viewModel.closeFullscreen() }" not in ps_t or
                   "onClose = {\n" in ps_t))
    checks.append(("VideoPlayerManager full limit (no % split)",
                   "val budgetMb = maxMb" in vpm_t))
    checks.append(("VideoPlayerManager getSimpleCacheForEviction",
                   "fun getSimpleCacheForEviction(" in vpm_t))
    checks.append(("VideoPlayerManager pause → sweep",
                   "fun pause()" in vpm_t and "CacheBudgetEnforcer.sweepAsync()" in vpm_t))
    checks.append(("VideoPlayerManager release → sweep",
                   "fun release()" in vpm_t and vpm_t.count("CacheBudgetEnforcer.sweepAsync()") >= 2))
    checks.append(("CacheBudgetEnforcer exists",
                   "object CacheBudgetEnforcer" in cbe_t))
    checks.append(("CacheBudgetEnforcer sweep reads video size",
                   "VideoPlayerManager.getCacheSizeBytes" in cbe_t))
    checks.append(("CacheBudgetEnforcer evicts via removeSpan",
                   "cache.removeSpan(span)" in cbe_t))
    checks.append(("PinBoardApplication inits enforcer",
                   "CacheBudgetEnforcer.init(" in pa_t))

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

    for label, path in [("Screen", ps), ("Manager", vpm), ("Enforcer", cbe)]:
        s = strip(path.read_text(encoding="utf-8"))
        po, pc = s.count("("), s.count(")")
        bo, bc = s.count("{"), s.count("}")
        checks.append((f"{label} paren balance ({po}/{pc})", po == pc))
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
        run(["git", "commit", "-m", "Fix onClose anchor + unified cache budget (CacheBudgetEnforcer)"])


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
    log("PinBoard — onClose anchor fix + unified cache budget")
    log("=" * 70)
    if not (PROJECT_ROOT / "app/build.gradle.kts").exists(): sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t): sys.exit(1)

    patch_onclose_release()
    patch_video_player_manager()
    write_cache_budget_enforcer()
    patch_pinboard_application()
    patch_image_cache_manager_comment()
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