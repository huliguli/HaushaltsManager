"""User preferences persisted as JSON next to the database.

Stores lightweight UI state that should survive restarts but does not belong
in the financial database: theme, last window geometry, whether the
quick-setup wizard has run, and the timestamp/notes of the last update check.
"""

from __future__ import annotations

import json
from typing import Any

from app_meta import config_path
from modules.logging_setup import get_logger

_log = get_logger("config")

_DEFAULTS: dict[str, Any] = {
    "theme": "light",                # "light" | "dark"
    "window": {"w": 1240, "h": 820, "x": None, "y": None, "maximized": False},
    "wizard_completed": False,
    "update_check_enabled": True,
    "last_update_check": None,        # ISO timestamp
    "skipped_version": None,          # release tag the user chose to skip
}


class Config:
    """Tiny JSON-backed settings store with dotted-key access."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = json.loads(json.dumps(_DEFAULTS))
        self.load()

    def load(self) -> None:
        path = config_path()
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                self._data.update(stored)
        except (OSError, ValueError) as exc:
            _log.warning("Konnte Einstellungen nicht laden: %s", exc)

    def save(self) -> None:
        try:
            with open(config_path(), "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
        except OSError as exc:
            _log.warning("Konnte Einstellungen nicht speichern: %s", exc)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    # Convenience accessors -------------------------------------------------
    @property
    def theme(self) -> str:
        return self._data.get("theme", "light")

    @theme.setter
    def theme(self, value: str) -> None:
        self.set("theme", value)

    @property
    def window(self) -> dict[str, Any]:
        return self._data.get("window", dict(_DEFAULTS["window"]))

    @window.setter
    def window(self, value: dict[str, Any]) -> None:
        self.set("window", value)
