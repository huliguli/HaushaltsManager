"""Shared application context: services + a Qt signal bus.

A single ``AppContext`` is created at startup and passed to every view. It owns
the database, repositories and config, exposes the current theme palette, and
provides two signals views use to stay in sync:

    * ``data_changed`` — emitted after any data mutation; views refresh.
    * ``theme_changed`` — emitted when the user toggles light/dark.
"""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QObject, pyqtSignal

from modules import budget, interop
from modules.config import Config
from modules.db_handler.database import Database
from modules.db_handler.repositories import (
    BankProfileRepository,
    CategoryBudgetRepository,
    CreditRepository,
    FixedCostRepository,
    ImportLogRepository,
    ImportRuleRepository,
    IncomeRepository,
    MonthlySummaryRepository,
    PotMovementRepository,
    PotRepository,
    SavingsAccountRepository,
    SavingsGoalRepository,
    SettingsRepository,
    SubscriptionIgnoreRepository,
    VariableExpenseRepository,
    VariableIncomeRepository,
)
from modules.logging_setup import get_logger
from modules.models import BudgetOverview
from ui import theme


class AppContext(QObject):
    data_changed = pyqtSignal()
    theme_changed = pyqtSignal(str)
    # Drilldown: a chart element was clicked; the main window switches to the
    # Haushaltsbuch with (year, month, category) applied ("" = all categories).
    drilldown_requested = pyqtSignal(int, int, str)
    # "Verwalten" on the dashboard Töpfe card: jump to Haushaltsbuch → Töpfe.
    pots_requested = pyqtSignal()

    def __init__(self, db: Database, config: Config) -> None:
        super().__init__()
        self.db = db
        self.config = config
        self.log = get_logger("ui")

        self.income = IncomeRepository(db)
        self.var_income = VariableIncomeRepository(db)
        self.fixed = FixedCostRepository(db)
        self.expenses = VariableExpenseRepository(db)
        self.credits = CreditRepository(db)
        self.settings = SettingsRepository(db)
        self.summaries = MonthlySummaryRepository(db)
        self.budgets = CategoryBudgetRepository(db)
        self.import_rules = ImportRuleRepository(db)
        self.import_log = ImportLogRepository(db)
        self.bank_profiles = BankProfileRepository(db)
        self.goals = SavingsGoalRepository(db)
        self.sub_ignores = SubscriptionIgnoreRepository(db)
        self.savings_accounts = SavingsAccountRepository(db)
        self.pots = PotRepository(db)
        self.pot_moves = PotMovementRepository(db)

        # Sister-app discovery once per session (fail-silent by contract).
        self.sister = interop.discover_sister()

    # -- theme --------------------------------------------------------------
    @property
    def theme_name(self) -> str:
        return self.config.theme

    @property
    def colors(self) -> dict:
        return theme.palette(self.config.theme)

    def set_theme(self, name: str) -> None:
        self.config.theme = name
        self.theme_changed.emit(name)

    # -- data events --------------------------------------------------------
    def notify_changed(self) -> None:
        """Signal that data was mutated so open views can refresh."""
        # Keep the published expense contract in step with every mutation
        # (cheap full rebuild; never raises — see modules.interop).
        interop.refresh_ausgaben_monat(self.db, self.fixed, self.expenses)
        self.data_changed.emit()

    def request_drilldown(self, year: int, month: int, category: str = "") -> None:
        """Jump to the Haushaltsbuch expenses filtered to (year, month[, category])."""
        self.drilldown_requested.emit(year, month, category or "")

    def request_pots(self) -> None:
        """Jump to the Haushaltsbuch Töpfe tab."""
        self.pots_requested.emit()

    # -- convenience aggregates --------------------------------------------
    def overview(self, year: int | None = None, month: int | None = None) -> BudgetOverview:
        today = date.today()
        return budget.compute_overview(
            self.income, self.fixed, self.expenses,
            year or today.year, month or today.month,
            var_income_repo=self.var_income,
        )
