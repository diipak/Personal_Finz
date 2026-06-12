import sqlite3
import os
import sys
import hashlib
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DEFAULT_DB_DIR, DB_PATH
from engine.rules import apply_rules_to_unpinned_transactions

ACCOUNT_MAPPING = {
    'Revolut': 'b941a58f-79ce-4e81-9da2-39dc370be4f1',
    'Revolut Personal': 'b941a58f-79ce-4e81-9da2-39dc370be4f1',
    'Commerzbank': 'cbca2eaf-fb8b-4e15-9b7e-ca8ea977a62b',
    'Commerzbank Giro': 'cbca2eaf-fb8b-4e15-9b7e-ca8ea977a62b',
    'Advanzia Bank credit card': 'advanzia-manual-id',
    'HDFC': 'hdfc-manual-id',
    'HDFC Bank Account': 'hdfc-manual-id'
}

def merge_databases():
    old_db_path = os.path.join(DEFAULT_DB_DIR, "data.db")
    new_db_path = DB_PATH
    
    if not os.path.exists(old_db_path):
        logger.error(f"Legacy database data.db not found at {old_db_path}")
        return
        
    logger.info(f"Source Legacy DB: {old_db_path}")
    logger.info(f"Target DB: {new_db_path}")
    
    # Connect to databases
    src_conn = sqlite3.connect(old_db_path)
    src_conn.row_factory = sqlite3.Row
    src_cur = src_conn.cursor()
    
    dest_conn = sqlite3.connect(new_db_path)
    dest_conn.row_factory = sqlite3.Row
    dest_cur = dest_conn.cursor()
    
    # Enable foreign keys for safety check
    dest_cur.execute("PRAGMA foreign_keys = ON")
    
    # 1. Merge rules table to regex_rules
    logger.info("Migrating classification rules...")
    src_cur.execute("SELECT * FROM rules")
    rules_copied = 0
    rules_ignored = 0
    for rule in src_cur.fetchall():
        pattern = rule["pattern"]
        match_type = rule["match_type"] or "substring"
        category = rule["category"]
        display_name = rule["display_name"]
        flexibility = rule["flexibility"] or "Flexible"
        amount_min = rule["amount_min"]
        amount_max = rule["amount_max"]
        priority = rule["priority"] or 0
        
        try:
            dest_cur.execute(
                """
                INSERT OR IGNORE INTO regex_rules (
                    pattern_string, match_type, target_category, display_name, flexibility_tier, amount_min, amount_max, priority
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (pattern, match_type, category, display_name, flexibility, amount_min, amount_max, priority)
            )
            if dest_conn.total_changes > 0:
                rules_copied += 1
            else:
                rules_ignored += 1
        except Exception as e:
            logger.error(f"Error inserting rule '{pattern}': {e}")
            
    dest_conn.commit()
    logger.info(f"Rules migration complete. Copied: {rules_copied}, Ignored/Duplicates: {rules_ignored}")

    # 2. Merge transactions
    logger.info("Migrating transactions ledger...")
    src_cur.execute("SELECT * FROM transactions")
    txns_copied = 0
    txns_ignored = 0
    txns_errors = 0
    
    # Fetch existing accounts in target DB to validate mapped IDs
    dest_cur.execute("SELECT account_id FROM accounts")
    valid_account_ids = {r[0] for r in dest_cur.fetchall()}
    logger.info(f"Valid account IDs in target database: {valid_account_ids}")
    
    for t in src_cur.fetchall():
        # Generate hash/transaction_id
        tx_id = t["hash"] or t["external_sync_id"]
        if not tx_id:
            composite = f"{t['date']}{t['description']}{t['amount']}"
            tx_id = hashlib.sha256(composite.encode()).hexdigest()
            
        # Map account name to valid account_id
        old_acc = t["account"]
        acc_id = ACCOUNT_MAPPING.get(old_acc)
        
        # If not in custom map, check if it's already a valid account_id in target
        if not acc_id:
            if old_acc in valid_account_ids:
                acc_id = old_acc
            else:
                # Query target by name
                dest_cur.execute("SELECT account_id FROM accounts WHERE account_name = ?", (old_acc,))
                row = dest_cur.fetchone()
                if row:
                    acc_id = row["account_id"]
                else:
                    logger.warning(f"Could not map account '{old_acc}' to a valid account_id. Skipping transaction {tx_id[:8]}...")
                    txns_errors += 1
                    continue
                    
        booking_date = t["date"]
        desc = t["description"]
        display_name = t["display_name"] or desc
        cat = t["category"] or "Unsorted"
        flex = t["flexibility"] or "Flexible"
        amt = t["amount"]
        curr = t["currency"] or "EUR"
        is_guess = t["is_guess"] or 0
        is_pinned = t["is_pinned"] or 0
        is_ignored = t["is_ignored"] or 0
        status_str = t["status"] or "SETTLED"
        ez_synced = t["ez_synced"] or 0
        
        try:
            dest_cur.execute(
                """
                INSERT OR IGNORE INTO transactions (
                    transaction_id, account_id, booking_date, description, display_name, category, flexibility_tier, amount, currency, is_guess, is_pinned, is_ignored, status, ez_synced
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (tx_id, acc_id, booking_date, desc, display_name, cat, flex, amt, curr, is_guess, is_pinned, is_ignored, status_str, ez_synced)
            )
            # Check if rows changed
            if dest_conn.total_changes > 0:
                txns_copied += 1
            else:
                txns_ignored += 1
        except Exception as e:
            logger.error(f"Error inserting transaction {tx_id}: {e}")
            txns_errors += 1
            
    dest_conn.commit()
    logger.info(f"Transactions migration complete. Copied: {txns_copied}, Ignored/Duplicates: {txns_ignored}, Errors: {txns_errors}")

    # 3. Retroactive rules-based re-classification
    logger.info("Executing rule propagation sweep on unpinned transactions...")
    try:
        updated_count = apply_rules_to_unpinned_transactions()
        logger.info(f"Reclassified {updated_count} unpinned transactions.")
    except Exception as e:
        logger.error(f"Error applying rules sweep: {e}")

    # 4. Update current balances
    logger.info("Updating current balances in accounts table...")
    try:
        dest_cur.execute("SELECT account_id FROM accounts")
        acc_ids = [r["account_id"] for r in dest_cur.fetchall()]
        for aid in acc_ids:
            dest_cur.execute("SELECT SUM(amount) as bal FROM transactions WHERE account_id = ? AND status = 'SETTLED' AND is_ignored = 0", (aid,))
            bal_val = dest_cur.fetchone()["bal"] or 0.0
            dest_cur.execute("UPDATE accounts SET current_balance = ? WHERE account_id = ?", (bal_val, aid))
            logger.info(f"  Account {aid}: updated balance to {bal_val}")
        dest_conn.commit()
        logger.info("Account balances updated successfully.")
    except Exception as e:
        logger.error(f"Error updating balances: {e}")
        dest_conn.rollback()

    src_conn.close()
    dest_conn.close()
    logger.info("Database merge complete.")

if __name__ == "__main__":
    merge_databases()
