-- ==========================================================================
--  HaushaltsManager — SQLite schema
--  RULE: every monetary value is stored as INTEGER cents (never REAL/float).
--  Dates are ISO-8601 strings (YYYY-MM-DD). NULL end_date == open-ended.
-- ==========================================================================

PRAGMA foreign_keys = ON;

-- Schema version for forward-compatible migrations.
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

-- --- Income (multiple sources: minijob, part-time, ...) -------------------
CREATE TABLE IF NOT EXISTS income_sources (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    amount_cents INTEGER NOT NULL DEFAULT 0,
    income_type  TEXT    NOT NULL DEFAULT 'sonstiges',  -- minijob|teilzeit|vollzeit|sonstiges
    active       INTEGER NOT NULL DEFAULT 1,
    note         TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- --- Fixed / recurring costs ----------------------------------------------
CREATE TABLE IF NOT EXISTS fixed_costs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    amount_cents INTEGER NOT NULL DEFAULT 0,
    category     TEXT    NOT NULL DEFAULT 'Sonstiges',
    start_date   TEXT,                                  -- ISO, optional
    end_date     TEXT,                                  -- ISO, NULL = unbegrenzt
    note         TEXT,
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- --- Variable expenses (dated, categorised, optional receipt) -------------
-- recurring = 1 marks a monthly-recurring template: it counts in its start
-- month (its `date`) and in every later month, materialised on the fly.
CREATE TABLE IF NOT EXISTS variable_expenses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT    NOT NULL,                      -- ISO YYYY-MM-DD
    amount_cents INTEGER NOT NULL DEFAULT 0,
    category     TEXT    NOT NULL DEFAULT 'Sonstiges',
    description  TEXT,
    receipt_path TEXT,                                  -- optional image path
    recurring    INTEGER NOT NULL DEFAULT 0,            -- 1 = monatlich wiederkehrend
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- --- Credits / loans -------------------------------------------------------
-- Either total_cents or monthly_cents is enough; the missing one is derived.
-- Likewise end_date vs. term_months. Optional link to a fixed_costs row that
-- mirrors the monthly rate.
CREATE TABLE IF NOT EXISTS credits (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    name                 TEXT    NOT NULL,
    total_cents          INTEGER,                       -- Gesamtbetrag (optional)
    monthly_cents        INTEGER,                       -- Monatsrate (optional)
    start_date           TEXT,                          -- ISO, optional
    end_date             TEXT,                          -- ISO, optional
    term_months          INTEGER,                       -- Laufzeit/Restlaufzeit (optional)
    interest_rate        REAL,                          -- annual %, optional
    category             TEXT    NOT NULL DEFAULT 'Divers',  -- Auto|Haus|Divers|Persönlich
    note                 TEXT,
    status               TEXT    NOT NULL DEFAULT 'aktiv',   -- aktiv|abbezahlt|pausiert
    linked_fixed_cost_id INTEGER,
    created_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (linked_fixed_cost_id) REFERENCES fixed_costs(id) ON DELETE SET NULL
);

-- --- Key/value settings inside the financial DB ---------------------------
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- --- Cached monthly summaries (snapshots for history/exports) -------------
CREATE TABLE IF NOT EXISTS monthly_summary (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL,                   -- 1-12
    income_cents    INTEGER NOT NULL DEFAULT 0,
    fixed_cents     INTEGER NOT NULL DEFAULT 0,
    variable_cents  INTEGER NOT NULL DEFAULT 0,
    remaining_cents INTEGER NOT NULL DEFAULT 0,
    note            TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (year, month)
);

-- --- Indexes ---------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_var_date     ON variable_expenses(date);
CREATE INDEX IF NOT EXISTS idx_var_category ON variable_expenses(category);
CREATE INDEX IF NOT EXISTS idx_fixed_active ON fixed_costs(active);
CREATE INDEX IF NOT EXISTS idx_credit_status ON credits(status);
