import sqlite3
import os
import sys
import shutil
import logging
import re
import hashlib

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_PATH, DEFAULT_DB_DIR

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
            ('hdfc-manual-id', 'HDFC Bank Account', 'Manual Fallback', 0.0, 'INR', 'hdfc-manual-id', '2026-06-10 00:00:00')
            """
        )
        conn.commit()

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

def upsert_api_transaction(db_conn, txn_data: dict) -> bool:
    """
    Upsert a transaction.
    Matches on transaction_id UNIQUE constraint.
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
    
    # Resolve account name to account_id if account_id is actually a display name
    cursor = db_conn.cursor()
    cursor.execute("SELECT account_id FROM accounts WHERE account_name = ?", (data["account_id"],))
    row = cursor.fetchone()
    if row:
        data["account_id"] = row["account_id"]

    try:
        db_conn.execute(
            """
            INSERT INTO transactions (
                transaction_id, account_id, booking_date, description, display_name, category, flexibility_tier, amount, currency, is_guess, is_pinned, is_ignored, status, ez_synced
            ) VALUES (
                :transaction_id, :account_id, :booking_date, :description, :display_name, :category, :flexibility_tier, :amount, :currency, :is_guess, :is_pinned, :is_ignored, :status, :ez_synced
            )
            ON CONFLICT(transaction_id) DO UPDATE SET
                status = excluded.status,
                description = COALESCE(excluded.description, description),
                display_name = COALESCE(excluded.display_name, display_name),
                category = COALESCE(excluded.category, category),
                flexibility_tier = COALESCE(excluded.flexibility_tier, flexibility_tier),
                is_guess = excluded.is_guess,
                is_pinned = COALESCE(excluded.is_pinned, is_pinned),
                is_ignored = COALESCE(excluded.is_ignored, is_ignored),
                amount = excluded.amount
            """,
            data
        )
        db_conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error upserting transaction: {e}")
        db_conn.rollback()
        return False

def upsert_manual_transaction(db_conn, txn_data: dict) -> bool:
    """Delegates to upsert_api_transaction after mapping legacy keys."""
    return upsert_api_transaction(db_conn, txn_data)
