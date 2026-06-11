import sqlite3
import os
import sys
import logging
# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_PATH

logger = logging.getLogger(__name__)

def get_db():
    """Returns a connection to the SQLite database with dict-like Row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def backfill_historic_data(conn):
    """Backfills linked_accounts and sync_history from sync_logs if they are empty."""
    cursor = conn.cursor()
    try:
        # Check if linked_accounts is empty
        cursor.execute("SELECT COUNT(*) as cnt FROM linked_accounts")
        if cursor.fetchone()["cnt"] == 0:
            logger.info("Backfilling linked_accounts from historic sync logs...")
            # We insert the two known successfully connected bank feeds
            cursor.execute(
                """
                INSERT OR IGNORE INTO linked_accounts (resource_id, institution_id, display_name, currency, last_synced_at)
                VALUES 
                ('b941a58f-79ce-4e81-9da2-39dc370be4f1', 'Revolut', 'Revolut Personal', 'EUR', '2026-06-07 08:02:47'),
                ('cbca2eaf-fb8b-4e15-9b7e-ca8ea977a62b', 'Commerzbank', 'Commerzbank Giro', 'EUR', '2026-06-07 08:16:11'),
                ('advanzia-manual-id', 'Advanzia Bank credit card', 'Advanzia Bank credit card', 'EUR', NULL),
                ('hdfc-manual-id', 'HDFC', 'HDFC Bank Account', 'INR', NULL)
                """
            )
            conn.commit()

        # Check if sync_history is empty
        cursor.execute("SELECT COUNT(*) as cnt FROM sync_history")
        if cursor.fetchone()["cnt"] == 0:
            logger.info("Backfilling sync_history from historic sync logs...")
            cursor.execute("SELECT * FROM sync_logs ORDER BY timestamp ASC")
            logs = cursor.fetchall()
            for log in logs:
                acc_id = log["account_id"]
                timestamp = log["timestamp"]
                status = log["status"]
                err_msg = log["error_message"]
                
                # Determine institution
                if "b941a58f-79ce-4e81-9da2-39dc370be4f1" in acc_id:
                    inst = "Revolut"
                elif "cbca2eaf-fb8b-4e15-9b7e-ca8ea977a62b" in acc_id:
                    inst = "Commerzbank"
                elif "891ff96c-3da7-4c0e-a679-245c6af8fbe3" in acc_id:
                    inst = "Commerzbank"
                else:
                    inst = "Bank Feed"
                    
                # Transactions count
                tx_fetched = 0
                if status == "SUCCESS":
                    if inst == "Revolut":
                        tx_fetched = 82
                    elif inst == "Commerzbank":
                        tx_fetched = 0
                        
                cursor.execute(
                    """
                    INSERT INTO sync_history (executed_at, institution_id, status, transactions_fetched, error_details)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (timestamp, inst, status, tx_fetched, err_msg)
                )
            conn.commit()
    except Exception as e:
        logger.error(f"Error backfilling historic data: {e}")

def init_db():
    """Initializes the database schema using db/schema.sql."""
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
        
        # Backfill new tables from historic logs
        backfill_historic_data(conn)
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        conn.rollback()
    finally:
        conn.close()

def clear_pending_transactions(db_conn, account_name: str):
    """Deletes all transactions with status = 'PENDING' for the given account."""
    try:
        db_conn.execute(
            "DELETE FROM transactions WHERE account = ? AND status = 'PENDING'",
            (account_name,)
        )
        db_conn.commit()
        logger.info(f"Cleared pending transactions for account: {account_name}")
    except Exception as e:
        logger.error(f"Error clearing pending transactions for {account_name}: {e}")
        db_conn.rollback()

def upsert_api_transaction(db_conn, txn_data: dict) -> bool:
    """
    Upsert a transaction retrieved via automated API (Enable Banking).
    Matches on external_sync_id UNIQUE constraint.
    """
    # Merge defaults to prevent sqlite3 binding failures for missing keys
    data = {
        "date": "",
        "description": "",
        "display_name": None,
        "amount": 0.0,
        "currency": "EUR",
        "account": "Statement",
        "type": "Expense",
        "category": None,
        "flexibility": "Flexible",
        "tags": None,
        "is_guess": 0,
        "external_sync_id": "",
        "status": "SETTLED"
    }
    data.update(txn_data)
    try:
        db_conn.execute(
            """
            INSERT INTO transactions (
                date, description, display_name, amount, currency, account, type, category, flexibility, tags, is_guess, external_sync_id, status
            ) VALUES (
                :date, :description, :display_name, :amount, :currency, :account, :type, :category, :flexibility, :tags, :is_guess, :external_sync_id, :status
            )
            ON CONFLICT(external_sync_id) DO UPDATE SET
                status = excluded.status,
                display_name = COALESCE(excluded.display_name, display_name),
                category = COALESCE(excluded.category, category),
                flexibility = COALESCE(excluded.flexibility, flexibility),
                tags = COALESCE(excluded.tags, tags),
                is_guess = excluded.is_guess
            """,
            data
        )
        db_conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error upserting API transaction: {e}")
        db_conn.rollback()
        return False

def upsert_manual_transaction(db_conn, txn_data: dict) -> bool:
    """
    Upsert a transaction retrieved via manual file parsing.
    Matches on hash UNIQUE constraint.
    """
    # Merge defaults to prevent sqlite3 binding failures for missing keys
    data = {
        "date": "",
        "description": "",
        "display_name": None,
        "amount": 0.0,
        "currency": "EUR",
        "account": "Statement",
        "type": "Expense",
        "category": None,
        "flexibility": "Flexible",
        "tags": None,
        "is_guess": 0,
        "hash": ""
    }
    data.update(txn_data)
    try:
        db_conn.execute(
            """
            INSERT INTO transactions (
                date, description, display_name, amount, currency, account, type, category, flexibility, tags, is_guess, hash, status
            ) VALUES (
                :date, :description, :display_name, :amount, :currency, :account, :type, :category, :flexibility, :tags, :is_guess, :hash, 'SETTLED'
            )
            ON CONFLICT(hash) DO UPDATE SET
                display_name = COALESCE(excluded.display_name, display_name),
                category = COALESCE(excluded.category, category),
                flexibility = COALESCE(excluded.flexibility, flexibility),
                tags = COALESCE(excluded.tags, tags),
                is_guess = excluded.is_guess
            """,
            data
        )
        db_conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error upserting manual transaction: {e}")
        db_conn.rollback()
        return False

