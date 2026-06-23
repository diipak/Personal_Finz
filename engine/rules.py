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
    Metadata dict keys: ['category', 'display_name', 'flexibility', 'merchant_id', 'cluster_id']
    """
    desc = str(description).strip()
    abs_amount = abs(amount)
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Fetch all rules with their resolved merchant details
        cursor.execute("""
            SELECT 
                r.rule_id, r.pattern_string, r.match_type, r.amount_min, r.amount_max, r.priority,
                r.target_merchant_id, r.target_cluster_id,
                r.target_category as legacy_category, r.display_name as legacy_display_name, r.flexibility_tier as legacy_flexibility,
                m.name as resolved_merchant_name, cat.name as resolved_category, cat.flexibility_tier as resolved_flexibility
            FROM regex_rules r
            LEFT JOIN merchants m ON r.target_merchant_id = m.merchant_id
            LEFT JOIN categories cat ON m.category_id = cat.category_id
            ORDER BY r.priority DESC, r.rule_id ASC
        """)
        rules = cursor.fetchall()
        
        for r in rules:
            pattern = r["pattern_string"]
            match_type = r["match_type"] or "substring"
            
            matched = False
            if match_type == "substring":
                from engine.normalizer import normalize
                norm_desc = normalize(desc)
                norm_pattern = normalize(pattern)
                if re.search(rf"\b{re.escape(norm_pattern)}\b", norm_desc, re.IGNORECASE) or pattern.lower() in desc.lower():
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
                
                # Resolve details: prioritize merchant/cluster, fall back to legacy rule columns
                merchant_id = r["target_merchant_id"]
                cluster_id = r["target_cluster_id"]
                
                # Resolve details from merchant
                category = r["resolved_category"]
                display_name = r["resolved_merchant_name"]
                flexibility = r["resolved_flexibility"]
                
                # Resolve details from cluster if merchant not directly set
                if not merchant_id and cluster_id:
                    cursor.execute("""
                        SELECT c.merchant_id, m.name as merchant_name, cat.name as category, cat.flexibility_tier
                        FROM merchant_clusters c
                        LEFT JOIN merchants m ON c.merchant_id = m.merchant_id
                        LEFT JOIN categories cat ON m.category_id = cat.category_id
                        WHERE c.cluster_id = ?
                    """, (cluster_id,))
                    c_info = cursor.fetchone()
                    if c_info:
                        merchant_id = c_info["merchant_id"]
                        category = c_info["category"] or category
                        display_name = c_info["merchant_name"] or display_name
                        flexibility = c_info["flexibility_tier"] or flexibility
                        
                # Fallback to legacy fields
                if not category:
                    category = r["legacy_category"]
                if not display_name:
                    display_name = r["legacy_display_name"]
                if not flexibility:
                    flexibility = r["legacy_flexibility"]
                    
                if not flexibility:
                    flexibility = "Flexible"
                
                return {
                    "category": category,
                    "display_name": display_name,
                    "flexibility": flexibility,
                    "merchant_id": merchant_id,
                    "cluster_id": cluster_id
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
        cursor.execute("SELECT transaction_id as id, description, amount, display_name FROM transactions WHERE is_pinned = 0")
        txns = cursor.fetchall()
        
        for t in txns:
            match = match_rule(t["description"], t["amount"])
            
            if match:
                # If match has a cluster_id or merchant_id, we resolve the cluster_id to set
                cluster_id = match["cluster_id"]
                if not cluster_id and match["merchant_id"]:
                    # Try to find a cluster for this pattern linked to that merchant
                    from engine.merchant_normalizer import normalize_pattern_name
                    p_name = normalize_pattern_name(t["description"])
                    cursor.execute("SELECT cluster_id FROM merchant_clusters WHERE cluster_name = ?", (p_name,))
                    c_row = cursor.fetchone()
                    if c_row:
                        cluster_id = c_row["cluster_id"]
                        # Ensure cluster is linked to this merchant
                        cursor.execute("UPDATE merchant_clusters SET merchant_id = ? WHERE cluster_id = ?", (match["merchant_id"], cluster_id))
                    else:
                        import json
                        samples = json.dumps([t["description"]])
                        cursor.execute("""
                            INSERT INTO merchant_clusters (cluster_name, merchant_id, confidence_score, is_locked, is_user_verified, sample_descriptions)
                            VALUES (?, ?, 1.0, 0, 0, ?)
                        """, (p_name, match["merchant_id"], samples))
                        cluster_id = cursor.lastrowid
                
                # Update transaction
                cursor.execute(
                    """
                    UPDATE transactions SET
                        category = ?,
                        display_name = ?,
                        flexibility_tier = ?,
                        is_guess = 0,
                        cluster_id = COALESCE(?, cluster_id)
                    WHERE transaction_id = ?
                    """,
                    (
                        match["category"],
                        match["display_name"] or t["description"],
                        match["flexibility"],
                        cluster_id,
                        t["id"]
                    )
                )
                updated_count += 1
                
                # Update stats cache for this merchant if it exists
                if match["merchant_id"]:
                    from db.database import update_merchant_stats_new
                    update_merchant_stats_new(conn, match["merchant_id"])
                    
        conn.commit()
        logger.info(f"Rule re-application updated {updated_count} unpinned transactions.")
    except Exception as e:
        logger.error(f"Error applying rules to unpinned transactions: {e}")
        conn.rollback()
    finally:
        conn.close()
    return updated_count
