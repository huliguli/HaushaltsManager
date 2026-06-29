"""Self-update via the GitHub Releases API.

On start the app asks GitHub for the latest release; if it is newer than the
running version a non-blocking dialog offers to download and install it. The
install mirrors the proven pattern from the sibling SFC tool: download the new
executable, write a tiny batch script that waits for this process to exit,
swaps the file and relaunches.

Safety rules:
    * Every network call is wrapped — no internet means the check simply yields
      ``None`` and the app starts normally.
    * Downloads are accepted only over HTTPS from github.com hosts.
    * The self-replace step only runs in a frozen (PyInstaller) build; in a dev
      run the updater just reports availability.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

from PyQt6.QtCore import QThread, pyqtSignal

from app_meta import is_frozen
from modules.logging_setup import get_logger

_log = get_logger("updater")

_API = "https://api.github.com/repos/{repo}/releases/latest"
_USER_AGENT = "HaushaltsManager-Updater"
_ALLOWED_HOSTS = ("github.com", "objects.githubusercontent.com", "githubusercontent.com")
# Sanity ceiling so a malicious/compromised release cannot fill the disk.
_MAX_UPDATE_BYTES = 300 * 1024 * 1024


class _Cancelled(Exception):
    """Internal signal that a download was cancelled cooperatively."""


def _safe_remove(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


@dataclass
class UpdateInfo:
    version: str            # tag without leading "v"
    tag: str
    notes: str              # release body / changelog
    asset_url: str          # browser_download_url of the .exe asset
    html_url: str           # release page (fallback link)
    hash_url: str = ""      # browser_download_url of the .sha256 asset (optional)


def parse_version(text: str) -> tuple[int, ...]:
    """Turn '1.2.3' or 'v1.2.3' into a comparable integer tuple."""
    cleaned = re.sub(r"[^0-9.]", "", (text or "").lstrip("vV"))
    parts = [int(p) for p in cleaned.split(".") if p != ""]
    return tuple(parts) or (0,)


def is_newer(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def _https_github(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = parsed.hostname or ""
    return parsed.scheme == "https" and any(
        host == h or host.endswith("." + h) for h in _ALLOWED_HOSTS)


def check_for_update(repo: str, current_version: str) -> UpdateInfo | None:
    """Query the latest release. Returns UpdateInfo if newer, else None.

    Never raises: any error (offline, rate limit, parse) yields None.
    """
    url = _API.format(repo=repo)
    if not _https_github(url):
        return None
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json"})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - offline is normal, not an error
        _log.info("Update-Prüfung übersprungen: %s", exc)
        return None

    tag = data.get("tag_name") or ""
    if not tag or not is_newer(tag, current_version):
        return None

    asset_url = ""
    hash_url = ""
    for asset in data.get("assets", []):
        name = (asset.get("name") or "").lower()
        if name.endswith(".sha256"):
            hash_url = asset.get("browser_download_url", "")
        elif name.endswith(".exe") and not asset_url:
            asset_url = asset.get("browser_download_url", "")

    return UpdateInfo(
        version=tag.lstrip("vV"),
        tag=tag,
        notes=data.get("body") or "Keine Änderungshinweise vorhanden.",
        asset_url=asset_url,
        html_url=data.get("html_url") or f"https://github.com/{repo}/releases/latest",
        hash_url=hash_url,
    )


def _parse_sha256(text: str) -> str | None:
    """Extract the first 64-hex SHA-256 digest from a checksum file's text."""
    match = re.search(r"[0-9a-fA-F]{64}", text or "")
    return match.group(0).lower() if match else None


def sha256_of_file(path: str) -> str:
    """Streaming SHA-256 of a file (lower-case hex)."""
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_checksum(hash_url: str) -> str | None:
    """Download a .sha256 asset over HTTPS and return the expected digest."""
    if not _https_github(hash_url):
        return None
    req = urllib.request.Request(hash_url, headers={"User-Agent": _USER_AGENT})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        return _parse_sha256(resp.read(4096).decode("utf-8", "replace"))


def download_asset(asset_url: str, progress_cb=None, should_interrupt=None) -> str | None:
    """Download an update asset over HTTPS to a temp file; return its path.

    Returns ``None`` if ``should_interrupt()`` becomes true (cooperative cancel).
    Enforces a maximum size and always removes the temp file on cancel/error, so
    a half-downloaded executable is never left behind.
    """
    if not _https_github(asset_url):
        raise ValueError("Unsichere oder unbekannte Download-Adresse.")
    req = urllib.request.Request(asset_url, headers={"User-Agent": _USER_AGENT})
    ctx = ssl.create_default_context()
    fd, tmp_path = tempfile.mkstemp(suffix=".exe", prefix="HaushaltsManager-update-")
    os.close(fd)
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            if total and total > _MAX_UPDATE_BYTES:
                raise ValueError("Update-Datei ist unerwartet groß.")
            read = 0
            with open(tmp_path, "wb") as out:
                while True:
                    if should_interrupt and should_interrupt():
                        raise _Cancelled()
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    read += len(chunk)
                    if read > _MAX_UPDATE_BYTES:
                        raise ValueError("Update-Datei ist unerwartet groß.")
                    if progress_cb and total:
                        progress_cb(int(read * 100 / total))
        return tmp_path
    except _Cancelled:
        _safe_remove(tmp_path)
        return None
    except Exception:
        _safe_remove(tmp_path)
        raise


def apply_update_and_restart(new_exe_path: str) -> bool:
    """Swap the running executable with the downloaded one and relaunch.

    Only effective in a frozen build. Returns True if the relaunch script was
    started (the caller should then quit the application).
    """
    if not is_frozen():
        _log.info("apply_update im Dev-Modus übersprungen (nur als .exe wirksam).")
        return False

    try:
        target = sys.executable
        pid = os.getpid()
        bat = (
            "@echo off\r\n"
            ":wait\r\n"
            f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul\r\n'
            "if not errorlevel 1 ( timeout /t 1 /nobreak >nul & goto wait )\r\n"
            f'move /Y "{new_exe_path}" "{target}" >nul\r\n'
            f'start "" "{target}"\r\n'
            'del "%~f0"\r\n'
        )
        fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="hm-update-")
        with os.fdopen(fd, "w", encoding="ascii") as fh:
            fh.write(bat)
        subprocess.Popen(
            ["cmd", "/c", bat_path],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except Exception as exc:  # noqa: BLE001 - honour the module's never-raises contract
        _log.warning("Update konnte nicht angewendet werden: %s", exc)
        _safe_remove(new_exe_path)
        return False


# --- Qt threads (non-blocking) ---------------------------------------------
class UpdateChecker(QThread):
    """Runs the version check off the UI thread; emits UpdateInfo or None."""

    result = pyqtSignal(object)

    def __init__(self, repo: str, current_version: str, parent=None) -> None:
        super().__init__(parent)
        self._repo = repo
        self._version = current_version

    def run(self) -> None:
        self.result.emit(check_for_update(self._repo, self._version))


class UpdateInstaller(QThread):
    """Downloads the asset off the UI thread, reporting progress."""

    progress = pyqtSignal(int)
    ready = pyqtSignal(str)     # path to the downloaded exe
    failed = pyqtSignal(str)

    def __init__(self, asset_url: str, hash_url: str = "", parent=None) -> None:
        super().__init__(parent)
        self._asset_url = asset_url
        self._hash_url = hash_url

    def cancel(self) -> None:
        """Request a cooperative cancel (checked inside the download loop)."""
        self.requestInterruption()

    def run(self) -> None:
        try:
            path = download_asset(
                self._asset_url, self.progress.emit, self.isInterruptionRequested)
            if path is None:
                return  # cancelled; the temp file was already removed
            # If the release ships a checksum, verify the download against it.
            # A mismatch is fatal (reject); a failure to fetch the checksum is
            # only logged (HTTPS already protects authenticity/integrity).
            if self._hash_url:
                try:
                    expected = fetch_checksum(self._hash_url)
                except Exception as exc:  # noqa: BLE001
                    _log.info("Prüfsummen-Abruf übersprungen: %s", exc)
                    expected = None
                if expected and sha256_of_file(path).lower() != expected:
                    _safe_remove(path)
                    self.failed.emit(
                        "Die Prüfsumme der heruntergeladenen Datei stimmt nicht "
                        "überein. Das Update wurde aus Sicherheitsgründen abgebrochen.")
                    return
            self.ready.emit(path)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
