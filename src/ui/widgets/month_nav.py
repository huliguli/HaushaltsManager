"""Reusable month navigator: ◀ [Monat Jahr] ▶ with a month_changed signal.

Extracted so the dashboard, the trends view and the household book can share one
implementation of the wrap-around month arithmetic and the German month labels
(previously duplicated per view). Emits ``month_changed(year, month)`` whenever
the user steps to another month. Theme colours are passed in and refreshed via
:meth:`refresh_icons` so the chevrons stay legible in light and dark.
"""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from modules import dates
from ui import icons


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

        self._prev = self._nav_button("chevron_left", "Vorheriger Monat", -1)
        self._next = self._nav_button("chevron_right", "Nächster Monat", 1)
        self._label = QLabel()
        self._label.setObjectName("H2")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumWidth(168)

        layout.addWidget(self._prev)
        layout.addWidget(self._label)
        layout.addWidget(self._next)
        self._render()

    def _nav_button(self, icon_name: str, tip: str, delta: int) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("Ghost")
        btn.setFixedWidth(40)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tip)
        btn.setAccessibleName(tip)
        btn.clicked.connect(lambda: self._shift(delta))
        btn._icon_name = icon_name  # type: ignore[attr-defined]
        self._tint_button(btn)
        return btn

    def _tint_button(self, btn: QPushButton) -> None:
        color = self._colors["text"]
        btn.setIcon(icons.icon(btn._icon_name, color, 18))  # type: ignore[attr-defined]
        btn.setIconSize(QSize(18, 18))

    # -- state --------------------------------------------------------------
    def year_month(self) -> tuple[int, int]:
        return self._year, self._month

    def set_month(self, year: int, month: int, *, emit: bool = False) -> None:
        self._year, self._month = year, month
        self._render()
        if emit:
            self.month_changed.emit(self._year, self._month)

    def _shift(self, delta: int) -> None:
        year, month = dates.shift_month(self._year, self._month, delta)
        if not self._allow_future:
            today = date.today()
            if (year, month) > (today.year, today.month):
                return
        self._year, self._month = year, month
        self._render()
        self.month_changed.emit(self._year, self._month)

    def refresh_icons(self, colors: dict | None = None) -> None:
        """Re-tint the chevrons after a theme change."""
        if colors is not None:
            self._colors = colors
        for btn in (self._prev, self._next):
            self._tint_button(btn)

    def _render(self) -> None:
        self._label.setText(f"{dates.month_name(self._month)} {self._year}")
        self._label.setAccessibleName(f"Monat {dates.month_name(self._month)} {self._year}")
        if not self._allow_future:
            today = date.today()
            self._next.setEnabled((self._year, self._month) < (today.year, today.month))
