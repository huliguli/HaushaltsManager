"""Small reusable UI building blocks: cards, section headers, layout helpers."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QColor


def clear_layout(layout: QLayout) -> None:
    """Remove and delete every item in a layout (for full re-renders)."""
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def card() -> QFrame:
    frame = QFrame()
    frame.setObjectName("Card")
    return frame


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


def faint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Faint")
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
        self._stripe.setStyleSheet(
            f"background: {accent}; border-top-left-radius: 14px; "
            f"border-bottom-left-radius: 14px;"
        )
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

    def set_accent(self, color: str) -> None:
        self._accent = color
        self._stripe.setStyleSheet(
            f"background: {color}; border-top-left-radius: 14px; "
            f"border-bottom-left-radius: 14px;"
        )


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
