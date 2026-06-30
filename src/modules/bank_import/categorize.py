"""Rule-based, learning expense categorisation — deterministic and fully local.

A category is suggested by matching the normalised payee+purpose against a list
of rules. User-taught rules (from the database) win over the built-in German
seed set. Matching is whole-word (space padded) so a short pattern like ``dm``
cannot accidentally fire inside ``admin`` or ``gmbh``.

No network, no model — just transparent string rules the user can inspect and
edit, the same data-frugal idea as the Mijonex house assistant.
"""

from __future__ import annotations

from modules.bank_import.model import (
    CAT_LEARNED,
    CAT_NONE,
    CAT_RULE,
    BankTransaction,
    normalize,
)

DEFAULT_CATEGORY = "Sonstiges"

# Built-in German starter rules: (pattern, expense category). Patterns are
# matched as whole words against the normalised payee+purpose. Kept specific
# enough to avoid obvious false positives; the user's learned rules refine this.
SEED_RULES: list[tuple[str, str]] = [
    # --- Lebensmittel (groceries) ---
    ("rewe", "Lebensmittel"), ("edeka", "Lebensmittel"), ("aldi", "Lebensmittel"),
    ("lidl", "Lebensmittel"), ("kaufland", "Lebensmittel"), ("penny", "Lebensmittel"),
    ("netto", "Lebensmittel"), ("real", "Lebensmittel"), ("famila", "Lebensmittel"),
    ("denns", "Lebensmittel"), ("alnatura", "Lebensmittel"), ("nahkauf", "Lebensmittel"),
    ("supermarkt", "Lebensmittel"), ("baeckerei", "Lebensmittel"),
    ("backerei", "Lebensmittel"), ("metzgerei", "Lebensmittel"), ("wochenmarkt", "Lebensmittel"),
    # --- Tanken (fuel) ---
    ("aral", "Tanken"), ("shell", "Tanken"), ("esso", "Tanken"), ("total", "Tanken"),
    ("agip", "Tanken"), ("avia", "Tanken"), ("omv", "Tanken"), ("hem", "Tanken"),
    ("star tankstelle", "Tanken"), ("tankstelle", "Tanken"), ("tanken", "Tanken"),
    # --- Freizeit (leisure / eating out / subscriptions) ---
    ("netflix", "Freizeit"), ("spotify", "Freizeit"), ("disney", "Freizeit"),
    ("dazn", "Freizeit"), ("sky", "Freizeit"), ("steam", "Freizeit"),
    ("playstation", "Freizeit"), ("nintendo", "Freizeit"), ("twitch", "Freizeit"),
    ("youtube premium", "Freizeit"), ("kino", "Freizeit"), ("cinemaxx", "Freizeit"),
    ("cineplex", "Freizeit"), ("restaurant", "Freizeit"), ("mcdonald", "Freizeit"),
    ("burger king", "Freizeit"), ("kfc", "Freizeit"), ("subway", "Freizeit"),
    ("pizzeria", "Freizeit"), ("doener", "Freizeit"), ("doner", "Freizeit"),
    ("starbucks", "Freizeit"), ("fitnessstudio", "Freizeit"), ("mcfit", "Freizeit"),
    ("clever fit", "Freizeit"),
    # --- Kleidung (clothing) ---
    ("h m", "Kleidung"), ("zalando", "Kleidung"), ("zara", "Kleidung"),
    ("c a", "Kleidung"), ("about you", "Kleidung"), ("primark", "Kleidung"),
    ("deichmann", "Kleidung"), ("snipes", "Kleidung"), ("kik", "Kleidung"),
    ("s oliver", "Kleidung"), ("esprit", "Kleidung"),
    # --- Drogerie (drugstore) ---
    ("dm", "Drogerie"), ("rossmann", "Drogerie"), ("mueller", "Drogerie"),
    ("muller", "Drogerie"), ("drogerie", "Drogerie"), ("douglas", "Drogerie"),
    # --- Gesundheit (health) ---
    ("apotheke", "Gesundheit"), ("zahnarzt", "Gesundheit"), ("arztpraxis", "Gesundheit"),
    ("physiotherapie", "Gesundheit"), ("optiker", "Gesundheit"), ("fielmann", "Gesundheit"),
    # --- Haushalt (household / furniture / DIY) ---
    ("ikea", "Haushalt"), ("obi", "Haushalt"), ("bauhaus", "Haushalt"),
    ("hornbach", "Haushalt"), ("toom", "Haushalt"), ("xxxlutz", "Haushalt"),
    ("poco", "Haushalt"), ("hoeffner", "Haushalt"), ("hoffner", "Haushalt"),
    ("action", "Haushalt"), ("tedi", "Haushalt"),
]


def _matches(pattern: str, padded_text: str) -> bool:
    """Whole-word containment: pattern must appear as complete word(s)."""
    return pattern != "" and f" {pattern} " in padded_text


def learned_pattern(payee: str) -> str:
    """Normalised pattern stored when the user teaches a category for a payee."""
    return normalize(payee)


class Categorizer:
    """Suggests an expense category for a transaction from learned + seed rules."""

    def __init__(self, learned_rules: list[tuple[str, str]] | None = None) -> None:
        # Learned rules first (highest priority), pre-normalised; drop empties.
        self._learned = [(normalize(p), c) for p, c in (learned_rules or []) if normalize(p)]
        self._seed = [(normalize(p), c) for p, c in SEED_RULES]

    def categorize(self, t: BankTransaction) -> BankTransaction:
        """Fill ``category`` / ``category_confidence`` on the transaction in place."""
        if t.is_income:
            # Income goes to an income source, which has no expense category.
            t.category = ""
            t.category_confidence = CAT_NONE
            return t
        padded = f" {normalize(t.payee + ' ' + t.purpose)} "
        for pat, cat in self._learned:
            if _matches(pat, padded):
                t.category, t.category_confidence = cat, CAT_LEARNED
                return t
        for pat, cat in self._seed:
            if _matches(pat, padded):
                t.category, t.category_confidence = cat, CAT_RULE
                return t
        t.category, t.category_confidence = DEFAULT_CATEGORY, CAT_NONE
        return t

    def categorize_all(self, transactions: list[BankTransaction]) -> list[BankTransaction]:
        for t in transactions:
            self.categorize(t)
        return transactions
