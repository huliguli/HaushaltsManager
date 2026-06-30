"""Rule-based, learning expense categorisation — deterministic and fully local.

A category is suggested by matching the normalised payee+purpose against an
ordered rule list. User-taught rules (from the database) win over the built-in
German seed set (see :mod:`modules.bank_import.seed_rules`).

Matching modes
--------------
* **Word-prefix** (default): a pattern matches when it starts at a word
  boundary, open-ended — so ``"mcdonald"`` also catches ``"MCDONALDS BERLIN"``
  and city/branch suffixes, which plain whole-word matching misses. This is the
  key to a high hit rate on real statements, where merchant names are glued to
  numbers, cities and legal-form suffixes.
* **Whole-word** (for patterns in :data:`WHOLE_WORD_ONLY`): short or
  common-word tokens (``dm``, ``total``, ``netto`` …) match only as a complete
  word, so ``"dm"`` never fires inside ``"admin"`` and ``"total"`` never inside
  ``"Totalbetrag"``.

The first matching rule wins, so the disambiguation block at the top of the seed
list (e.g. ``"amazon prime"`` before ``"amazon"``, ``"uber eats"`` before
``"uber"``) is what keeps look-alikes apart.

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
from modules.bank_import.seed_rules import SEED_RULES, WHOLE_WORD_ONLY

DEFAULT_CATEGORY = "Sonstiges"


def _whole_word(pattern: str, padded_text: str) -> bool:
    """Pattern must appear as one or more complete words (space padded)."""
    return pattern != "" and f" {pattern} " in padded_text


def _word_prefix(pattern: str, padded_text: str) -> bool:
    """Pattern must start at a word boundary; the end is open.

    ``padded_text`` is space-padded, so a leading space marks a word start. The
    open end lets a brand token also match its plural/suffix forms
    (``"mcdonald"`` -> ``"mcdonalds"``, ``"rossmann"`` -> ``"rossmann1234"``).
    """
    return pattern != "" and f" {pattern}" in padded_text


def learned_pattern(payee: str) -> str:
    """Normalised pattern stored when the user teaches a category for a payee."""
    return normalize(payee)


class Categorizer:
    """Suggests an expense category for a transaction from learned + seed rules."""

    def __init__(self, learned_rules: list[tuple[str, str]] | None = None) -> None:
        # Learned rules first (highest priority), pre-normalised; drop empties.
        # They use word-prefix matching (a taught payee is distinctive enough).
        self._learned = [(normalize(p), c) for p, c in (learned_rules or []) if normalize(p)]
        # Each seed rule carries whether it must match whole-word, decided once.
        self._seed = [
            (norm, c, norm in WHOLE_WORD_ONLY)
            for norm, c in ((normalize(p), c) for p, c in SEED_RULES)
            if norm
        ]

    def categorize(self, t: BankTransaction) -> BankTransaction:
        """Fill ``category`` / ``category_confidence`` on the transaction in place."""
        if t.is_income:
            # Income goes to an income source, which has no expense category.
            t.category = ""
            t.category_confidence = CAT_NONE
            return t
        padded = f" {normalize(t.payee + ' ' + t.purpose)} "
        for pat, cat in self._learned:
            if _word_prefix(pat, padded):
                t.category, t.category_confidence = cat, CAT_LEARNED
                return t
        for pat, cat, whole in self._seed:
            if (whole and _whole_word(pat, padded)) or (not whole and _word_prefix(pat, padded)):
                t.category, t.category_confidence = cat, CAT_RULE
                return t
        t.category, t.category_confidence = DEFAULT_CATEGORY, CAT_NONE
        return t

    def categorize_all(self, transactions: list[BankTransaction]) -> list[BankTransaction]:
        for t in transactions:
            self.categorize(t)
        return transactions
