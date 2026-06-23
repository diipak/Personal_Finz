import sqlite3
import os
import sys
import shutil
import logging
import re
import hashlib
import json

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_PATH, DEFAULT_DB_DIR
from engine.normalizer import normalize
from engine.merchant_normalizer import normalize_merchant_name, normalize_pattern_name

logger = logging.getLogger(__name__)

# In-memory vault state (Phase 1: plaintext DB, in-memory toggle)
vault_state = {
    "locked": False,
    "passcode_hash": None
}

def is_vault_locked() -> bool:
    return vault_state["locked"]

def set_vault_lock(locked: bool):
    vault_state["locked"] = locked

def set_vault_passcode(passcode: str):
    if passcode:
        vault_state["passcode_hash"] = hashlib.sha256(passcode.encode()).hexdigest()
    else:
        vault_state["passcode_hash"] = None

def verify_vault_passcode(passcode: str) -> bool:
    if not vault_state["passcode_hash"]:
        return True
    h = hashlib.sha256(passcode.encode()).hexdigest()
    return h == vault_state["passcode_hash"]

def get_db():
    """Returns a connection to the SQLite database with dict-like Row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.create_function("normalize_desc", 1, normalize)
    return conn

def migrate_old_data(conn):
    """Migrates data from old tables (old_transactions, old_linked_accounts, old_rules) to new tables."""
    cursor = conn.cursor()
    logger.info("Executing database schema migration...")
    
    # 1. Migrate accounts
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='old_linked_accounts'")
        if cursor.fetchone():
            cursor.execute("SELECT * FROM old_linked_accounts")
            old_accs = cursor.fetchall()
            for acc in old_accs:
                acc_id = acc["resource_id"]
                inst = acc["institution_id"]
                name = acc["display_name"]
                curr = acc["currency"] or "EUR"
                last_sync = acc["last_synced_at"] or "2026-06-10 00:00:00"
                
                acc_type = "Automated (PSD2)"
                if acc_id.endswith("-manual-id") or inst in ["HDFC", "Advanzia Bank credit card"]:
                    acc_type = "Manual Fallback"
                    
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO accounts (
                        account_id, account_name, account_type, current_balance, native_currency, psd2_resource_hash, last_synchronized
                    ) VALUES (?, ?, ?, 0.0, ?, ?, ?)
                    """,
                    (acc_id, name, acc_type, curr, acc_id, last_sync)
                )
            logger.info(f"Migrated {len(old_accs)} account feeds.")
    except Exception as e:
        logger.error(f"Migration error for accounts: {e}")

    # 2. Migrate rules
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='old_rules'")
        if cursor.fetchone():
            cursor.execute("SELECT * FROM old_rules")
            old_rules = cursor.fetchall()
            for r in old_rules:
                pat = r["pattern"]
                cat = r["category"]
                flex = r["flexibility"] or "Flexible"
                match_t = r["match_type"] or "substring"
                disp = r["display_name"] if "display_name" in r.keys() else None
                amt_min = r["amount_min"] if "amount_min" in r.keys() else None
                amt_max = r["amount_max"] if "amount_max" in r.keys() else None
                prio = r["priority"] if "priority" in r.keys() else 0
                
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO regex_rules (
                        pattern_string, match_type, target_category, display_name, flexibility_tier, amount_min, amount_max, priority
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (pat, match_t, cat, disp, flex, amt_min, amt_max, prio)
                )
            logger.info(f"Migrated {len(old_rules)} matching rules.")
    except Exception as e:
        logger.error(f"Migration error for rules: {e}")

    # 3. Migrate transactions
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='old_transactions'")
        if cursor.fetchone():
            cursor.execute("SELECT * FROM old_transactions")
            old_txns = cursor.fetchall()
            migrated_cnt = 0
            for t in old_txns:
                tx_id = t["hash"] or t["external_sync_id"]
                if not tx_id:
                    composite = f"{t['date']}{t['description']}{t['amount']}"
                    tx_id = hashlib.sha256(composite.encode()).hexdigest()
                    
                # Resolve account_id from t["account"] (which was account_name in old DB)
                cursor.execute("SELECT account_id FROM accounts WHERE account_name = ?", (t["account"],))
                acc_row = cursor.fetchone()
                acc_id = acc_row["account_id"] if acc_row else t["account"]
                
                booking_date = t["date"]
                desc = t["description"]
                cat = t["category"] or "Unsorted"
                flex = t["flexibility"] or "Flexible"
                amt = t["amount"]
                curr = t["currency"] or "EUR"
                is_guess = t["is_guess"] or 0
                is_pinned = t["is_pinned"] or 0
                status_str = t["status"] or "SETTLED"
                
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO transactions (
                        transaction_id, account_id, booking_date, description, category, flexibility_tier, amount, currency, is_guess, is_pinned, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (tx_id, acc_id, booking_date, desc, cat, flex, amt, curr, is_guess, is_pinned, status_str)
                )
                migrated_cnt += 1
            
            # Update current balances based on transactions
            cursor.execute("SELECT account_id FROM accounts")
            acc_ids = [r["account_id"] for r in cursor.fetchall()]
            for aid in acc_ids:
                cursor.execute("SELECT SUM(amount) as bal FROM transactions WHERE account_id = ? AND status = 'SETTLED'", (aid,))
                bal_val = cursor.fetchone()["bal"] or 0.0
                cursor.execute("UPDATE accounts SET current_balance = ? WHERE account_id = ?", (bal_val, aid))
            
            logger.info(f"Migrated {migrated_cnt} ledger transactions and updated balances.")
    except Exception as e:
        logger.error(f"Migration error for transactions: {e}")

    # Drop old tables
    try:
        cursor.execute("DROP TABLE IF EXISTS old_transactions")
        cursor.execute("DROP TABLE IF EXISTS old_linked_accounts")
        cursor.execute("DROP TABLE IF EXISTS old_rules")
        conn.commit()
    except Exception as e:
        logger.error(f"Error dropping old tables: {e}")

def seed_default_accounts(conn):
    """Seeds default accounts if accounts table is empty."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM accounts")
    if cursor.fetchone()["cnt"] == 0:
        logger.info("Seeding default bank feeds into accounts table...")
        cursor.execute(
            """
            INSERT OR IGNORE INTO accounts (
                account_id, account_name, account_type, current_balance, native_currency, psd2_resource_hash, last_synchronized
            ) VALUES 
            ('b941a58f-79ce-4e81-9da2-39dc370be4f1', 'Commerzbank Giro', 'Automated (PSD2)', 0.0, 'EUR', 'b941a58f-79ce-4e81-9da2-39dc370be4f1', '2026-06-07 08:02:47'),
            ('cbca2eaf-fb8b-4e15-9b7e-ca8ea977a62b', 'Revolut Personal', 'Automated (PSD2)', 0.0, 'EUR', 'cbca2eaf-fb8b-4e15-9b7e-ca8ea977a62b', '2026-06-07 08:16:11'),
            ('advanzia-manual-id', 'Advanzia Bank credit card', 'Manual Fallback', 0.0, 'EUR', 'advanzia-manual-id', '2026-06-10 00:00:00'),
            ('hdfc-manual-id', 'HDFC Bank Account', 'Manual Fallback', 0.0, 'INR', 'hdfc-manual-id', '2026-06-10 00:00:00'),
            ('amazon-manual-id', 'Amazon Visa', 'Manual Fallback', 0.0, 'EUR', 'amazon-manual-id', '2026-06-10 00:00:00'),
            ('traderepublic-manual-id', 'Trade Republic', 'Manual Fallback', 0.0, 'EUR', 'traderepublic-manual-id', '2026-06-10 00:00:00')
            """
        )
        conn.commit()

def seed_merchant_stats(conn):
    """
    One-time seeding function to update normalized columns in the transactions table
    and populate the merchant_stats table from existing records.
    """
    cursor = conn.cursor()
    try:
        # Check if we need to compute normalized columns on existing transactions
        cursor.execute("SELECT COUNT(*) FROM transactions WHERE normalized_merchant IS NULL OR normalized_pattern IS NULL")
        missing_count = cursor.fetchone()[0]
        if missing_count > 0:
            logger.info(f"Computing normalization columns for {missing_count} existing transactions...")
            cursor.execute("SELECT transaction_id, description FROM transactions WHERE normalized_merchant IS NULL OR normalized_pattern IS NULL")
            txns = cursor.fetchall()
            for t in txns:
                m = normalize_merchant_name(t["description"])
                p = normalize_pattern_name(t["description"])
                cursor.execute(
                    "UPDATE transactions SET normalized_merchant = ?, normalized_pattern = ? WHERE transaction_id = ?",
                    (m, p, t["transaction_id"])
                )
            conn.commit()

        # Check if merchant_stats is empty
        cursor.execute("SELECT COUNT(*) FROM merchant_stats")
        stats_count = cursor.fetchone()[0]
        if stats_count == 0:
            logger.info("Seeding merchant_stats table from existing transactions...")
            cursor.execute(
                """
                INSERT INTO merchant_stats (
                    merchant_key, parent_merchant, transaction_count, total_amount, avg_amount, first_seen, last_seen, known_category
                )
                SELECT 
                    normalized_pattern as merchant_key,
                    normalized_merchant as parent_merchant,
                    COUNT(*) as transaction_count,
                    SUM(amount) as total_amount,
                    AVG(amount) as avg_amount,
                    MIN(booking_date) as first_seen,
                    MAX(booking_date) as last_seen,
                    -- known_category is set only if ALL transactions for that pattern are pinned (user-confirmed)
                    -- is_guess=1 means AI guessed and user has not reviewed -> treat as uncategorized
                    CASE 
                        WHEN MIN(is_guess) = 0 AND MAX(is_pinned) = 1 THEN MAX(CASE WHEN is_pinned = 1 THEN category ELSE NULL END)
                        ELSE NULL 
                    END as known_category
                FROM transactions
                WHERE normalized_pattern IS NOT NULL AND normalized_pattern != ''
                GROUP BY normalized_pattern, normalized_merchant
                """
            )
            conn.commit()
            logger.info("Successfully seeded merchant_stats table.")
    except Exception as e:
        logger.error(f"Error seeding merchant stats: {e}")

def init_db():
    """Initializes the database schema using db/schema.sql and runs migration if necessary."""
    # Copy old data.db if it exists and personal_finz.db doesn't
    old_db_path = os.path.join(DEFAULT_DB_DIR, "data.db")
    if not os.path.exists(DB_PATH) and os.path.exists(old_db_path):
        try:
            shutil.copy2(old_db_path, DB_PATH)
            logger.info("Copied old data.db to personal_finz.db for migration.")
        except Exception as copy_err:
            logger.error(f"Failed to copy data.db for migration: {copy_err}")

    # Check if we need to rename tables for migration
    needs_migration = False
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(transactions)")
                cols = [col[1] for col in cursor.fetchall()]
                if "date" in cols and "booking_date" not in cols:
                    # Old structure! We need to migrate.
                    needs_migration = True
                    logger.info("Detected old database schema structure. Renaming tables for migration...")
                    cursor.execute("ALTER TABLE transactions RENAME TO old_transactions;")
                    cursor.execute("ALTER TABLE linked_accounts RENAME TO old_linked_accounts;")
                    cursor.execute("ALTER TABLE rules RENAME TO old_rules;")
                    conn.commit()
                else:
                    altered = False
                    if "display_name" not in cols:
                        logger.info("Adding display_name column to transactions table...")
                        cursor.execute("ALTER TABLE transactions ADD COLUMN display_name TEXT;")
                        altered = True
                    if "is_ignored" not in cols:
                        logger.info("Adding is_ignored column to transactions table...")
                        cursor.execute("ALTER TABLE transactions ADD COLUMN is_ignored BOOLEAN DEFAULT 0;")
                        altered = True
                    if "status" not in cols:
                        logger.info("Adding status column to transactions table...")
                        cursor.execute("ALTER TABLE transactions ADD COLUMN status TEXT DEFAULT 'SETTLED';")
                        altered = True
                    if "ez_synced" not in cols:
                        logger.info("Adding ez_synced column to transactions table...")
                        cursor.execute("ALTER TABLE transactions ADD COLUMN ez_synced BOOLEAN DEFAULT 0;")
                        altered = True
                    if "normalized_merchant" not in cols:
                        logger.info("Adding normalized_merchant column to transactions table...")
                        cursor.execute("ALTER TABLE transactions ADD COLUMN normalized_merchant TEXT;")
                        altered = True
                    if "normalized_pattern" not in cols:
                        logger.info("Adding normalized_pattern column to transactions table...")
                        cursor.execute("ALTER TABLE transactions ADD COLUMN normalized_pattern TEXT;")
                        altered = True
                    if "transfer_subtype" not in cols:
                        logger.info("Adding transfer_subtype column to transactions table...")
                        cursor.execute("ALTER TABLE transactions ADD COLUMN transfer_subtype TEXT;")
                        altered = True
                    if altered:
                        conn.commit()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='regex_rules'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(regex_rules)")
                r_cols = [col[1] for col in cursor.fetchall()]
                r_altered = False
                if "match_type" not in r_cols:
                    logger.info("Adding match_type column to regex_rules table...")
                    cursor.execute("ALTER TABLE regex_rules ADD COLUMN match_type TEXT DEFAULT 'regex';")
                    r_altered = True
                if "display_name" not in r_cols:
                    logger.info("Adding display_name column to regex_rules table...")
                    cursor.execute("ALTER TABLE regex_rules ADD COLUMN display_name TEXT;")
                    r_altered = True
                if "amount_min" not in r_cols:
                    logger.info("Adding amount_min column to regex_rules table...")
                    cursor.execute("ALTER TABLE regex_rules ADD COLUMN amount_min REAL;")
                    r_altered = True
                if "amount_max" not in r_cols:
                    logger.info("Adding amount_max column to regex_rules table...")
                    cursor.execute("ALTER TABLE regex_rules ADD COLUMN amount_max REAL;")
                    r_altered = True
                if "priority" not in r_cols:
                    logger.info("Adding priority column to regex_rules table...")
                    cursor.execute("ALTER TABLE regex_rules ADD COLUMN priority INTEGER DEFAULT 0;")
                    r_altered = True
                if r_altered:
                    conn.commit()
            
            # Ensure merchant_stats has parent_merchant and transfer_subtype columns (added after initial table creation)
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='merchant_stats'")
            if cursor.fetchone():
                try:
                    cursor.execute("PRAGMA table_info(merchant_stats)")
                    ms_cols = [row[1] for row in cursor.fetchall()]
                    ms_altered = False
                    if "parent_merchant" not in ms_cols:
                        logger.info("Adding parent_merchant column to merchant_stats table...")
                        cursor.execute("ALTER TABLE merchant_stats ADD COLUMN parent_merchant TEXT;")
                        ms_altered = True
                    if "transfer_subtype" not in ms_cols:
                        logger.info("Adding transfer_subtype column to merchant_stats table...")
                        cursor.execute("ALTER TABLE merchant_stats ADD COLUMN transfer_subtype TEXT;")
                        ms_altered = True
                    if ms_altered:
                        conn.commit()
                except Exception as ms_err:
                    logger.warning(f"Could not check/alter merchant_stats: {ms_err}")
                
            conn.close()
        except Exception as check_err:
            logger.error(f"Error checking schema for migration: {check_err}")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    schema_path = os.path.join(base_dir, "db", "schema.sql")
    
    if not os.path.exists(schema_path):
        logger.error(f"Schema file not found at {schema_path}")
        return
        
    with open(schema_path, "r") as f:
        schema_sql = f.read()
        
    conn = get_db()
    try:
        conn.executescript(schema_sql)
        conn.commit()
        logger.info("Database initialized successfully.")
        
        if needs_migration:
            migrate_old_data(conn)
        else:
            seed_default_accounts(conn)
            
        # Always run the merchant stats seeder - it is idempotent and only fills gaps
        seed_merchant_stats(conn)
            
        # Initialize passcode hash from settings if set
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'vault_passcode_hash'")
        row = cursor.fetchone()
        if row and row["value"]:
            vault_state["passcode_hash"] = row["value"]
            
        cursor.execute("SELECT value FROM settings WHERE key = 'vault_locked'")
        row = cursor.fetchone()
        if row and row["value"] == "true":
            vault_state["locked"] = True
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        conn.rollback()
    finally:
        conn.close()

def clear_pending_transactions(db_conn, account_id: str):
    """Deletes all transactions with status = 'PENDING' for the given account."""
    try:
        db_conn.execute(
            "DELETE FROM transactions WHERE account_id = ? AND status = 'PENDING'",
            (account_id,)
        )
        db_conn.commit()
        logger.info(f"Cleared pending transactions for account: {account_id}")
    except Exception as e:
        logger.error(f"Error clearing pending transactions for {account_id}: {e}")
        db_conn.rollback()

def update_merchant_stats_new(db_conn, merchant_id: int):
    """Recomputes and updates the cache in merchant_stats_new for the given merchant."""
    if not merchant_id:
        return
    cursor = db_conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO merchant_stats_new (merchant_id, transaction_count, total_spend, total_income, first_seen, last_seen, updated_at)
            SELECT 
                ? as merchant_id,
                COUNT(t.transaction_id) as transaction_count,
                SUM(CASE WHEN t.amount < 0 THEN t.amount ELSE 0 END) as total_spend,
                SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END) as total_income,
                MIN(t.booking_date) as first_seen,
                MAX(t.booking_date) as last_seen,
                CURRENT_TIMESTAMP as updated_at
            FROM transactions t
            JOIN merchant_clusters c ON t.cluster_id = c.cluster_id
            WHERE c.merchant_id = ?
            ON CONFLICT(merchant_id) DO UPDATE SET
                transaction_count = excluded.transaction_count,
                total_spend = excluded.total_spend,
                total_income = excluded.total_income,
                first_seen = excluded.first_seen,
                last_seen = excluded.last_seen,
                updated_at = CURRENT_TIMESTAMP
        """, (merchant_id, merchant_id))
    except Exception as e:
        logger.error(f"Error updating merchant_stats_new for merchant {merchant_id}: {e}")

def upsert_api_transaction(db_conn, txn_data: dict) -> bool:
    """
    Upserts a transaction and resolves its cluster_id.
    Updates the merchant stats cache dynamically.
    """
    # Map old columns to new columns for compatibility if they are passed as old keys
    data = {
        "transaction_id": txn_data.get("transaction_id") or txn_data.get("external_sync_id") or txn_data.get("hash") or "",
        "account_id": txn_data.get("account_id") or txn_data.get("account") or "",
        "booking_date": txn_data.get("booking_date") or txn_data.get("date") or "",
        "description": txn_data.get("description") or "",
        "display_name": txn_data.get("display_name") or txn_data.get("description") or "",
        "category": txn_data.get("category") or "Unsorted",
        "flexibility_tier": txn_data.get("flexibility_tier") or txn_data.get("flexibility") or "Flexible",
        "amount": txn_data.get("amount") or 0.0,
        "currency": txn_data.get("currency") or "EUR",
        "is_guess": txn_data.get("is_guess") or 0,
        "is_pinned": txn_data.get("is_pinned") or 0,
        "is_ignored": txn_data.get("is_ignored") or 0,
        "status": txn_data.get("status") or "SETTLED",
        "ez_synced": txn_data.get("ez_synced") or 0
    }
    
    # Compute two-tier normalized merchant names
    data["normalized_merchant"] = normalize_merchant_name(data["description"])
    data["normalized_pattern"] = normalize_pattern_name(data["description"])
    
    # Resolve account name to account_id if account_id is actually a display name
    cursor = db_conn.cursor()
    cursor.execute("SELECT account_id FROM accounts WHERE account_name = ?", (data["account_id"],))
    row = cursor.fetchone()
    if row:
        data["account_id"] = row["account_id"]

    try:
        # Get old merchant_id before update to clean up stats cache later
        cursor.execute("""
            SELECT c.merchant_id 
            FROM transactions t
            LEFT JOIN merchant_clusters c ON t.cluster_id = c.cluster_id
            WHERE t.transaction_id = ?
        """, (data["transaction_id"],))
        old_row = cursor.fetchone()
        old_merchant_id = old_row["merchant_id"] if old_row else None

        # Resolve cluster_id from Memory Engine first (exact and prefix matches only)
        from engine.memory import match_memory
        mem_match = match_memory(db_conn, data["description"])
        
        cluster_id = None
        merchant_id = None
        
        if mem_match and mem_match["is_auto_resolved"]:
            merchant_id = mem_match["merchant_id"]
            # Look up or create cluster for this pattern
            cursor.execute("SELECT cluster_id FROM merchant_clusters WHERE cluster_name = ?", (data["normalized_pattern"],))
            cluster_row = cursor.fetchone()
            if cluster_row:
                cluster_id = cluster_row["cluster_id"]
                # Link cluster to this merchant if not linked
                cursor.execute("UPDATE merchant_clusters SET merchant_id = ?, confidence_score = 1.0 WHERE cluster_id = ? AND merchant_id IS NULL", (merchant_id, cluster_id))
            else:
                samples = json.dumps([data["description"]])
                cursor.execute(
                    """
                    INSERT INTO merchant_clusters (cluster_name, merchant_id, confidence_score, is_locked, is_user_verified, sample_descriptions)
                    VALUES (?, ?, 1.0, 0, 1, ?)
                    """,
                    (data["normalized_pattern"], merchant_id, samples)
                )
                cluster_id = cursor.lastrowid
        elif mem_match and not mem_match["is_auto_resolved"]:
            # Soft similarity suggestion match - do not auto-resolve
            cursor.execute("SELECT cluster_id FROM merchant_clusters WHERE cluster_name = ?", (data["normalized_pattern"],))
            cluster_row = cursor.fetchone()
            if cluster_row:
                cluster_id = cluster_row["cluster_id"]
            else:
                samples = json.dumps([data["description"]])
                cursor.execute(
                    """
                    INSERT INTO merchant_clusters (cluster_name, merchant_id, confidence_score, is_locked, is_user_verified, sample_descriptions)
                    VALUES (?, NULL, ?, 0, 0, ?)
                    """,
                    (data["normalized_pattern"], mem_match["confidence_score"], samples)
                )
                cluster_id = cursor.lastrowid
                
            # Create a suggested rule in ai_suggested_rules if not exists
            cursor.execute(
                "SELECT suggestion_id FROM ai_suggested_rules WHERE pattern_string = ? AND status = 'PENDING'",
                (data["normalized_pattern"],)
            )
            if not cursor.fetchone():
                cursor.execute(
                    """
                    SELECT m.name as merchant_name, cat.name as category, COALESCE(cat.flexibility_tier, 'Flexible') as flexibility
                    FROM merchants m
                    LEFT JOIN categories cat ON m.category_id = cat.category_id
                    WHERE m.merchant_id = ?
                    """,
                    (mem_match["merchant_id"],)
                )
                m_info = cursor.fetchone()
                if m_info:
                    samples_json = json.dumps([data["description"]])
                    cursor.execute(
                        """
                        INSERT INTO ai_suggested_rules (
                            merchant_name, pattern_string, match_type, suggested_category,
                            suggested_display_name, flexibility_tier, confidence_score, status, transaction_count, sample_descriptions
                        ) VALUES (?, ?, 'substring', ?, ?, ?, ?, 'PENDING', 1, ?)
                        """,
                        (
                            m_info["merchant_name"],
                            data["normalized_pattern"],
                            m_info["category"] or "Other",
                            m_info["merchant_name"],
                            m_info["flexibility"],
                            mem_match["confidence_score"],
                            samples_json
                        )
                    )
        else:
            # Fall back to existing resolution logic
            cursor.execute("SELECT cluster_id, merchant_id FROM merchant_clusters WHERE cluster_name = ?", (data["normalized_pattern"],))
            cluster_row = cursor.fetchone()
            if cluster_row:
                cluster_id = cluster_row["cluster_id"]
                merchant_id = cluster_row["merchant_id"]
            else:
                cursor.execute("SELECT merchant_id FROM merchants WHERE name = ?", (data["normalized_merchant"],))
                merchant_row = cursor.fetchone()
                merchant_id = merchant_row["merchant_id"] if merchant_row else None
                
                samples = json.dumps([data["description"]])
                cursor.execute(
                    """
                    INSERT INTO merchant_clusters (cluster_name, merchant_id, confidence_score, is_locked, is_user_verified, sample_descriptions)
                    VALUES (?, ?, 0.1, 0, 0, ?)
                    """,
                    (data["normalized_pattern"], merchant_id, samples)
                )
                cluster_id = cursor.lastrowid
                
        data["cluster_id"] = cluster_id

        # For backward compatibility, update denormalized category, display name and flexibility tier from the resolved merchant
        if merchant_id:
            cursor.execute("""
                SELECT m.name as resolved_merchant_name, cat.name as category, COALESCE(cat.flexibility_tier, 'Flexible') as flexibility_tier
                FROM merchants m
                LEFT JOIN categories cat ON m.category_id = cat.category_id
                WHERE m.merchant_id = ?
            """, (merchant_id,))
            m_info = cursor.fetchone()
            if m_info:
                data["category"] = m_info["category"] or data["category"]
                data["flexibility_tier"] = m_info["flexibility_tier"] or data["flexibility_tier"]
                data["display_name"] = m_info["resolved_merchant_name"] or data["display_name"]

        # Upsert the transaction
        db_conn.execute(
            """
            INSERT INTO transactions (
                transaction_id, account_id, booking_date, description, display_name, 
                normalized_merchant, normalized_pattern, category, flexibility_tier, 
                amount, currency, is_guess, is_pinned, is_ignored, status, ez_synced, cluster_id
            ) VALUES (
                :transaction_id, :account_id, :booking_date, :description, :display_name, 
                :normalized_merchant, :normalized_pattern, :category, :flexibility_tier, 
                :amount, :currency, :is_guess, :is_pinned, :is_ignored, :status, :ez_synced, :cluster_id
            )
            ON CONFLICT(transaction_id) DO UPDATE SET
                status = excluded.status,
                description = COALESCE(excluded.description, description),
                display_name = COALESCE(excluded.display_name, display_name),
                normalized_merchant = COALESCE(excluded.normalized_merchant, normalized_merchant),
                normalized_pattern = COALESCE(excluded.normalized_pattern, normalized_pattern),
                category = COALESCE(excluded.category, category),
                flexibility_tier = COALESCE(excluded.flexibility_tier, flexibility_tier),
                is_guess = excluded.is_guess,
                is_pinned = COALESCE(excluded.is_pinned, is_pinned),
                is_ignored = COALESCE(excluded.is_ignored, is_ignored),
                amount = excluded.amount,
                cluster_id = excluded.cluster_id
            """,
            data
        )

        # Update stats cache for old and new merchants
        if old_merchant_id:
            update_merchant_stats_new(db_conn, old_merchant_id)
        if merchant_id:
            update_merchant_stats_new(db_conn, merchant_id)

        db_conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error upserting transaction: {e}")
        db_conn.rollback()
        return False
        db_conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error upserting transaction: {e}")
        db_conn.rollback()
        return False

def upsert_manual_transaction(db_conn, txn_data: dict) -> bool:
    """Delegates to upsert_api_transaction after mapping legacy keys."""
    return upsert_api_transaction(db_conn, txn_data)

def get_llm_cache(db_conn, normalized_key: str) -> dict:
    """Query llm_cache for a matching category and flexibility tier."""
    cursor = db_conn.cursor()
    cursor.execute(
        "SELECT category, flexibility_tier FROM llm_cache WHERE merchant_key = ?",
        (normalized_key,)
    )
    row = cursor.fetchone()
    if row:
        return {
            "category": row["category"],
            "flexibility_tier": row["flexibility_tier"]
        }
    return None

def set_llm_cache(db_conn, normalized_key: str, category: str, flexibility: str):
    """Insert or replace a classification result in the llm_cache table."""
    try:
        db_conn.execute(
            "INSERT OR REPLACE INTO llm_cache (merchant_key, category, flexibility_tier) VALUES (?, ?, ?)",
            (normalized_key, category, flexibility)
        )
        db_conn.commit()
    except Exception as e:
        logger.error(f"Error setting LLM cache: {e}")
        db_conn.rollback()

def get_past_category_normalized(db_conn, normalized_key: str) -> dict:
    """Finds the most recent transaction with the same normalized description."""
    cursor = db_conn.cursor()
    cursor.execute(
        """
        SELECT category, flexibility_tier, display_name, is_guess FROM transactions 
        WHERE normalize_desc(description) = ? AND category != 'Unsorted'
        ORDER BY booking_date DESC LIMIT 1
        """,
        (normalized_key,)
    )
    row = cursor.fetchone()
    if row:
        return {
            "category": row["category"],
            "flexibility_tier": row["flexibility_tier"],
            "display_name": row["display_name"],
            "is_guess": row["is_guess"]
        }
    return None
