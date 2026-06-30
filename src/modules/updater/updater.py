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


def cleanup_temp_downloads() -> None:
    """Delete leftover update installers from %TEMP% (best effort, never raises).

    The installer runs detached after the app quits, so apply_update_and_restart
    cannot remove its own file. We sweep the stale ``HaushaltsManager-update-*``
    files on the next start instead, so they do not accumulate over updates.
    """
    import glob
    try:
        pattern = os.path.join(tempfile.gettempdir(), "HaushaltsManager-update-*")
        for path in glob.glob(pattern):
            _safe_remove(path)
    except Exception:  # noqa: BLE001 - cosmetic cleanup, must never block startup
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


def verify_download(path: str, expected_sha256: str | None) -> bool:
    """True if the file matches ``expected_sha256`` (or no checksum was given).

    Returns ``False`` only on an actual digest mismatch. A missing/``None``
    expected digest means "cannot verify here" and returns ``True`` — the
    authoritative protection against a tampered installer is the Authenticode
    signature check in :func:`apply_update_and_restart`; HTTPS protects the
    transport. Extracted as a pure function so the accept/reject decision is
    unit-testable without a live download.
    """
    if not expected_sha256:
        return True
    return sha256_of_file(path).lower() == expected_sha256.lower()


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


# Pinned code-signing certificate thumbprint(s) (SHA-1, upper-case, no spaces).
# An update installer must be Authenticode-signed by one of these certificates
# before we run it, so a tampered release cannot execute even if its .sha256 was
# forged (binary and checksum live in the same GitHub release / TLS origin).
# MIGRATION NOTE: when switching to a real OV/EV certificate, add its thumbprint
# here in the SAME release that begins signing with it. Old clients pin the old
# value, so that one transition needs a manual download (like onefile->onedir).
_TRUSTED_CERT_THUMBPRINTS = (
    "A89CFB32A07F35CBD07699B1C6CCF733B8814DF4",  # self-signed CN=HaushaltsManager
)


def authenticode_thumbprint(path: str) -> str | None:
    """Return the signing certificate's thumbprint (upper-case), else None.

    Uses PowerShell's ``Get-AuthenticodeSignature``. We compare the certificate
    *thumbprint* (the cryptographic identity of our key) rather than the trust
    *status*: the project ships a self-signed certificate that does not chain to
    a trusted root, yet only the holder of our private key can produce a binary
    carrying this thumbprint. The path is passed via an environment variable, not
    string-interpolated into the command, so it cannot be injected.
    """
    try:
        env = dict(os.environ, HM_VERIFY_PATH=path)
        # Drop any inherited PSModulePath: if the app was launched from a
        # PowerShell 7 process, that variable points at pwsh module folders and
        # Windows PowerShell 5.1 then fails to load Microsoft.PowerShell.Security
        # (which provides Get-AuthenticodeSignature). Removing it makes the host
        # fall back to its own default module path. Match case-insensitively —
        # Windows env keys may be stored in any case.
        for _key in [k for k in env if k.upper() == "PSMODULEPATH"]:
            env.pop(_key, None)
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "$ErrorActionPreference='Stop';"
             "(Get-AuthenticodeSignature -LiteralPath $env:HM_VERIFY_PATH)"
             ".SignerCertificate.Thumbprint"],
            capture_output=True, timeout=30, env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        # Decode the raw bytes as ASCII, ignoring any console-codepage noise: the
        # thumbprint is 40 hex chars, so extract it with a regex instead of
        # trusting the exact framing. (text=True once crashed on a stray 0x81
        # byte that the cp1252 default codec could not decode.)
        out = (proc.stdout or b"").decode("ascii", "ignore")
        match = re.search(r"[0-9A-Fa-f]{40}", out)
        return match.group(0).upper() if match else None
    except Exception as exc:  # noqa: BLE001 - treat any failure as "unverified"
        _log.warning("Authenticode-Prüfung fehlgeschlagen: %s", exc)
        return None


def is_trusted_installer(path: str) -> bool:
    """True only if the file is Authenticode-signed by a pinned certificate."""
    thumbprint = authenticode_thumbprint(path)
    return bool(thumbprint and thumbprint.upper() in _TRUSTED_CERT_THUMBPRINTS)


def apply_update_and_restart(installer_path: str) -> bool:
    """Run the downloaded installer silently to update in place, then relaunch.

    The release asset is an Inno Setup installer (HaushaltsManager-Setup.exe).
    We launch it with /VERYSILENT; the installer closes the running app (via the
    Windows Restart Manager / CloseApplications), replaces the program files and
    relaunches the app through its [Run] entry. The caller must quit the app
    right after this returns True so the files are not locked.

    Only effective in a frozen build. Before launching, the installer's
    Authenticode signature is verified against a pinned certificate thumbprint
    and the update is aborted fail-closed if it does not match. Returns True only
    if the installer was actually started (never raises — honours the module's
    never-raises contract).
    """
    if not is_frozen():
        _log.info("apply_update im Dev-Modus übersprungen (nur als Installer wirksam).")
        return False

    # Fail-closed: never execute an installer that is not signed by our key.
    if not is_trusted_installer(installer_path):
        _log.warning(
            "Update abgebrochen: Installer-Signatur ungültig oder nicht vertrauenswürdig.")
        _safe_remove(installer_path)
        return False

    try:
        # Detached so it survives this process exiting; argument array (no shell)
        # so the path cannot be misinterpreted.
        flags = (getattr(subprocess, "DETACHED_PROCESS", 0)
                 | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        subprocess.Popen(
            [installer_path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCANCEL"],
            creationflags=flags, close_fds=True)
        _log.info("Update-Installer gestartet: %s", installer_path)
        return True
    except Exception as exc:  # noqa: BLE001 - honour the module's never-raises contract
        _log.warning("Update konnte nicht angewendet werden: %s", exc)
        _safe_remove(installer_path)
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
            # only logged (HTTPS protects transport, the Authenticode check at
            # apply time is the authoritative tamper guard).
            expected = None
            if self._hash_url:
                try:
                    expected = fetch_checksum(self._hash_url)
                except Exception as exc:  # noqa: BLE001
                    _log.info("Prüfsummen-Abruf übersprungen: %s", exc)
                    expected = None
            if not verify_download(path, expected):
                _safe_remove(path)
                self.failed.emit(
                    "Die Prüfsumme der heruntergeladenen Datei stimmt nicht "
                    "überein. Das Update wurde aus Sicherheitsgründen abgebrochen.")
                return
            self.ready.emit(path)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
