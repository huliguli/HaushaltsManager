"""Reusable month navigator: ◀ [Monat Jahr ▾] ▶ (Heute) with month_changed.

Extracted so the dashboard, the trends view and the household book can share one
implementation of the wrap-around month arithmetic and the German month labels
(previously duplicated per view). Emits ``month_changed(year, month)`` whenever
the user steps to another month. Theme colours are passed in and refreshed via
:meth:`refresh_icons` so the chevrons stay legible in light and dark.

v2.6.0 additions: the month label opens a month/year picker popup (far months
no longer need a dozen clicks), a "Heute" button jumps back to the current
month, and :meth:`step` is public so the app-wide keyboard layer
(Strg+Bild↑/Bild↓ in the main window) can drive the visible navigator.
"""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from modules import dates
from ui import icons


class _MonthPickerPopup(QFrame):
    """Popup with a year stepper and a 3×4 month grid (closes on choice)."""

    def __init__(self, nav: "MonthNavigator") -> None:
        super().__init__(nav, Qt.WindowType.Popup)
        self.setObjectName("Card")
        self._nav = nav
        self._year = nav._year

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        self._back = self._year_button("chevron_left", "Vorheriges Jahr", -1)
        self._fwd = self._year_button("chevron_right", "Nächstes Jahr", 1)
        self._year_lbl = QLabel()
        self._year_lbl.setObjectName("H2")
        self._year_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.addWidget(self._back)
        head.addWidget(self._year_lbl, 1)
        head.addWidget(self._fwd)
        layout.addLayout(head)

        grid = QGridLayout()
        grid.setSpacing(6)
        self._month_btns: list[QPushButton] = []
        for i in range(12):
            btn = QPushButton(dates.month_name(i + 1)[:3])
            btn.setObjectName("Ghost")
            btn.setFixedWidth(66)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setAccessibleName(f"{dates.month_name(i + 1)} {self._year}")
            btn.clicked.connect(lambda _c, m=i + 1: self._choose(m))
            grid.addWidget(btn, i // 3, i % 3)
            self._month_btns.append(btn)
        layout.addLayout(grid)
        self._render()

    def _year_button(self, icon_name: str, tip: str, delta: int) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("Ghost")
        btn.setFixedWidth(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tip)
        btn.setAccessibleName(tip)
        btn.setIcon(icons.icon(icon_name, self._nav._colors["text"], 16))
        btn.setIconSize(QSize(16, 16))
        btn.clicked.connect(lambda: self._shift_year(delta))
        return btn

    def _shift_year(self, delta: int) -> None:
        self._year = max(2000, self._year + delta)
        self._render()

    def _render(self) -> None:
        self._year_lbl.setText(str(self._year))
        today = date.today()
        c = self._nav._colors
        for i, btn in enumerate(self._month_btns):
            month = i + 1
            future = (self._year, month) > (today.year, today.month)
            btn.setEnabled(self._nav._allow_future or not future)
            if (self._year, month) == (self._nav._year, self._nav._month):
                # Mark the currently shown month; inline so it renders on the
                # popup regardless of ancestor styling.
                btn.setStyleSheet(
                    f"QPushButton{{background:{c['primary_btn']};color:{c['on_primary']};"
                    f"border:1px solid {c['primary_btn']};border-radius:10px;font-weight:600;}}")
            else:
                btn.setStyleSheet("")
        self._fwd.setEnabled(self._nav._allow_future or self._year < today.year)

    def _choose(self, month: int) -> None:
        year = self._year
        self.close()
        self._nav.set_month(year, month, emit=True)


class MonthNavigator(QWidget):
    month_changed = pyqtSignal(int, int)  # (year, month)

    def __init__(self, colors: dict, year: int | None = None, month: int | None = None,
                 allow_future: bool = False, parent=None) -> None:
        super().__init__(parent)
        today = date.today()
        self._year = year or today.year
        self._month = month or today.month
        self._allow_future = allow_future
        self._colors = colors

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._prev = self._nav_button("chevron_left", "Vorheriger Monat (Strg+Bild auf)", -1)
        self._next = self._nav_button("chevron_right", "Nächster Monat (Strg+Bild ab)", 1)
        # The label is a flat button: clicking it opens the month/year picker.
        self._label = QPushButton()
        self._label.setMinimumWidth(168)
        self._label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._label.setToolTip("Monat und Jahr direkt wählen")
        self._label.clicked.connect(self._open_picker)
        self._style_label()

        self._today_btn = QPushButton("Heute")
        self._today_btn.setObjectName("Ghost")
        self._today_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._today_btn.setToolTip("Zum aktuellen Monat springen")
        self._today_btn.setAccessibleName("Zum aktuellen Monat springen")
        self._today_btn.clicked.connect(self.go_today)

        layout.addWidget(self._prev)
        layout.addWidget(self._label)
        layout.addWidget(self._next)
        layout.addWidget(self._today_btn)
        self._render()

    def _nav_button(self, icon_name: str, tip: str, delta: int) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("Ghost")
        btn.setFixedWidth(40)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tip)
        btn.setAccessibleName(tip)
        btn.clicked.connect(lambda: self.step(delta))
        btn._icon_name = icon_name  # type: ignore[attr-defined]
        self._tint_button(btn)
        return btn

    def _tint_button(self, btn: QPushButton) -> None:
        color = self._colors["text"]
        btn.setIcon(icons.icon(btn._icon_name, color, 18))  # type: ignore[attr-defined]
        btn.setIconSize(QSize(18, 18))

    def _style_label(self) -> None:
        # H2-like text on a borderless button; inline because the navigator can
        # sit on transparent scroll containers where global QSS fills vanish.
        self._label.setStyleSheet(
            "QPushButton{background:transparent;border:none;"
            f"color:{self._colors['text']};font-weight:700;font-size:15px;}}"
            f"QPushButton:hover{{color:{self._colors['primary']};}}")

    # -- state --------------------------------------------------------------
    def year_month(self) -> tuple[int, int]:
        return self._year, self._month

    def set_month(self, year: int, month: int, *, emit: bool = False) -> None:
        self._year, self._month = year, month
        self._render()
        if emit:
            self.month_changed.emit(self._year, self._month)

    def step(self, delta: int) -> None:
        """Step one month back/forward (public: also driven by the keyboard layer)."""
        year, month = dates.shift_month(self._year, self._month, delta)
        if not self._allow_future:
            today = date.today()
            if (year, month) > (today.year, today.month):
                return
        self._year, self._month = year, month
        self._render()
        self.month_changed.emit(self._year, self._month)

    def go_today(self) -> None:
        """Jump back to the current month (no-op when already there)."""
        today = date.today()
        if (self._year, self._month) == (today.year, today.month):
            return
        self.set_month(today.year, today.month, emit=True)

    def _open_picker(self) -> None:
        popup = _MonthPickerPopup(self)
        popup.adjustSize()
        anchor = self._label.mapToGlobal(self._label.rect().bottomLeft())
        popup.move(anchor.x(), anchor.y() + 4)
        popup.show()

    def refresh_icons(self, colors: dict | None = None) -> None:
        """Re-tint the chevrons and label after a theme change."""
        if colors is not None:
            self._colors = colors
        for btn in (self._prev, self._next):
            self._tint_button(btn)
        self._style_label()

    def _render(self) -> None:
        today = date.today()
        self._label.setText(f"{dates.month_name(self._month)} {self._year}")
        self._label.setAccessibleName(
            f"Monat {dates.month_name(self._month)} {self._year} – Monat und Jahr wählen")
        self._today_btn.setVisible((self._year, self._month) != (today.year, today.month))
        if not self._allow_future:
            self._next.setEnabled((self._year, self._month) < (today.year, today.month))
