-- SQLite Schema for Personal_Finz

-- Transactions Table
CREATE TABLE IF NOT EXISTS transactions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT NOT NULL,               -- Format: YYYY-MM-DD
    description   TEXT NOT NULL,               -- Raw bank description
    display_name  TEXT,                        -- Mapped clean name
    amount        REAL NOT NULL,               -- Numeric amount (pos/neg)
    currency      TEXT DEFAULT 'EUR',          -- Transaction currency (e.g. EUR, INR)
    account       TEXT NOT NULL,               -- Account name
    type          TEXT NOT NULL,               -- Income | Expense | Transfer
    category      TEXT,                        -- Category name
    flexibility   TEXT DEFAULT 'Flexible',     -- Fixed | Flexible | Discretionary
    tags          TEXT,                        -- Comma-separated tag list
    is_guess      BOOLEAN DEFAULT 0,           -- 1 if LLM guess, 0 if deterministic
    is_pinned     BOOLEAN DEFAULT 0,           -- 1 if user locked/manual
    is_ignored    BOOLEAN DEFAULT 0,           -- 1 if excluded from analytics
    hash          TEXT UNIQUE,                 -- Deduplication hash for manual statement parsing
    external_sync_id TEXT UNIQUE,                 -- Enable Banking sync ID or fallback hash
    status        TEXT DEFAULT 'SETTLED',       -- PENDING | SETTLED
    ez_synced     BOOLEAN DEFAULT 0,           -- 1 if synced to ezBookkeeping
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sync History Logs Table
CREATE TABLE IF NOT EXISTS sync_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    TEXT NOT NULL,
    sync_source   TEXT NOT NULL,               -- 'enable_banking' | 'manual_file'
    status        TEXT NOT NULL,               -- 'SUCCESS' | 'FAILED' | 'SKIPPED'
    initiated_by  TEXT NOT NULL,               -- 'CRON' | 'USER_BUTTON'
    error_message TEXT,
    timestamp     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Rules Table
CREATE TABLE IF NOT EXISTS rules (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern       TEXT NOT NULL,               -- Match pattern
    match_type    TEXT DEFAULT 'substring',     -- substring | regex | exact
    category      TEXT NOT NULL,               -- Mapped category
    display_name  TEXT,                        -- Rename merchant to this (optional)
    flexibility   TEXT,                        -- Flexibility category (optional)
    tags          TEXT,                        -- Comma-separated tags (optional)
    amount_min    REAL,                        -- >= amount (optional)
    amount_max    REAL,                        -- <= amount (optional)
    priority      INTEGER DEFAULT 0            -- Priority evaluation order
);

-- Connected Bank Feeds Table
CREATE TABLE IF NOT EXISTS linked_accounts (
    resource_id       TEXT PRIMARY KEY,
    institution_id    TEXT NOT NULL,
    display_name      TEXT NOT NULL,
    currency          TEXT DEFAULT 'EUR',
    last_synced_at    TIMESTAMP
);

-- Sync Audit Execution History Table
CREATE TABLE IF NOT EXISTS sync_history (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    executed_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    institution_id       TEXT NOT NULL,
    status               TEXT NOT NULL,
    transactions_fetched INTEGER DEFAULT 0,
    error_details        TEXT
);

-- Settings Table
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_sync_enabled', 'true');


