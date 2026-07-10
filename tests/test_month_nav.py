"""Widget tests for the MonthNavigator (offscreen Qt platform).

The navigator carries real behaviour now (Heute button, month/year picker,
public step()), so the state transitions are pinned down here — the pure
month arithmetic itself lives in dates.shift_month and is tested there.
"""

import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# The QApplication must stay referenced for the whole module lifetime: an
# unreferenced instance gets garbage-collected while widgets still exist,
# which crashes the interpreter (segfault, not a test failure).
_APP = None


def _navigator(**kwargs):
    global _APP
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - Qt unavailable in this env
        import pytest
        pytest.skip(f"Qt nicht verfügbar: {exc}")
    _APP = QApplication.instance() or QApplication([])
    from ui import theme
    from ui.widgets.month_nav import MonthNavigator
    return MonthNavigator(theme.palette("light"), **kwargs)


def test_step_respects_future_limit():
    today = date.today()
    nav = _navigator(allow_future=False)
    nav.step(1)  # would leave the current month towards the future
    assert nav.year_month() == (today.year, today.month)
    nav.step(-1)
    prev = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    assert nav.year_month() == prev


def test_step_allows_future_when_enabled():
    today = date.today()
    nav = _navigator(allow_future=True)
    nav.step(1)
    nxt = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    assert nav.year_month() == nxt


def test_today_button_and_go_today():
    today = date.today()
    nav = _navigator(allow_future=False)
    assert not nav._today_btn.isVisibleTo(nav)  # on the current month: hidden
    nav.step(-1)
    assert nav._today_btn.isVisibleTo(nav)      # off the current month: shown
    emitted = []
    nav.month_changed.connect(lambda y, m: emitted.append((y, m)))
    nav.go_today()
    assert nav.year_month() == (today.year, today.month)
    assert emitted == [(today.year, today.month)]
    nav.go_today()  # already there: must not emit again
    assert emitted == [(today.year, today.month)]


def test_picker_disables_future_months():
    from ui.widgets.month_nav import _MonthPickerPopup

    today = date.today()
    nav = _navigator(allow_future=False)
    popup = _MonthPickerPopup(nav)
    # In the current year every month after the current one must be disabled.
    for i, btn in enumerate(popup._month_btns):
        expected = (i + 1) <= today.month
        assert btn.isEnabled() == expected
    # Stepping into a past year enables all twelve months.
    popup._shift_year(-1)
    assert all(btn.isEnabled() for btn in popup._month_btns)
    popup.close()


def test_picker_choose_emits_and_updates():
    from ui.widgets.month_nav import _MonthPickerPopup

    nav = _navigator(allow_future=False)
    popup = _MonthPickerPopup(nav)
    popup._shift_year(-1)
    emitted = []
    nav.month_changed.connect(lambda y, m: emitted.append((y, m)))
    popup._choose(3)
    year = date.today().year - 1
    assert nav.year_month() == (year, 3)
    assert emitted == [(year, 3)]
