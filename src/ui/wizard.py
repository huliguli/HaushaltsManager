"""Quick-setup wizard: guided first-run entry of income, fixed costs, expenses.

Collects items in memory across three pages (reusing the standard add dialogs)
and commits them to the database only when the user finishes. It can be
re-opened any time from Settings or Import/Export.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from modules.money import format_eur
from ui.dialogs import ExpenseDialog, FixedCostDialog, IncomeDialog


class _CollectPage(QWizardPage):
    """A wizard page that collects a list of models via an add dialog."""

    def __init__(self, title: str, subtitle: str, add_factory: Callable,
                 formatter: Callable, parent=None) -> None:
        super().__init__(parent)
        self.setTitle(title)
        self.setSubTitle(subtitle)
        self._add_factory = add_factory
        self._formatter = formatter
        self.items: list = []

        layout = QVBoxLayout(self)
        self.list = QListWidget()
        layout.addWidget(self.list, 1)

        buttons = QHBoxLayout()
        add = QPushButton("+ Hinzufügen")
        add.setObjectName("Primary")
        add.clicked.connect(self._add)
        remove = QPushButton("Entfernen")
        remove.setObjectName("Ghost")
        remove.clicked.connect(self._remove)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        layout.addLayout(buttons)

    def _add(self) -> None:
        dlg = self._add_factory(self)
        if dlg.exec():
            self.items.append(dlg.result_model)
            self._refresh()

    def _remove(self) -> None:
        row = self.list.currentRow()
        if 0 <= row < len(self.items):
            del self.items[row]
            self._refresh()

    def _refresh(self) -> None:
        self.list.clear()
        for item in self.items:
            self.list.addItem(self._formatter(item))


class QuickSetupWizard(QWizard):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Quick-Setup")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setMinimumSize(560, 480)
        self.setButtonText(QWizard.WizardButton.NextButton, "Weiter")
        self.setButtonText(QWizard.WizardButton.BackButton, "Zurück")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Fertig")
        self.setButtonText(QWizard.WizardButton.CancelButton, "Abbrechen")

        self.addPage(self._intro())
        self.income_page = _CollectPage(
            "Schritt 1 – Einnahmen", "Trage deine monatlichen Einnahmequellen ein.",
            lambda p: IncomeDialog(parent=p),
            lambda i: f"{i.name} · {format_eur(i.amount_cents)}")
        self.fixed_page = _CollectPage(
            "Schritt 2 – Fixkosten", "Erfasse deine laufenden Fixkosten (z. B. Miete, Strom).",
            lambda p: FixedCostDialog(parent=p),
            lambda i: f"{i.name} · {format_eur(i.amount_cents)} · {i.category}")
        self.expense_page = _CollectPage(
            "Schritt 3 – Erste Ausgaben (optional)", "Optional: erste variable Ausgaben.",
            lambda p: ExpenseDialog(parent=p),
            lambda i: f"{i.category} · {format_eur(i.amount_cents)}")
        self.addPage(self.income_page)
        self.addPage(self.fixed_page)
        self.addPage(self.expense_page)

    def _intro(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Willkommen beim HaushaltsManager")
        page.setSubTitle("In drei kurzen Schritten ist alles eingerichtet.")
        layout = QVBoxLayout(page)
        text = QLabel(
            "Dieser Assistent hilft dir, deine Finanzen einzurichten:\n\n"
            "  1.  Einnahmen  (z. B. Gehalt, Minijob)\n"
            "  2.  Fixkosten  (z. B. Miete, Versicherungen)\n"
            "  3.  Erste Ausgaben  (optional)\n\n"
            "Du kannst alles später jederzeit ändern. Bestehende Daten lassen sich "
            "außerdem unter „Import / Export“ aus Excel oder PDF einlesen.")
        text.setWordWrap(True)
        layout.addWidget(text)
        layout.addStretch(1)
        return page

    def commit(self, ctx) -> dict:
        """Persist all collected items. Returns a small count summary."""
        counts = {"income": 0, "fixed": 0, "expenses": 0}
        for item in self.income_page.items:
            ctx.income.add(item)
            counts["income"] += 1
        for item in self.fixed_page.items:
            ctx.fixed.add(item)
            counts["fixed"] += 1
        for item in self.expense_page.items:
            ctx.expenses.add(item)
            counts["expenses"] += 1
        ctx.config.set("wizard_completed", True)
        ctx.notify_changed()
        return counts


def run_wizard(ctx, parent=None) -> bool:
    """Show the wizard and commit on finish. Returns True if completed."""
    wizard = QuickSetupWizard(parent)
    if wizard.exec():
        wizard.commit(ctx)
        return True
    return False
