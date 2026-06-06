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
    Upsert a transaction retrieved via automated API (GoCardless).
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

