"""Dialog to choose when a planned savings plan should start.

The user picks the start month (current, next, or any future month); the plan
then runs for its term from that month, so it is planned into exactly the right
(possibly future) months. A live summary shows the resulting from–to range.
"""

from __future__ import annotations

from datetime import date

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from modules import dates, planning
from modules.money import format_eur
from ui.widgets.common import primary_button

# How many months into the future the start can be chosen (current + N-1 ahead).
_START_CHOICES = 36


def _months_label(n: int) -> str:
    return "1 Monat" if n == 1 else f"{n} Monate"


class SavingsStartDialog(QDialog):
    """Pick the start month for a savings plan and confirm planning it."""

    def __init__(self, colors: dict, monthly_cents: int, months: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sparplan einplanen")
        self.setModal(True)
        self.setMinimumWidth(470)
        self._months = int(months)
        self._monthly = int(monthly_cents)
        today = date.today()
        self.start_year, self.start_month = today.year, today.month

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)

        header = QLabel("Sparplan einplanen")
        header.setObjectName("H2")
        root.addWidget(header)
        intro = QLabel(
            f"Sparrate {format_eur(self._monthly)} / Monat über {_months_label(self._months)}. "
            f"Wähle, ab wann der Sparplan laufen soll – er wird als Fixposten "
            f"(Kategorie „Sparen“) nur in den betroffenen Monaten eingeplant.")
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        root.addWidget(intro)

        start_label = QLabel("Start des Sparplans")
        start_label.setObjectName("FieldLabel")
        root.addWidget(start_label)

        self.combo = QComboBox()
        self.combo.setAccessibleName("Startmonat des Sparplans")
        for i in range(_START_CHOICES):
            y, m = dates.shift_month(today.year, today.month, i)
            label = f"{dates.month_name(m)} {y}"
            if i == 0:
                label += "  (aktueller Monat)"
            elif i == 1:
                label += "  (nächster Monat)"
            self.combo.addItem(label, (y, m))
        self.combo.currentIndexChanged.connect(self._update_summary)
        root.addWidget(self.combo)

        self.summary = QLabel()
        self.summary.setObjectName("Faint")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        root.addStretch(1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Abbrechen")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        ok = primary_button("Einplanen", colors)
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        root.addLayout(buttons)

        self._update_summary()

    def start_date(self) -> date:
        """First day of the chosen start month."""
        return date(self.start_year, self.start_month, 1)

    def _update_summary(self) -> None:
        y, m = self.combo.currentData()
        end = dates.parse_date(planning.term_end_iso(date(y, m, 1), self._months))
        self.summary.setText(
            f"Läuft von {dates.month_name(m)} {y} bis "
            f"{dates.month_name(end.month)} {end.year} ({_months_label(self._months)}).")

    def _accept(self) -> None:
        self.start_year, self.start_month = self.combo.currentData()
        self.accept()
