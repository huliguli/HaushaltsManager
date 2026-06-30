"""Tests for the local bank-statement import (parsers + categoriser + de-dup).

All fixtures here are SYNTHETIC and anonymised — no real statements, IBANs,
names or amounts. Everything must run fully offline.
"""

import pytest

from modules.bank_import import parsers
from modules.bank_import.categorize import Categorizer
from modules.bank_import.model import (
    CAT_LEARNED,
    CAT_NONE,
    CAT_RULE,
    BankTransaction,
    normalize,
    transaction_hash,
)
from modules.bank_import.parsers import BankImportError

# --- synthetic statement fixtures -----------------------------------------
_CAMT = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt><Stmt>
    <Ntry>
      <Amt Ccy="EUR">34.90</Amt><CdtDbtInd>DBIT</CdtDbtInd>
      <BookgDt><Dt>2026-06-05</Dt></BookgDt><ValDt><Dt>2026-06-05</Dt></ValDt>
      <NtryDtls><TxDtls>
        <Refs><EndToEndId>E2E-001</EndToEndId></Refs>
        <RltdPties><Cdtr><Nm>REWE Markt GmbH</Nm></Cdtr></RltdPties>
        <RmtInf><Ustrd>REWE SAGT DANKE 12345</Ustrd></RmtInf>
      </TxDtls></NtryDtls>
    </Ntry>
    <Ntry>
      <Amt Ccy="EUR">2000.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>
      <BookgDt><Dt>2026-06-01</Dt></BookgDt>
      <NtryDtls><TxDtls>
        <Refs><EndToEndId>NOTPROVIDED</EndToEndId></Refs>
        <RltdPties><Dbtr><Nm>Arbeitgeber AG</Nm></Dbtr></RltdPties>
        <RmtInf><Ustrd>Gehalt Juni</Ustrd></RmtInf>
      </TxDtls></NtryDtls>
    </Ntry>
  </Stmt></BkToCstmrStmt>
</Document>
"""

_CAMT_XXE = """<?xml version="1.0"?>
<!DOCTYPE Document [<!ENTITY xxe "EXPANDED">]>
<Document><BkToCstmrStmt><Stmt><Ntry>
  <Amt Ccy="EUR">1.00</Amt><CdtDbtInd>DBIT</CdtDbtInd>
  <BookgDt><Dt>2026-06-05</Dt></BookgDt>
  <NtryDtls><TxDtls><RmtInf><Ustrd>&xxe;</Ustrd></RmtInf></TxDtls></NtryDtls>
</Ntry></Stmt></BkToCstmrStmt></Document>
"""

_MT940 = """:20:STARTUMSATZ
:25:DE00111122223333444455/0
:28C:0/1
:60F:C260601EUR1000,00
:61:2606050605DR34,90NMSCNONREF
:86:020?00KARTENZAHLUNG?20REWE SAGT DANKE?32REWE MARKT GMBH
:61:2606010601CR2000,00NTRFGEHALT
:86:051?00GUTSCHRIFT?20Gehalt Juni?32ARBEITGEBER AG
:62F:C260630EUR2965,10
"""


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# --- CAMT ------------------------------------------------------------------
def test_camt_parse(tmp_path):
    txs = parsers.parse_camt(_write(tmp_path, "s.xml", _CAMT))
    assert len(txs) == 2
    out, inc = txs[0], txs[1]
    assert out.amount_cents == -3490 and out.payee == "REWE Markt GmbH"
    assert out.purpose == "REWE SAGT DANKE 12345" and out.reference == "E2E-001"
    assert out.booking_date == "2026-06-05" and out.kind == "expense"
    assert inc.amount_cents == 200000 and inc.is_income and inc.payee == "Arbeitgeber AG"


def test_camt_blocks_xxe(tmp_path):
    # forbid_dtd=True must reject the DTD/entity outright (no expansion).
    with pytest.raises(BankImportError):
        parsers.parse_camt(_write(tmp_path, "evil.xml", _CAMT_XXE))


# --- MT940 -----------------------------------------------------------------
def test_mt940_parse(tmp_path):
    txs = parsers.parse_mt940(_write(tmp_path, "s.sta", _MT940))
    assert len(txs) == 2
    assert txs[0].amount_cents == -3490 and txs[0].booking_date == "2026-06-05"
    assert "REWE" in txs[0].payee.upper() and "REWE SAGT DANKE" in txs[0].purpose
    assert txs[1].amount_cents == 200000 and txs[1].is_income
    assert "ARBEITGEBER" in txs[1].payee.upper()


# --- CSV -------------------------------------------------------------------
def test_csv_signed_amount():
    rows = [["05.06.2026", "REWE SAGT DANKE", "-34,90"],
            ["01.06.2026", "Arbeitgeber AG Gehalt", "2.000,00"]]
    mapping = {"date": 0, "purpose": 1, "amount": 2, "payee": None,
               "debit": None, "credit": None}
    txs = parsers.parse_csv(rows, mapping)
    assert [t.amount_cents for t in txs] == [-3490, 200000]
    assert txs[0].booking_date == "2026-06-05"


def test_csv_debit_credit_columns():
    rows = [["05.06.2026", "REWE", "34,90", ""],
            ["01.06.2026", "Gehalt", "", "2.000,00"]]
    mapping = {"date": 0, "payee": 1, "debit": 2, "credit": 3,
               "amount": None, "purpose": None}
    txs = parsers.parse_csv(rows, mapping)
    assert txs[0].amount_cents == -3490   # debit -> expense
    assert txs[1].amount_cents == 200000  # credit -> income


def test_csv_requires_amount_mapping():
    with pytest.raises(BankImportError):
        parsers.parse_csv([["x"]], {"date": 0})


# --- format detection / safety --------------------------------------------
def test_detect_format(tmp_path):
    assert parsers.detect_format(_write(tmp_path, "a.xml", _CAMT)) == "camt"
    assert parsers.detect_format(_write(tmp_path, "a.sta", _MT940)) == "mt940"
    assert parsers.detect_format(_write(tmp_path, "a.csv", "a;b;c\n1;2;3\n")) == "csv"


def test_empty_file_rejected(tmp_path):
    p = tmp_path / "empty.xml"
    p.write_bytes(b"")
    with pytest.raises(BankImportError):
        parsers.parse_camt(p)


def test_corrupt_inputs_raise_clean_error(tmp_path):
    # Truncated XML, a PDF with no booking lines and a CSV without an amount
    # column must all raise BankImportError (never an uncaught crash).
    bad_xml = tmp_path / "bad.xml"
    bad_xml.write_text("<Document><Stmt><Ntry><Amt>kapu", encoding="utf-8")
    with pytest.raises(BankImportError):
        parsers.parse_camt(bad_xml)
    with pytest.raises(BankImportError):
        parsers.parse_mt940_text("kein gueltiger mt940 inhalt")
    with pytest.raises(BankImportError):
        parsers.parse_csv([["nur text", "ohne betrag"]], {"date": 0, "amount": None,
                                                           "debit": None, "credit": None})


# --- categorisation --------------------------------------------------------
def _tx(payee="", purpose="", amount=-1000):
    return BankTransaction(booking_date="2026-06-05", amount_cents=amount,
                           payee=payee, purpose=purpose)


def test_categorizer_seed_rules():
    cat = Categorizer()
    assert cat.categorize(_tx("REWE Markt GmbH", "danke")).category == "Lebensmittel"
    assert cat.categorize(_tx("ARAL Tankstelle")).category == "Tanken"
    assert cat.categorize(_tx("NETFLIX.COM")).category == "Freizeit"
    unknown = cat.categorize(_tx("Irgendein Laden XY"))
    assert unknown.category == "Sonstiges" and unknown.category_confidence == CAT_NONE


def test_categorizer_whole_word_no_false_positive():
    # "h m" (from H&M) must not fire inside "gmbh menue"; and DM only as a word.
    cat = Categorizer()
    assert cat.categorize(_tx("Restaurant GmbH Menue")).category != "Kleidung"
    assert cat.categorize(_tx("H&M Hennes")).category == "Kleidung"
    assert cat.categorize(_tx("DM-DROGERIE Filiale")).category == "Drogerie"


def test_categorizer_learned_overrides_seed():
    # A learned rule for a payee wins over seed and the default.
    cat = Categorizer(learned_rules=[("Mein Hofladen", "Lebensmittel")])
    t = cat.categorize(_tx("Mein Hofladen e.K."))
    assert t.category == "Lebensmittel" and t.category_confidence == CAT_LEARNED


def test_income_has_no_category():
    t = Categorizer().categorize(_tx("Arbeitgeber AG", amount=200000))
    assert t.is_income and t.category == "" and t.category_confidence == CAT_NONE


# --- normalisation + de-dup ------------------------------------------------
def test_normalize_and_hash_stability():
    a = _tx("REWE Märkt GmbH", "Zweck 1", -3490)
    a.reference = "E2E-001"
    b = _tx("REWE Markt GmbH", "Zweck 1", -3490)
    b.reference = "E2E-001"
    assert transaction_hash(a) == transaction_hash(b)  # same reference -> same hash
    assert normalize("REWE Märkt GmbH!! 12") == "rewe markt gmbh 12"


def test_hash_uses_content_when_reference_is_placeholder():
    a = _tx("Shop", "Z", -1000)
    a.reference = "NOTPROVIDED"
    b = _tx("Shop", "Z", -1000)
    b.reference = ""
    # placeholder and empty both fall back to the content hash -> equal
    assert transaction_hash(a) == transaction_hash(b)


# --- DB-backed: learned rules, de-dup log, profiles ------------------------
def test_rules_learning_and_dedup_and_profiles(tmp_path):
    from modules.db_handler.database import Database
    from modules.db_handler.repositories import (
        BankProfileRepository, ImportLogRepository, ImportRuleRepository)

    db = Database(tmp_path / "bank.db")
    rules = ImportRuleRepository(db)
    log = ImportLogRepository(db)
    profiles = BankProfileRepository(db)

    # Unknown payee -> default; after learning, the rule wins.
    cat0 = Categorizer(rules.rules())
    assert cat0.categorize(_tx("Hofladen Krause")).category == "Sonstiges"
    rules.upsert(normalize("Hofladen Krause"), "Lebensmittel", learned=True)
    cat1 = Categorizer(rules.rules())
    learned = cat1.categorize(_tx("Hofladen Krause e.K."))
    assert learned.category == "Lebensmittel" and learned.category_confidence == CAT_LEARNED

    # De-dup: a hash becomes "known" once logged.
    t = _tx("Shop", "ref", -500)
    t.reference = "UNIQUE-1"
    h = transaction_hash(t)
    assert log.known([h]) == set()
    log.add(h, t.booking_date, t.amount_cents)
    assert log.known([h]) == {h}
    log.add(h, t.booking_date, t.amount_cents)  # idempotent (INSERT OR IGNORE)

    # CSV profiles round-trip.
    profiles.upsert("Sparkasse", '{"date":0,"amount":3}')
    assert profiles.list_names() == ["Sparkasse"]
    assert profiles.get("Sparkasse") == '{"date":0,"amount":3}'
    db.close()
