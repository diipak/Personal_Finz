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

-- 2. Relational Categories & Subcategories
CREATE TABLE IF NOT EXISTS categories (
    category_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL UNIQUE,
    flexibility_tier TEXT NOT NULL DEFAULT 'Flexible',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subcategories (
    subcategory_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id      INTEGER NOT NULL,
    name             TEXT NOT NULL,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(category_id) ON DELETE CASCADE,
    UNIQUE (category_id, name)
);

-- 3. Merchants and Merchant Clusters
CREATE TABLE IF NOT EXISTS merchants (
    merchant_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name                 TEXT NOT NULL UNIQUE,
    parent_merchant_id   INTEGER,
    category_id          INTEGER,
    subcategory_id       INTEGER,
    confidence_score     REAL DEFAULT 1.0,
    is_verified          BOOLEAN DEFAULT 0,
    is_system            BOOLEAN DEFAULT 0, -- 1 for system transfer merchants
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_merchant_id) REFERENCES merchants(merchant_id) ON DELETE SET NULL,
    FOREIGN KEY (category_id) REFERENCES categories(category_id) ON DELETE SET NULL,
    FOREIGN KEY (subcategory_id) REFERENCES subcategories(subcategory_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS merchant_clusters (
    cluster_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_name         TEXT NOT NULL UNIQUE, -- e.g. 'PAYPAL NETFLIX'
    merchant_id          INTEGER,
    confidence_score     REAL DEFAULT 0.0,
    is_locked            BOOLEAN DEFAULT 0,
    is_user_verified     BOOLEAN DEFAULT 0,
    sample_descriptions   TEXT,                 -- JSON list of sample descriptions
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (merchant_id) REFERENCES merchants(merchant_id) ON DELETE SET NULL
);

-- 4. Transactions table (Core master ledger)
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id      TEXT PRIMARY KEY,      -- Unique SHA-256 fingerprint matching document bytes or API ID
    account_id          TEXT NOT NULL,         -- Link to accounts
    booking_date        TEXT NOT NULL,         -- YYYY-MM-DD
    description         TEXT NOT NULL,         -- Raw description
    display_name        TEXT,                  -- Normalized display name
    normalized_merchant TEXT,                  -- Clean primary merchant name for clustering
    normalized_pattern  TEXT,                  -- Detailed pattern preserving behavior
    category            TEXT DEFAULT 'Unsorted',
    flexibility_tier    TEXT NOT NULL,         -- 'Fixed', 'Flexible', 'Discretionary', 'Income'
    amount              REAL NOT NULL,         -- Float amount (negative for expense, positive for income)
    currency            TEXT NOT NULL,         -- 'EUR' or 'INR'
    is_guess            BOOLEAN DEFAULT 0,     -- 1 if LLM guessed
    is_pinned           BOOLEAN DEFAULT 0,     -- 1 if user reviewed/approved
    is_ignored          BOOLEAN DEFAULT 0,     -- 1 if user ignored/deleted from calculations
    status              TEXT DEFAULT 'SETTLED',-- 'SETTLED' or 'PENDING'
    ez_synced           BOOLEAN DEFAULT 0,     -- 1 if pushed to ezBookkeeping
    transfer_subtype    TEXT,
    cluster_id          INTEGER REFERENCES merchant_clusters(cluster_id) ON DELETE SET NULL,
    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
);

-- 5. Daily snapshots table (For net worth graph reconstruction)
CREATE TABLE IF NOT EXISTS daily_snapshots (
    snapshot_date               TEXT NOT NULL,  -- YYYY-MM-DD
    account_id                  TEXT NOT NULL,
    balance_in_native_currency   REAL NOT NULL,
    PRIMARY KEY (snapshot_date, account_id),
    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
);

-- 6. Exchange rates table
CREATE TABLE IF NOT EXISTS exchange_rates (
    source_currency     TEXT NOT NULL,         -- 'EUR'
    target_currency     TEXT NOT NULL,         -- 'INR'
    spot_rate           REAL NOT NULL,         -- Spot conversion rate (e.g. 91.24)
    last_api_update     TEXT NOT NULL,         -- YYYY-MM-DD
    PRIMARY KEY (source_currency, target_currency)
);

-- 7. Regex Rules table (Regex matching engine parameters)
CREATE TABLE IF NOT EXISTS regex_rules (
    rule_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_string      TEXT NOT NULL UNIQUE,  -- Regex or substring pattern
    match_type          TEXT DEFAULT 'regex',  -- 'regex', 'substring', 'exact'
    target_category     TEXT NOT NULL,
    display_name        TEXT,
    flexibility_tier    TEXT NOT NULL,         -- 'Fixed', 'Flexible', 'Discretionary', 'Income'
    amount_min          REAL,
    amount_max          REAL,
    priority            INTEGER DEFAULT 0,
    target_merchant_id  INTEGER REFERENCES merchants(merchant_id) ON DELETE CASCADE,
    target_cluster_id   INTEGER REFERENCES merchant_clusters(cluster_id) ON DELETE CASCADE
);

-- 8. Settings table
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- 9. Sync logs table (For rate-limit checks)
CREATE TABLE IF NOT EXISTS sync_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    TEXT NOT NULL,
    sync_source   TEXT NOT NULL,               -- 'enable_banking' | 'manual_file'
    status        TEXT NOT NULL,               -- 'SUCCESS' | 'FAILED' | 'SKIPPED'
    initiated_by  TEXT NOT NULL,               -- 'CRON' | 'USER_BUTTON'
    error_message TEXT,
    timestamp     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 10. Sync history table (For audit logs UI)
CREATE TABLE IF NOT EXISTS sync_history (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    executed_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    institution_id       TEXT NOT NULL,
    status               TEXT NOT NULL,
    transactions_fetched INTEGER DEFAULT 0,
    error_details        TEXT
);

-- 11. LLM Cache table for normalized merchant categories
CREATE TABLE IF NOT EXISTS llm_cache (
    merchant_key      TEXT PRIMARY KEY,  -- Normalized description
    category          TEXT NOT NULL,
    flexibility_tier  TEXT NOT NULL,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 12. Merchant stats table (Avoids repeatedly scanning transactions)
CREATE TABLE IF NOT EXISTS merchant_stats (
    merchant_key TEXT PRIMARY KEY,          -- The normalized pattern (e.g. 'PAYPAL NETFLIX', 'REWE')
    parent_merchant TEXT,                   -- The normalized merchant (e.g. 'NETFLIX')
    transaction_count INTEGER DEFAULT 0,
    total_amount REAL DEFAULT 0.0,
    avg_amount REAL DEFAULT 0.0,
    first_seen TEXT,
    last_seen TEXT,
    known_category TEXT,
    transfer_subtype TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 13. Merchant stats cache table (Optimized for new structure)
CREATE TABLE IF NOT EXISTS merchant_stats_new (
    merchant_id          INTEGER PRIMARY KEY,
    transaction_count    INTEGER DEFAULT 0,
    total_spend          REAL DEFAULT 0.0,
    total_income         REAL DEFAULT 0.0,
    first_seen           TEXT,
    last_seen            TEXT,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (merchant_id) REFERENCES merchants(merchant_id) ON DELETE CASCADE
);

-- 14. AI suggested rules table (For review and rule promotion)
CREATE TABLE IF NOT EXISTS ai_suggested_rules (
    suggestion_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_name         TEXT NOT NULL,         -- Normalized merchant name
    pattern_string        TEXT NOT NULL,         -- Suggested pattern string
    match_type            TEXT DEFAULT 'substring', -- 'regex', 'substring', 'exact'
    suggested_category    TEXT NOT NULL,
    suggested_display_name TEXT,
    flexibility_tier      TEXT NOT NULL,         -- 'Fixed', 'Flexible', 'Discretionary', 'Income'
    amount_min            REAL,
    amount_max            REAL,
    confidence_score      REAL DEFAULT 0.0,
    status                TEXT DEFAULT 'PENDING',-- 'PENDING', 'APPROVED', 'REJECTED', 'SUPERSEDED'
    transaction_count     INTEGER DEFAULT 0,     -- Number of transactions in cluster
    sample_descriptions   TEXT,                  -- JSON array or comma-separated list of raw descriptions
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 15. Merchant Signatures (Memory Engine Cache Table)
CREATE TABLE IF NOT EXISTS merchant_signatures (
    signature_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_string       TEXT NOT NULL UNIQUE,     -- Clean, normalized pattern (e.g. 'google one')
    merchant_id          INTEGER NOT NULL,          -- Links to core merchants table
    signature_type       TEXT NOT NULL,             -- 'EXACT', 'PREFIX', 'REGEX', 'AI_DISCOVERED', 'USER_CREATED'
    source_action        TEXT NOT NULL,             -- 'user_verify', 'workbench_promote', 'auto_resolved', 'ai_review'
    is_user_verified     BOOLEAN DEFAULT 0,         -- 1 if user explicitly verified or promoted this pattern
    confidence_score     REAL NOT NULL DEFAULT 0.5, -- Range [0.0 - 1.0]
    match_count          INTEGER DEFAULT 0,         -- Usage frequency
    last_matched_at      TIMESTAMP,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (merchant_id) REFERENCES merchants(merchant_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_signatures_pattern ON merchant_signatures(pattern_string);

-- 16. Unified Resolved View
CREATE VIEW IF NOT EXISTS v_transactions_resolved AS
SELECT 
    t.transaction_id,
    t.account_id,
    t.booking_date,
    t.description,
    t.amount,
    t.currency,
    t.is_guess,
    t.is_pinned,
    t.is_ignored,
    t.status,
    t.cluster_id,
    c.cluster_name,
    m.merchant_id,
    COALESCE(m.name, t.display_name, t.description) AS resolved_merchant_name,
    parent.name AS parent_merchant_name,
    m.is_system AS is_system_merchant,
    COALESCE(cat.name, t.category, 'Unsorted') AS category,
    sc.name AS subcategory,
    COALESCE(cat.flexibility_tier, t.flexibility_tier, 'Flexible') AS flexibility_tier
FROM transactions t
LEFT JOIN merchant_clusters c ON t.cluster_id = c.cluster_id
LEFT JOIN merchants m ON c.merchant_id = m.merchant_id
LEFT JOIN merchants parent ON m.parent_merchant_id = parent.merchant_id
LEFT JOIN categories cat ON m.category_id = cat.category_id
LEFT JOIN subcategories sc ON m.subcategory_id = sc.subcategory_id;

-- Seeding Default Settings & Rates
INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_sync_enabled', 'true');
INSERT OR IGNORE INTO settings (key, value) VALUES ('vault_passcode_hash', NULL);
INSERT OR IGNORE INTO settings (key, value) VALUES ('vault_locked', 'false');

INSERT OR IGNORE INTO exchange_rates (source_currency, target_currency, spot_rate, last_api_update)
VALUES ('EUR', 'INR', 90.0, '2026-06-10');
