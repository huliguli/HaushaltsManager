"""Base class for all top-level views.

Each view receives the shared :class:`AppContext` and implements ``refresh()``
to (re)load its data. The main window calls ``refresh()`` when the view becomes
visible and whenever the global ``data_changed`` signal fires.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from ui.app_context import AppContext


class BaseView(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx

    def refresh(self) -> None:  # noqa: D401 - overridden by subclasses
        """Reload data into the view. Overridden by subclasses."""

    def on_theme_changed(self) -> None:
        """Re-render when the theme changes (default: full refresh)."""
        self.refresh()

    # -- keyboard-layer hooks (all optional) ---------------------------------
    # The main window's app-wide shortcuts delegate to the ACTIVE view through
    # these; a view that has nothing to offer simply inherits the defaults.
    def create_new(self) -> bool:
        """Ctrl+N: open this view's "new entry" dialog. True when handled."""
        return False

    def focus_search(self) -> bool:
        """Ctrl+F: focus this view's search field. True when handled."""
        return False

    def month_navigator(self):
        """The view's active MonthNavigator (or None) for Strg+Bild↑/↓."""
        return None
