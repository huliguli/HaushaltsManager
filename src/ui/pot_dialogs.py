"""Dialogs for Töpfe: savings account, pot, booking and transfer.

Each dialog builds a validated model / result and carries the guidance the
feature lives on: the pot's monthly rate mirrors a real standing order at the
bank ("richte einen Dauerauftrag über dieselbe Rate ein, dann stimmt der Topf
von allein"), movements cover everything irregular.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QRadioButton, QWidget

from modules import dates
from modules.models import Pot, PotMovement, SavingsAccount
from modules.money import format_eur
from ui.dialogs import _BaseDialog, _opt_date
from ui.widgets.inputs import MoneyLineEdit, labelled


class AccountDialog(_BaseDialog):
    """Add or edit a savings account (name + recorded balance)."""

    def __init__(self, item: SavingsAccount | None = None, parent: QWidget | None = None) -> None:
        super().__init__("Sparkonto bearbeiten" if item and item.id
                         else "Sparkonto anlegen", parent)
        self._id = item.id if item else None

        self.name = QLineEdit(item.name if item else "")
        self.name.setPlaceholderText("z. B. Sparkonto ING")
        self.balance = MoneyLineEdit(item.balance_cents if item else None)
        bal_date = (item.balance_date if item and item.balance_date
                    else dates.to_iso(dates.today()))
        self.balance_date = QLineEdit(dates.format_date(bal_date))
        self.note = QLineEdit(item.note if item else "")

        self.add_row(labelled("Bezeichnung", self.name))
        self.add_row(labelled("Aktueller Kontostand", self.balance,
                              hint="Der Stand laut Bank – die Töpfe verteilen "
                                   "diese Summe. Gelegentlich aktualisieren."),
                     labelled("Stand vom", self.balance_date))
        self.add_row(labelled("Notiz (optional)", self.note))

    def build(self) -> None:
        name = self.name.text().strip()
        if not name:
            raise ValueError("Bitte eine Bezeichnung eingeben.")
        balance = self.balance.cents()
        if balance is None:
            raise ValueError("Bitte den aktuellen Kontostand eingeben (0 ist erlaubt).")
        self.result_model = SavingsAccount(
            id=self._id, name=name, balance_cents=balance,
            balance_date=_opt_date(self.balance_date.text()) or dates.to_iso(dates.today()),
            note=self.note.text().strip())


class PotDialog(_BaseDialog):
    """Add or edit a pot. ``start_cents`` (add only) becomes an initial booking."""

    def __init__(self, accounts, goals, item: Pot | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__("Topf bearbeiten" if item and item.id else "Topf anlegen", parent)
        self._id = item.id if item else None
        self.start_cents = 0  # filled by build() when creating

        self.account = QComboBox()
        for acc in accounts:
            self.account.addItem(acc.name, acc.id)
        if item:
            index = self.account.findData(item.account_id)
            if index >= 0:
                self.account.setCurrentIndex(index)
        self.name = QLineEdit(item.name if item else "")
        self.name.setPlaceholderText("z. B. Urlaub, Notgroschen, Auto")
        self.monthly = MoneyLineEdit(
            item.monthly_cents if item and item.monthly_cents else None,
            placeholder="keine Rate")
        rate_start = (item.rate_start if item and item.rate_start
                      else dates.to_iso(dates.today()))
        self.rate_start = QLineEdit(dates.format_date(rate_start))
        self.goal = QComboBox()
        self.goal.addItem("– kein Sparziel –", None)
        for goal in goals:
            self.goal.addItem(
                f"{goal.name} ({format_eur(goal.target_cents)})", goal.id)
        if item and item.goal_id is not None:
            index = self.goal.findData(item.goal_id)
            if index >= 0:
                self.goal.setCurrentIndex(index)
        self.initial = None
        if not item:
            self.initial = MoneyLineEdit(None, placeholder="0,00")
        self.note = QLineEdit(item.note if item else "")

        self.add_row(labelled("Sparkonto", self.account),
                     labelled("Bezeichnung", self.name))
        self.add_row(labelled(
            "Monatsrate (optional)", self.monthly,
            hint="Tipp: Richte bei deiner Bank einen Dauerauftrag über genau "
                 "diese Rate auf das Sparkonto ein – dann wächst der Topf hier "
                 "von allein und stimmt immer mit der Bank überein."),
            labelled("Rate zählt ab", self.rate_start))
        if self.initial is not None:
            self.add_row(labelled(
                "Schon vorhandener Betrag (optional)", self.initial,
                hint="Was von der Konto-Summe JETZT schon zu diesem Topf "
                     "gehört – wird als erste Buchung eingetragen."),
                labelled("Sparziel verknüpfen (optional)", self.goal))
        else:
            self.add_row(labelled("Sparziel verknüpfen (optional)", self.goal))
        self.add_row(labelled("Notiz (optional)", self.note))

    def build(self) -> None:
        name = self.name.text().strip()
        if not name:
            raise ValueError("Bitte eine Bezeichnung eingeben.")
        if self.account.currentData() is None:
            raise ValueError("Bitte zuerst ein Sparkonto anlegen.")
        monthly = self.monthly.cents() or 0
        if monthly < 0:
            raise ValueError("Die Monatsrate darf nicht negativ sein.")
        rate_start = _opt_date(self.rate_start.text()) or dates.to_iso(dates.today())
        if self.initial is not None:
            start = self.initial.cents() or 0
            if start < 0:
                raise ValueError("Der vorhandene Betrag darf nicht negativ sein.")
            self.start_cents = start
        self.result_model = Pot(
            id=self._id, account_id=self.account.currentData(), name=name,
            monthly_cents=monthly, rate_start=rate_start,
            goal_id=self.goal.currentData(), note=self.note.text().strip())


class MovementDialog(_BaseDialog):
    """One explicit booking: Einzahlung (+) oder Entnahme (−)."""

    def __init__(self, pots, preselect_pot_id: int | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__("Topf-Buchung", parent)

        self.pot = QComboBox()
        for pot in pots:
            self.pot.addItem(pot.name, pot.id)
        if preselect_pot_id is not None:
            index = self.pot.findData(preselect_pot_id)
            if index >= 0:
                self.pot.setCurrentIndex(index)
        self.kind_in = QRadioButton("Einzahlung")
        self.kind_out = QRadioButton("Entnahme")
        self.kind_in.setChecked(True)
        kind_wrap = QWidget()
        kind_row = QHBoxLayout(kind_wrap)
        kind_row.setContentsMargins(0, 0, 0, 0)
        kind_row.addWidget(self.kind_in)
        kind_row.addWidget(self.kind_out)
        kind_row.addStretch(1)
        self.amount = MoneyLineEdit(None)
        self.date = QLineEdit(dates.format_date(dates.to_iso(dates.today())))
        self.note = QLineEdit("")
        self.note.setPlaceholderText("z. B. Autoreparatur, Weihnachtsgeld")

        self.add_row(labelled("Topf", self.pot), labelled("Art", kind_wrap))
        self.add_row(labelled("Betrag", self.amount), labelled("Datum", self.date))
        self.add_row(labelled(
            "Notiz (optional)", self.note,
            hint="Nur für Sonderfälle nötig – die Monatsrate des Topfs "
                 "läuft automatisch weiter."))

    def build(self) -> None:
        if self.pot.currentData() is None:
            raise ValueError("Bitte zuerst einen Topf anlegen.")
        amount = self.amount.cents()
        if amount is None or amount <= 0:
            raise ValueError("Bitte einen Betrag größer als 0 eingeben.")
        signed = amount if self.kind_in.isChecked() else -amount
        self.result_model = PotMovement(
            pot_id=self.pot.currentData(),
            date=_opt_date(self.date.text()) or dates.to_iso(dates.today()),
            amount_cents=signed, note=self.note.text().strip())


class TransferDialog(_BaseDialog):
    """Move money between two pots (one atomic double booking)."""

    def __init__(self, pots, parent: QWidget | None = None) -> None:
        super().__init__("Zwischen Töpfen umbuchen", parent)
        self.src = QComboBox()
        self.dst = QComboBox()
        for pot in pots:
            self.src.addItem(pot.name, pot.id)
            self.dst.addItem(pot.name, pot.id)
        if self.dst.count() > 1:
            self.dst.setCurrentIndex(1)
        self.amount = MoneyLineEdit(None)
        self.note = QLineEdit("")

        self.add_row(labelled("Von Topf", self.src), labelled("Nach Topf", self.dst))
        self.add_row(labelled("Betrag", self.amount),
                     labelled("Notiz (optional)", self.note))

    def build(self) -> None:
        src, dst = self.src.currentData(), self.dst.currentData()
        if src is None or dst is None:
            raise ValueError("Es braucht mindestens zwei Töpfe zum Umbuchen.")
        if src == dst:
            raise ValueError("Bitte zwei verschiedene Töpfe wählen.")
        amount = self.amount.cents()
        if amount is None or amount <= 0:
            raise ValueError("Bitte einen Betrag größer als 0 eingeben.")
        self.result = (src, dst, amount, self.note.text().strip())