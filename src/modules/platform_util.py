"""Small cross-platform OS-integration helpers.

Keeps platform branches in one place so the rest of the app stays OS-agnostic
(a prerequisite for shipping Windows and macOS from the same code base).
"""

from __future__ import annotations

import os
import subprocess
import sys

from modules.logging_setup import get_logger

_log = get_logger("platform")


def open_path(path) -> None:
    """Open a file or reveal a folder in the OS file manager (best effort).

    Never raises — opening a location must not crash the app if the shell call
    fails. Uses ``os.startfile`` on Windows, ``open`` on macOS and ``xdg-open``
    on Linux.
    """
    target = str(path)
    try:
        if sys.platform == "win32":
            os.startfile(target)  # noqa: S606 - a known local path, no shell
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
    except Exception as exc:  # noqa: BLE001 - opening a folder must never block/crash
        _log.info("Konnte Pfad nicht öffnen (%s): %s", target, exc)
