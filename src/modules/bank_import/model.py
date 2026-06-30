"""The unified transaction model plus text-normalisation and de-dup hashing.

Every parser (CAMT/MT940/CSV/PDF) emits :class:`BankTransaction` objects so the
categoriser, the de-dup layer and the review UI all speak one language. Amounts
are signed integer cents: positive = money in (income), negative = money out
(expense) — consistent with the rest of the app's cent arithmetic.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

# Parse confidence: how sure we are the row was read correctly.
CONFIDENCE_HIGH = "high"      # structured format (CAMT/MT940/clean CSV)
CONFIDENCE_MEDIUM = "medium"  # CSV with guessed columns
CONFIDENCE_LOW = "low"        # PDF text / OCR best-effort

# Category confidence: where the category suggestion came from.
CAT_LEARNED = "learned"       # a rule the user taught us
CAT_RULE = "rule"             # a built-in seed rule
CAT_GUESS = "guess"           # weak keyword guess
CAT_NONE = "none"             # no idea -> default category


@dataclass
class BankTransaction:
    booking_date: str                 # ISO YYYY-MM-DD
    amount_cents: int                 # signed: + income / - expense
    payee: str = ""                   # counterparty name
    purpose: str = ""                 # remittance info / Verwendungszweck
    value_date: str | None = None     # ISO, optional
    reference: str = ""               # EndToEndId / bank ref (for de-dup)
    source_format: str = ""           # 'camt' | 'mt940' | 'csv' | 'pdf'
    confidence: str = CONFIDENCE_HIGH
    raw: str = ""                     # original snippet (debug / review tooltip)
    # --- filled in by the categoriser / review UI ---
    category: str = ""                # expense category (for expenses)
    category_confidence: str = CAT_NONE
    selected: bool = True             # whether to import this row

    @property
    def is_income(self) -> bool:
        return self.amount_cents > 0

    @property
    def kind(self) -> str:
        return "income" if self.is_income else "expense"

    @property
    def abs_cents(self) -> int:
        return abs(self.amount_cents)


# Placeholder references some banks emit instead of a real unique id; treating
# them as "no reference" forces the content-based hash so two genuinely
# different transactions are not collapsed into one.
_PLACEHOLDER_REFS = {"", "notprovided", "nonref", "na", "n/a", "0", "-"}


def normalize(text: str | None) -> str:
    """Lower-case, strip accents/punctuation and collapse whitespace.

    Used both for de-dup keys and for matching categorisation rules against the
    payee/purpose, so "REWE SAGT DANKE 12345" and "rewe sagt danke" align.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def transaction_hash(t: BankTransaction) -> str:
    """Stable hash identifying a transaction across re-imports (de-dup).

    Prefers the bank's own reference; falls back to date + signed amount +
    normalised payee + purpose when the reference is missing or a placeholder.
    """
    ref = (t.reference or "").strip().lower()
    if ref and ref not in _PLACEHOLDER_REFS:
        basis = f"ref:{ref}"
    else:
        basis = "|".join((
            t.booking_date, str(t.amount_cents),
            normalize(t.payee), normalize(t.purpose),
        ))
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()
