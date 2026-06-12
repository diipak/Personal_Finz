-- SQLite local-sovereign schema for Personal_Finz

-- 1. Accounts table (PSD2 accounts and manual assets)
CREATE TABLE IF NOT EXISTS accounts (
    account_id          TEXT PRIMARY KEY,
    account_name        TEXT NOT NULL,
    account_type        TEXT NOT NULL,         -- 'Automated (PSD2)', 'Manual Fallback', 'Manual Asset'
    current_balance     REAL NOT NULL,
    native_currency     TEXT NOT NULL,         -- 'EUR' or 'INR'
    psd2_resource_hash  TEXT,                  -- Identification token for Enable Banking node
    last_synchronized   TEXT NOT NULL          -- ISO timestamp of last execution loop
);

-- 2. Transactions table (Core master ledger)
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id      TEXT PRIMARY KEY,      -- Unique SHA-256 fingerprint matching document bytes or API ID
    account_id          TEXT NOT NULL,         -- Link to accounts
    booking_date        TEXT NOT NULL,         -- YYYY-MM-DD
    description         TEXT NOT NULL,         -- Raw description
    display_name        TEXT,                  -- Normalized display name
    category            TEXT DEFAULT 'Unsorted',
    flexibility_tier    TEXT NOT NULL,         -- 'Fixed', 'Flexible', 'Discretionary', 'Income'
    amount              REAL NOT NULL,         -- Float amount (negative for expense, positive for income)
    currency            TEXT NOT NULL,         -- 'EUR' or 'INR'
    is_guess            BOOLEAN DEFAULT 0,     -- 1 if LLM guessed
    is_pinned           BOOLEAN DEFAULT 0,     -- 1 if user reviewed/approved
    is_ignored          BOOLEAN DEFAULT 0,     -- 1 if user ignored/deleted from calculations
    status              TEXT DEFAULT 'SETTLED',-- 'SETTLED' or 'PENDING'
    ez_synced           BOOLEAN DEFAULT 0,     -- 1 if pushed to ezBookkeeping
    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
);

-- 3. Daily snapshots table (For net worth graph reconstruction)
CREATE TABLE IF NOT EXISTS daily_snapshots (
    snapshot_date               TEXT NOT NULL,  -- YYYY-MM-DD
    account_id                  TEXT NOT NULL,
    balance_in_native_currency   REAL NOT NULL,
    PRIMARY KEY (snapshot_date, account_id),
    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
);

-- 4. Exchange rates table
CREATE TABLE IF NOT EXISTS exchange_rates (
    source_currency     TEXT NOT NULL,         -- 'EUR'
    target_currency     TEXT NOT NULL,         -- 'INR'
    spot_rate           REAL NOT NULL,         -- Spot conversion rate (e.g. 91.24)
    last_api_update     TEXT NOT NULL,         -- YYYY-MM-DD
    PRIMARY KEY (source_currency, target_currency)
);

-- 5. Regex Rules table (Regex matching engine parameters)
CREATE TABLE IF NOT EXISTS regex_rules (
    rule_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_string      TEXT NOT NULL UNIQUE,  -- Regex or substring pattern
    match_type          TEXT DEFAULT 'regex',  -- 'regex', 'substring', 'exact'
    target_category     TEXT NOT NULL,
    display_name        TEXT,
    flexibility_tier    TEXT NOT NULL,         -- 'Fixed', 'Flexible', 'Discretionary', 'Income'
    amount_min          REAL,
    amount_max          REAL,
    priority            INTEGER DEFAULT 0
);

-- 6. Settings table
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- 7. Sync logs table (For rate-limit checks)
CREATE TABLE IF NOT EXISTS sync_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    TEXT NOT NULL,
    sync_source   TEXT NOT NULL,               -- 'enable_banking' | 'manual_file'
    status        TEXT NOT NULL,               -- 'SUCCESS' | 'FAILED' | 'SKIPPED'
    initiated_by  TEXT NOT NULL,               -- 'CRON' | 'USER_BUTTON'
    error_message TEXT,
    timestamp     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. Sync history table (For audit logs UI)
CREATE TABLE IF NOT EXISTS sync_history (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    executed_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    institution_id       TEXT NOT NULL,
    status               TEXT NOT NULL,
    transactions_fetched INTEGER DEFAULT 0,
    error_details        TEXT
);

-- Seeding Default Settings & Rates
INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_sync_enabled', 'true');
INSERT OR IGNORE INTO settings (key, value) VALUES ('vault_passcode_hash', NULL); -- NULL means no vault passcode set up yet
INSERT OR IGNORE INTO settings (key, value) VALUES ('vault_locked', 'false');

INSERT OR IGNORE INTO exchange_rates (source_currency, target_currency, spot_rate, last_api_update)
VALUES ('EUR', 'INR', 90.0, '2026-06-10');
