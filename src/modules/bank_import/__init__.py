"""Local, privacy-preserving bank-statement import.

Everything in this package runs entirely on the user's machine: no network, no
external service, no upload. Statements (CAMT.053 / MT940 / CSV / PDF) are parsed
into :class:`BankTransaction` objects, categorised with a rule-based, learning
classifier and de-duplicated before the user confirms them into the household
book. The design mirrors a deterministic, data-frugal rules engine (no LLM).
"""
