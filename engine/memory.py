import re
import logging
from engine.merchant_normalizer import normalize_pattern_name

logger = logging.getLogger(__name__)

def clean_and_tokenize(text: str) -> set:
    """Strips punctuation, normalizes to uppercase, splits, and filters out single characters."""
    if not text:
        return set()
    cleaned = re.sub(r"[^A-Z0-9\s]", " ", text.upper())
    return {w for w in cleaned.split() if len(w) > 1}

def calculate_jaccard_similarity(text_a: str, text_b: str) -> float:
    """Computes the token-based Jaccard similarity coefficient between two strings."""
    tokens_a = clean_and_tokenize(text_a)
    tokens_b = clean_and_tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a.intersection(tokens_b)
    union = tokens_a.union(tokens_b)
    return len(intersection) / len(union)

def match_memory(db_conn, description: str) -> dict:
    """
    Looks up the transaction description in the memory engine (merchant_signatures).
    
    Returns a dictionary if matched:
        {
            "merchant_id": int,
            "is_auto_resolved": bool, # True for EXACT and PREFIX, False for SIMILARITY
            "match_type": str,        # 'EXACT', 'PREFIX', or 'SIMILARITY'
            "confidence_score": float
        }
    Or None if no match is found or if a similarity conflict occurs.
    """
    if not description:
        return None
        
    normalized_pattern = normalize_pattern_name(description).strip().lower()
    if not normalized_pattern:
        return None
        
    cursor = db_conn.cursor()
    
    # 1. Exact Match Check
    cursor.execute(
        """
        SELECT merchant_id, confidence_score 
        FROM merchant_signatures 
        WHERE pattern_string = ? AND signature_type = 'EXACT'
        """,
        (normalized_pattern,)
    )
    row = cursor.fetchone()
    if row:
        logger.info(f"Exact memory match found for '{normalized_pattern}': Merchant {row['merchant_id']}")
        return {
            "merchant_id": row["merchant_id"],
            "is_auto_resolved": True,
            "match_type": "EXACT",
            "confidence_score": row["confidence_score"]
        }
        
    # 2. Verified Prefix Match Check
    cursor.execute(
        """
        SELECT merchant_id, pattern_string, confidence_score 
        FROM merchant_signatures 
        WHERE signature_type = 'PREFIX' AND is_user_verified = 1
        """
    )
    prefixes = cursor.fetchall()
    prefix_matches = []
    for p in prefixes:
        p_str = p["pattern_string"].lower()
        if normalized_pattern.startswith(p_str):
            prefix_matches.append(p)
            
    if prefix_matches:
        # If there are multiple prefixes, sort by length descending to pick the most specific match
        prefix_matches.sort(key=lambda x: len(x["pattern_string"]), reverse=True)
        best_prefix = prefix_matches[0]
        logger.info(f"Verified prefix memory match found for '{normalized_pattern}' starting with '{best_prefix['pattern_string']}': Merchant {best_prefix['merchant_id']}")
        return {
            "merchant_id": best_prefix["merchant_id"],
            "is_auto_resolved": True,
            "match_type": "PREFIX",
            "confidence_score": best_prefix["confidence_score"]
        }
        
    # 3. Soft Jaccard Similarity Match Check
    # Retrieve all user-verified signatures
    cursor.execute(
        """
        SELECT merchant_id, pattern_string, confidence_score 
        FROM merchant_signatures 
        WHERE is_user_verified = 1
        """
    )
    signatures = cursor.fetchall()
    
    similarity_candidates = []
    for s in signatures:
        sig_str = s["pattern_string"]
        score = calculate_jaccard_similarity(normalized_pattern, sig_str)
        if score >= 0.7:
            similarity_candidates.append({
                "merchant_id": s["merchant_id"],
                "pattern_string": s["pattern_string"],
                "confidence_score": s["confidence_score"],
                "similarity_score": score
            })
            
    if similarity_candidates:
        # Check if there are competing merchant IDs (similarity conflict)
        unique_merchants = {c["merchant_id"] for c in similarity_candidates}
        if len(unique_merchants) > 1:
            logger.warning(f"Similarity conflict detected for '{normalized_pattern}': Matches multiple merchants: {unique_merchants}. Routing to review.")
            return None # Routing always to manual review Workbench
            
        # Pick the candidate with the highest similarity score
        similarity_candidates.sort(key=lambda x: x["similarity_score"], reverse=True)
        best_cand = similarity_candidates[0]
        logger.info(f"Soft similarity memory match found for '{normalized_pattern}' against '{best_cand['pattern_string']}' (Score: {best_cand['similarity_score']:.2f}): Merchant {best_cand['merchant_id']}")
        return {
            "merchant_id": best_cand["merchant_id"],
            "is_auto_resolved": False, # Similarity matches never auto-resolve
            "match_type": "SIMILARITY",
            "confidence_score": best_cand["similarity_score"]
        }
        
    return None
