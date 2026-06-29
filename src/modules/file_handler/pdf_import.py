"""PDF text and amount extraction (PyMuPDF / fitz).

Reads account statements or loan contracts and pulls out candidate monetary
amounts with their surrounding line, so the import view can show an editable,
correctable preview. The amount regex matches German (1.234,56) and plain
(1234.56) formats while avoiding bare integers like years.
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF

from modules.money import try_parse_eur

# Amount shapes (most specific first):
#   1.234 / 1.234,56  (German grouped, optional decimals)
#   1234,56           (German decimal)
#   1234.56           (plain/US decimal)
_AMOUNT_RE = re.compile(
    r"-?\d{1,3}(?:\.\d{3})+(?:,\d{2})?"
    r"|-?\d+,\d{2}"
    r"|-?\d+\.\d{2}"
)


def extract_text(path: str | Path) -> str:
    """Return the full text content of a PDF."""
    doc = fitz.open(path)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def extract_amounts(path: str | Path, max_items: int = 400) -> list[dict]:
    """Find candidate amounts. Each item: {raw, cents, line}.

    Lines are trimmed to a readable length for the preview table.
    """
    out: list[dict] = []
    for raw_line in extract_text(path).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for match in _AMOUNT_RE.finditer(line):
            cents = try_parse_eur(match.group(0))
            if not cents:
                continue
            out.append({"raw": match.group(0), "cents": cents, "line": line[:140]})
            if len(out) >= max_items:
                return out
    return out
