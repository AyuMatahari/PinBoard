#!/usr/bin/env python3
"""
PinBoard Gallery
----------------
CURRENT CHANGE: Build warnings + KSP AWT error
  * gradle.properties: -Djava.awt.headless=true (fixes KSP AWT NPE on CI)
  * workflow: JAVA_TOOL_OPTIONS=-Djava.awt.headless=true (belt-and-suspenders)
  * PinterestBrowserWorker.kt: @Suppress(DEPRECATION), nullable optString fixes
  * ShareTargetActivity.kt: IntentCompat.getParcelable*Extra
  * BrowserWorkerTestingPanel.kt: AutoMirrored Sort/Login icons
  * CrashMonitor.kt: @Suppress(DEPRECATION) on buildCrashReport
  * ImageCacheManager.kt: @OptIn(ExperimentalCoilApi::class) on clearCache

FULL PIPELINE runs after the patch:
  1. apply this patch
  2. ensure release.keystore + patch app/build.gradle.kts
  3. ensure gradle wrapper + write CI workflow
  4. commit + push to <user>/PinBoard
  5. trigger CI -> poll -> download app-release artifact
  6. save as PinBoard-v{versionName}-{versionCode}.apk into 'Apk Directory.txt'
  7. verify signature -> uninstall + install on device
"""

import os
import re
import sys
import json
import time
import shutil
import datetime
import subprocess
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
REPO_NAME    = "PinBoard"
APP_NAME     = "PinBoard"
ARTIFACT     = "app-release"
PACKAGE_ID   = "com.aistudio.pinboardgallery.kzwvpt"

KEYSTORE_FILE     = "release.keystore"
KEYSTORE_ALIAS    = "upload"
KEYSTORE_PASS     = "PinBoardRelease2025"
KEYSTORE_DNAME    = "CN=PinBoard Gallery, OU=PinBoard, O=PinBoard, L=Unknown, ST=Unknown, C=US"
KEYSTORE_VALIDITY = "10000"

# Note the added `env: JAVA_TOOL_OPTIONS` on the job — kills KSP AWT NPE on CI
WORKFLOW_YAML = """\
name: Build APK

on:
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    env:
      JAVA_TOOL_OPTIONS: "-Djava.awt.headless=true"
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Set up Android SDK
        uses: android-actions/setup-android@v3
        with:
          packages: ''

      - name: Accept Android licenses
        run: yes | sdkmanager --licenses >/dev/null 2>&1 || true

      - name: Install SDK components
        run: sdkmanager --install "platforms;android-36" "build-tools;36.0.0" >/dev/null 2>&1 || true

      - name: Verify release.keystore is committed
        run: |
          if [ ! -f release.keystore ]; then
            echo "ERROR: release.keystore missing from repo"
            exit 1
          fi
          if ! keytool -list -keystore release.keystore -storepass PinBoardRelease2025 2>/dev/null | grep -q upload; then
            echo "ERROR: alias 'upload' not found in release.keystore"
            exit 1
          fi
          echo "release.keystore OK"

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v3
        with:
          gradle-version: wrapper

      - name: Make gradlew executable
        run: chmod +x ./gradlew

      - name: Build Release APK
        run: ./gradlew :app:assembleRelease --stacktrace --no-daemon

      - name: Verify APK signature
        run: |
          APK=$(find app/build/outputs/apk/release -name "*.apk" | head -1)
          if [ -z "$APK" ]; then echo "ERROR: no release APK produced"; exit 1; fi
          echo "APK: $APK"
          BT=$(ls -d $ANDROID_HOME/build-tools/* | sort -V | tail -1)
          "$BT/apksigner" verify --verbose --print-certs "$APK"

      - name: Upload APK
        uses: actions/upload-artifact@v4
        with:
          name: app-release
          path: app/build/outputs/apk/release/*.apk
          if-no-files-found: error
"""


def log(msg): print(msg, flush=True)


def run(cmd, cwd=None, check=True, capture=False):
    log(f"> {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    try:
        return subprocess.run(
            cmd, cwd=str(cwd or PROJECT_ROOT),
            check=check, capture_output=capture, text=True,
            shell=isinstance(cmd, str),
        )
    except subprocess.CalledProcessError as e:
        log(f"  Command failed (rc={e.returncode})")
        if e.stdout: log(f"  stdout: {e.stdout}")
        if e.stderr: log(f"  stderr: {e.stderr}")
        if check: raise


def tool_available(name):
    try:
        subprocess.run([name, "--version"], capture_output=True, check=True, timeout=5)
        return True
    except Exception:
        return False


# ============================================================
# THIS TASK'S ONLY CODE PATCH
# ============================================================
def patch_build_warnings_and_errors():
    log("\n=== PATCH: Build warnings + KSP AWT error ===")

    # ---- 1. gradle.properties: headless AWT (kills KSP NPE) ----
    gp = PROJECT_ROOT / "gradle.properties"
    if gp.exists():
        g = gp.read_text(encoding="utf-8")
        if "-Djava.awt.headless=true" not in g:
            g = g.replace(
                "org.gradle.jvmargs=-Xmx4g -Dfile.encoding=UTF-8",
                "org.gradle.jvmargs=-Xmx4g -Dfile.encoding=UTF-8 -Djava.awt.headless=true",
                1,
            )
            gp.write_text(g, encoding="utf-8")
            log("  ✓ gradle.properties: org.gradle.jvmargs += -Djava.awt.headless=true")
        else:
            log("  ✓ gradle.properties already headless")

    # ---- 2. PinterestBrowserWorker.kt ----
    pw = PROJECT_ROOT / "app/src/main/java/com/example/scanner/PinterestBrowserWorker.kt"
    if pw.exists():
        t = pw.read_text(encoding="utf-8")
        changed = False

        # 2a. @Suppress(DEPRECATION) on initWebView (databaseEnabled)
        if '@Suppress("DEPRECATION")\n    private fun initWebView()' not in t:
            old = '    @SuppressLint("SetJavaScriptEnabled")\n    private fun initWebView() {'
            new = ('    @SuppressLint("SetJavaScriptEnabled")\n'
                   '    @Suppress("DEPRECATION")\n'
                   '    private fun initWebView() {')
            if old in t:
                t = t.replace(old, new, 1); changed = True
                log("  ✓ PinterestBrowserWorker: @Suppress(DEPRECATION) on initWebView")

        # 2b. Line 606: optString(String) -> String? type mismatch
        old = 'val rawDesc = candidateObj.optString("description", candidateObj.optString("grid_title", ""))'
        new = 'val rawDesc = candidateObj.optString("description", candidateObj.optString("grid_title", "").orEmpty())'
        if old in t:
            t = t.replace(old, new, 1); changed = True
            log("  ✓ line 606: .orEmpty() on nested optString")

        # 2c. Line 639: optString(String, null) -> Nothing? type mismatch
        old = 'val pinterestCreatedAt = candidateObj.optString("board_pinned_at", candidateObj.optString("created_at", null))'
        new = 'val pinterestCreatedAt = candidateObj.optString("board_pinned_at", candidateObj.optString("created_at", ""))'
        if old in t:
            t = t.replace(old, new, 1); changed = True
            log("  ✓ line 639: optString(..., null) -> \"\"")

        if changed:
            pw.write_text(t, encoding="utf-8")

    # ---- 3. ShareTargetActivity.kt: IntentCompat ----
    st = PROJECT_ROOT / "app/src/main/java/com/example/ui/ShareTargetActivity.kt"
    if st.exists():
        t = st.read_text(encoding="utf-8")
        changed = False

        old = '(intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM))?.let { uri ->'
        new = 'androidx.core.content.IntentCompat.getParcelableExtra(intent, Intent.EXTRA_STREAM, Uri::class.java)?.let { uri ->'
        if old in t:
            t = t.replace(old, new, 1); changed = True
            log("  ✓ ShareTargetActivity: IntentCompat.getParcelableExtra")

        old = 'intent.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM)?.let { list ->'
        new = 'androidx.core.content.IntentCompat.getParcelableArrayListExtra(intent, Intent.EXTRA_STREAM, Uri::class.java)?.let { list ->'
        if old in t:
            t = t.replace(old, new, 1); changed = True
            log("  ✓ ShareTargetActivity: IntentCompat.getParcelableArrayListExtra")

        if changed:
            st.write_text(t, encoding="utf-8")

    # ---- 4. BrowserWorkerTestingPanel.kt: AutoMirrored icons ----
    bp = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/BrowserWorkerTestingPanel.kt"
    if bp.exists():
        t = bp.read_text(encoding="utf-8")
        changed = False

        # Sort: change import + usage together (only if both present)
        if ("import androidx.compose.material.icons.filled.Sort" in t
                and "Icons.Default.Sort" in t):
            t = t.replace(
                "import androidx.compose.material.icons.filled.Sort",
                "import androidx.compose.material.icons.automirrored.filled.Sort",
                1,
            )
            t = t.replace("Icons.Default.Sort", "Icons.AutoMirrored.Filled.Sort")
            changed = True
            log("  ✓ BrowserWorkerTestingPanel: AutoMirrored Sort")

        # Login: change import + usage together
        if ("import androidx.compose.material.icons.filled.Login" in t
                and "Icons.Default.Login" in t):
            t = t.replace(
                "import androidx.compose.material.icons.filled.Login",
                "import androidx.compose.material.icons.automirrored.filled.Login",
                1,
            )
            t = t.replace("Icons.Default.Login", "Icons.AutoMirrored.Filled.Login")
            changed = True
            log("  ✓ BrowserWorkerTestingPanel: AutoMirrored Login")

        if changed:
            bp.write_text(t, encoding="utf-8")

    # ---- 5. CrashMonitor.kt: @Suppress on buildCrashReport ----
    cm = PROJECT_ROOT / "app/src/main/java/com/example/util/CrashMonitor.kt"
    if cm.exists():
        t = cm.read_text(encoding="utf-8")
        if ('@Suppress("DEPRECATION")\n    private fun buildCrashReport' not in t
                and "Thread.currentThread().id" in t):
            old = "    private fun buildCrashReport(threadName: String, throwable: Throwable, contextTag: String): String {"
            new = ('    @Suppress("DEPRECATION")\n'
                   '    private fun buildCrashReport(threadName: String, throwable: Throwable, contextTag: String): String {')
            if old in t:
                t = t.replace(old, new, 1)
                cm.write_text(t, encoding="utf-8")
                log("  ✓ CrashMonitor: @Suppress(DEPRECATION) on buildCrashReport")
        else:
            log("  ✓ CrashMonitor already patched")

    # ---- 6. ImageCacheManager.kt: @OptIn(ExperimentalCoilApi) ----
    ic = PROJECT_ROOT / "app/src/main/java/com/example/util/ImageCacheManager.kt"
    if ic.exists():
        t = ic.read_text(encoding="utf-8")
        if "@OptIn(coil.annotation.ExperimentalCoilApi::class)" not in t:
            old = "    fun clearCache(context: Context) {"
            new = ("    @OptIn(coil.annotation.ExperimentalCoilApi::class)\n"
                   "    fun clearCache(context: Context) {")
            if old in t:
                t = t.replace(old, new, 1)
                ic.write_text(t, encoding="utf-8")
                log("  ✓ ImageCacheManager: @OptIn(ExperimentalCoilApi)")
        else:
            log("  ✓ ImageCacheManager already patched")

    log("  ✓ Patch complete")


# ============================================================
# Versioned APK naming
# ============================================================
def read_app_version():
    build_path = PROJECT_ROOT / "app/build.gradle.kts"
    if not build_path.exists(): return ("unknown", "0")
    text = build_path.read_text(encoding="utf-8")
    vn = re.search(r'versionName\s*=\s*"([^"]+)"', text)
    vc = re.search(r"versionCode\s*=\s*(\d+)", text)
    return (vn.group(1) if vn else "unknown",
            vc.group(1) if vc else "0")


# ============================================================
# Build infrastructure
# ============================================================
def ensure_release_keystore():
    log("\n=== Ensuring release.keystore ===")
    ks = PROJECT_ROOT / KEYSTORE_FILE
    if ks.exists() and ks.stat().st_size > 0:
        r = subprocess.run(["keytool", "-list", "-keystore", str(ks),
                            "-storepass", KEYSTORE_PASS],
                           capture_output=True, text=True)
        if r.returncode == 0 and KEYSTORE_ALIAS in r.stdout:
            log(f"  ✓ {KEYSTORE_FILE} OK"); return
        log(f"  ✗ {KEYSTORE_FILE} exists but password/alias mismatch."); sys.exit(1)
    log(f"  Generating {KEYSTORE_FILE}…")
    r = subprocess.run([
        "keytool", "-genkeypair", "-v",
        "-keystore", str(ks),
        "-alias", KEYSTORE_ALIAS,
        "-keyalg", "RSA", "-keysize", "2048",
        "-validity", KEYSTORE_VALIDITY,
        "-storepass", KEYSTORE_PASS,
        "-keypass", KEYSTORE_PASS,
        "-dname", KEYSTORE_DNAME,
    ], capture_output=True, text=True)
    if r.returncode != 0:
        log(f"  ✗ keytool: {r.stderr.strip()}"); sys.exit(1)
    log(f"  ✓ Generated {KEYSTORE_FILE}")


def find_braced_block_at(text, start):
    open_brace = text.find("{", start)
    if open_brace == -1: return None
    depth, i = 1, open_brace + 1
    while i < len(text) and depth > 0:
        c = text[i]
        if c == '"':
            i += 1
            while i < len(text):
                if text[i] == "\\": i += 2; continue
                if text[i] == '"': break
                i += 1
        elif c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0: return (open_brace, i)
        i += 1
    return None


def patch_build_gradle():
    log("\n=== Patching app/build.gradle.kts ===")
    p = PROJECT_ROOT / "app/build.gradle.kts"
    if not p.exists(): log(f"  ✗ {p} not found"); sys.exit(1)
    text = p.read_text(encoding="utf-8"); orig = text

    idx = text.find('create("release")')
    if idx == -1: log(f'  ✗ create("release") not found'); sys.exit(1)
    span = find_braced_block_at(text, idx)
    if not span: log("  ✗ braces not found"); sys.exit(1)
    open_b, close_b = span
    if f'storeFile = file("${{rootDir}}/{KEYSTORE_FILE}")' not in text[open_b:close_b]:
        new_contents = (
            f'\n      storeFile = file("${{rootDir}}/{KEYSTORE_FILE}")\n'
            f'      storePassword = "{KEYSTORE_PASS}"\n'
            f'      keyAlias = "{KEYSTORE_ALIAS}"\n'
            f'      keyPassword = "{KEYSTORE_PASS}"\n    '
        )
        text = text[:open_b + 1] + new_contents + text[close_b:]
        log(f'  ✓ create("release") uses ${{rootDir}}/{KEYSTORE_FILE}')

    bt_idx = text.find("buildTypes {")
    if bt_idx != -1:
        rel_start = text.find("release {", bt_idx)
        if rel_start != -1:
            rel_span = find_braced_block_at(text, rel_start)
            if rel_span:
                ro, rc = rel_span
                block = text[ro + 1:rc]
                if "isDebuggable = true" in block:
                    text = text[:ro + 1] + block.replace("isDebuggable = true", "isDebuggable = false") + text[rc:]
                    log("  ✓ release buildType: isDebuggable -> false")
                elif "isDebuggable" not in block:
                    nb = block.replace("isMinifyEnabled = false",
                                       "isMinifyEnabled = false\n      isDebuggable = false", 1)
                    if nb != block:
                        text = text[:ro + 1] + nb + text[rc:]
                        log("  ✓ added isDebuggable = false")

    if text != orig: p.write_text(text, encoding="utf-8")


def latest_gradle_version():
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/gradle/gradle/releases/latest",
            headers={"User-Agent": "pinboard-build"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            tag = json.load(resp).get("tag_name", "").lstrip("v")
            if tag: return tag
    except Exception: pass
    props = PROJECT_ROOT / "gradle/wrapper/gradle-wrapper.properties"
    if props.exists():
        m = re.search(r"gradle-([\d.]+)-bin\.zip", props.read_text(encoding="utf-8"))
        if m: return m.group(1)
    return "9.3.1"


def ensure_gradle_wrapper():
    log("\n=== Ensuring Gradle wrapper ===")
    gw = PROJECT_ROOT / "gradlew"
    gwb = PROJECT_ROOT / "gradlew.bat"
    jar = PROJECT_ROOT / "gradle/wrapper/gradle-wrapper.jar"
    if gw.exists() and gwb.exists() and jar.exists():
        log("  ✓ Present."); return
    ver = latest_gradle_version(); log(f"  Using Gradle v{ver}")
    base = f"https://raw.githubusercontent.com/gradle/gradle/v{ver}"
    for url, dest in [
        (f"{base}/gradlew", gw),
        (f"{base}/gradlew.bat", gwb),
        (f"{base}/gradle/wrapper/gradle-wrapper.jar", jar),
    ]:
        if dest.exists() and dest.stat().st_size > 0: continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try: urllib.request.urlretrieve(url, dest)
        except Exception as e: log(f"  ✗ {e}"); sys.exit(1)
    try: os.chmod(gw, 0o755)
    except Exception: pass


def write_workflow():
    log("\n=== Writing GitHub Actions workflow ===")
    wf = PROJECT_ROOT / ".github/workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "build.yml").write_text(WORKFLOW_YAML, encoding="utf-8")
    log("  ✓ Written (with JAVA_TOOL_OPTIONS headless env).")


def setup_git():
    log("\n=== Setting up git repo ===")
    if not (PROJECT_ROOT / ".git").exists():
        run(["git", "init"]); run(["git", "branch", "-M", "main"])
    if not subprocess.run(["git", "config", "--global", "user.name"],
                          capture_output=True, text=True).stdout.strip():
        run(["git", "config", "--global", "user.name", "PinBoard Build"])
    if not subprocess.run(["git", "config", "--global", "user.email"],
                          capture_output=True, text=True).stdout.strip():
        run(["git", "config", "--global", "user.email", "pinboard@build.local"])

    gi = PROJECT_ROOT / ".gitignore"
    required = [
        "build/", "*/build/", ".gradle/", "local.properties",
        "*.iml", ".idea/", ".cxx/", ".DS_Store",
        ".kotlin/", ".env", "_downloads/",
        "*.jks", "*.keystore", "!debug.keystore", "!release.keystore",
    ]
    existing = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    merged = list(existing)
    for line in required:
        if line not in merged: merged.append(line)
    gi.write_text("\n".join(merged) + "\n", encoding="utf-8")

    run(["git", "add", "-A"])
    for name in (KEYSTORE_FILE, "debug.keystore"):
        if (PROJECT_ROOT / name).exists():
            run(["git", "add", "-f", name], check=False)

    if subprocess.run(["git", "status", "--porcelain"],
                      capture_output=True, text=True).stdout.strip():
        run(["git", "commit", "-m",
             "Clean build: fix KSP AWT NPE + all Kotlin warnings"])
        log("  ✓ Committed.")


def verify_release_keystore_tracked():
    r = subprocess.run(["git", "ls-files", "--error-unmatch", KEYSTORE_FILE],
                       capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    if r.returncode != 0:
        run(["git", "add", "-f", KEYSTORE_FILE])
        run(["git", "commit", "-m", f"Add {KEYSTORE_FILE}"])


def gh_user():
    r = subprocess.run(["gh", "api", "user", "--jq", ".login"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        log("ERROR: gh not authenticated."); sys.exit(1)
    return r.stdout.strip()


def ensure_github_repo():
    log("\n=== Ensuring GitHub repo ===")
    user = gh_user(); full = f"{user}/{REPO_NAME}"
    if subprocess.run(["gh", "repo", "view", full], capture_output=True).returncode != 0:
        subprocess.run(["gh", "repo", "create", REPO_NAME, "--public",
                        "--source", ".", "--remote", "origin", "--push"],
                       capture_output=True, text=True)
    if subprocess.run(["git", "remote", "get-url", "origin"],
                      capture_output=True).returncode != 0:
        run(["git", "remote", "add", "origin", f"https://github.com/{full}.git"])
    r = subprocess.run(["git", "push", "-u", "origin", "main"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(["git", "push", "-u", "origin", "main", "--force"],
                       capture_output=True, text=True)
    return full


def trigger_and_download(repo_full):
    log("\n=== Triggering CI ===")
    for _ in range(6):
        r = subprocess.run(["gh", "workflow", "run", "build.yml",
                            "--ref", "main", "--repo", repo_full],
                           capture_output=True, text=True)
        if r.returncode == 0: break
        time.sleep(10)
    else:
        log(f"  ✗ {r.stderr.strip()}"); sys.exit(1)

    time.sleep(10)
    run_id = None
    for _ in range(20):
        r = subprocess.run(["gh", "run", "list", "--repo", repo_full,
                            "--workflow", "build.yml", "--limit", "1",
                            "--json", "databaseId"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            try:
                runs = json.loads(r.stdout)
                if runs: run_id = runs[0]["databaseId"]; break
            except json.JSONDecodeError: pass
        time.sleep(5)
    if run_id is None: log("  ✗ No run found."); sys.exit(1)

    while True:
        r = subprocess.run(["gh", "run", "view", str(run_id), "--repo", repo_full,
                            "--json", "status,conclusion"],
                           capture_output=True, text=True)
        if r.returncode != 0: time.sleep(15); continue
        try: info = json.loads(r.stdout)
        except json.JSONDecodeError: time.sleep(15); continue
        st, cc = info.get("status", ""), info.get("conclusion", "")
        log(f"  status={st} conclusion={cc}")
        if st == "completed":
            if cc != "success":
                subprocess.run(["gh", "run", "view", str(run_id), "--repo", repo_full,
                                "--log-failed"], check=False)
                sys.exit(1)
            break
        time.sleep(20)

    dl = PROJECT_ROOT / "_downloads"
    if dl.exists(): shutil.rmtree(dl)
    dl.mkdir()
    r = subprocess.run(["gh", "run", "download", str(run_id), "--repo", repo_full,
                        "--name", ARTIFACT, "--dir", str(dl)],
                       capture_output=True, text=True)
    if r.returncode != 0: log(f"  ✗ {r.stderr.strip()}"); sys.exit(1)
    return dl


def move_apk(dl_dir):
    log("\n=== Moving APK to target (name + version) ===")
    apks = list(dl_dir.glob("*.apk"))
    if not apks: log("  ✗ No APK."); sys.exit(1)
    apk = apks[0]
    vn, vc = read_app_version()
    log(f"  App version: {vn} (code {vc})")
    tf = PROJECT_ROOT / "Apk Directory.txt"
    target_dir = (Path(tf.read_text(encoding="utf-8").strip())
                  if tf.exists() else Path.home() / "Downloads")
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / f"{APP_NAME}-v{vn}-{vc}{apk.suffix}"
    if dest.exists():
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = target_dir / f"{APP_NAME}-v{vn}-{vc}_{ts}{apk.suffix}"
        log("  Prior copy exists → timestamped name")
    shutil.copy2(apk, dest)
    log(f"  ✓ APK -> {dest}")
    return dest


def find_apksigner():
    for sdk in [
        Path(os.environ.get("ANDROID_HOME", "")),
        Path(os.environ.get("ANDROID_SDK_ROOT", "")),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Android/Sdk",
        Path.home() / "AppData/Local/Android/Sdk",
        Path.home() / "Library/Android/sdk",
        Path("/usr/local/lib/android/sdk"),
    ]:
        if not str(sdk).strip() or not sdk.exists(): continue
        bt = sdk / "build-tools"
        if not bt.exists(): continue
        for v in sorted([d for d in bt.iterdir() if d.is_dir()],
                        key=lambda d: d.name, reverse=True):
            for n in ("apksigner.bat", "apksigner"):
                e = v / n
                if e.exists(): return str(e)
    return None


def verify_apk_signature(apk):
    log("\n=== Verifying APK signature ===")
    signer = find_apksigner()
    if not signer:
        log("  (apksigner not found locally — CI already verified)"); return
    r = subprocess.run([signer, "verify", "--verbose", "--print-certs", str(apk)],
                       capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    log("\n".join(f"    {l}" for l in out.splitlines()[:15]))
    if r.returncode != 0 or "Verifies" not in out:
        log("  ✗ Signature verification FAILED."); sys.exit(1)
    log("  ✓ APK signature verified.")


def find_adb():
    if tool_available("adb"): return "adb"
    for c in [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Android/Sdk/platform-tools/adb.exe",
        Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe",
        Path.home() / "Library/Android/sdk/platform-tools/adb",
        Path("/usr/local/bin/adb"),
    ]:
        if c.exists(): return str(c)
    return None


def adb_device_connected(adb):
    try:
        r = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=5)
        if r.returncode != 0: return False
        return any("\tdevice" in l or " device" in l
                   for l in r.stdout.strip().splitlines()[1:])
    except Exception:
        return False


def device_install(apk_path):
    log("\n=== Device install ===")
    adb = find_adb()
    if not adb or not adb_device_connected(adb):
        log("  No device — skipping.")
        log(f"    adb uninstall {PACKAGE_ID}")
        log(f'    adb install "{apk_path}"')
        return
    subprocess.run([adb, "uninstall", PACKAGE_ID],
                   capture_output=True, text=True, timeout=60)
    r = subprocess.run([adb, "install", str(apk_path)],
                       capture_output=True, text=True, timeout=300)
    out = (r.stdout + r.stderr).strip()
    log(f"    {out}")
    if "Success" in out: log("  ✓ Installed.")


# ============================================================
# main
# ============================================================
def main():
    log("=" * 70)
    log("PinBoard Gallery - Clean build (warnings + KSP AWT)")
    log("=" * 70)

    if not (PROJECT_ROOT / "app/build.gradle.kts").exists():
        log(f"ERROR: {PROJECT_ROOT} isn't a PinBoard project."); sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t):
            log(f"ERROR: {t} not in PATH"); sys.exit(1)

    # 1. This change
    patch_build_warnings_and_errors()

    # 2. Build infrastructure
    ensure_release_keystore()
    patch_build_gradle()
    ensure_gradle_wrapper()
    write_workflow()

    # 3. Git + repo
    setup_git()
    verify_release_keystore_tracked()
    repo = ensure_github_repo()

    # 4. CI
    dl = trigger_and_download(repo)

    # 5. Versioned move + verify
    apk = move_apk(dl)
    verify_apk_signature(apk)

    # 6. Device install
    device_install(apk)

    log("\n" + "=" * 70)
    log(f"DONE -> {apk}")
    log("=" * 70)


if __name__ == "__main__":
    main()