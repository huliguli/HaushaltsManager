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

-- --- One-off / dated income (e.g. imported bank credits) ------------------
-- Unlike income_sources (recurring monthly), each row counts ONLY in its own
-- month. A one-off transfer (someone paying you back 50 EUR) must never inflate
-- the recurring monthly income. New table -> auto-created in existing DBs too.
CREATE TABLE IF NOT EXISTS variable_income (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT    NOT NULL,                      -- ISO YYYY-MM-DD
    amount_cents INTEGER NOT NULL DEFAULT 0,
    source       TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
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
-- recurring = 1 marks a recurring template: it counts in its start month
-- (its `date`) and in every later month hit by its cadence, materialised on
-- the fly. recur_interval_months (1/3/12) sets the cadence; recur_end
-- (optional, ISO) is the last date an occurrence may fall on.
CREATE TABLE IF NOT EXISTS variable_expenses (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    date                  TEXT    NOT NULL,             -- ISO YYYY-MM-DD
    amount_cents          INTEGER NOT NULL DEFAULT 0,
    category              TEXT    NOT NULL DEFAULT 'Sonstiges',
    description           TEXT,
    receipt_path          TEXT,                         -- optional image path
    recurring             INTEGER NOT NULL DEFAULT 0,   -- 1 = wiederkehrend
    recur_interval_months INTEGER NOT NULL DEFAULT 1,   -- 1/3/12 Monate
    recur_end             TEXT,                         -- optional ISO end date
    created_at            TEXT    NOT NULL DEFAULT (datetime('now'))
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

-- --- Bank-statement import: learned categorisation rules ------------------
-- pattern = normalised payee/purpose substring; learned = taught by a user
-- correction (vs. a built-in seed rule, which is not stored here).
CREATE TABLE IF NOT EXISTS import_rules (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern    TEXT    NOT NULL,
    category   TEXT    NOT NULL,
    learned    INTEGER NOT NULL DEFAULT 1,
    priority   INTEGER NOT NULL DEFAULT 100,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (pattern)
);

-- --- Bank-statement import: de-dup log (so a re-import skips known rows) ----
CREATE TABLE IF NOT EXISTS import_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_hash        TEXT    NOT NULL,
    booking_date   TEXT,
    amount_cents   INTEGER,
    imported_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    batch_id       TEXT,                                -- one id per commit run
    created_kind   TEXT,                                -- 'expense' | 'income'
    created_row_id INTEGER,                             -- row the commit created
    UNIQUE (tx_hash)
);

-- --- Bank-statement import: saved CSV column profiles per bank -------------
CREATE TABLE IF NOT EXISTS bank_profiles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    mapping_json TEXT    NOT NULL,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (name)
);

-- --- Category budgets (schema v3): optional monthly target per category ----
-- One target limit (integer cents) per expense category. Purely additive; a
-- missing row simply means "no budget set" for that category. The dashboard
-- and the trends view show spent-vs-limit with a traffic-light.
CREATE TABLE IF NOT EXISTS category_budgets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category     TEXT    NOT NULL,
    limit_cents  INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (category)
);

-- --- Savings goals (schema v5): persisted target with derived progress -----
-- The saved amount is never booked: it is the scheduled state (monthly rate ×
-- months since start, see modules.savings_goals) plus manual_cents, a user
-- correction for start balances or skipped months. Purely additive — the
-- table is created on existing databases by this CREATE IF NOT EXISTS.
CREATE TABLE IF NOT EXISTS savings_goals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    target_cents  INTEGER NOT NULL DEFAULT 0,
    monthly_cents INTEGER NOT NULL DEFAULT 0,
    start_date    TEXT    NOT NULL,                    -- ISO; first saving month
    manual_cents  INTEGER NOT NULL DEFAULT 0,          -- correction, may be negative
    note          TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- --- Abo-Radar (schema v5): hidden/adopted suggestion patterns --------------
-- One row per normalised payee pattern the user dismissed or already adopted
-- as a fixed cost, so the suggestion never resurfaces. Financial-adjacent
-- data, therefore part of WIPE_TABLES (a full reset clears it).
CREATE TABLE IF NOT EXISTS subscription_ignores (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern    TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (pattern)
);

-- --- Töpfe (schema v6): virtual partitions of real savings accounts --------
-- A savings account holds one anonymous lump sum at the bank; pots make its
-- composition visible ("1.000 € = 400 € Urlaub + 250 € Auto + …"). A pot
-- grows by an optional monthly rate (mirroring the user's real standing
-- order) plus explicit movements; the account's recorded balance is compared
-- against the pots' sum ("nicht verteilt"). All additive CREATE IF NOT EXISTS.
CREATE TABLE IF NOT EXISTS savings_accounts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    balance_cents INTEGER NOT NULL DEFAULT 0,    -- zuletzt erfasster Kontostand
    balance_date  TEXT,                          -- ISO; wann erfasst
    note          TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    INTEGER NOT NULL,
    name          TEXT    NOT NULL,
    monthly_cents INTEGER NOT NULL DEFAULT 0,    -- Rate (Dauerauftrags-Anteil), 0 = keine
    rate_start    TEXT,                          -- ISO; Rate zählt ab diesem Monat
    goal_id       INTEGER,                       -- optional verknüpftes Sparziel
    note          TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES savings_accounts(id) ON DELETE CASCADE,
    FOREIGN KEY (goal_id) REFERENCES savings_goals(id) ON DELETE SET NULL
);

-- Signed movements: + Einzahlung, − Entnahme. Transfers between pots are two
-- rows committed together. The pot balance = rate part + SUM(amount_cents).
CREATE TABLE IF NOT EXISTS pot_movements (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pot_id       INTEGER NOT NULL,
    date         TEXT    NOT NULL,               -- ISO YYYY-MM-DD
    amount_cents INTEGER NOT NULL,
    note         TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (pot_id) REFERENCES pots(id) ON DELETE CASCADE
);

-- --- Interop (App-Familie, schema v7) ---------------------------------------
-- Contract instead of table access: the sister app (KFZ-Manager) reads ONLY
-- interop_meta and interop_ausgaben_monat below — never the private tables.
-- interop_ausgaben_monat is a MATERIALISED table (not a view): the monthly
-- total needs the recurring-expense and fixed-cost logic that lives in Python
-- (modules.budget / repositories), so modules.interop rebuilds it at startup
-- and after every data change. Spec: the KFZ-Manager repo's INTEROP.md.
CREATE TABLE IF NOT EXISTS interop_meta (
    interop_version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS interop_ausgaben_monat (
    jahr       INTEGER NOT NULL,
    monat      INTEGER NOT NULL,               -- 1-12
    summe_cent INTEGER NOT NULL DEFAULT 0,     -- Fixkosten + variable Ausgaben
    PRIMARY KEY (jahr, monat)
);

-- --- Indexes ---------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_var_date     ON variable_expenses(date);
CREATE INDEX IF NOT EXISTS idx_varincome_date ON variable_income(date);
CREATE INDEX IF NOT EXISTS idx_var_category ON variable_expenses(category);
-- NOTE: the partial index on variable_expenses(recurring) is created in
-- Database._migrate (NOT here) because on a pre-1.4 database the recurring
-- column is added by an ALTER that runs AFTER this script — an index here would
-- reference a not-yet-existing column and fail on upgrade.
CREATE INDEX IF NOT EXISTS idx_fixed_active ON fixed_costs(active);
CREATE INDEX IF NOT EXISTS idx_credit_status ON credits(status);
CREATE INDEX IF NOT EXISTS idx_import_log_hash    ON import_log(tx_hash);
CREATE INDEX IF NOT EXISTS idx_import_rules_pattern ON import_rules(pattern);
CREATE INDEX IF NOT EXISTS idx_pots_account ON pots(account_id);
CREATE INDEX IF NOT EXISTS idx_pot_moves_pot ON pot_movements(pot_id);
