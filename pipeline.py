import hashlib
import logging
import sys
import os
import pandas as pd

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from parsers.detect import parse_file
from parsers.gocardless_sync import sync_account_transactions
from engine.normalizer import normalize
from engine.rules import match_rule
from engine.llm import ask_llm
from db.database import get_db, clear_pending_transactions, upsert_manual_transaction, upsert_api_transaction
from db.sync_ez import sync_new_transactions

logger = logging.getLogger(__name__)

def process_manual_file(file_path: str, account_name: str) -> int:
    """
    Parses a bank statement file, categorizes transactions,
    writes them to SQLite, and syncs to ezBookkeeping.
    """
    logger.info(f"Processing manual file: {file_path} for account: {account_name}")
    try:
        df = parse_file(file_path)
    except Exception as e:
        logger.error(f"Failed to parse file {file_path}: {e}")
        raise
        
    conn = get_db()
    success_count = 0
    
    for _, row in df.iterrows():
        try:
            date_val = str(row["Completed Date"]).strip()
            desc_val = str(row["Description"]).strip()
            amount_val = float(row["Amount"])
            currency_val = str(row.get("Currency", "EUR")).strip()
            
            # Generate deduplication hash for manual imports
            raw_hash_str = f"{date_val}_{desc_val}_{amount_val}"
            tx_hash = hashlib.sha256(raw_hash_str.encode()).hexdigest()
            
            # Categorize using rules
            norm_desc = normalize(desc_val)
            rule_result = match_rule(norm_desc, amount_val)
            
            if rule_result:
                category = rule_result["category"]
                display_name = rule_result["display_name"] or desc_val
                flexibility = rule_result["flexibility"]
                tags = rule_result["tags"]
                is_guess = 0
            else:
                # LLM Fallback
                category = ask_llm(desc_val, amount_val)
                display_name = desc_val
                tags = None
                is_guess = 1
                
                # Get default flexibility for guess category
                if category in ["Rent", "Utilities", "Telephone Bill", "Internet Bill", "Insurance", "Tax"]:
                    flexibility = "Fixed"
                elif category in ["Transfer", "Income"]:
                    flexibility = "Flexible"
                else:
                    flexibility = "Discretionary"
                    
            txn_dict = {
                "date": date_val,
                "description": desc_val,
                "display_name": display_name,
                "amount": amount_val,
                "currency": currency_val,
                "account": account_name,
                "type": "Income" if amount_val > 0 else "Expense",
                "category": category,
                "flexibility": flexibility,
                "tags": tags,
                "is_guess": is_guess,
                "hash": tx_hash
            }
            
            if upsert_manual_transaction(conn, txn_dict):
                success_count += 1
                
        except Exception as row_err:
            logger.error(f"Error processing row {row}: {row_err}")
            
    conn.close()
    logger.info(f"Successfully loaded {success_count} manual transactions to database.")
    
    # Sync to ezBookkeeping
    sync_new_transactions()
    
    return success_count

def process_gocardless_sync(account_id: str, account_name: str, secret_id: str, secret_key: str) -> int:
    """
    Pulls recent transactions from GoCardless API, clears transient pending state,
    applies rules/LLM fallback, upserts to SQLite, and syncs to ezBookkeeping.
    """
    logger.info(f"Syncing GoCardless account {account_id} ({account_name})")
    
    # Fetch transactions via GoCardless client
    txns = sync_account_transactions(account_id, account_name, secret_id, secret_key)
    
    conn = get_db()
    
    # Sweep existing PENDING transactions for this account first
    clear_pending_transactions(conn, account_name)
    
    success_count = 0
    for txn in txns:
        try:
            desc_val = txn["description"]
            amount_val = txn["amount"]
            
            # Categorize using rules
            norm_desc = normalize(desc_val)
            rule_result = match_rule(norm_desc, amount_val)
            
            if rule_result:
                category = rule_result["category"]
                display_name = rule_result["display_name"] or desc_val
                flexibility = rule_result["flexibility"]
                tags = rule_result["tags"]
                is_guess = 0
            else:
                # LLM Fallback
                category = ask_llm(desc_val, amount_val)
                display_name = desc_val
                tags = None
                is_guess = 1
                
                # Get default flexibility for guess category
                if category in ["Rent", "Utilities", "Telephone Bill", "Internet Bill", "Insurance", "Tax"]:
                    flexibility = "Fixed"
                elif category in ["Transfer", "Income"]:
                    flexibility = "Flexible"
                else:
                    flexibility = "Discretionary"
                    
            txn["category"] = category
            txn["display_name"] = display_name
            txn["flexibility"] = flexibility
            txn["tags"] = tags
            txn["is_guess"] = is_guess
            
            if upsert_api_transaction(conn, txn):
                success_count += 1
                
        except Exception as txn_err:
            logger.error(f"Error processing synced transaction {txn}: {txn_err}")
            
    conn.close()
    logger.info(f"Successfully upserted {success_count} API transactions to database.")
    
    # Sync to ezBookkeeping
    sync_new_transactions()
    
    return success_count
