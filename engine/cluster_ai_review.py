import json
import logging
import requests
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import OLLAMA_URL, LLM_MODEL, ALLOWED_CATEGORIES
from engine.merchant_cluster_builder import build_merchant_clusters

logger = logging.getLogger(__name__)

def run_cluster_ai_review(db_conn) -> int:
    """
    Runs the AI suggestion engine on uncategorized merchant clusters.
    Generates rule suggestions and saves them to the database.
    """
    logger.info("Starting AI review of merchant clusters...")
    
    # 1. Build clusters from merchant_stats
    clusters = build_merchant_clusters(db_conn)
    if not clusters:
        logger.info("No merchant clusters found that meet the review thresholds.")
        return 0
        
    # 2. Batch clusters for Ollama query to save tokens
    batch_size = 3
    total_suggestions = 0
    
    for i in range(0, len(clusters), batch_size):
        batch = clusters[i:i+batch_size]
        
        prompt = f"""You are a precise personal finance assistant.
Analyze the following merchant clusters and suggest categorization rules.

Allowed Categories:
{", ".join(ALLOWED_CATEGORIES)}

For each cluster, suggest:
1. pattern_string: a clean, specific lowercase substring to match transactions of this behavior (e.g. "netflix" for sample pattern "PAYPAL NETFLIX", "uber eats" for "UBER EATS").
2. match_type: "substring"
3. suggested_category: one of the allowed categories.
4. suggested_display_name: a clean, title-cased display name (e.g. "Netflix", "Uber Eats").
5. flexibility_tier: "Fixed", "Flexible", "Discretionary", or "Income".

Input Clusters:
{json.dumps(batch, indent=2)}

Respond with a JSON object containing a key "rules" which is a list of objects, one for each input cluster, containing:
- merchant: the exact merchant name from the input cluster
- pattern_string: the suggested pattern string
- match_type: "substring"
- suggested_category: the suggested category
- suggested_display_name: the suggested display name
- flexibility_tier: the suggested flexibility tier
- confidence_score: a confidence value between 0.0 and 1.0 (float)
- confidence_reason: a natural language explanation of why this name/category was suggested (e.g. "Recognized international streaming service brand.")
- supporting_signals: a list of positive matching strings (e.g. ["Description contains netflix", "Standard subscription pricing"])
- conflict_indicators: a list of warning strings or conflicts, if any (e.g. ["Higher transaction amount than usual"])
- frequency: the estimated frequency of the transaction (must be one of: "Weekly", "Monthly", "Quarterly", "Infrequent")

Do not return any explanations or conversational text. Return ONLY the raw JSON object.
"""
        try:
            logger.info(f"Sending batch of {len(batch)} clusters to Ollama ({LLM_MODEL})...")
            response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": LLM_MODEL,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                    "options": {
                        "temperature": 0.0
                    }
                },
                timeout=180
            )
            response.raise_for_status()
            result_str = response.json().get("response", "").strip()
            
            # Strip reasoning block if present
            if "<think>" in result_str:
                parts = result_str.split("</think>")
                if len(parts) > 1:
                    result_str = parts[-1].strip()
                    
            result_data = json.loads(result_str)
            rules = result_data.get("rules", [])
            
            cursor = db_conn.cursor()
            for rule in rules:
                merchant_name = rule.get("merchant")
                pattern_string = rule.get("pattern_string")
                match_type = rule.get("match_type", "substring")
                suggested_cat = rule.get("suggested_category", "Other")
                suggested_disp = rule.get("suggested_display_name")
                flex_tier = rule.get("flexibility_tier", "Flexible")
                confidence = float(rule.get("confidence_score", 0.5))
                
                # Match corresponding cluster to retrieve transaction count and sample patterns
                cluster = next((c for c in batch if c["merchant"] == merchant_name), None)
                tx_count = cluster["transaction_count"] if cluster else 0
                sample_desc = json.dumps(cluster["sample_patterns"]) if cluster else "[]"
                
                # Validate category
                if suggested_cat not in ALLOWED_CATEGORIES:
                    # Case-insensitive recovery
                    matched = False
                    for cat in ALLOWED_CATEGORIES:
                        if cat.lower() == suggested_cat.lower():
                            suggested_cat = cat
                            matched = True
                            break
                    if not matched:
                        suggested_cat = "Other"
                        
                # Ensure flexibility is valid
                if flex_tier not in ["Fixed", "Flexible", "Discretionary", "Income"]:
                    flex_tier = "Flexible"
                    
                if not pattern_string:
                    pattern_string = merchant_name.lower()
                    
                # 3. Mark previous pending suggestions for the same merchant/pattern as SUPERSEDED
                cursor.execute(
                    """
                    UPDATE ai_suggested_rules 
                    SET status = 'SUPERSEDED' 
                    WHERE merchant_name = ? AND status = 'PENDING'
                    """,
                    (merchant_name,)
                )
                
                # 4. Insert new suggestion as PENDING
                explanation_data = {
                    "reason": rule.get("confidence_reason") or "Suggested by classification heuristics.",
                    "supporting_signals": rule.get("supporting_signals") or ["New transaction cluster matching standard patterns."],
                    "conflict_indicators": rule.get("conflict_indicators") or [],
                    "frequency": rule.get("frequency") or "Infrequent"
                }
                explanation_json = json.dumps(explanation_data)

                cursor.execute(
                    """
                    INSERT INTO ai_suggested_rules (
                        merchant_name, pattern_string, match_type, suggested_category,
                        suggested_display_name, flexibility_tier, amount_min, amount_max,
                        confidence_score, status, transaction_count, sample_descriptions, explanation_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?)
                    """,
                    (
                        merchant_name,
                        pattern_string.lower(),
                        match_type,
                        suggested_cat,
                        suggested_disp or merchant_name.title(),
                        flex_tier,
                        cluster["average_amount"] if cluster else None, # default amount_min
                        None, # default amount_max
                        confidence,
                        tx_count,
                        sample_desc,
                        explanation_json
                    )
                )
                total_suggestions += 1
                
            db_conn.commit()
            
        except Exception as e:
            logger.error(f"Error querying Ollama or saving suggestions: {e}")
            
    logger.info(f"AI review completed. Generated {total_suggestions} suggestions.")
    return total_suggestions

if __name__ == "__main__":
    import sqlite3
    from db.database import get_db
    conn = get_db()
    try:
        run_cluster_ai_review(conn)
    finally:
        conn.close()
