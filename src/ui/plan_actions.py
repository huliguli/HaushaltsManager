"""User-facing flow for adding a planned savings plan or loan to the Haushaltsbuch.

Each action first asks for confirmation (showing the exact amounts and term),
then creates the entries via :mod:`modules.planning`, and finally offers an
immediate one-click undo. The created rows also stay editable/deletable in the
Fixkosten and Kredite views, so undoing is possible later too.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox

from modules import dates, planning
from modules.money import format_eur


def _until_label(months: int) -> str:
    """German 'Monat Jahr' of the last month of an ``months``-long term."""
    y, m = dates.shift_month(dates.today().year, dates.today().month, max(1, int(months)) - 1)
    return f"{dates.month_name(m)} {y}"


def _offer_undo(parent, title: str, text: str, undo_fn) -> None:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(title)
    box.setText(text)
    undo_btn = box.addButton("Rückgängig", QMessageBox.ButtonRole.DestructiveRole)
    box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
    box.exec()
    if box.clickedButton() is undo_btn:
        undo_fn()


def confirm_and_plan_savings(parent, ctx, monthly_cents: int, months: int) -> None:
    """Confirm, then plan a savings rate as a fixed cost; offer to undo."""
    if monthly_cents <= 0:
        return
    until = _until_label(months)
    msg = (
        f"Diesen Sparplan zum Haushaltsbuch hinzufügen?\n\n"
        f"Es wird eine monatliche Sparrate von {format_eur(monthly_cents)} als "
        f"Fixposten (Kategorie „Sparen“) über {int(months)} Monate (bis {until}) "
        f"eingeplant.\n\nDu kannst ihn jederzeit wieder rückgängig machen.")
    if QMessageBox.question(parent, "Zum Haushaltsbuch hinzufügen", msg) \
            != QMessageBox.StandardButton.Yes:
        return
    fixed_id = planning.plan_savings(ctx.fixed, monthly_cents, months)
    ctx.notify_changed()

    def undo() -> None:
        planning.unplan_savings(ctx.fixed, fixed_id)
        ctx.notify_changed()

    _offer_undo(
        parent, "Sparplan eingeplant",
        f"Der Sparplan ({format_eur(monthly_cents)} / Monat, bis {until}) wurde als "
        f"Fixposten angelegt.\nDu findest ihn unter Haushaltsbuch → Fixkosten.",
        undo)


def confirm_and_plan_credit(parent, ctx, *, name: str, total_cents: int | None,
                            monthly_cents: int, term_months: int,
                            interest_rate: float | None, category: str) -> None:
    """Confirm, then plan a loan as a Credit + linked fixed cost; offer to undo."""
    if monthly_cents <= 0 or term_months <= 0:
        QMessageBox.information(
            parent, "Nicht möglich",
            "Für diese Finanzierung liegt keine gültige Monatsrate oder Laufzeit vor.")
        return
    until = _until_label(term_months)
    rate_txt = ""
    if interest_rate:
        rate_txt = f", {interest_rate:.2f} % Zinsen".replace(".", ",")
    total_txt = f"{format_eur(total_cents)} " if total_cents else ""
    msg = (
        f"Diesen Kredit zum Haushaltsbuch hinzufügen?\n\n"
        f"{name}: {total_txt}Monatsrate {format_eur(monthly_cents)} über "
        f"{int(term_months)} Monate (bis {until}){rate_txt}.\n\n"
        f"Er wird unter „Kredite“ angelegt und die Monatsrate als Fixposten "
        f"(Kategorie „Kredit“) eingeplant.\nDu kannst ihn jederzeit wieder "
        f"rückgängig machen.")
    if QMessageBox.question(parent, "Zum Haushaltsbuch hinzufügen", msg) \
            != QMessageBox.StandardButton.Yes:
        return
    credit_id, _fixed_id = planning.plan_credit(
        ctx.credits, ctx.fixed, name=name, total_cents=total_cents,
        monthly_cents=monthly_cents, term_months=term_months,
        interest_rate=interest_rate, category=category)
    ctx.notify_changed()

    def undo() -> None:
        planning.unplan_credit(ctx.credits, ctx.fixed, credit_id)
        ctx.notify_changed()

    _offer_undo(
        parent, "Kredit eingeplant",
        f"„{name}“ ({format_eur(monthly_cents)} / Monat, bis {until}) wurde unter "
        f"Kredite angelegt und als Fixposten eingeplant.",
        undo)
