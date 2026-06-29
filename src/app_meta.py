"""Central application metadata and filesystem locations.

Single source of truth for the app name, version, GitHub repo and all
on-disk paths. Keeping this in one tiny module avoids hard-coded paths
scattered through the code base (a classic "runs only on my machine" trap)
and makes the PyInstaller one-file build behave identically to a dev run.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "HaushaltsManager"
APP_DISPLAY_NAME = "HaushaltsManager"
GITHUB_REPO = "huliguli/HaushaltsManager"

# Fallback version; the real value is read from the bundled version.json below.
_FALLBACK_VERSION = "1.0.4"


def is_frozen() -> bool:
    """True when running from a PyInstaller-built executable."""
    return getattr(sys, "frozen", False)


def resource_dir() -> Path:
    """Directory that holds bundled read-only resources.

    Under PyInstaller one-file builds the payload is unpacked to a temporary
    folder exposed as ``sys._MEIPASS``. During development it is the project
    root (the parent of ``src``).
    """
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    # src/app_meta.py -> project root is two levels up
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    """Absolute path to a bundled resource (works in dev and frozen builds)."""
    return resource_dir().joinpath(*parts)


def _read_bundled_version() -> str:
    """Read the version string from the bundled version.json."""
    for candidate in (resource_path("version.json"), resource_path("src", "version.json")):
        try:
            with open(candidate, "r", encoding="utf-8") as fh:
                return str(json.load(fh).get("version", _FALLBACK_VERSION))
        except (OSError, ValueError):
            continue
    return _FALLBACK_VERSION


APP_VERSION = _read_bundled_version()


def data_dir() -> Path:
    """Per-user writable data directory.

    The packaged executable typically lives in a read-only location
    (Program Files), so the database, config and logs must live in the
    user profile instead. On Windows that is ``%APPDATA%\\HaushaltsManager``.
    """
    base = os.environ.get("APPDATA")
    if base:
        path = Path(base) / APP_NAME
    else:  # non-Windows / unusual setups
        path = Path.home() / f".{APP_NAME.lower()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return data_dir() / "haushalt.db"


def config_path() -> Path:
    return data_dir() / "config.json"


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def schema_path() -> Path:
    """Location of the bundled SQL schema."""
    return resource_path("src", "database", "schema.sql")


def app_icon_path() -> Path:
    """Location of the bundled application icon (.ico).

    Resolved via :func:`resource_path` so it works both in development and
    inside a PyInstaller one-file bundle (sys._MEIPASS).
    """
    return resource_path("assets", "app.ico")
