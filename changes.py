#!/usr/bin/env python3
"""
PinBoard Gallery - Fix + Build + Deploy Script (self-contained)
---------------------------------------------------------------
1. Fixes Disable Arrow Navigation toggle wiring in SettingsDialog call
2. Ensures gradlew / gradlew.bat / gradle-wrapper.jar exist
3. Ensures debug.keystore exists (generates if missing)
4. Writes GitHub Actions workflow (with tools-package fix)
5. Pushes to GitHub (repo: PinBoard)
6. Triggers CI build, downloads APK
7. Moves APK into directory from 'Apk Directory.txt'
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
ARTIFACT     = "app-debug"

# FIX: pass packages: '' so sdkmanager does not try to install the removed 'tools' package.
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
        run: |
          yes | sdkmanager --licenses >/dev/null 2>&1 || true

      - name: Install Android SDK components
        run: |
          sdkmanager --install "platforms;android-36" "build-tools;36.0.0" >/dev/null 2>&1 || true

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v3
        with:
          gradle-version: wrapper

      - name: Make gradlew executable
        run: chmod +x ./gradlew

      - name: Build Debug APK
        run: ./gradlew :app:assembleDebug --stacktrace --no-daemon

      - name: Upload APK
        uses: actions/upload-artifact@v4
        with:
          name: app-debug
          path: app/build/outputs/apk/debug/*.apk
          if-no-files-found: error
"""


def log(msg):
    print(msg, flush=True)


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
        subprocess.run([name, "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


# ---------- 1. Fix the toggle wiring ----------
def fix_disable_arrow_navigation():
    log("\n=== [1/8] Fixing Disable Arrow Navigation toggle ===")
    path = PROJECT_ROOT / "app/src/main/java/com/example/ui/PinBoardGalleryScreen.kt"
    if not path.exists():
        log(f"ERROR: {path} not found"); sys.exit(1)

    text = path.read_text(encoding="utf-8")

    if "onToggleDisableArrowNavigation = { viewModel.setDisableArrowNavigation(it) }" in text:
        log("  Already fixed. Skipping."); return

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
            log("ERROR: Could not locate SettingsDialog anchor."); sys.exit(1)
        inject = (
            "        disableArrowNavigation = disableArrowNavigation,\n"
            "        onToggleDisableArrowNavigation = { viewModel.setDisableArrowNavigation(it) },\n"
        )
        text = text[:m.end(1)] + inject + text[m.end(1):]

    path.write_text(text, encoding="utf-8")
    log("  Patched PinBoardGalleryScreen.kt.")


# ---------- 2. Gradle wrapper ----------
def latest_gradle_version():
    log("  Fetching latest Gradle release tag...")
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
    log("\n=== [2/8] Ensuring Gradle wrapper files ===")
    gradlew     = PROJECT_ROOT / "gradlew"
    gradlew_bat = PROJECT_ROOT / "gradlew.bat"
    wrapper_jar = PROJECT_ROOT / "gradle/wrapper/gradle-wrapper.jar"

    if gradlew.exists() and gradlew_bat.exists() and wrapper_jar.exists():
        log("  All wrapper files already present."); return

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
            log(f"  ERROR: {e}"); sys.exit(1)

    try: os.chmod(gradlew, 0o755)
    except Exception: pass
    log("  Gradle wrapper ready.")


# ---------- 3. debug.keystore ----------
def ensure_debug_keystore():
    log("\n=== [3/8] Ensuring debug.keystore ===")
    ks = PROJECT_ROOT / "debug.keystore"
    if ks.exists():
        log("  debug.keystore exists."); return
    log("  Generating debug.keystore...")
    try:
        subprocess.run([
            "keytool", "-genkeypair", "-v",
            "-keystore", str(ks),
            "-alias", "androiddebugkey",
            "-keyalg", "RSA", "-keysize", "2048",
            "-validity", "10000",
            "-storepass", "android", "-keypass", "android",
            "-dname", "CN=Android Debug,O=Android,C=US",
        ], check=True, capture_output=True, text=True)
    except Exception as e:
        log(f"  ERROR: {e}"); sys.exit(1)
    log("  Generated.")


# ---------- 4. Workflow ----------
def write_workflow():
    log("\n=== [4/8] Writing GitHub Actions workflow ===")
    wf_dir = PROJECT_ROOT / ".github/workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "build.yml").write_text(WORKFLOW_YAML, encoding="utf-8")
    log("  Wrote .github/workflows/build.yml")


# ---------- 5. Local git ----------
def setup_git():
    log("\n=== [5/8] Setting up git repo ===")
    if not (PROJECT_ROOT / ".git").exists():
        run(["git", "init"])
        run(["git", "branch", "-M", "main"])
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
    if not gi.exists():
        gi.write_text(
            "build/\n*/build/\n.gradle/\nlocal.properties\n*.iml\n.idea/\n.cxx/\n.DS_Store\n"
            ".kotlin/\n.env\n_downloads/\n"
            "*.jks\n*.keystore\n!debug.keystore\n",
            encoding="utf-8",
        )
        log("  Created .gitignore")

    if subprocess.run(["git", "status", "--porcelain"],
                      capture_output=True, text=True).stdout.strip():
        run(["git", "add", "-A"])
        run(["git", "commit", "-m",
             "Fix Disable Arrow Navigation toggle wiring + CI build"])
        log("  Committed.")
    else:
        log("  Nothing to commit.")


# ---------- 6. GitHub repo ----------
def gh_user():
    r = subprocess.run(["gh", "api", "user", "--jq", ".login"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        log("ERROR: gh not authenticated. Run: gh auth login"); sys.exit(1)
    return r.stdout.strip()


def ensure_github_repo():
    log("\n=== [6/8] Ensuring GitHub repository ===")
    user = gh_user()
    full = f"{user}/{REPO_NAME}"
    log(f"  User: {user}")

    if subprocess.run(["gh", "repo", "view", full],
                      capture_output=True).returncode == 0:
        log(f"  {full} already exists.")
    else:
        log(f"  Creating {full}...")
        r = subprocess.run(
            ["gh", "repo", "create", REPO_NAME, "--public",
             "--source", ".", "--remote", "origin", "--push"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            log(f"  create rc={r.returncode}: {r.stderr.strip()}")
            if subprocess.run(["gh", "repo", "view", full],
                              capture_output=True).returncode != 0:
                sys.exit(1)
        else:
            log("  Created and pushed.")

    if subprocess.run(["git", "remote", "get-url", "origin"],
                      capture_output=True).returncode != 0:
        run(["git", "remote", "add", "origin", f"https://github.com/{full}.git"])

    log("  Pushing latest commits...")
    r = subprocess.run(["git", "push", "-u", "origin", "main"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        log(f"  push: {r.stderr.strip()}")
        r2 = subprocess.run(["git", "push", "-u", "origin", "main", "--force"],
                            capture_output=True, text=True)
        if r2.returncode != 0:
            log(f"  ERROR: {r2.stderr.strip()}"); sys.exit(1)
    return full


# ---------- 7. Trigger workflow + download ----------
def trigger_and_download(repo_full):
    log("\n=== [7/8] Triggering GitHub Actions build ===")
    for attempt in range(6):
        r = subprocess.run(
            ["gh", "workflow", "run", "build.yml", "--ref", "main", "--repo", repo_full],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            log("  Workflow dispatched."); break
        log(f"  Retry {attempt+1}/5 (workflow not registered yet)...")
        time.sleep(10)
    else:
        log(f"  ERROR: {r.stderr.strip()}"); sys.exit(1)

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
        log("  ERROR: No run found."); sys.exit(1)
    log(f"  Run #{run_id}. Waiting...")

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
                log(f"  Build failed: {cc}")
                subprocess.run(["gh", "run", "view", str(run_id),
                                "--repo", repo_full, "--log-failed"], check=False)
                sys.exit(1)
            break
        time.sleep(20)

    log("  Downloading APK...")
    dl = PROJECT_ROOT / "_downloads"
    if dl.exists(): shutil.rmtree(dl)
    dl.mkdir()
    r = subprocess.run(
        ["gh", "run", "download", str(run_id), "--repo", repo_full,
         "--name", ARTIFACT, "--dir", str(dl)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        log(f"  ERROR: {r.stderr.strip()}"); sys.exit(1)
    return dl


# ---------- 8. Move APK ----------
def move_apk(dl_dir):
    log("\n=== [8/8] Moving APK to target ===")
    apks = list(dl_dir.glob("*.apk"))
    if not apks:
        log("  ERROR: No APK in artifact."); sys.exit(1)
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
    log(f"  APK -> {dest}")
    return dest


# ---------- main ----------
def main():
    log("=" * 70)
    log("PinBoard Gallery - Fix + Build + Deploy")
    log("=" * 70)

    if not (PROJECT_ROOT / "app/build.gradle.kts").exists():
        log(f"ERROR: {PROJECT_ROOT} isn't a PinBoard project."); sys.exit(1)
    if not tool_available("git"):
        log("ERROR: git not in PATH"); sys.exit(1)
    if not tool_available("gh"):
        log("ERROR: gh not in PATH"); sys.exit(1)

    fix_disable_arrow_navigation()
    ensure_gradle_wrapper()
    ensure_debug_keystore()
    write_workflow()
    setup_git()
    repo = ensure_github_repo()
    dl   = trigger_and_download(repo)
    dest = move_apk(dl)

    log("\n" + "=" * 70)
    log(f"DONE -> {dest}")
    log("=" * 70)


if __name__ == "__main__":
    main()