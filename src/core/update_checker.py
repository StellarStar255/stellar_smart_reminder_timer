"""Auto-update: check GitHub Releases and install the new version in one click.

Flow:
  1. UpdateChecker runs in a background thread shortly after startup and
     queries the GitHub Releases "latest" API.
  2. If the release tag is newer than src.version.__version__, it emits
     update_available with the version, release notes and the download URL
     of the asset matching the current platform.
  3. UpdateDialog offers 立即升级: the asset is downloaded to a temp dir
     with progress, then handed to a platform-specific installer step:
       - macOS: helper shell script mounts the DMG, replaces the app in
         /Applications after this process exits, relaunches it.
       - Windows: run the Inno Setup installer silently; it closes the
         running app, installs, and relaunches.
       - Linux: open a terminal-less pkexec dpkg -i, then relaunch.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from src.version import __version__, APP_NAME, GITHUB_REPO

LATEST_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_REQUEST_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": f"{APP_NAME}/{__version__}",
}


def _parse_version(text: str):
    """'v1.2.3' / '1.2.3' -> (1, 2, 3); unparseable parts become 0."""
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def is_newer(remote_tag: str, local_version: str = __version__) -> bool:
    return _parse_version(remote_tag) > _parse_version(local_version)


def platform_asset_suffix() -> str:
    """Filename suffix of the installer asset for this platform."""
    if sys.platform == "darwin":
        return ".dmg"
    if sys.platform == "win32":
        return ".exe"
    return ".deb"


def pick_asset(assets: list) -> dict | None:
    suffix = platform_asset_suffix()
    for asset in assets or []:
        if asset.get("name", "").endswith(suffix):
            return asset
    return None


class UpdateChecker(QThread):
    """Background check for a newer GitHub release."""

    # version, release notes, asset name, asset download url
    update_available = pyqtSignal(str, str, str, str)

    def run(self):
        try:
            req = urllib.request.Request(LATEST_API_URL, headers=_REQUEST_HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                release = json.load(resp)
        except Exception:
            return  # offline / rate-limited / no releases yet — stay silent

        tag = release.get("tag_name", "")
        if release.get("draft") or release.get("prerelease") or not is_newer(tag):
            return
        asset = pick_asset(release.get("assets"))
        if not asset:
            return
        self.update_available.emit(
            tag.lstrip("v"),
            release.get("body") or "",
            asset["name"],
            asset["browser_download_url"],
        )


class UpdateDownloader(QThread):
    """Download the installer asset with progress reporting."""

    progress = pyqtSignal(int)          # 0-100, -1 when size unknown
    finished_ok = pyqtSignal(str)       # downloaded file path
    failed = pyqtSignal(str)

    def __init__(self, url: str, filename: str, parent=None):
        super().__init__(parent)
        self._url = url
        self._filename = filename

    def run(self):
        try:
            target_dir = tempfile.mkdtemp(prefix="stellarpulse_update_")
            target = os.path.join(target_dir, self._filename)
            req = urllib.request.Request(self._url, headers=_REQUEST_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp, \
                    open(target, "wb") as out:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    self.progress.emit(int(done * 100 / total) if total else -1)
            self.finished_ok.emit(target)
        except Exception as exc:
            self.failed.emit(str(exc))


def launch_installer(installer_path: str) -> str | None:
    """Start the platform installer and return None, or an error message.

    The caller should quit the app immediately after a None return —
    every branch finishes the installation while the app is closed and
    then relaunches it.
    """
    if sys.platform == "darwin":
        return _install_macos(installer_path)
    if sys.platform == "win32":
        return _install_windows(installer_path)
    return _install_linux(installer_path)


def _install_macos(dmg_path: str) -> str | None:
    """Mount the DMG and swap the app bundle after this process exits."""
    app_path = _current_mac_app_bundle()
    if not app_path:
        # Running from source — just open the DMG for a manual drag.
        subprocess.Popen(["open", dmg_path])
        return None

    script = f"""#!/bin/bash
# Wait for the app to fully quit before replacing it
sleep 2
MOUNT_DIR=$(hdiutil attach -nobrowse -readonly "{dmg_path}" | tail -1 | cut -f3-)
if [ -z "$MOUNT_DIR" ]; then exit 1; fi
NEW_APP=$(ls -d "$MOUNT_DIR"/*.app | head -1)
if [ -n "$NEW_APP" ]; then
    rm -rf "{app_path}"
    ditto "$NEW_APP" "{app_path}"
fi
hdiutil detach "$MOUNT_DIR" -quiet
rm -f "{dmg_path}"
open "{app_path}"
"""
    helper = os.path.join(os.path.dirname(dmg_path), "install_update.sh")
    with open(helper, "w") as f:
        f.write(script)
    os.chmod(helper, 0o755)
    # Detach fully so the helper survives this process quitting
    subprocess.Popen(["/bin/bash", helper], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return None


def _current_mac_app_bundle() -> str | None:
    """Path of the .app bundle this process runs from, if frozen."""
    if not getattr(sys, "frozen", False):
        return None
    path = sys.executable
    while path and path != "/":
        if path.endswith(".app"):
            return path
        path = os.path.dirname(path)
    return None


def _install_windows(exe_path: str) -> str | None:
    """Run the Inno Setup installer silently; it relaunches the app."""
    try:
        subprocess.Popen(
            [exe_path, "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
            close_fds=True,
        )
        return None
    except Exception as exc:
        return str(exc)


def _install_linux(deb_path: str) -> str | None:
    """Install the deb via pkexec (GUI auth prompt), then relaunch."""
    exe = sys.executable if getattr(sys, "frozen", False) else None
    relaunch = f' && nohup "{exe}" >/dev/null 2>&1 &' if exe else ""
    try:
        subprocess.Popen(
            ["/bin/sh", "-c",
             f'pkexec dpkg -i "{deb_path}"{relaunch}'],
            start_new_session=True,
        )
        return None
    except Exception as exc:
        return str(exc)
