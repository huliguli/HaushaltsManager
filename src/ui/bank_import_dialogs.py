"""Dialogs for the bank-statement import: CSV column mapping and review/confirm.

Both follow the app's QSS object names (H2/Primary/Ghost) so they pick up the
light/dark theme automatically. No data leaves the machine here either.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules import dates
from modules.bank_import.model import (
    CAT_LEARNED,
    CAT_NONE,
    CAT_RULE,
    BankTransaction,
    normalize,
)
from modules.models import EXPENSE_CATEGORIES
from modules.money import format_eur
from ui.widgets.inputs import labelled

# Confidence -> (short label, traffic-light key) for the category indicator.
_CONF_LABEL = {
    CAT_LEARNED: ("gelernt", "green"),
    CAT_RULE: ("Regel", "blue"),
    "guess": ("Vermutung", "amber"),
    CAT_NONE: ("offen", "grey"),
}


class BankCsvMappingDialog(QDialog):
    """Map CSV columns to bank fields; optionally load/save a per-bank profile."""

    _FIELDS = [
        ("date", "Datum"),
        ("amount", "Betrag (mit Vorzeichen)"),
        ("debit", "Soll / Belastung"),
        ("credit", "Haben / Gutschrift"),
        ("payee", "Empfänger"),
        ("purpose", "Verwendungszweck"),
    ]

    def __init__(self, headers, rows, guess, profiles_repo, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kontoauszug (CSV) – Spalten zuordnen")
        self.setModal(True)
        self.setMinimumSize(780, 560)
        self._headers = headers
        self._profiles = profiles_repo
        self._saved_name = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)
        title = QLabel("CSV-Spalten zuordnen")
        title.setObjectName("H2")
        root.addWidget(title)
        root.addWidget(QLabel(
            "Ordne die Spalten zu. Entweder eine Betragsspalte mit Vorzeichen "
            "ODER getrennte Soll/Haben-Spalten."))

        # Saved profiles.
        prof_row = QHBoxLayout()
        self._profile_box = QComboBox()
        self._profile_box.addItem("— Profil wählen —", None)
        for name in (profiles_repo.list_names() if profiles_repo else []):
            self._profile_box.addItem(name, name)
        self._profile_box.currentIndexChanged.connect(self._load_profile)
        prof_row.addWidget(labelled("Gespeichertes Bank-Profil", self._profile_box))
        prof_row.addStretch(1)
        root.addLayout(prof_row)

        # Field -> column combos.
        self._combos: dict[str, QComboBox] = {}
        grid = QHBoxLayout()
        col_a = QVBoxLayout()
        col_b = QVBoxLayout()
        for i, (key, label) in enumerate(self._FIELDS):
            combo = QComboBox()
            combo.addItem("— keine —", None)
            for ci, h in enumerate(headers):
                combo.addItem(f"{ci + 1}: {h or '(leer)'}", ci)
            if guess.get(key) is not None:
                idx = combo.findData(guess[key])
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            self._combos[key] = combo
            (col_a if i % 2 == 0 else col_b).addWidget(labelled(label, combo))
        grid.addLayout(col_a, 1)
        grid.addLayout(col_b, 1)
        root.addLayout(grid)

        # Preview.
        preview = QTableWidget(min(len(rows), 6), len(headers))
        preview.setHorizontalHeaderLabels([str(h) for h in headers])
        preview.verticalHeader().setVisible(False)
        preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for r in range(min(len(rows), 6)):
            for c in range(len(headers)):
                val = rows[r][c] if c < len(rows[r]) else ""
                preview.setItem(r, c, QTableWidgetItem("" if val is None else str(val)))
        preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(QLabel("Vorschau:"))
        root.addWidget(preview, 1)

        self._error = QLabel("")
        self._error.setStyleSheet("color: #d6453d;")
        self._error.hide()
        root.addWidget(self._error)

        buttons = QHBoxLayout()
        save_btn = QPushButton("Als Profil speichern…")
        save_btn.setObjectName("Ghost")
        save_btn.clicked.connect(self._save_profile)
        buttons.addWidget(save_btn)
        buttons.addStretch(1)
        cancel = QPushButton("Abbrechen")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Weiter")
        ok.setObjectName("Primary")
        ok.clicked.connect(self._accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        root.addLayout(buttons)

    def mapping(self) -> dict[str, int | None]:
        return {k: c.currentData() for k, c in self._combos.items()}

    def saved_profile_name(self) -> str:
        return self._saved_name

    def _set_mapping(self, mapping: dict) -> None:
        for key, combo in self._combos.items():
            idx = combo.findData(mapping.get(key))
            combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _load_profile(self) -> None:
        name = self._profile_box.currentData()
        if not name or not self._profiles:
            return
        import json
        raw = self._profiles.get(name)
        if raw:
            try:
                self._set_mapping(json.loads(raw))
            except (ValueError, TypeError):
                pass

    def _save_profile(self) -> None:
        if not self._valid():
            return
        name, ok = QInputDialog.getText(self, "Profil speichern", "Name des Bank-Profils:")
        if ok and name.strip() and self._profiles:
            import json
            self._profiles.upsert(name.strip(), json.dumps(self.mapping()))
            self._saved_name = name.strip()

    def _valid(self) -> bool:
        m = self.mapping()
        if m.get("amount") is None and m.get("debit") is None and m.get("credit") is None:
            self._error.setText("Bitte eine Betragsspalte oder Soll/Haben zuordnen.")
            self._error.show()
            return False
        return True

    def _accept(self) -> None:
        if self._valid():
            self.accept()


class BankReviewDialog(QDialog):
    """Review parsed transactions, adjust categories, confirm into the book."""

    _COLS = ["", "Datum", "Betrag", "Empfänger", "Verwendungszweck", "Art", "Kategorie"]

    def __init__(self, transactions: list[BankTransaction], skipped: int,
                 colors: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kontoauszug prüfen und übernehmen")
        self.setModal(True)
        self.setMinimumSize(1040, 640)
        self._txs = transactions
        self._colors = colors
        self._checks: list[QCheckBox] = []
        self._combos: list[QComboBox] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(12)
        title = QLabel("Erkannte Buchungen")
        title.setObjectName("H2")
        root.addWidget(title)

        n_in = sum(1 for t in transactions if t.is_income)
        n_out = len(transactions) - n_in
        info = QLabel(
            f"{len(transactions)} neue Buchungen: {n_out} Ausgaben, {n_in} Einnahmen."
            + (f"  ·  {skipped} bereits importiert (übersprungen)." if skipped else "")
            + "  Ausgaben sind vorausgewählt; Einnahmen werden als Einnahmequelle "
            "angelegt (für regelmäßige Einnahmen).")
        info.setObjectName("Muted")
        info.setWordWrap(True)
        root.addWidget(info)

        bar = QHBoxLayout()
        sel_all = QPushButton("Alle auswählen")
        sel_all.setObjectName("Ghost")
        sel_all.clicked.connect(lambda: self._set_all(True))
        sel_none = QPushButton("Alle abwählen")
        sel_none.setObjectName("Ghost")
        sel_none.clicked.connect(lambda: self._set_all(False))
        same_payee = QPushButton("Kategorie auf gleichen Empfänger übertragen")
        same_payee.setObjectName("Ghost")
        same_payee.clicked.connect(self._apply_same_payee)
        bar.addWidget(sel_all)
        bar.addWidget(sel_none)
        bar.addWidget(same_payee)
        bar.addStretch(1)
        root.addLayout(bar)

        self.table = QTableWidget(len(transactions), len(self._COLS))
        self.table.setHorizontalHeaderLabels(self._COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # Taller rows so the category combo cell-widget has room to show its
        # current text (a cramped row clips it to an empty-looking box).
        self.table.verticalHeader().setDefaultSectionSize(40)
        for r, t in enumerate(transactions):
            self._build_row(r, t)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3, 5):
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        # Category hosts a combo cell-widget that ResizeToContents cannot measure
        # -> fixed width so the category name is fully readable.
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        # Wide enough for the longest category name ("Essen Bestellen & Fast
        # Food") plus the dropdown arrow (ResizeToContents cannot measure it).
        self.table.setColumnWidth(6, 270)
        root.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Abbrechen")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Ausgewählte übernehmen")
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        root.addLayout(buttons)

    def _build_row(self, r: int, t: BankTransaction) -> None:
        chk = QCheckBox()
        chk.setChecked(not t.is_income)  # expenses pre-selected, income opt-in
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(12, 0, 0, 0)
        hl.addWidget(chk)
        self.table.setCellWidget(r, 0, holder)
        self._checks.append(chk)

        self.table.setItem(r, 1, self._ro(dates.format_date(t.booking_date) or "—"))

        amt = self._ro(format_eur(t.amount_cents, plus=t.is_income), right=True)
        amt.setForeground(QColor(self._colors["green"] if t.is_income else self._colors["red"]))
        self.table.setItem(r, 2, amt)

        self.table.setItem(r, 3, self._ro(t.payee or "—"))
        self.table.setItem(r, 4, self._ro(t.purpose or "—"))
        self.table.setItem(r, 5, self._ro("Einnahme" if t.is_income else "Ausgabe"))

        if t.is_income:
            self._combos.append(None)  # income has no category
            self.table.setItem(r, 6, self._ro("(Einnahmequelle)"))
        else:
            cell = QWidget()
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(6, 2, 8, 2)
            cl.setSpacing(8)
            label_text, key = _CONF_LABEL.get(t.category_confidence, _CONF_LABEL[CAT_NONE])
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {self._colors.get(key, self._colors['grey'])}; font-size: 12px;")
            dot.setToolTip(f"Vorschlag: {label_text}")
            combo = QComboBox()
            combo.setObjectName("CellCombo")
            combo.addItems(EXPENSE_CATEGORIES)
            if t.category in EXPENSE_CATEGORIES:
                combo.setCurrentText(t.category)
            cl.addWidget(dot)
            cl.addWidget(combo, 1)
            self.table.setCellWidget(r, 6, cell)
            self._combos.append(combo)

    @staticmethod
    def _ro(text: str, right: bool = False) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if right:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    def _set_all(self, value: bool) -> None:
        for chk in self._checks:
            chk.setChecked(value)

    def _apply_same_payee(self) -> None:
        """Copy the current row's category to all rows with the same payee."""
        row = self.table.currentRow()
        if row < 0 or self._combos[row] is None:
            return
        target_cat = self._combos[row].currentText()
        key = normalize(self._txs[row].payee)
        if not key:
            return
        for i, t in enumerate(self._txs):
            if self._combos[i] is not None and normalize(t.payee) == key:
                self._combos[i].setCurrentText(target_cat)

    def accepted_transactions(self) -> list[BankTransaction]:
        """Selected transactions with their final (combo) category applied."""
        out: list[BankTransaction] = []
        for i, t in enumerate(self._txs):
            if not self._checks[i].isChecked():
                continue
            if self._combos[i] is not None:
                t.category = self._combos[i].currentText()
            out.append(t)
        return out


class ImportRulesDialog(QDialog):
    """Manage the learned/manual categorisation rules (view, edit, add, delete)."""

    def __init__(self, rules_repo, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kategorisierungs-Regeln")
        self.setModal(True)
        self.setMinimumSize(620, 520)
        self._repo = rules_repo

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(12)
        title = QLabel("Kategorisierungs-Regeln")
        title.setObjectName("H2")
        root.addWidget(title)
        hint = QLabel("Diese Regeln ordnen einen Empfänger automatisch einer Kategorie "
                      "zu. Sie entstehen aus deinen Korrekturen beim Import und lassen "
                      "sich hier anpassen.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        root.addWidget(hint)

        from PyQt6.QtWidgets import QLineEdit
        add = QHBoxLayout()
        self._pattern = QLineEdit()
        self._pattern.setPlaceholderText("Empfänger oder Stichwort")
        self._cat = QComboBox()
        self._cat.addItems(EXPENSE_CATEGORIES)
        add_btn = QPushButton("Hinzufügen")
        add_btn.setObjectName("Primary")
        add_btn.clicked.connect(self._add)
        add.addWidget(self._pattern, 1)
        add.addWidget(self._cat)
        add.addWidget(add_btn)
        root.addLayout(add)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Muster", "Kategorie", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # Taller rows so the category combo cell-widget shows its text.
        self.table.verticalHeader().setDefaultSectionSize(40)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        head.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(1, 240)
        root.addWidget(self.table, 1)
        self._reload()

        close = QPushButton("Schließen")
        close.setObjectName("Ghost")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        root.addLayout(row)

    def _reload(self) -> None:
        rules = self._repo.list_full()
        self.table.setRowCount(len(rules))
        for r, rule in enumerate(rules):
            item = QTableWidgetItem(rule["pattern"])
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 0, item)
            combo = QComboBox()
            combo.setObjectName("CellCombo")
            combo.addItems(EXPENSE_CATEGORIES)
            if rule["category"] in EXPENSE_CATEGORIES:
                combo.setCurrentText(rule["category"])
            combo.currentTextChanged.connect(
                lambda cat, pat=rule["pattern"], learned=rule["learned"]:
                self._repo.upsert(pat, cat, learned=bool(learned)))
            self.table.setCellWidget(r, 1, combo)
            btn = QPushButton("Löschen")
            btn.setObjectName("Danger")
            btn.clicked.connect(lambda _c, rid=rule["id"]: self._delete(rid))
            wrap = QWidget()
            wl = QHBoxLayout(wrap)
            wl.setContentsMargins(6, 2, 6, 2)
            wl.addWidget(btn)
            self.table.setCellWidget(r, 2, wrap)

    def _add(self) -> None:
        pattern = normalize(self._pattern.text())
        if pattern:
            self._repo.upsert(pattern, self._cat.currentText(), learned=False)
            self._pattern.clear()
            self._reload()

    def _delete(self, rule_id: int) -> None:
        self._repo.delete(rule_id)
        self._reload()


class BankProfilesDialog(QDialog):
    """View and delete saved CSV bank-import column profiles."""

    def __init__(self, profiles_repo, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bank-Profile (CSV)")
        self.setModal(True)
        self.setMinimumSize(460, 420)
        self._repo = profiles_repo

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(12)
        title = QLabel("Gespeicherte Bank-Profile")
        title.setObjectName("H2")
        root.addWidget(title)
        hint = QLabel("Spalten-Zuordnungen, die du beim CSV-Import gespeichert hast.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Profil", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table, 1)
        self._reload()

        close = QPushButton("Schließen")
        close.setObjectName("Ghost")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        root.addLayout(row)

    def _reload(self) -> None:
        profiles = self._repo.list_full()
        self.table.setRowCount(len(profiles))
        for r, p in enumerate(profiles):
            item = QTableWidgetItem(p["name"])
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 0, item)
            btn = QPushButton("Löschen")
            btn.setObjectName("Danger")
            btn.clicked.connect(lambda _c, pid=p["id"]: self._delete(pid))
            wrap = QWidget()
            wl = QHBoxLayout(wrap)
            wl.setContentsMargins(6, 2, 6, 2)
            wl.addWidget(btn)
            self.table.setCellWidget(r, 1, wrap)

    def _delete(self, profile_id: int) -> None:
        self._repo.delete(profile_id)
        self._reload()
