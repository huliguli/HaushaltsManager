"""Custom update dialog.

Replaces a QMessageBox (whose background follows the OS dark/light mode and
clashed with the app's stylesheet, making the text unreadable). This dialog is
fully app-styled, so it stays readable in both themes, shows the changelog in a
scrollable area, and uses clean German button labels.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from app_meta import APP_VERSION
from ui import icons


class UpdateDialog(QDialog):
    """Shows an available update with changelog and three choices.

    After ``exec()`` read :attr:`choice` — one of ``"install"``, ``"skip"`` or
    ``"later"`` (the default if the dialog is just closed).
    """

    def __init__(self, info, colors: dict, parent=None) -> None:
        super().__init__(parent)
        self.choice = "later"
        c = colors
        self.setWindowTitle("Update verfügbar")
        self.setModal(True)
        self.setMinimumSize(520, 470)
        self.setStyleSheet(f"QDialog {{ background: {c['bg']}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(14)

        # Header: icon + headline
        header = QHBoxLayout()
        header.setSpacing(12)
        icon = QLabel()
        icon.setPixmap(icons.pixmap("download", c["primary"], 30))
        header.addWidget(icon)
        head_text = QVBoxLayout()
        head_text.setSpacing(2)
        title = QLabel(f"Version {info.version} ist verfügbar")
        title.setStyleSheet(f"color: {c['text']}; font-size: 18px; font-weight: 700;")
        sub = QLabel(f"Installiert: Version {APP_VERSION}")
        sub.setStyleSheet(f"color: {c['text_muted']}; font-size: 13px;")
        head_text.addWidget(title)
        head_text.addWidget(sub)
        header.addLayout(head_text)
        header.addStretch(1)
        root.addLayout(header)

        # Changelog
        notes_label = QLabel("Änderungen in dieser Version")
        notes_label.setStyleSheet(
            f"color: {c['text_muted']}; font-size: 12px; font-weight: 600;")
        root.addWidget(notes_label)

        notes = QTextEdit()
        notes.setReadOnly(True)
        try:
            notes.setMarkdown(info.notes or "")
        except Exception:  # noqa: BLE001 - fall back to plain text
            notes.setPlainText(info.notes or "")
        notes.setStyleSheet(
            f"QTextEdit {{ background: {c['surface']}; color: {c['text']}; "
            f"border: 1px solid {c['border']}; border-radius: 10px; padding: 8px; }}")
        root.addWidget(notes, 1)

        # Buttons
        buttons = QHBoxLayout()
        later = QPushButton("Später")
        later.setObjectName("Ghost")
        later.clicked.connect(lambda: self._choose("later"))
        skip = QPushButton("Diese Version überspringen")
        skip.setObjectName("Danger")
        skip.clicked.connect(lambda: self._choose("skip"))
        install = QPushButton("Jetzt aktualisieren")
        install.setObjectName("Primary")
        install.clicked.connect(lambda: self._choose("install"))
        buttons.addWidget(later)
        buttons.addStretch(1)
        buttons.addWidget(skip)
        buttons.addWidget(install)
        root.addLayout(buttons)

    def _choose(self, value: str) -> None:
        self.choice = value
        self.accept()
