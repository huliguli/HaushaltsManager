"""Main application window: sidebar navigation, view stack, theme toggle.

The window remembers its size/position between runs and exposes a light/dark
toggle. Views are created once and kept in a QStackedWidget; switching the
sidebar re-runs the visible view's ``refresh()`` so data is always current.
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app_meta import APP_DISPLAY_NAME, APP_VERSION, GITHUB_REPO, app_icon_path
from modules.updater import updater
from ui import icons, theme
from ui.app_context import AppContext
from ui.views.abo_radar_view import AboRadarView
from ui.views.base_view import BaseView
from ui.views.dashboard_view import DashboardView
from ui.views.einstellungen_view import EinstellungenView
from ui.views.haushaltsbuch_view import HaushaltsbuchView
from ui.views.import_export_view import ImportExportView
from ui.views.kredite_view import KrediteView
from ui.views.rechner_view import RechnerView
from ui.views.sparplaner_view import SparplanerView
from ui.views.verlauf_view import VerlaufView

# (label, icon name, view class). Einstellungen must stay last — the update flow
# and thread cleanup reference it as self._views[-1].
_NAV = [
    ("Dashboard", "dashboard", DashboardView),
    ("Verlauf", "chart", VerlaufView),
    ("Haushaltsbuch", "book", HaushaltsbuchView),
    ("Kredite", "credit", KrediteView),
    ("Rechner", "calculator", RechnerView),
    ("Sparplaner", "trend", SparplanerView),
    ("Abo-Radar", "refresh", AboRadarView),
    ("Import / Export", "exchange", ImportExportView),
    ("Einstellungen", "settings", EinstellungenView),
]


class MainWindow(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.setObjectName("Root")
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.setMinimumSize(1060, 680)
        _icon = app_icon_path()
        if _icon.exists():
            self.setWindowIcon(QIcon(str(_icon)))

        self._views: list[BaseView] = []
        self._nav_buttons: list[QPushButton] = []
        self._update_checker = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        self._stack = QStackedWidget()
        for _label, _icon, view_cls in _NAV:
            view = view_cls(ctx)
            self._views.append(view)
            self._stack.addWidget(view)
        root.addWidget(self._stack, 1)

        self.ctx.data_changed.connect(self._refresh_current)
        self.ctx.theme_changed.connect(self._on_theme_changed)
        self.ctx.drilldown_requested.connect(self._on_drilldown)
        self.ctx.pots_requested.connect(self._on_pots_requested)

        self._init_shortcuts()
        self._restore_geometry()
        self._init_background_timers()
        self._select(0)

    # -- keyboard layer -------------------------------------------------------
    def _init_shortcuts(self) -> None:
        """App-wide shortcuts (Qt maps Ctrl to Cmd on macOS automatically).

        Strg+1..9 switch views, Strg+N opens the active view's "new entry"
        dialog, Strg+F jumps to the expense search, Strg+Bild↑/↓ steps the
        visible month navigator. Plain Bild↑/↓ stays untouched so tables and
        scroll areas keep their normal page scrolling.
        """
        for i in range(len(_NAV)):
            sc = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            sc.activated.connect(lambda i=i: self._select(i))
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self._shortcut_new)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._shortcut_search)
        QShortcut(QKeySequence("Ctrl+PgUp"), self).activated.connect(
            lambda: self._shortcut_month(-1))
        QShortcut(QKeySequence("Ctrl+PgDown"), self).activated.connect(
            lambda: self._shortcut_month(1))

    def _current_view(self) -> BaseView:
        return self._views[self._stack.currentIndex()]

    def _shortcut_new(self) -> None:
        self._current_view().create_new()

    def _shortcut_search(self) -> None:
        # Views with their own search handle it; otherwise jump to the
        # household book, whose expense search is the app-wide one.
        if self._current_view().focus_search():
            return
        book_index = next(
            (i for i, (_l, _i, cls) in enumerate(_NAV) if cls is HaushaltsbuchView), None)
        if book_index is not None:
            self._select(book_index)
            self._views[book_index].focus_search()

    def _shortcut_month(self, delta: int) -> None:
        nav = self._current_view().month_navigator()
        if nav is not None and nav.isEnabled():
            nav.step(delta)

    # -- sidebar ------------------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(232)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(16, 22, 16, 18)
        layout.setSpacing(6)

        brand = QLabel(APP_DISPLAY_NAME)
        brand.setObjectName("Brand")
        sub = QLabel("FINANZÜBERSICHT")
        sub.setObjectName("BrandSub")
        layout.addWidget(brand)
        layout.addWidget(sub)
        layout.addSpacing(18)

        group = QButtonGroup(self)
        group.setExclusive(True)
        icon_color = theme.palette(self.ctx.theme_name)["sidebar_text"]
        for index, (label, icon_name, _cls) in enumerate(_NAV):
            btn = QPushButton(f"  {label}")
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setToolTip(f"{label} (Strg+{index + 1})")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIcon(icons.icon(icon_name, icon_color, 20))
            btn.setIconSize(QSize(20, 20))
            btn.clicked.connect(lambda _checked, i=index: self._select(i))
            group.addButton(btn, index)
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch(1)

        self._theme_btn = QPushButton("  Dunkles Design")
        self._theme_btn.setObjectName("NavButton")
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.clicked.connect(self._toggle_theme)
        layout.addWidget(self._theme_btn)

        version = QLabel(f"v{APP_VERSION}")
        version.setObjectName("BrandSub")
        version.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(version)

        self._update_theme_button()
        return bar

    # -- navigation ---------------------------------------------------------
    def _select(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        if 0 <= index < len(self._nav_buttons):
            self._nav_buttons[index].setChecked(True)
        self._views[index].refresh()

    def _refresh_current(self) -> None:
        self._views[self._stack.currentIndex()].refresh()

    def _on_drilldown(self, year: int, month: int, category: str) -> None:
        """Chart drilldown: open the Haushaltsbuch expenses, filtered."""
        index = next(
            (i for i, (_l, _i, cls) in enumerate(_NAV) if cls is HaushaltsbuchView), None)
        if index is None:
            return
        self._select(index)
        self._views[index].show_expenses_filter(year, month, category or None)

    def _on_pots_requested(self) -> None:
        """Dashboard Töpfe card: open the Haushaltsbuch Töpfe tab."""
        index = next(
            (i for i, (_l, _i, cls) in enumerate(_NAV) if cls is HaushaltsbuchView), None)
        if index is None:
            return
        self._select(index)
        self._views[index].show_pots()

    # -- theme --------------------------------------------------------------
    def _toggle_theme(self) -> None:
        new = "light" if self.ctx.theme_name == "dark" else "dark"
        self.ctx.set_theme(new)

    def _update_theme_button(self) -> None:
        is_dark = self.ctx.theme_name == "dark"
        color = theme.palette(self.ctx.theme_name)["sidebar_text"]
        self._theme_btn.setText("  Helles Design" if is_dark else "  Dunkles Design")
        self._theme_btn.setIcon(icons.icon("sun" if is_dark else "moon", color, 20))
        self._theme_btn.setIconSize(QSize(20, 20))

    def _on_theme_changed(self, _name: str) -> None:
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().setStyleSheet(theme.build_qss(self.ctx.colors))
        # Re-tint sidebar icons for the new theme.
        color = self.ctx.colors["sidebar_text"]
        for (_label, icon_name, _cls), btn in zip(_NAV, self._nav_buttons):
            btn.setIcon(icons.icon(icon_name, color, 20))
        self._update_theme_button()
        for view in self._views:
            view.on_theme_changed()

    # -- periodic background checks ------------------------------------------
    # A long-running app must stay current without restarts: updates are
    # re-checked hourly, the family folder every few minutes (so a newly
    # installed/started sister app appears live on the dashboard).
    UPDATE_CHECK_INTERVAL_MS = 60 * 60 * 1000
    FAMILY_POLL_INTERVAL_MS = 5 * 60 * 1000

    def _init_background_timers(self) -> None:
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(self.UPDATE_CHECK_INTERVAL_MS)
        self._update_timer.timeout.connect(self._periodic_update_check)
        self._update_timer.start()

        self._family_timer = QTimer(self)
        self._family_timer.setInterval(self.FAMILY_POLL_INTERVAL_MS)
        self._family_timer.timeout.connect(self._family_tick)
        self._family_timer.start()
        self._sister_db_mtime = self._current_sister_mtime()

    def _periodic_update_check(self) -> None:
        """Hourly re-check while the app runs (same rules as at startup).

        Skips silently while a previous check, an update dialog or a download
        is still active; versions the user postponed stay quiet for the
        session (see EinstellungenView.session_dismissed).
        """
        if not self.ctx.config.get("update_check_enabled", True):
            return
        if self._update_checker is not None and self._update_checker.isRunning():
            return
        settings_view = self._views[-1]
        if getattr(settings_view, "update_flow_active", lambda: False)():
            return
        self._update_checker = updater.UpdateChecker(GITHUB_REPO, APP_VERSION, parent=self)
        self._update_checker.result.connect(self._on_startup_update)
        self._update_checker.start()

    def _current_sister_mtime(self) -> float | None:
        """Last-modified stamp of the sister DB (None when not connected)."""
        sister = self.ctx.sister
        if sister.status == "aktiv" and sister.db_path is not None:
            try:
                return sister.db_path.stat().st_mtime
            except OSError:
                return None
        return None

    def _family_tick(self) -> None:
        """Re-announce ourselves and pick up sister-app changes live.

        Catches both cases without an app restart: the sister gets installed/
        updated while we run (state change), or she writes new data that our
        dashboard card shows (DB mtime change). Views are only refreshed when
        something actually changed, so user interaction is never disturbed
        by a needless rebuild.
        """
        from modules import interop
        interop.announce_self(self.ctx.db.path)
        changed = self.ctx.refresh_sister()
        mtime = self._current_sister_mtime()
        if changed or mtime != self._sister_db_mtime:
            self._sister_db_mtime = mtime
            self._refresh_current()

    # -- startup update check ----------------------------------------------
    def maybe_check_updates(self) -> None:
        """Start a non-blocking update check if the user enabled it."""
        # Sweep any leftover installer from a previous update first.
        updater.cleanup_temp_downloads()
        if not self.ctx.config.get("update_check_enabled", True):
            return
        # Parent the thread to the window so its C++ lifetime is tied to ours;
        # closeEvent additionally waits for it (a parent alone does not make Qt
        # wait for a running QThread).
        self._update_checker = updater.UpdateChecker(GITHUB_REPO, APP_VERSION, parent=self)
        self._update_checker.result.connect(self._on_startup_update)
        self._update_checker.start()

    def _on_startup_update(self, info) -> None:
        if info is None or info.tag == self.ctx.config.get("skipped_version"):
            return
        # The Settings view owns the update dialog/installer flow.
        settings_view = self._views[-1]
        # „Später“ gilt für die laufende Sitzung — der Stunden-Check fragt
        # nicht jede Stunde erneut nach derselben Version.
        if info.tag in getattr(settings_view, "session_dismissed", set()):
            return
        # Opt-in auto-update: install straight away instead of asking. The
        # install path keeps every safety check (checksum + signature pin).
        if self.ctx.config.get("update_auto_install", False) and info.asset_url \
                and hasattr(settings_view, "auto_install"):
            settings_view.auto_install(info)
            return
        if hasattr(settings_view, "show_update_dialog"):
            settings_view.show_update_dialog(info)

    # -- geometry persistence ----------------------------------------------
    def _restore_geometry(self) -> None:
        win = self.ctx.config.window
        self.resize(int(win.get("w", 1240)), int(win.get("h", 820)))
        if win.get("x") is not None and win.get("y") is not None:
            self.move(int(win["x"]), int(win["y"]))
        if win.get("maximized"):
            self.showMaximized()

    def _stop_background_threads(self) -> None:
        """Stop any running update threads so none is destroyed while running.

        The download thread cancels cooperatively (checked inside its loop); the
        check thread has no interruption point but is bounded by its network
        timeout, so we wait with a cap and proceed regardless on shutdown.
        """
        threads = [self._update_checker]
        settings = self._views[-1] if self._views else None
        if settings is not None and hasattr(settings, "background_threads"):
            threads += settings.background_threads()
        for thread in threads:
            if thread is not None and thread.isRunning():
                thread.requestInterruption()
                thread.wait(4000)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._stop_background_threads()
        maximized = self.isMaximized()
        geo = self.normalGeometry()
        self.ctx.config.window = {
            "w": geo.width(), "h": geo.height(),
            "x": geo.x(), "y": geo.y(), "maximized": maximized,
        }
        self.ctx.db.close()
        super().closeEvent(event)
