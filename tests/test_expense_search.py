"""Search over the whole book, not just the newest rows.

The view used to load the 5000 most recent expenses and filter them in Python,
so an older booking was reported as "not found" — with no hint that the list had
been truncated. These tests pin the SQL-side search down.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _repo(tmp_path):
    from modules.db_handler.database import Database
    from modules.db_handler.repositories import VariableExpenseRepository

    db = Database(tmp_path / "search.db")
    return db, VariableExpenseRepository(db)


def test_search_finds_bookings_beyond_the_old_5000_row_window(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from modules.models import VariableExpense

    db, expenses = _repo(tmp_path)
    # One old, distinctive booking ...
    expenses.add(VariableExpense(date="2019-01-05", amount_cents=1234,
                                 category="Sonstiges", description="Nadel im Heuhaufen"))
    # ... buried under more than 5000 newer ones.
    rows = [VariableExpense(date="2026-03-01", amount_cents=500,
                            category="Lebensmittel", description="Heu").to_params()
            for _ in range(5200)]
    db.conn.executemany(
        "INSERT INTO variable_expenses (date, amount_cents, category, description, "
        "receipt_path, recurring, recur_interval_months, recur_end) "
        "VALUES (:date, :amount_cents, :category, :description, :receipt_path, "
        ":recurring, :recur_interval_months, :recur_end)", rows)
    db.conn.commit()

    hits = expenses.search("Nadel")
    assert len(hits) == 1, "die alte Buchung muss gefunden werden"
    assert hits[0].description == "Nadel im Heuhaufen"
    assert expenses.count_search("Nadel") == 1
    db.close()


def test_search_covers_category_and_amount_not_only_the_description(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from modules.models import VariableExpense

    db, expenses = _repo(tmp_path)
    expenses.add(VariableExpense(date="2026-08-01", amount_cents=4285,
                                 category="Lebensmittel", description="Supermarkt"))
    expenses.add(VariableExpense(date="2026-08-02", amount_cents=6740,
                                 category="Auto & Tanken", description="Tankstelle"))

    # By description
    assert len(expenses.search("supermarkt")) == 1
    # By category name — previously impossible
    assert len(expenses.search("tanken")) == 1
    # By amount, typed the German way — previously impossible
    assert len(expenses.search("42,85")) == 1
    assert expenses.search("42,85")[0].description == "Supermarkt"
    # A term that matches nothing stays empty
    assert expenses.search("gibtesnicht") == []
    db.close()


def test_search_can_be_combined_with_a_category_filter(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from modules.models import VariableExpense

    db, expenses = _repo(tmp_path)
    expenses.add(VariableExpense(date="2026-08-01", amount_cents=1000,
                                 category="Lebensmittel", description="Markt"))
    expenses.add(VariableExpense(date="2026-08-02", amount_cents=2000,
                                 category="Freizeit & Unterhaltung", description="Markt"))

    both = expenses.search("Markt")
    assert len(both) == 2
    only_food = expenses.search("Markt", category="Lebensmittel")
    assert len(only_food) == 1
    assert only_food[0].amount_cents == 1000
    assert expenses.count_search("Markt", category="Lebensmittel") == 1
    db.close()


def test_empty_search_returns_everything_up_to_the_render_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from modules.models import VariableExpense

    db, expenses = _repo(tmp_path)
    for i in range(5):
        expenses.add(VariableExpense(date=f"2026-08-0{i + 1}", amount_cents=100 * (i + 1),
                                     category="Sonstiges", description=f"Nr {i}"))
    assert len(expenses.search("")) == 5
    assert expenses.count_search("") == 5
    # The limit caps rendering, and the count still reports the truth.
    assert len(expenses.search("", limit=2)) == 2
    assert expenses.count_search("") == 5
    db.close()
