#!/usr/bin/env python3
"""
PinBoard Gallery - Release Build + Deploy (automated)
-----------------------------------------------------
1. Creates stable release.keystore (alias=upload) in project root
2. Patches app/build.gradle.kts so release builds sign with it
3. Ensures Disable Arrow Navigation wiring is present
4. Ensures gradle wrapper + .gitignore entries
5. Writes GitHub Actions workflow that builds & verifies a signed release APK
6. Force-commits release.keystore + workflow, pushes to repo 'PinBoard'
7. Triggers CI, downloads APK, verifies signature, moves to 'Apk Directory'
8. Uninstalls stale package + installs fresh APK on connected device
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
ARTIFACT     = "app-release"
PACKAGE_ID   = "com.aistudio.pinboardgallery.kzwvpt"   # from app/build.gradle.kts

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
          if [ -z "$APK" ]; then
            echo "ERROR: no release APK produced"
            exit 1
          fi
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


# ---------- Keystore helpers ----------
def ensure_release_keystore():
    log("\n=== [1/10] Ensuring release.keystore ===")
    ks = PROJECT_ROOT / KEYSTORE_FILE

    if ks.exists() and ks.stat().st_size > 0:
        r = subprocess.run(
            ["keytool", "-list", "-keystore", str(ks), "-storepass", KEYSTORE_PASS],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and KEYSTORE_ALIAS in r.stdout:
            log(f"  ✓ {KEYSTORE_FILE} exists with alias '{KEYSTORE_ALIAS}'.")
            return
        log(f"  ✗ {KEYSTORE_FILE} exists but alias '{KEYSTORE_ALIAS}' not usable with the chosen password.")
        log(f"    keytool: {r.stderr.strip() or r.stdout.strip()}")
        log(f"    Delete it manually and re-run, or ensure alias '{KEYSTORE_ALIAS}' exists with password.")
        sys.exit(1)

    log(f"  Generating {KEYSTORE_FILE} (alias={KEYSTORE_ALIAS}, validity={KEYSTORE_VALIDITY}d)...")
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
    """Return (open_brace_idx, close_brace_idx) of a balanced {} block starting at/after start."""
    open_brace = text.find("{", start)
    if open_brace == -1:
        return None
    depth = 1
    i = open_brace + 1
    while i < len(text) and depth > 0:
        c = text[i]
        if c == '"':
            i += 1
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == '"':
                    break
                i += 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return (open_brace, i)
        i += 1
    return None


def patch_build_gradle():
    log("\n=== [2/10] Patching app/build.gradle.kts ===")
    p = PROJECT_ROOT / "app/build.gradle.kts"
    if not p.exists():
        log(f"  ✗ {p} not found"); sys.exit(1)

    text = p.read_text(encoding="utf-8")
    orig = text

    # ---- (a) Replace create("release") block contents ----
    marker = 'create("release")'
    idx = text.find(marker)
    if idx == -1:
        log(f"  ✗ {marker} not found in build.gradle.kts"); sys.exit(1)
    span = find_braced_block_at(text, idx)
    if not span:
        log(f"  ✗ could not locate braces for {marker}"); sys.exit(1)
    open_b, close_b = span
    new_contents = (
        f'\n      storeFile = file("${{rootDir}}/{KEYSTORE_FILE}")\n'
        f'      storePassword = "{KEYSTORE_PASS}"\n'
        f'      keyAlias = "{KEYSTORE_ALIAS}"\n'
        f'      keyPassword = "{KEYSTORE_PASS}"\n    '
    )
    text = text[:open_b + 1] + new_contents + text[close_b:]
    log(f'  ✓ create("release") now uses ${{rootDir}}/{KEYSTORE_FILE}')

    # ---- (b) Ensure isDebuggable = false in release buildType ----
    bt_idx = text.find("buildTypes {")
    if bt_idx != -1:
        rel_start = text.find("release {", bt_idx)
        if rel_start != -1:
            rel_span = find_braced_block_at(text, rel_start)
            if rel_span:
                rel_open, rel_close = rel_span
                block = text[rel_open + 1:rel_close]
                if "isDebuggable = true" in block:
                    text = text[:rel_open + 1] + block.replace("isDebuggable = true", "isDebuggable = false") + text[rel_close:]
                    log("  ✓ release buildType: isDebuggable -> false")
                elif "isDebuggable" not in block:
                    block_new = block.replace(
                        "isMinifyEnabled = false",
                        "isMinifyEnabled = false\n      isDebuggable = false",
                        1,
                    )
                    if block_new != block:
                        text = text[:rel_open + 1] + block_new + text[rel_close:]
                        log("  ✓ release buildType: added isDebuggable = false")
                    else:
                        log("  ⚠ could not locate isMinifyEnabled = false in release block")
                else:
                    log("  ✓ release buildType already has isDebuggable = false")

    if text != orig:
        p.write_text(text, encoding="utf-8")
    else:
        log("  No changes needed in app/build.gradle.kts")


# ---------- Arrow-nav fix ----------
def fix_disable_arrow_navigation():
    log("\n=== [3/10] Ensuring Disable Arrow Navigation wiring ===")
    path = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not path.exists():
        log(f"  ✗ {path} not found"); sys.exit(1)

    text = path.read_text(encoding="utf-8")
    if "onToggleDisableArrowNavigation = { viewModel.setDisableArrowNavigation(it) }" in text:
        log("  ✓ Already wired."); return

    old = (
        "        portraitAlbumCards = portraitAlbumCards,\n"
        "        onTogglePortraitAlbumCards = { viewModel.setPortraitAlbumCards(it) },\n"
        "        isBrowserTestingVisible = isBrowserTestingVisible,\n"
    )
    new = (
        "        portraitAlbumCards = portraitAlbumCards,\n"
        "        onTogglePortraitAlbumCards = { viewModel.setPortraitAlbumCards(it) },\n"
        "        disableArrowNavigation = disableArrowNavigation,\n"
        "        onToggleDisableArrowNavigation = { viewModel.setDisableArrowNavigation(it) },\n"
        "        isBrowserTestingVisible = isBrowserTestingVisible,\n"
    )
    if old in text:
        text = text.replace(old, new, 1)
    else:
        m = re.search(
            r"(onTogglePortraitAlbumCards\s*=\s*\{[^}]+\}\s*,\s*\n)(\s*isBrowserTestingVisible\s*=)",
            text,
        )
        if not m:
            log("  ✗ Could not locate SettingsDialog anchor."); sys.exit(1)
        inject = (
            "        disableArrowNavigation = disableArrowNavigation,\n"
            "        onToggleDisableArrowNavigation = { viewModel.setDisableArrowNavigation(it) },\n"
        )
        text = text[:m.end(1)] + inject + text[m.end(1):]

    path.write_text(text, encoding="utf-8")
    log("  ✓ Patched PinBoardGalleryScreen.kt")


# ---------- Gradle wrapper ----------
def latest_gradle_version():
    log("  Fetching latest Gradle release tag…")
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/gradle/gradle/releases/latest",
            headers={"User-Agent": "pinboard-build"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            tag = json.load(resp).get("tag_name", "").lstrip("v")
            if tag: return tag
    except Exception as e:
        log(f"  WARN: {e}")
    props = PROJECT_ROOT / "gradle/wrapper/gradle-wrapper.properties"
    if props.exists():
        m = re.search(r"gradle-([\d.]+)-bin\.zip", props.read_text(encoding="utf-8"))
        if m: return m.group(1)
    return "9.3.1"


def ensure_gradle_wrapper():
    log("\n=== [4/10] Ensuring Gradle wrapper files ===")
    gradlew     = PROJECT_ROOT / "gradlew"
    gradlew_bat = PROJECT_ROOT / "gradlew.bat"
    wrapper_jar = PROJECT_ROOT / "gradle/wrapper/gradle-wrapper.jar"

    if gradlew.exists() and gradlew_bat.exists() and wrapper_jar.exists():
        log("  ✓ All wrapper files already present."); return

    ver = latest_gradle_version()
    log(f"  Using Gradle v{ver}")
    base = f"https://raw.githubusercontent.com/gradle/gradle/v{ver}"
    for url, dest in [
        (f"{base}/gradlew", gradlew),
        (f"{base}/gradlew.bat", gradlew_bat),
        (f"{base}/gradle/wrapper/gradle-wrapper.jar", wrapper_jar),
    ]:
        if dest.exists() and dest.stat().st_size > 0:
            log(f"  {dest.name} exists, skip."); continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        log(f"  Downloading {dest.name}")
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as e:
            log(f"  ✗ {e}"); sys.exit(1)
    try: os.chmod(gradlew, 0o755)
    except Exception: pass
    log("  ✓ Gradle wrapper ready.")


# ---------- Workflow ----------
def write_workflow():
    log("\n=== [5/10] Writing GitHub Actions workflow ===")
    wf_dir = PROJECT_ROOT / ".github/workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "build.yml").write_text(WORKFLOW_YAML, encoding="utf-8")
    log("  ✓ Wrote .github/workflows/build.yml")


# ---------- Git ----------
def setup_git():
    log("\n=== [6/10] Setting up git repo ===")
    if not (PROJECT_ROOT / ".git").exists():
        run(["git", "init"]); run(["git", "branch", "-M", "main"])
        log("  Initialized repo.")
    else:
        log("  Repo already exists.")

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
        if line not in merged:
            merged.append(line)
    gi.write_text("\n".join(merged) + "\n", encoding="utf-8")
    log("  ✓ .gitignore has '!release.keystore' / '!debug.keystore' exceptions")

    run(["git", "add", "-A"])

    # Force-add both keystores if present (ignore gitignore)
    for name in (KEYSTORE_FILE, "debug.keystore"):
        f = PROJECT_ROOT / name
        if f.exists():
            run(["git", "add", "-f", name], check=False)
            log(f"  Force-added {name}")

    if subprocess.run(["git", "status", "--porcelain"],
                      capture_output=True, text=True).stdout.strip():
        run(["git", "commit", "-m",
             "Release signing: stable release.keystore + assembleRelease workflow"])
        log("  ✓ Committed.")
    else:
        log("  Nothing to commit.")


def verify_release_keystore_tracked():
    log("\n=== [7/10] Verifying release.keystore is tracked ===")
    r = subprocess.run(
        ["git", "ls-files", "--error-unmatch", KEYSTORE_FILE],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    if r.returncode == 0:
        log("  ✓ release.keystore is tracked in git.")
        return
    log(f"  ✗ {KEYSTORE_FILE} not tracked — force-adding + committing…")
    run(["git", "add", "-f", KEYSTORE_FILE])
    run(["git", "commit", "-m", f"Add {KEYSTORE_FILE} for stable release signing"])
    r2 = subprocess.run(
        ["git", "ls-files", "--error-unmatch", KEYSTORE_FILE],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    if r2.returncode != 0:
        log("  ✗ Still not tracked. Aborting."); sys.exit(1)
    log("  ✓ Now tracked.")


# ---------- GitHub ----------
def gh_user():
    r = subprocess.run(["gh", "api", "user", "--jq", ".login"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        log("ERROR: gh not authenticated. Run: gh auth login"); sys.exit(1)
    return r.stdout.strip()


def ensure_github_repo():
    log("\n=== [8/10] Ensuring GitHub repository ===")
    user = gh_user(); full = f"{user}/{REPO_NAME}"
    log(f"  User: {user}")

    if subprocess.run(["gh", "repo", "view", full], capture_output=True).returncode == 0:
        log(f"  ✓ {full} exists.")
    else:
        log(f"  Creating {full}…")
        r = subprocess.run(
            ["gh", "repo", "create", REPO_NAME, "--public",
             "--source", ".", "--remote", "origin", "--push"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            log(f"  create rc={r.returncode}: {r.stderr.strip()}")
            if subprocess.run(["gh", "repo", "view", full], capture_output=True).returncode != 0:
                sys.exit(1)

    if subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True).returncode != 0:
        run(["git", "remote", "add", "origin", f"https://github.com/{full}.git"])

    log("  Pushing…")
    r = subprocess.run(["git", "push", "-u", "origin", "main"], capture_output=True, text=True)
    if r.returncode != 0:
        log(f"  push: {r.stderr.strip()}")
        r2 = subprocess.run(["git", "push", "-u", "origin", "main", "--force"],
                            capture_output=True, text=True)
        if r2.returncode != 0:
            log(f"  ✗ {r2.stderr.strip()}"); sys.exit(1)
    return full


# ---------- CI ----------
def trigger_and_download(repo_full):
    log("\n=== [9/10] Triggering GitHub Actions build ===")
    for attempt in range(6):
        r = subprocess.run(
            ["gh", "workflow", "run", "build.yml", "--ref", "main", "--repo", repo_full],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            log("  ✓ Workflow dispatched."); break
        log(f"  Retry {attempt+1}/5 (workflow not registered yet)…")
        time.sleep(10)
    else:
        log(f"  ✗ {r.stderr.strip()}"); sys.exit(1)

    time.sleep(10)
    run_id = None
    for _ in range(20):
        r = subprocess.run(
            ["gh", "run", "list", "--repo", repo_full,
             "--workflow", "build.yml", "--limit", "1",
             "--json", "databaseId,status"],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and r.stdout.strip():
            try:
                runs = json.loads(r.stdout)
                if runs:
                    run_id = runs[0]["databaseId"]; break
            except json.JSONDecodeError:
                pass
        time.sleep(5)

    if run_id is None:
        log("  ✗ No run found."); sys.exit(1)
    log(f"  Run #{run_id}. Waiting…")

    while True:
        r = subprocess.run(
            ["gh", "run", "view", str(run_id), "--repo", repo_full,
             "--json", "status,conclusion"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            time.sleep(15); continue
        try: info = json.loads(r.stdout)
        except json.JSONDecodeError: time.sleep(15); continue
        st, cc = info.get("status", ""), info.get("conclusion", "")
        log(f"  status={st} conclusion={cc}")
        if st == "completed":
            if cc != "success":
                log(f"  ✗ Build failed: {cc}")
                subprocess.run(["gh", "run", "view", str(run_id),
                                "--repo", repo_full, "--log-failed"], check=False)
                sys.exit(1)
            break
        time.sleep(20)

    log("  Downloading APK…")
    dl = PROJECT_ROOT / "_downloads"
    if dl.exists(): shutil.rmtree(dl)
    dl.mkdir()
    r = subprocess.run(
        ["gh", "run", "download", str(run_id), "--repo", repo_full,
         "--name", ARTIFACT, "--dir", str(dl)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        log(f"  ✗ {r.stderr.strip()}"); sys.exit(1)
    return dl


# ---------- APK helpers ----------
def find_apksigner():
    sdk_dirs = [
        Path(os.environ.get("ANDROID_HOME", "")),
        Path(os.environ.get("ANDROID_SDK_ROOT", "")),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Android/Sdk",
        Path.home() / "AppData/Local/Android/Sdk",
        Path.home() / "Library/Android/sdk",
        Path("/usr/local/lib/android/sdk"),
    ]
    for sdk in sdk_dirs:
        if not str(sdk).strip() or not sdk.exists(): continue
        bt = sdk / "build-tools"
        if not bt.exists(): continue
        versions = sorted([d for d in bt.iterdir() if d.is_dir()],
                          key=lambda d: d.name, reverse=True)
        for v in versions:
            for name in ("apksigner.bat", "apksigner"):
                exe = v / name
                if exe.exists():
                    return str(exe)
    return None


def verify_apk_signature(apk_path):
    log("\n=== [10a/10] Verifying downloaded APK signature ===")
    signer = find_apksigner()
    if not signer:
        log("  apksigner not found locally — skipping local verification (CI already verified).")
        return
    log(f"  apksigner: {signer}")
    r = subprocess.run(
        [signer, "verify", "--verbose", "--print-certs", str(apk_path)],
        capture_output=True, text=True,
    )
    out = (r.stdout + r.stderr).strip()
    log("\n".join(f"    {line}" for line in out.splitlines()[:15]))
    if r.returncode != 0 or "Verifies" not in out:
        log("  ✗ Signature verification FAILED — do not install this APK."); sys.exit(1)
    if "CN=PinBoard Gallery" not in out:
        log("  ⚠ Signer CN is not 'PinBoard Gallery' — unexpected cert, check build.gradle.kts.")
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
        for line in r.stdout.strip().splitlines()[1:]:
            if "\tdevice" in line or " device" in line:
                return True
    except Exception:
        pass
    return False


def move_apk(dl_dir):
    log("\n=== [10b/10] Moving APK to target ===")
    apks = list(dl_dir.glob("*.apk"))
    if not apks:
        log("  ✗ No APK in artifact."); sys.exit(1)
    apk = apks[0]

    target_file = PROJECT_ROOT / "Apk Directory.txt"
    if target_file.exists():
        target_dir = Path(target_file.read_text(encoding="utf-8").strip())
    else:
        target_dir = Path.home() / "Downloads"
        log("  WARN: 'Apk Directory.txt' missing, using Downloads.")

    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / apk.name
    if dest.exists():
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = target_dir / f"{apk.stem}_{ts}{apk.suffix}"
    shutil.copy2(apk, dest)
    log(f"  ✓ APK -> {dest}")
    return dest


def device_install(apk_path):
    log("\n=== [10c/10] Installing on connected device ===")
    adb = find_adb()
    if not adb or not adb_device_connected(adb):
        log("  No device / adb — skipping auto-install.")
        log(f"  Manual install:")
        log(f"    adb uninstall {PACKAGE_ID}")
        log(f'    adb install "{apk_path}"')
        return
    log(f"  adb: {adb}")

    log(f"  Uninstalling {PACKAGE_ID} (clears any signature conflict)…")
    r = subprocess.run([adb, "uninstall", PACKAGE_ID], capture_output=True, text=True, timeout=60)
    log(f"    {(r.stdout + r.stderr).strip()}")

    log(f"  Installing {apk_path.name}…")
    r = subprocess.run([adb, "install", str(apk_path)], capture_output=True, text=True, timeout=300)
    out = (r.stdout + r.stderr).strip()
    log(f"    {out}")
    if "Success" in out:
        log("  ✓ Installed.")
    else:
        log("  ✗ Install failed — see message above.")


# ---------- main ----------
def main():
    log("=" * 70)
    log("PinBoard Gallery - Release Build + Deploy")
    log("=" * 70)

    if not (PROJECT_ROOT / "app/build.gradle.kts").exists():
        log(f"ERROR: {PROJECT_ROOT} isn't a PinBoard project."); sys.exit(1)
    if not tool_available("git"):
        log("ERROR: git not in PATH"); sys.exit(1)
    if not tool_available("gh"):
        log("ERROR: gh not in PATH"); sys.exit(1)
    if not tool_available("keytool"):
        log("ERROR: keytool not in PATH (install a JDK)"); sys.exit(1)

    ensure_release_keystore()
    patch_build_gradle()
    fix_disable_arrow_navigation()
    ensure_gradle_wrapper()
    write_workflow()
    setup_git()
    verify_release_keystore_tracked()
    repo = ensure_github_repo()
    dl   = trigger_and_download(repo)
    apk  = move_apk(dl)
    verify_apk_signature(apk)
    device_install(apk)

    log("\n" + "=" * 70)
    log(f"DONE -> {apk}")
    log("=" * 70)


if __name__ == "__main__":
    main()