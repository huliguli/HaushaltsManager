"""Small reusable UI building blocks: cards, section headers, layout helpers."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QSizePolicy,
    QStackedLayout,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QColor

# Shared with theme.py so card stripes and the card frame round identically.
from ui.theme import RADIUS_CARD


def clear_layout(layout: QLayout) -> None:
    """Remove and delete every item in a layout (for full re-renders)."""
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def soft_shadow(widget: QWidget, color_rgba: str = "rgba(20,30,50,0.10)") -> None:
    """Apply a subtle drop shadow (QSS can't do shadows on arbitrary frames)."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(22)
    effect.setXOffset(0)
    effect.setYOffset(4)
    effect.setColor(QColor(0, 0, 0, 28))
    widget.setGraphicsEffect(effect)


def heading(text: str, level: int = 1) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("H1" if level == 1 else "H2")
    return lbl


def muted(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Muted")
    return lbl


class StatCard(QFrame):
    """A dashboard summary card: title, big value, small hint, accent stripe."""

    def __init__(self, title: str, accent: str = "#2f6bd8") -> None:
        super().__init__()
        self.setObjectName("Card")
        self.setMinimumHeight(108)
        self._accent = accent

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stripe = QFrame()
        self._stripe.setFixedWidth(5)
        self._stripe.setStyleSheet(self._stripe_qss(accent))
        root.addWidget(self._stripe)

        body = QVBoxLayout()
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(5)
        self._title = QLabel(title)
        self._title.setObjectName("CardTitle")
        self._value = QLabel("–")
        self._value.setObjectName("CardValue")
        self._hint = QLabel("")
        self._hint.setObjectName("CardHint")
        self._hint.setWordWrap(True)
        body.addWidget(self._title)
        body.addWidget(self._value)
        body.addWidget(self._hint)
        body.addStretch(1)
        root.addLayout(body, 1)

        soft_shadow(self)

    def set_value(self, text: str, color: str | None = None) -> None:
        self._value.setText(text)
        if color:
            self._value.setStyleSheet(f"color: {color};")

    def set_hint(self, text: str) -> None:
        self._hint.setText(text)

    @staticmethod
    def _stripe_qss(color: str) -> str:
        # Match the card's corner radius exactly so the stripe and card edge align
        # (set in one place so __init__ and set_accent can never drift apart).
        return (f"background: {color}; border-top-left-radius: {RADIUS_CARD}px; "
                f"border-bottom-left-radius: {RADIUS_CARD}px;")

    def set_accent(self, color: str) -> None:
        self._accent = color
        self._stripe.setStyleSheet(self._stripe_qss(color))


class Pill(QLabel):
    """A small coloured status pill (e.g. 'noch 6 Monate', 'überfällig')."""

    def __init__(self, text: str, fg: str, bg: str) -> None:
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            f"color: {fg}; background: {bg}; border-radius: 9px; "
            f"padding: 3px 10px; font-size: 12px; font-weight: 600;"
        )


def pill_cell(pill: Pill) -> QWidget:
    """Wrap a Pill in a left-aligned cell widget for a table status column."""
    wrap = QWidget()
    layout = QHBoxLayout(wrap)
    layout.setContentsMargins(6, 2, 6, 2)
    layout.addWidget(pill)
    layout.addStretch(1)
    return wrap


def align_table_headers(table: QTableWidget, right_cols=()) -> None:
    """Left-align header labels to match left-aligned text data; right-align the
    given (money) columns so header and figures line up under each other."""
    table.horizontalHeader().setDefaultAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    for col in right_cols:
        item = table.horizontalHeaderItem(col)
        if item is not None:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)


class TablePanel(QWidget):
    """A table that shows a friendly centered empty-state when it has no rows.

    The table and the placeholder share a QStackedLayout; call
    :meth:`update_state` after (re)filling the table to switch between them.
    """

    def __init__(self, table: QTableWidget, message: str, hint: str = "") -> None:
        super().__init__()
        self._table = table
        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)

        placeholder = QFrame()
        placeholder.setObjectName("Card")
        box = QVBoxLayout(placeholder)
        box.addStretch(1)
        title = QLabel(message)
        title.setObjectName("H2")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(title)
        if hint:
            sub = QLabel(hint)
            sub.setObjectName("Muted")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setWordWrap(True)
            box.addWidget(sub)
        box.addStretch(1)

        self._stack.addWidget(table)        # index 0: data
        self._stack.addWidget(placeholder)  # index 1: empty
        self.update_state()

    def update_state(self) -> None:
        self._stack.setCurrentIndex(1 if self._table.rowCount() == 0 else 0)
