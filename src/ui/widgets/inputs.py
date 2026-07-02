"""Form input widgets: German money field and a labelled-field helper."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QLineEdit, QVBoxLayout, QWidget

from modules.money import format_eur, try_parse_eur


class MoneyLineEdit(QLineEdit):
    """Line edit that accepts German/plain money input and self-formats.

    Use :meth:`cents` to read the parsed integer-cent value (``None`` if the
    field is empty or invalid) and :meth:`set_cents` to populate it.
    """

    def __init__(self, cents: int | None = None, placeholder: str = "0,00") -> None:
        super().__init__()
        self.setPlaceholderText(placeholder)
        if cents is not None:
            self.set_cents(cents)
        self.editingFinished.connect(self._reformat)

    def cents(self) -> int | None:
        return try_parse_eur(self.text())

    def set_cents(self, cents: int | None) -> None:
        self.setText("" if cents is None else format_eur(cents, symbol=False))

    def _reformat(self) -> None:
        value = self.cents()
        if value is not None:
            self.setText(format_eur(value, symbol=False))


def labelled(label_text: str, widget: QWidget, *, hint: str = "") -> QWidget:
    """Wrap a widget with a small caption label above it (and optional hint).

    The caption is also wired to the input for accessibility: a screen reader
    announces the field's name (and hint) instead of just "text field". Because
    every dialog/calculator field routes through here, one change makes the whole
    app's forms navigable without sight (WCAG 1.3.1 / 4.1.2).
    """
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)

    caption = QLabel(label_text)
    caption.setObjectName("FieldLabel")
    caption.setBuddy(widget)
    widget.setAccessibleName(label_text)
    layout.addWidget(caption)
    layout.addWidget(widget)

    if hint:
        hint_lbl = QLabel(hint)
        hint_lbl.setObjectName("Faint")
        hint_lbl.setWordWrap(True)
        layout.addWidget(hint_lbl)
        widget.setAccessibleDescription(hint)

    # Expose the inner widget for convenient access.
    container.inner = widget  # type: ignore[attr-defined]
    return container
