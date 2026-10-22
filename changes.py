#!/usr/bin/env python3
"""
PinBoard Gallery
----------------
CURRENT CHANGE: Restore sees backups from previous installs
  * Manifest gains MANAGE_EXTERNAL_STORAGE (+ READ_EXTERNAL_STORAGE for API 29-32)
  * BackupManager gets hasAllFilesAccess() + requestAllFilesAccess()
  * Restore dialog shows a "Grant All Files Access" banner when the
    permission is missing; auto-refreshes the file list on ON_RESUME

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

WORKFLOW_YAML = """\
name: Build APK

on:
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
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
def patch_restore_all_files_access():
    log("\n=== PATCH: Restore sees backups from previous installs (All Files Access) ===")

    # ---------- 1. AndroidManifest.xml ----------
    manifest = PROJECT_ROOT / "app/src/main/AndroidManifest.xml"
    if not manifest.exists(): log(f"  ✗ {manifest} not found"); sys.exit(1)
    m = manifest.read_text(encoding="utf-8")
    if "MANAGE_EXTERNAL_STORAGE" not in m:
        anchor = '    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />\n'
        if anchor not in m:
            log("  ✗ manifest anchor not found"); sys.exit(1)
        m = m.replace(
            anchor,
            anchor +
            '\n'
            '    <!-- Android 11+ scoped storage: File.listFiles() on shared Download/ only\n'
            '         sees files created by the CURRENT install. This permission lets the\n'
            '         Restore dialog see every .json in Download/PinterestViewerDownloads/Backup,\n'
            '         including backups written by PREVIOUS installations. User grants\n'
            '         via Settings -> Special app access -> All files access. -->\n'
            '    <uses-permission android:name="android.permission.MANAGE_EXTERNAL_STORAGE" />\n'
            '    <uses-permission\n'
            '        android:name="android.permission.READ_EXTERNAL_STORAGE"\n'
            '        android:maxSdkVersion="32" />\n',
            1,
        )
        manifest.write_text(m, encoding="utf-8")
        log("  ✓ manifest: MANAGE_EXTERNAL_STORAGE + READ_EXTERNAL_STORAGE")
    else:
        log("  ✓ manifest: permission already present")

    # ---------- 2. BackupManager helpers ----------
    bm = PROJECT_ROOT / "app/src/main/java/com/example/util/BackupManager.kt"
    if not bm.exists(): log(f"  ✗ {bm} not found"); sys.exit(1)
    b = bm.read_text(encoding="utf-8")
    b_changed = False

    if "fun hasAllFilesAccess()" not in b:
        # Ensure imports are present
        imp_pairs = [
            ("import android.content.Intent\n",     "import android.content.Context\n"),
            ("import android.net.Uri\n",            "import android.content.Intent\n"),
            ("import android.os.Build\n",           "import android.net.Uri\n"),
            ("import android.provider.Settings\n",  "import android.os.Build\n"),
        ]
        for imp, after in imp_pairs:
            if imp in b: continue
            if after in b:
                b = b.replace(after, after + imp, 1)
            else:
                b = b.replace("\nobject BackupManager", "\n" + imp + "object BackupManager", 1)

        anchor = "    fun isBackupEnabled(context: Context): Boolean {\n"
        if anchor not in b:
            log("  ✗ BackupManager isBackupEnabled anchor not found"); sys.exit(1)
        helpers = (
            "    /**\n"
            "     * True when this app can read arbitrary files under shared Download/.\n"
            "     * On Android 11+ this needs MANAGE_EXTERNAL_STORAGE, granted via\n"
            "     * Settings -> Special app access -> All files access. Without it the\n"
            "     * File API returns only files created by THIS installation, which is\n"
            "     * why backups from previous installs disappear from the Restore list.\n"
            "     */\n"
            "    fun hasAllFilesAccess(): Boolean =\n"
            "        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) true\n"
            "        else try { Environment.isExternalStorageManager() } catch (_: Throwable) { false }\n"
            "\n"
            "    /** Opens the system All-files-access screen for this app. */\n"
            "    fun requestAllFilesAccess(context: Context) {\n"
            "        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return\n"
            "        try {\n"
            "            val intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION).apply {\n"
            "                data = Uri.parse(\"package:\" + context.packageName)\n"
            "            }\n"
            "            context.startActivity(intent)\n"
            "            return\n"
            "        } catch (_: Throwable) {}\n"
            "        try { context.startActivity(Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)) } catch (_: Throwable) {}\n"
            "    }\n"
            "\n"
        )
        b = b.replace(anchor, helpers + anchor, 1)
        b_changed = True
        log("  ✓ BackupManager: hasAllFilesAccess() + requestAllFilesAccess()")

    if b_changed:
        bm.write_text(b, encoding="utf-8")

    # ---------- 3. SettingsDialog: banner + auto-refresh on resume ----------
    sd = PROJECT_ROOT / "app/src/main/java/com/example/ui/components/SettingsDialog.kt"
    if not sd.exists(): log(f"  ✗ {sd} not found"); sys.exit(1)
    s = sd.read_text(encoding="utf-8")

    if "backup_all_files_access_btn" in s:
        log("  ✓ SettingsDialog: banner already present")
        return

    anchor = (
        '                        Text(\n'
        '                            "Select a backup from /Download/PinterestViewerDownloads/Backup to restore:",\n'
        '                            fontSize = 12.sp,\n'
        '                            color = PinterestTextSecondary\n'
        '                        )\n'
        '                        Spacer(modifier = Modifier.height(10.dp))\n'
    )
    if anchor not in s:
        log("  ✗ SettingsDialog restore-dialog anchor not found"); sys.exit(1)

    injection = (
        '                        Text(\n'
        '                            "Select a backup from /Download/PinterestViewerDownloads/Backup to restore:",\n'
        '                            fontSize = 12.sp,\n'
        '                            color = PinterestTextSecondary\n'
        '                        )\n'
        '                        Spacer(modifier = Modifier.height(10.dp))\n'
        '\n'
        '                        // Android 11+ needs All Files Access so backups written by\n'
        '                        // previous installs in Download/… become visible here.\n'
        '                        if (!com.example.util.BackupManager.hasAllFilesAccess()) {\n'
        '                            androidx.compose.material3.Surface(\n'
        '                                shape = RoundedCornerShape(12.dp),\n'
        '                                color = PinterestPillGray,\n'
        '                                modifier = Modifier.fillMaxWidth()\n'
        '                            ) {\n'
        '                                Column(modifier = Modifier.padding(10.dp)) {\n'
        '                                    Text(\n'
        '                                        text = "All Files Access is needed to see every .json in the backup folder, including backups from previous app installs.",\n'
        '                                        fontSize = 11.sp,\n'
        '                                        color = PinterestBlack,\n'
        '                                        fontWeight = FontWeight.SemiBold\n'
        '                                    )\n'
        '                                    Spacer(modifier = Modifier.height(6.dp))\n'
        '                                    androidx.compose.material3.Button(\n'
        '                                        onClick = {\n'
        '                                            com.example.util.BackupManager.requestAllFilesAccess(context)\n'
        '                                        },\n'
        '                                        colors = ButtonDefaults.buttonColors(containerColor = PinterestRed),\n'
        '                                        shape = RoundedCornerShape(14.dp),\n'
        '                                        contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 12.dp, vertical = 4.dp),\n'
        '                                        modifier = Modifier.testTag("backup_all_files_access_btn")\n'
        '                                    ) {\n'
        '                                        Text("Grant All Files Access", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold)\n'
        '                                    }\n'
        '                                }\n'
        '                            }\n'
        '                            Spacer(modifier = Modifier.height(10.dp))\n'
        '                        }\n'
        '\n'
        '                        // Refresh the list when the app resumes (i.e. after the\n'
        '                        // user toggles All Files Access in system Settings).\n'
        '                        val backupLifecycleOwner = androidx.lifecycle.compose.LocalLifecycleOwner.current\n'
        '                        DisposableEffect(backupLifecycleOwner, showRestoreDialog) {\n'
        '                            val obs = androidx.lifecycle.LifecycleEventObserver { _, event ->\n'
        '                                if (event == androidx.lifecycle.Lifecycle.Event.ON_RESUME && showRestoreDialog) {\n'
        '                                    val refreshed = com.example.util.BackupManager.getAvailableBackups(context)\n'
        '                                    if (refreshed.isNotEmpty()) {\n'
        '                                        availableBackups = refreshed\n'
        '                                        if (selectedBackupFile == null ||\n'
        '                                            refreshed.none { it.absolutePath == selectedBackupFile?.absolutePath }\n'
        '                                        ) {\n'
        '                                            selectedBackupFile = refreshed.firstOrNull()\n'
        '                                        }\n'
        '                                    }\n'
        '                                }\n'
        '                            }\n'
        '                            backupLifecycleOwner.lifecycle.addObserver(obs)\n'
        '                            onDispose { backupLifecycleOwner.lifecycle.removeObserver(obs) }\n'
        '                        }\n'
    )
    s = s.replace(anchor, injection, 1)
    sd.write_text(s, encoding="utf-8")
    log("  ✓ SettingsDialog: banner + auto-refresh on resume")
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
    log("  ✓ Written.")


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
             "Restore: All Files Access so previous-install backups appear"])
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
    log("PinBoard Gallery - Restore sees previous-install backups")
    log("=" * 70)

    if not (PROJECT_ROOT / "app/build.gradle.kts").exists():
        log(f"ERROR: {PROJECT_ROOT} isn't a PinBoard project."); sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t):
            log(f"ERROR: {t} not in PATH"); sys.exit(1)

    # 1. This change
    patch_restore_all_files_access()

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