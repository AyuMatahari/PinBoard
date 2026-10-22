#!/usr/bin/env python3
"""
PinBoard Gallery
----------------
CURRENT CHANGE: Restore compat
  * Restore dialog lists every .json in the backup folder
    (except the internal master_pins_archive.json)
  * Compact (old, single-line) AND pretty-printed JSON both restore
  * UTF-8 BOM / stray whitespace tolerated
  * Clear error message if a file isn't a PinBoard backup

FULL PIPELINE (runs every time):
  1. apply restore-compat patch to BackupManager.kt
  2. verify release.keystore + patch app/build.gradle.kts
  3. ensure gradle wrapper + write CI workflow
  4. commit + push to <user>/PinBoard
  5. trigger CI → poll → download app-release artifact
  6. save APK as  PinBoard-v{versionName}-{versionCode}.apk
     into the folder from 'Apk Directory.txt'
  7. verify signature (apksigner) → uninstall+install on device
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
# THIS TASK'S ONLY CODE PATCH — Restore compat
# ============================================================
def patch_backup_restore_compat():
    log("\n=== PATCH: Restore compat (all .json files + compact JSON) ===")
    path = PROJECT_ROOT / "app/src/main/java/com/example/util/BackupManager.kt"
    if not path.exists():
        log(f"  ✗ {path} not found"); sys.exit(1)

    text = path.read_text(encoding="utf-8")
    changed = False

    # (A) getAvailableBackups: list ALL .json, exclude internal master archive
    prev_form = (
        "                dir.listFiles { f ->\n"
        "                    f.isFile && f.extension.equals(\"json\", ignoreCase = true)\n"
        "                }?.let { files.addAll(it) }\n"
    )
    orig_form = (
        "                dir.listFiles { f ->\n"
        "                    f.isFile && f.extension.equals(\"json\", ignoreCase = true) &&\n"
        "                            (f.name.startsWith(\"pinboard_backup_\") || f.name == \"latest_backup.json\")\n"
        "                }?.let { files.addAll(it) }\n"
    )
    new_form = (
        "                dir.listFiles { f ->\n"
        "                    f.isFile && f.extension.equals(\"json\", ignoreCase = true) &&\n"
        "                            f.name != \"master_pins_archive.json\"\n"
        "                }?.let { files.addAll(it) }\n"
    )
    if new_form in text:
        log("  ✓ getAvailableBackups already lists all .json (excl. master archive)")
    elif prev_form in text:
        text = text.replace(prev_form, new_form, 1); changed = True
        log("  ✓ getAvailableBackups: excluding master_pins_archive.json")
    elif orig_form in text:
        text = text.replace(orig_form, new_form, 1); changed = True
        log("  ✓ getAvailableBackups: listing ALL .json")

    # (B) restoreBackup: tolerant parse — compact OR pretty, BOM stripped
    old_parse = (
        "            val jsonStr = backupFile.readText()\n"
        "            val rootJson = JSONObject(jsonStr)\n"
    )
    new_parse = (
        "            // Tolerant: pretty or compact JSON, strips UTF-8 BOM, trims whitespace.\n"
        "            val rawStr = backupFile.readText()\n"
        "            val jsonStr = rawStr.trimStart('\\uFEFF', ' ', '\\t', '\\r', '\\n')\n"
        "            if (jsonStr.isBlank()) {\n"
        "                return@withContext Result.failure(Exception(\"Backup file is empty\"))\n"
        "            }\n"
        "            val rootJson = try {\n"
        "                JSONObject(jsonStr)\n"
        "            } catch (t: Throwable) {\n"
        "                return@withContext Result.failure(\n"
        "                    Exception(\"Not a valid JSON backup: ${t.message ?: t.javaClass.simpleName}\")\n"
        "                )\n"
        "            }\n"
    )
    if new_parse in text:
        log("  ✓ restoreBackup already has tolerant parse")
    elif old_parse in text:
        text = text.replace(old_parse, new_parse, 1); changed = True
        log("  ✓ restoreBackup: BOM strip + safe JSONObject parse")

    # (C) Structure validation — reject non-PinBoard JSON with a clear error
    old_valid = (
        "            var restoredBoardsCount = 0\n"
        "            var restoredPinsCount = 0\n"
        "            var settingsRestored = false\n"
    )
    new_valid = (
        "            val hasBoards = rootJson.has(\"boards\")\n"
        "            val hasPins = rootJson.has(\"pins\")\n"
        "            val hasSettings = rootJson.has(\"settings\")\n"
        "            val hasHistory = rootJson.has(\"board_history\")\n"
        "            if (!hasBoards && !hasPins && !hasSettings && !hasHistory) {\n"
        "                return@withContext Result.failure(\n"
        "                    Exception(\"Not a PinBoard backup (missing boards/pins/settings)\")\n"
        "                )\n"
        "            }\n"
        "\n"
        "            var restoredBoardsCount = 0\n"
        "            var restoredPinsCount = 0\n"
        "            var settingsRestored = false\n"
    )
    if "missing boards/pins/settings" in text:
        log("  ✓ restoreBackup already validates structure")
    elif old_valid in text:
        text = text.replace(old_valid, new_valid, 1); changed = True
        log("  ✓ restoreBackup: added structure validation")

    # (D) Clearer outer failure message
    old_err = (
        "            Result.success(RestoreSummary(restoredBoardsCount, restoredPinsCount, settingsRestored))\n"
        "        } catch (t: Throwable) {\n"
        "            t.printStackTrace()\n"
        "            Result.failure(t)\n"
        "        }\n"
        "    }"
    )
    new_err = (
        "            Result.success(RestoreSummary(restoredBoardsCount, restoredPinsCount, settingsRestored))\n"
        "        } catch (t: Throwable) {\n"
        "            t.printStackTrace()\n"
        "            Result.failure(Exception(\"Restore failed: ${t.message ?: t.javaClass.simpleName}\"))\n"
        "        }\n"
        "    }"
    )
    if "Restore failed: ${t.message" in text:
        log("  ✓ restoreBackup already wraps failures clearly")
    elif old_err in text:
        text = text.replace(old_err, new_err, 1); changed = True
        log("  ✓ restoreBackup: clearer failure message")

    if changed:
        path.write_text(text, encoding="utf-8")
        log("  ✓ BackupManager.kt updated")
    else:
        log("  ✓ Already patched — no changes")


# ============================================================
# Versioned APK naming
# ============================================================
def read_app_version():
    build_path = PROJECT_ROOT / "app/build.gradle.kts"
    if not build_path.exists():
        return ("unknown", "0")
    text = build_path.read_text(encoding="utf-8")
    vn = re.search(r'versionName\s*=\s*"([^"]+)"', text)
    vc = re.search(r"versionCode\s*=\s*(\d+)", text)
    return (
        vn.group(1) if vn else "unknown",
        vc.group(1) if vc else "0",
    )


# ============================================================
# Build infrastructure
# ============================================================
def ensure_release_keystore():
    log("\n=== Ensuring release.keystore ===")
    ks = PROJECT_ROOT / KEYSTORE_FILE
    if ks.exists() and ks.stat().st_size > 0:
        r = subprocess.run(
            ["keytool", "-list", "-keystore", str(ks), "-storepass", KEYSTORE_PASS],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and KEYSTORE_ALIAS in r.stdout:
            log(f"  ✓ {KEYSTORE_FILE} OK (alias '{KEYSTORE_ALIAS}')")
            return
        log(f"  ✗ {KEYSTORE_FILE} exists but password/alias mismatch. Delete and re-run.")
        sys.exit(1)

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
        log(f"  ✗ keytool failed: {r.stderr.strip()}"); sys.exit(1)
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
    if not p.exists():
        log(f"  ✗ {p} not found"); sys.exit(1)

    text = p.read_text(encoding="utf-8")
    orig = text

    marker = 'create("release")'
    idx = text.find(marker)
    if idx == -1:
        log(f"  ✗ {marker} not found"); sys.exit(1)
    span = find_braced_block_at(text, idx)
    if not span:
        log(f"  ✗ could not locate braces for {marker}"); sys.exit(1)
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
                rel_open, rel_close = rel_span
                block = text[rel_open + 1:rel_close]
                if "isDebuggable = true" in block:
                    text = (text[:rel_open + 1]
                            + block.replace("isDebuggable = true", "isDebuggable = false")
                            + text[rel_close:])
                    log("  ✓ release buildType: isDebuggable -> false")
                elif "isDebuggable" not in block:
                    nb = block.replace("isMinifyEnabled = false",
                                       "isMinifyEnabled = false\n      isDebuggable = false", 1)
                    if nb != block:
                        text = text[:rel_open + 1] + nb + text[rel_close:]
                        log("  ✓ release buildType: added isDebuggable = false")

    if text != orig:
        p.write_text(text, encoding="utf-8")


def latest_gradle_version():
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/gradle/gradle/releases/latest",
            headers={"User-Agent": "pinboard-build"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            tag = json.load(resp).get("tag_name", "").lstrip("v")
            if tag: return tag
    except Exception:
        pass
    props = PROJECT_ROOT / "gradle/wrapper/gradle-wrapper.properties"
    if props.exists():
        m = re.search(r"gradle-([\d.]+)-bin\.zip", props.read_text(encoding="utf-8"))
        if m: return m.group(1)
    return "9.3.1"


def ensure_gradle_wrapper():
    log("\n=== Ensuring Gradle wrapper ===")
    gradlew = PROJECT_ROOT / "gradlew"
    gradlew_bat = PROJECT_ROOT / "gradlew.bat"
    wrapper_jar = PROJECT_ROOT / "gradle/wrapper/gradle-wrapper.jar"
    if gradlew.exists() and gradlew_bat.exists() and wrapper_jar.exists():
        log("  ✓ Present."); return
    ver = latest_gradle_version()
    log(f"  Using Gradle v{ver}")
    base = f"https://raw.githubusercontent.com/gradle/gradle/v{ver}"
    for url, dest in [
        (f"{base}/gradlew", gradlew),
        (f"{base}/gradlew.bat", gradlew_bat),
        (f"{base}/gradle/wrapper/gradle-wrapper.jar", wrapper_jar),
    ]:
        if dest.exists() and dest.stat().st_size > 0: continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try: urllib.request.urlretrieve(url, dest)
        except Exception as e:
            log(f"  ✗ {e}"); sys.exit(1)
    try: os.chmod(gradlew, 0o755)
    except Exception: pass


def write_workflow():
    log("\n=== Writing GitHub Actions workflow ===")
    wf_dir = PROJECT_ROOT / ".github/workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "build.yml").write_text(WORKFLOW_YAML, encoding="utf-8")
    log("  ✓ Written.")


# ============================================================
# Git + GitHub
# ============================================================
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
             "Restore compat: list all .json + support compact JSON"])
        log("  ✓ Committed.")


def verify_release_keystore_tracked():
    r = subprocess.run(
        ["git", "ls-files", "--error-unmatch", KEYSTORE_FILE],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    if r.returncode != 0:
        run(["git", "add", "-f", KEYSTORE_FILE])
        run(["git", "commit", "-m", f"Add {KEYSTORE_FILE}"])


def gh_user():
    r = subprocess.run(["gh", "api", "user", "--jq", ".login"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        log("ERROR: gh not authenticated. Run: gh auth login"); sys.exit(1)
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


# ============================================================
# CI trigger + download
# ============================================================
def trigger_and_download(repo_full):
    log("\n=== Triggering CI ===")
    for attempt in range(6):
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


# ============================================================
# Move APK to target with versioned filename
# ============================================================
def move_apk(dl_dir):
    log("\n=== Moving APK to target (name + version) ===")
    apks = list(dl_dir.glob("*.apk"))
    if not apks: log("  ✗ No APK."); sys.exit(1)
    apk = apks[0]

    version_name, version_code = read_app_version()
    log(f"  App version: {version_name} (code {version_code})")

    tf = PROJECT_ROOT / "Apk Directory.txt"
    target_dir = (Path(tf.read_text(encoding="utf-8").strip())
                  if tf.exists() else Path.home() / "Downloads")
    target_dir.mkdir(parents=True, exist_ok=True)

    dest = target_dir / f"{APP_NAME}-v{version_name}-{version_code}{apk.suffix}"
    if dest.exists():
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = target_dir / f"{APP_NAME}-v{version_name}-{version_code}_{ts}{apk.suffix}"
        log("  Prior copy exists → timestamped name")

    shutil.copy2(apk, dest)
    log(f"  ✓ APK -> {dest}")
    return dest


# ============================================================
# Signature + device install
# ============================================================
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
    log("PinBoard Gallery - Restore compat + full build pipeline")
    log("=" * 70)

    if not (PROJECT_ROOT / "app/build.gradle.kts").exists():
        log(f"ERROR: {PROJECT_ROOT} isn't a PinBoard project."); sys.exit(1)
    for t in ("git", "gh", "keytool"):
        if not tool_available(t):
            log(f"ERROR: {t} not found in PATH"); sys.exit(1)

    # ── 1. This task's change ─────────────────────────────────
    patch_backup_restore_compat()

    # ── 2. Build infrastructure ───────────────────────────────
    ensure_release_keystore()
    patch_build_gradle()
    ensure_gradle_wrapper()
    write_workflow()

    # ── 3. Git + GitHub repo ──────────────────────────────────
    setup_git()
    verify_release_keystore_tracked()
    repo = ensure_github_repo()

    # ── 4. CI: trigger → poll → download artifact ─────────────
    dl = trigger_and_download(repo)

    # ── 5. Versioned move + signature verify ──────────────────
    apk = move_apk(dl)                       # PinBoard-v{ver}-{code}.apk
    verify_apk_signature(apk)

    # ── 6. Device install ─────────────────────────────────────
    device_install(apk)

    log("\n" + "=" * 70)
    log(f"DONE -> {apk}")
    log("=" * 70)


if __name__ == "__main__":
    main()