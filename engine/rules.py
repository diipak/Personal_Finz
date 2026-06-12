import re
import sys
import os
import logging

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import get_db

logger = logging.getLogger(__name__)

def match_rule(description: str, amount: float) -> dict:
    """
    Checks the description and amount against SQLite rules.
    Returns a dict of metadata to apply, or None if no match is found.
    Metadata dict keys: ['category', 'display_name', 'flexibility']
    """
    desc = str(description).strip()
    abs_amount = abs(amount)
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Sort by priority desc so higher priority rules run first
        cursor.execute("SELECT * FROM regex_rules ORDER BY priority DESC, rule_id ASC")
        rules = cursor.fetchall()
        
        for r in rules:
            pattern = r["pattern_string"]
            match_type = r["match_type"] or "substring"
            
            matched = False
            if match_type == "substring":
                if re.search(rf"\b{re.escape(pattern)}\b", desc, re.IGNORECASE):
                    matched = True
            elif match_type == "exact":
                if pattern.lower() == desc.lower():
                    matched = True
            elif match_type == "regex":
                try:
                    if re.search(pattern, desc, re.IGNORECASE):
                        matched = True
                except re.error as e:
                    logger.error(f"Invalid regex rule pattern '{pattern}': {e}")
                    
            if matched:
                # Check amount bounds
                if r["amount_min"] is not None and abs_amount < r["amount_min"]:
                    continue
                if r["amount_max"] is not None and abs_amount > r["amount_max"]:
                    continue
                
                # Retrieve default flexibility based on category if not explicitly set
                category = r["target_category"]
                flexibility = r["flexibility_tier"]
                if not flexibility:
                    if category in ["Rent", "Utilities", "Telephone Bill", "Internet Bill", "Insurance", "Tax"]:
                        flexibility = "Fixed"
                    elif category in ["Transfer", "Income"]:
                        flexibility = "Flexible"
                    else:
                        flexibility = "Discretionary"
                
                return {
                    "category": category,
                    "display_name": r["display_name"],
                    "flexibility": flexibility
                }
    except Exception as e:
        logger.error(f"Error matching rules: {e}")
    finally:
        conn.close()
        
    return None

def apply_rules_to_unpinned_transactions() -> int:
    """
    Scans all unpinned transactions (is_pinned = 0) and re-applies rules.
    Returns the count of updated transactions.
    """
    conn = get_db()
    cursor = conn.cursor()
    updated_count = 0
    try:
        # Select all unpinned transactions
        cursor.execute("SELECT transaction_id as id, description, amount, display_name FROM transactions WHERE is_pinned = 0")
        txns = cursor.fetchall()
        
        for t in txns:
            # We normalize the description before matching
            from engine.normalizer import normalize
            norm_desc = normalize(t["description"])
            match = match_rule(norm_desc, t["amount"])
            
            if match:
                cursor.execute(
                    """
                    UPDATE transactions SET
                        category = ?,
                        display_name = ?,
                        flexibility_tier = ?,
                        is_guess = 0
                    WHERE transaction_id = ?
                    """,
                    (
                        match["category"],
                        match["display_name"] or t["description"],
                        match["flexibility"],
                        t["id"]
                    )
                )
                updated_count += 1
        conn.commit()
        logger.info(f"Rule re-application updated {updated_count} unpinned transactions.")
    except Exception as e:
        logger.error(f"Error applying rules to unpinned transactions: {e}")
        conn.rollback()
    finally:
        conn.close()
    return updated_count

