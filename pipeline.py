import hashlib
import logging
import sys
import os
import pandas as pd

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from parsers.detect import parse_file
from parsers.enable_banking_sync import sync_account_transactions
from engine.normalizer import normalize
from engine.rules import match_rule
from engine.llm import ask_llm
from db.database import (
    get_db, 
    clear_pending_transactions, 
    upsert_manual_transaction, 
    upsert_api_transaction,
    get_llm_cache,
    set_llm_cache,
    get_past_category_normalized
)
from db.sync_ez import sync_new_transactions

logger = logging.getLogger(__name__)

def process_manual_file(file_path: str, account_name: str, bank_type: str = None) -> int:
    """
    Parses a bank statement file, categorizes transactions,
    writes them to SQLite, and syncs to ezBookkeeping.
    """
    logger.info(f"Processing manual file: {file_path} for account: {account_name} with bank_type: {bank_type}")
    try:
        df = parse_file(file_path, bank_type=bank_type)
    except Exception as e:
        logger.error(f"Failed to parse file {file_path}: {e}")
        raise
        
    conn = get_db()
    success_count = 0
    
    # Step 1: Pre-filter out duplicate settled transactions
    processed_rows = []
    seen_hashes = set()
    for _, row in df.iterrows():
        try:
            date_val = str(row["Completed Date"]).strip()
            desc_val = str(row["Description"]).strip()
            amount_val = float(row["Amount"])
            currency_val = str(row.get("Currency", "EUR")).strip()
            
            # Generate deduplication hash for manual imports
            raw_hash_str = f"{date_val}_{desc_val}_{amount_val}"
            tx_hash = hashlib.sha256(raw_hash_str.encode()).hexdigest()
            
            # Check duplicate in current batch
            if tx_hash in seen_hashes:
                logger.info(f"Skipping batch duplicate manual transaction: {desc_val} ({date_val})")
                continue
                
            # Check duplicate in SQLite (inline index query)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM transactions WHERE transaction_id = ?", (tx_hash,))
            if cursor.fetchone():
                logger.info(f"Skipping database duplicate manual transaction: {desc_val} ({date_val})")
                continue
                
            seen_hashes.add(tx_hash)
            normalized_key = normalize(desc_val)
            
            processed_rows.append({
                "date_val": date_val,
                "desc_val": desc_val,
                "amount_val": amount_val,
                "currency_val": currency_val,
                "tx_hash": tx_hash,
                "normalized_key": normalized_key
            })
        except Exception as row_err:
            logger.error(f"Error pre-filtering row {row}: {row_err}")
            
    if not processed_rows:
        conn.close()
        logger.info("No new transactions to process.")
        return 0

    # Step 2: Classify unique merchants using Rules, Cache, and History
    merchant_classifications = {}
    unresolved_merchants = set()
    
    for row in processed_rows:
        norm_key = row["normalized_key"]
        if norm_key in merchant_classifications or norm_key in unresolved_merchants:
            continue
            
        desc = row["desc_val"]
        amt = row["amount_val"]
        
        # 1. Check Regex rules
        rule_result = match_rule(desc, amt)
        if rule_result:
            merchant_classifications[norm_key] = {
                "category": rule_result["category"],
                "display_name": rule_result["display_name"] or desc,
                "flexibility": rule_result["flexibility"],
                "tags": rule_result.get("tags"),
                "is_guess": 0
            }
            continue
            
        # 2. Check LLM persistent cache table
        cache_result = get_llm_cache(conn, norm_key)
        if cache_result:
            merchant_classifications[norm_key] = {
                "category": cache_result["category"],
                "display_name": desc,
                "flexibility": cache_result["flexibility_tier"],
                "tags": None,
                "is_guess": 1
            }
            continue
            
        # 3. Check normalized historical transactions
        history_result = get_past_category_normalized(conn, norm_key)
        if history_result:
            merchant_classifications[norm_key] = {
                "category": history_result["category"],
                "display_name": history_result["display_name"] or desc,
                "flexibility": history_result["flexibility_tier"],
                "tags": None,
                "is_guess": history_result["is_guess"]
            }
            # Save historical classification into cache for future hits
            set_llm_cache(conn, norm_key, history_result["category"], history_result["flexibility_tier"])
            continue
            
        # Add to unresolved merchant queue to be categorized by LLM in a single batch
        unresolved_merchants.add(norm_key)

    # Step 3: Call LLM once per unique unresolved merchant (cluster deduplication)
    for norm_key in unresolved_merchants:
        rep_row = next(r for r in processed_rows if r["normalized_key"] == norm_key)
        rep_desc = rep_row["desc_val"]
        rep_amt = rep_row["amount_val"]
        
        logger.info(f"LLM fallback classification for unique manual merchant: '{rep_desc}' (normalized: '{norm_key}')")
        category = ask_llm(rep_desc, rep_amt)
        
        # Determine flexibility tier
        if category in ["Rent", "Utilities", "Telephone Bill", "Internet Bill", "Insurance", "Tax"]:
            flexibility = "Fixed"
        elif category in ["Transfer", "Income"]:
            flexibility = "Flexible"
        else:
            flexibility = "Discretionary"
            
        # Store in persistent cache
        set_llm_cache(conn, norm_key, category, flexibility)
        
        merchant_classifications[norm_key] = {
            "category": category,
            "display_name": rep_desc,
            "flexibility": flexibility,
            "tags": None,
            "is_guess": 1
        }
        
    # Step 4: Write transactions to SQLite
    for row in processed_rows:
        try:
            norm_key = row["normalized_key"]
            cls = merchant_classifications[norm_key]
            
            txn_dict = {
                "date": row["date_val"],
                "description": row["desc_val"],
                "display_name": cls["display_name"],
                "amount": row["amount_val"],
                "currency": row["currency_val"],
                "account": account_name,
                "type": "Income" if row["amount_val"] > 0 else "Expense",
                "category": cls["category"],
                "flexibility": cls["flexibility"],
                "tags": cls["tags"],
                "is_guess": cls["is_guess"],
                "hash": row["tx_hash"]
            }
            
            if upsert_manual_transaction(conn, txn_dict):
                success_count += 1
                
        except Exception as row_err:
            logger.error(f"Error processing row upsert {row}: {row_err}")
            
    conn.close()
    logger.info(f"Successfully loaded {success_count} manual transactions to database.")
    
    # Sync to ezBookkeeping
    sync_new_transactions()
    
    return success_count

def process_enable_banking_sync(account_id: str, account_name: str) -> int:
    """
    Pulls recent transactions from Enable Banking API, clears transient pending state,
    applies rules/LLM fallback, upserts to SQLite, and syncs to ezBookkeeping.
    """
    logger.info(f"Syncing Enable Banking account {account_id} ({account_name})")
    
    # Fetch transactions via Enable Banking client
    txns = sync_account_transactions(account_id, account_name)
    
    conn = get_db()
    
    # Sweep existing PENDING transactions for this account first
    clear_pending_transactions(conn, account_name)
    
    # Step 1: Pre-filter out duplicate settled transactions
    processed_txns = []
    seen_ids = set()
    for txn in txns:
        try:
            tx_id = txn.get("transaction_id") or txn.get("external_sync_id") or txn.get("hash")
            if not tx_id:
                continue
                
            if tx_id in seen_ids:
                continue
                
            # If settled, skip if it already exists in SQLite
            status_str = txn.get("status", "SETTLED")
            if status_str == 'SETTLED':
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM transactions WHERE transaction_id = ?", (tx_id,))
                if cursor.fetchone():
                    continue
            
            seen_ids.add(tx_id)
            txn["normalized_key"] = normalize(txn["description"])
            processed_txns.append(txn)
        except Exception as pre_err:
            logger.error(f"Error pre-filtering API txn: {pre_err}")
            
    if not processed_txns:
        conn.close()
        logger.info("No new API transactions to sync.")
        return 0
        
    # Step 2: Classify unique merchants using Rules, Cache, and History
    merchant_classifications = {}
    unresolved_merchants = set()
    
    for txn in processed_txns:
        norm_key = txn["normalized_key"]
        if norm_key in merchant_classifications or norm_key in unresolved_merchants:
            continue
            
        desc = txn["description"]
        amt = txn["amount"]
        
        # 1. Check Regex rules
        rule_result = match_rule(desc, amt)
        if rule_result:
            merchant_classifications[norm_key] = {
                "category": rule_result["category"],
                "display_name": rule_result["display_name"] or desc,
                "flexibility": rule_result["flexibility"],
                "tags": rule_result.get("tags"),
                "is_guess": 0
            }
            continue
            
        # 2. Check LLM persistent cache table
        cache_result = get_llm_cache(conn, norm_key)
        if cache_result:
            merchant_classifications[norm_key] = {
                "category": cache_result["category"],
                "display_name": desc,
                "flexibility": cache_result["flexibility_tier"],
                "tags": None,
                "is_guess": 1
            }
            continue
            
        # 3. Check normalized historical transactions
        history_result = get_past_category_normalized(conn, norm_key)
        if history_result:
            merchant_classifications[norm_key] = {
                "category": history_result["category"],
                "display_name": history_result["display_name"] or desc,
                "flexibility": history_result["flexibility_tier"],
                "tags": None,
                "is_guess": history_result["is_guess"]
            }
            set_llm_cache(conn, norm_key, history_result["category"], history_result["flexibility_tier"])
            continue
            
        # Add to unresolved merchant queue
        unresolved_merchants.add(norm_key)
        
    # Step 3: Call LLM once per unique unresolved merchant
    for norm_key in unresolved_merchants:
        rep_txn = next(t for t in processed_txns if t["normalized_key"] == norm_key)
        rep_desc = rep_txn["description"]
        rep_amt = rep_txn["amount"]
        
        logger.info(f"LLM fallback classification for unique API merchant: '{rep_desc}' (normalized: '{norm_key}')")
        category = ask_llm(rep_desc, rep_amt)
        
        # Determine flexibility tier
        if category in ["Rent", "Utilities", "Telephone Bill", "Internet Bill", "Insurance", "Tax"]:
            flexibility = "Fixed"
        elif category in ["Transfer", "Income"]:
            flexibility = "Flexible"
        else:
            flexibility = "Discretionary"
            
        # Store in persistent cache
        set_llm_cache(conn, norm_key, category, flexibility)
        
        merchant_classifications[norm_key] = {
            "category": category,
            "display_name": rep_desc,
            "flexibility": flexibility,
            "tags": None,
            "is_guess": 1
        }
        
    # Step 4: Write transactions to SQLite
    success_count = 0
    for txn in processed_txns:
        try:
            norm_key = txn["normalized_key"]
            cls = merchant_classifications[norm_key]
            
            txn["category"] = cls["category"]
            txn["display_name"] = cls["display_name"]
            txn["flexibility"] = cls["flexibility"]
            txn["tags"] = cls["tags"]
            txn["is_guess"] = cls["is_guess"]
            
            if upsert_api_transaction(conn, txn):
                success_count += 1
        except Exception as txn_err:
            logger.error(f"Error processing synced transaction {txn}: {txn_err}")
            
    conn.close()
    logger.info(f"Successfully upserted {success_count} API transactions to database.")
    
    # Sync to ezBookkeeping
    sync_new_transactions()
    
    return success_count
