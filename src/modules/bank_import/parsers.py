"""Statement parsers — all local, all defensive.

Supported: CAMT.053 (ISO 20022 XML), MT940 (SWIFT text), CSV (with an explicit
column mapping) and PDF (best-effort text extraction). Every entry point caps
the input size and raises :class:`BankImportError` with a human message instead
of letting a malformed/hostile file crash the app.

Security notes:
    * XML is parsed with defusedxml and ``forbid_dtd=True`` — no DTD means no
      external entities and no entity-expansion ("billion laughs") attack.
    * No parser opens a network connection or touches anything outside the file.
"""

from __future__ import annotations

import csv as _csv
import io
import re
from pathlib import Path

from defusedxml.ElementTree import parse as _defused_parse

from modules.bank_import.model import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    BankTransaction,
)
from modules.money import MoneyParseError, parse_eur

# Input size ceilings (defence against decompression/parse bombs).
_MAX_TEXT_BYTES = 20 * 1024 * 1024     # CAMT / MT940 / CSV
_MAX_PDF_BYTES = 60 * 1024 * 1024


class BankImportError(Exception):
    """Raised when a statement cannot be read; carries a user-facing message."""


def _check_size(path: str | Path, cap: int) -> None:
    try:
        size = Path(path).stat().st_size
    except OSError as exc:
        raise BankImportError(f"Datei nicht lesbar: {exc}") from exc
    if size > cap:
        raise BankImportError(
            f"Die Datei ist zu groß ({size // (1024 * 1024)} MB). "
            f"Maximal {cap // (1024 * 1024)} MB werden verarbeitet.")
    if size == 0:
        raise BankImportError("Die Datei ist leer.")


def _read_text(path: str | Path) -> str:
    """Read a text statement, trying UTF-8 then the common German codepages."""
    data = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


# --- date helpers ----------------------------------------------------------
_DATE_PATTERNS = (
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})"), (1, 2, 3)),          # ISO
    (re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})"), (3, 2, 1)),        # DD.MM.YYYY
    (re.compile(r"^(\d{2})\.(\d{2})\.(\d{2})$"), (3, 2, 1)),       # DD.MM.YY
    (re.compile(r"^(\d{2})/(\d{2})/(\d{4})"), (3, 2, 1)),          # DD/MM/YYYY
)


def parse_date_flex(text: str | None) -> str | None:
    """Parse a date in ISO / German / slash format to ISO ``YYYY-MM-DD``."""
    if not text:
        return None
    s = str(text).strip()
    for rx, (yi, mi, di) in _DATE_PATTERNS:
        m = rx.match(s)
        if m:
            y, mo, d = m.group(yi), m.group(mi), m.group(di)
            if len(y) == 2:
                y = f"20{y}"
            return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None


# --- format detection ------------------------------------------------------
def detect_format(path: str | Path) -> str:
    """Best guess of the statement format: 'camt' | 'mt940' | 'csv' | 'pdf'."""
    p = Path(path)
    suffix = p.suffix.lower()
    try:
        head_bytes = p.open("rb").read(8192)
    except OSError as exc:
        raise BankImportError(f"Datei nicht lesbar: {exc}") from exc
    if head_bytes[:5] == b"%PDF-" or suffix == ".pdf":
        return "pdf"
    head = head_bytes.decode("utf-8", "replace").lstrip("﻿")
    low = head.lower()
    if head.lstrip().startswith("<?xml") or "<document" in low or "camt.05" in low:
        return "camt"
    if ":20:" in head or ":61:" in head or "\n:86:" in head:
        return "mt940"
    if suffix in (".csv", ".txt") or head.count(";") >= 2 or head.count(",") >= 2:
        return "csv"
    if suffix == ".xml":
        return "camt"
    return "csv"


# --- CAMT.053 (ISO 20022 XML) ----------------------------------------------
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first(elem, name: str):
    for e in elem.iter():
        if _local(e.tag) == name:
            return e
    return None


def _text(elem, name: str) -> str:
    e = _first(elem, name)
    return (e.text or "").strip() if e is not None else ""


def _all_text(elem, name: str) -> str:
    return " ".join(
        (e.text or "").strip() for e in elem.iter()
        if _local(e.tag) == name and e.text)


def _date_in(parent) -> str:
    """ISO date from a CAMT date wrapper (<BookgDt>/<ValDt> -> <Dt>/<DtTm>)."""
    if parent is None:
        return ""
    return parse_date_flex(_text(parent, "Dt") or _text(parent, "DtTm")) or ""


def parse_camt(path: str | Path) -> list[BankTransaction]:
    _check_size(path, _MAX_TEXT_BYTES)
    try:
        tree = _defused_parse(str(path), forbid_dtd=True)
    except Exception as exc:  # noqa: BLE001 - any XML error becomes a clean message
        raise BankImportError(
            "Die CAMT-/XML-Datei konnte nicht gelesen werden "
            f"(beschädigt oder kein gültiges CAMT.053): {exc}") from exc

    root = tree.getroot()
    entries = [e for e in root.iter() if _local(e.tag) == "Ntry"]
    if not entries:
        raise BankImportError("Keine Buchungen (Ntry) in der CAMT-Datei gefunden.")

    out: list[BankTransaction] = []
    for ntry in entries:
        amt_text = _text(ntry, "Amt")
        ind = _text(ntry, "CdtDbtInd").upper()  # DBIT (out) / CRDT (in)
        try:
            cents = parse_eur(amt_text)
        except MoneyParseError:
            continue
        signed = cents if ind == "CRDT" else -cents
        booking = _date_in(_first(ntry, "BookgDt"))
        value = _date_in(_first(ntry, "ValDt")) or None
        # Counterparty: creditor for outgoing, debtor for incoming payments.
        cdtr_el, dbtr_el = _first(ntry, "Cdtr"), _first(ntry, "Dbtr")
        cdtr = _text(cdtr_el, "Nm") if cdtr_el is not None else ""
        dbtr = _text(dbtr_el, "Nm") if dbtr_el is not None else ""
        payee = (dbtr if ind == "CRDT" else cdtr) or cdtr or dbtr
        purpose = _all_text(ntry, "Ustrd") or _text(ntry, "AddtlNtryInf")
        reference = _text(ntry, "EndToEndId") or _text(ntry, "AcctSvcrRef")
        out.append(BankTransaction(
            booking_date=booking or value or "", amount_cents=signed,
            payee=payee.strip(), purpose=purpose.strip(), value_date=value,
            reference=reference.strip(), source_format="camt",
            confidence=CONFIDENCE_HIGH, raw=amt_text))
    if not out:
        raise BankImportError("Aus der CAMT-Datei konnten keine Beträge gelesen werden.")
    return out


# --- MT940 (SWIFT text) ----------------------------------------------------
_MT940_61 = re.compile(
    r"^(?P<vdate>\d{6})(?P<edate>\d{4})?(?P<mark>RC|RD|C|D)(?P<funds>[A-Za-z])?"
    r"(?P<amount>[\d.,]+)N")


def _mt940_sign(mark: str) -> int:
    # C credit(+), D debit(-), RC reversal-of-credit(-), RD reversal-of-debit(+)
    return 1 if mark in ("C", "RD") else -1


def _mt940_field86(text: str) -> tuple[str, str]:
    """Return (payee, purpose) from a :86: field (structured ?nn or free text)."""
    if "?" not in text:
        return "", text.strip()
    parts = re.split(r"\?(\d{2})", text)
    fields: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        fields[parts[i]] = fields.get(parts[i], "") + parts[i + 1]
    purpose = " ".join(fields[k] for k in sorted(fields) if "20" <= k <= "29").strip()
    payee = (fields.get("32", "") + " " + fields.get("33", "")).strip()
    return payee, purpose or fields.get("00", "").strip()


def parse_mt940(path: str | Path) -> list[BankTransaction]:
    _check_size(path, _MAX_TEXT_BYTES)
    return parse_mt940_text(_read_text(path))


def parse_mt940_text(text: str) -> list[BankTransaction]:
    # Join hard-wrapped continuation lines, then split on the field tags.
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[BankTransaction] = []
    current: BankTransaction | None = None
    f86: list[str] = []

    def _flush() -> None:
        if current is not None:
            payee, purpose = _mt940_field86(" ".join(f86))
            current.payee, current.purpose = payee, purpose
            out.append(current)

    for line in lines:
        if line.startswith(":61:"):
            _flush()
            f86 = []
            body = line[4:]
            m = _MT940_61.match(body)
            if not m:
                current = None
                continue
            try:
                cents = parse_eur(m.group("amount"))
            except MoneyParseError:
                current = None
                continue
            yy = m.group("vdate")
            booking = f"20{yy[0:2]}-{yy[2:4]}-{yy[4:6]}"
            current = BankTransaction(
                booking_date=booking, amount_cents=_mt940_sign(m.group("mark")) * cents,
                reference="", source_format="mt940", confidence=CONFIDENCE_HIGH, raw=line)
        elif line.startswith(":86:") and current is not None:
            f86.append(line[4:])
        elif current is not None and f86 and not line.startswith(":"):
            f86.append(line)  # continuation of :86:
    _flush()
    if not out:
        raise BankImportError("Keine MT940-Buchungen (:61:) in der Datei gefunden.")
    return out


# --- CSV -------------------------------------------------------------------
_CSV_HINTS = {
    "date": ["buchungstag", "datum", "valuta", "buchung", "wertstellung"],
    "amount": ["betrag", "umsatz", "amount", "wert"],
    "payee": ["empfaenger", "empfänger", "beguenstigter", "begünstigter", "name",
              "auftraggeber", "zahlungsempfaenger", "beguenstigter zahlungsempfaenger"],
    "purpose": ["verwendungszweck", "buchungstext", "umsatztext", "vorgang", "zweck"],
    "debit": ["soll", "belastung", "ausgang"],
    "credit": ["haben", "gutschrift", "eingang"],
}


def read_csv_rows(path: str | Path) -> tuple[list[str], list[list[str]]]:
    """Read a CSV (auto delimiter + encoding); return (headers, data_rows)."""
    _check_size(path, _MAX_TEXT_BYTES)
    text = _read_text(path)
    sample = "\n".join(text.splitlines()[:20])
    try:
        dialect = _csv.Sniffer().sniff(sample, delimiters=";,\t")
        delimiter = dialect.delimiter
    except _csv.Error:
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    reader = _csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [r for r in reader if any((c or "").strip() for c in r)]
    if not rows:
        raise BankImportError("Die CSV-Datei enthält keine Zeilen.")
    return [str(h).strip() for h in rows[0]], [list(r) for r in rows[1:]]


def guess_csv_mapping(headers: list[str]) -> dict[str, int | None]:
    mapping: dict[str, int | None] = {k: None for k in
                                      ("date", "amount", "payee", "purpose", "debit", "credit")}
    lowered = [(i, str(h).strip().lower()) for i, h in enumerate(headers)]
    for field, hints in _CSV_HINTS.items():
        for i, head in lowered:
            if any(hint in head for hint in hints):
                mapping[field] = i
                break
    return mapping


def _cell(row: list, idx: int | None) -> str:
    if idx is None or idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


def parse_csv(data_rows: list[list], mapping: dict[str, int | None]) -> list[BankTransaction]:
    """Build transactions from mapped CSV rows.

    Amount may come from one signed column (``amount``) or from separate
    ``debit``/``credit`` columns. Unparseable rows are skipped, never fatal.
    """
    if mapping.get("amount") is None and mapping.get("debit") is None \
            and mapping.get("credit") is None:
        raise BankImportError("Bitte eine Betrags-Spalte (oder Soll/Haben) zuordnen.")
    out: list[BankTransaction] = []
    for row in data_rows:
        cents = _csv_amount(row, mapping)
        if cents is None or cents == 0:
            continue
        booking = parse_date_flex(_cell(row, mapping.get("date"))) or ""
        out.append(BankTransaction(
            booking_date=booking, amount_cents=cents,
            payee=_cell(row, mapping.get("payee")), purpose=_cell(row, mapping.get("purpose")),
            source_format="csv", confidence=CONFIDENCE_MEDIUM,
            raw=";".join(str(c) for c in row)[:200]))
    if not out:
        raise BankImportError("Aus der CSV-Datei konnten keine Buchungen gelesen werden.")
    return out


def _csv_amount(row: list, mapping: dict[str, int | None]) -> int | None:
    if mapping.get("amount") is not None:
        try:
            return parse_eur(_cell(row, mapping["amount"]))
        except MoneyParseError:
            return None
    debit = _cell(row, mapping.get("debit"))
    credit = _cell(row, mapping.get("credit"))
    try:
        if credit:
            return abs(parse_eur(credit))
        if debit:
            return -abs(parse_eur(debit))
    except MoneyParseError:
        return None
    return None


# --- PDF (best-effort) -----------------------------------------------------
# Inline layout (date and amount on one line) — used as a fallback.
_PDF_DATE = re.compile(r"\b(\d{2}\.\d{2}\.(?:\d{4}|\d{2}))\b")
_PDF_AMOUNT = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}\b")
# A line that is *only* a date / *only* a euro amount — the building blocks of
# the common tabular layout where each posting is serialised as separate lines
# (booking date / text / amount / value date / purpose...).
_PDF_LINE_DATE = re.compile(r"^(?:\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})$")
_PDF_LINE_AMOUNT = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$")
# Description words that mark a summary/info row, not a real posting (so a
# "Neuer Saldo  658,63" line is never imported as a transaction).
_PDF_NON_TX = re.compile(
    r"(?i)\b(saldo|kontostand|freistellungsauftrag|sparer-?pauschbetrag|"
    r"übertrag|uebertrag|zwischensumme|gesamtsumme|summe\b)")
# Page-footer/header lines that can follow the last posting on a page; they must
# not bleed into a transaction's purpose text.
_PDF_FOOTER = re.compile(
    r"(?i)^(girokonto|kontoauszug|auszugsnummer|bic |iban |blatt|seite|"
    r"uebertrag|übertrag|alter saldo|neuer saldo|ing[- ]?diba|herrn|frau|"
    r"datum$|\d{2}gkka)")


def parse_pdf(path: str | Path) -> list[BankTransaction]:
    """Best-effort PDF parsing for both common statement layouts.

    Many bank PDFs (ING, DKB, Sparkasse …) serialise each posting vertically as
    separate lines — booking date, description, amount, value date, then the
    purpose — rather than one line per booking. The primary pass recognises that
    tabular shape; if it finds nothing, a fallback scans for the older
    "date … amount on one line" shape. Results are low-confidence and the review
    screen lets the user fix category and sign before anything is saved.
    """
    _check_size(path, _MAX_PDF_BYTES)
    from modules.file_handler import pdf_import
    try:
        text = pdf_import.extract_text(path)
    except Exception as exc:  # noqa: BLE001
        raise BankImportError(f"Das PDF konnte nicht gelesen werden: {exc}") from exc

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out = _parse_pdf_tabular(lines) or _parse_pdf_inline(lines)
    if not out:
        raise BankImportError(
            "Im PDF wurden keine Buchungszeilen erkannt. Bitte einen CAMT-, "
            "MT940- oder CSV-Export der Bank verwenden.")
    return out


def _parse_pdf_tabular(lines: list[str]) -> list[BankTransaction]:
    """Vertical/tabular layout: rows of [date, text…, amount, date, purpose…].

    A posting is anchored on an amount-only line that has a booking date a few
    lines above (with the description in between) AND a value date directly
    below — the signature of a statement table row. That structural test alone
    excludes balances/totals; a stop-word check on the description is a second
    guard. The amount keeps its own sign (+ credit / − debit).
    """
    n = len(lines)
    out: list[BankTransaction] = []
    for i in range(n):
        if not _PDF_LINE_AMOUNT.match(lines[i]):
            continue
        # Walk back over up to 3 text lines to the booking date.
        desc: list[str] = []
        j = i - 1
        while (j >= 0 and len(desc) < 3
               and not _PDF_LINE_DATE.match(lines[j])
               and not _PDF_LINE_AMOUNT.match(lines[j])):
            desc.insert(0, lines[j])
            j -= 1
        if j < 0 or not _PDF_LINE_DATE.match(lines[j]) or not desc:
            continue
        # The value date must directly follow the amount (table-row signal).
        if i + 1 >= n or not _PDF_LINE_DATE.match(lines[i + 1]):
            continue
        payee = " ".join(desc).strip()
        if _PDF_NON_TX.search(payee):
            continue
        try:
            cents = parse_eur(lines[i])
        except MoneyParseError:
            continue
        if cents == 0:
            continue
        # Purpose: the text lines after the value date, up to the next row.
        purpose: list[str] = []
        k = i + 2
        while (k < n and len(purpose) < 6
               and not _PDF_LINE_DATE.match(lines[k])
               and not _PDF_LINE_AMOUNT.match(lines[k])
               and not _PDF_FOOTER.match(lines[k])):
            purpose.append(lines[k])
            k += 1
        out.append(BankTransaction(
            booking_date=parse_date_flex(lines[j]) or "",
            amount_cents=cents, payee=payee[:140],
            purpose=" ".join(purpose)[:160],
            value_date=parse_date_flex(lines[i + 1]),
            source_format="pdf", confidence=CONFIDENCE_LOW,
            raw=f"{lines[j]} | {payee} | {lines[i]}"[:200]))
    return out


def _parse_pdf_inline(lines: list[str]) -> list[BankTransaction]:
    """Fallback: a date and an amount on the same line (older simple layout)."""
    out: list[BankTransaction] = []
    for line in lines:
        date_m = _PDF_DATE.search(line)
        amounts = _PDF_AMOUNT.findall(line)
        if not date_m or not amounts:
            continue
        try:
            cents = parse_eur(amounts[-1])  # last number on the line ~ the booking
        except MoneyParseError:
            continue
        if cents == 0:
            continue
        # Keep the amount's own sign; an unsigned figure defaults to an expense.
        signed = cents if amounts[-1].lstrip().startswith("-") else -abs(cents)
        out.append(BankTransaction(
            booking_date=parse_date_flex(date_m.group(1)) or "", amount_cents=signed,
            purpose=line[:160], source_format="pdf", confidence=CONFIDENCE_LOW,
            raw=line[:200]))
    return out
