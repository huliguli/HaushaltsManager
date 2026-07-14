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


def _page_header(title: str, subtitle: str) -> QWidget:
    """Titel + Untertitel einer Wizard-Seite als app-gestylte Labels.

    Bewusst NICHT ``QWizardPage.setTitle/setSubTitle``: diesen Kopfbereich
    zeichnet der Plattform-Style mit der SYSTEM-Palette. Im Windows-Dunkelmodus
    ist er dadurch dunkel, während das App-Stylesheet die Textfarbe des hellen
    Themes erzwingt — Ergebnis: dunkelblauer Text auf dunkelgrauem Grund
    (unlesbar). Eigene Labels folgen dem App-Theme in hell UND dunkel.
    (Gleiche Fehlerklasse wie der QMessageBox-Dunkelmodus-Fehler aus v1.0.3.)
    """
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 6)
    layout.setSpacing(2)
    heading = QLabel(title)
    heading.setObjectName("H2")
    sub = QLabel(subtitle)
    sub.setObjectName("Muted")
    sub.setWordWrap(True)
    layout.addWidget(heading)
    layout.addWidget(sub)
    return box


class _CollectPage(QWizardPage):
    """A wizard page that collects a list of models via an add dialog."""

    def __init__(self, title: str, subtitle: str, add_factory: Callable,
                 formatter: Callable, parent=None) -> None:
        super().__init__(parent)
        self._add_factory = add_factory
        self._formatter = formatter
        self.items: list = []

        layout = QVBoxLayout(self)
        layout.addWidget(_page_header(title, subtitle))
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
        # ClassicStyle: zeichnet keinen Style-Header (siehe _page_header) —
        # damit folgt der ganze Assistent dem App-Theme statt dem OS-Modus.
        self.setWizardStyle(QWizard.WizardStyle.ClassicStyle)
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
        layout = QVBoxLayout(page)
        layout.addWidget(_page_header(
            "Willkommen beim HaushaltsManager",
            "In drei kurzen Schritten ist alles eingerichtet."))
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
