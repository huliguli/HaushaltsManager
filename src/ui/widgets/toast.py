"""Transient bottom toast with an undo action.

Deleting a row used to be final the moment the confirm dialog closed. The
toast keeps the deleted dataclass alive for a few seconds and re-inserts it
on "Rückgängig" — no schema, no tombstone rows, works for every entity that
has a repository ``add``. Only one toast is visible at a time; a new one
replaces the previous (whose undo window has then passed).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from ui.widgets.common import soft_shadow

_VISIBLE_MS = 6000


class Toast(QFrame):
    _active: "Toast | None" = None

    def __init__(self, window: QWidget, text: str, action_text: str, on_action) -> None:
        super().__init__(window)
        self.setObjectName("Card")
        row = QHBoxLayout(self)
        row.setContentsMargins(18, 10, 10, 10)
        row.setSpacing(14)
        label = QLabel(text)
        row.addWidget(label)
        btn = QPushButton(action_text)
        btn.setObjectName("Ghost")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self._run(on_action))
        row.addWidget(btn)
        soft_shadow(self)
        self.adjustSize()
        # Bottom-centred over the window content; positioned once at show time
        # (the short lifetime makes resize tracking not worth the complexity).
        self.move((window.width() - self.width()) // 2,
                  window.height() - self.height() - 26)
        self.show()
        self.raise_()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._timer.start(_VISIBLE_MS)

    def _run(self, fn) -> None:
        self.dismiss()
        fn()

    def dismiss(self) -> None:
        if Toast._active is self:
            Toast._active = None
        self._timer.stop()
        self.hide()
        self.deleteLater()


def show_undo(anchor: QWidget, text: str, on_undo) -> None:
    """Show 'text' with a Rückgängig button at the bottom of anchor's window."""
    window = anchor.window()
    if window is None:  # detached widget (should not happen in the app)
        return
    if Toast._active is not None:
        Toast._active.dismiss()
    Toast._active = Toast(window, text, "Rückgängig", on_undo)
