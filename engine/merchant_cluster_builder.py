"""
engine/merchant_cluster_builder.py

Builds merchant clusters from merchant_clusters and transactions for AI review.
"""
import logging
import json

logger = logging.getLogger(__name__)

def build_merchant_clusters(db_conn) -> list:
    """
    Groups uncategorized transaction patterns from the new merchant_clusters table
    for AI review. A cluster is considered uncategorized if merchant_id is NULL.

    Returns:
        List of dicts:
        [
            {
                "cluster_id": 1,
                "merchant": "PAYPAL NETFLIX",
                "transaction_count": 48,
                "average_amount": -15.99,
                "total_amount": -767.52,
                "sample_patterns": ["PAYPAL NETFLIX", "NETFLIX COM BILL"]
            }
        ]
    """
    from engine.merchant_normalizer import normalize_merchant_name
    cursor = db_conn.cursor()
    try:
        # Query clusters that are not user verified and not locked
        cursor.execute(
            """
            SELECT
                c.cluster_id,
                c.cluster_name,
                c.sample_descriptions,
                m.name AS merchant_name,
                COUNT(t.transaction_id) as transaction_count,
                SUM(t.amount) as total_amount
            FROM merchant_clusters c
            LEFT JOIN merchants m ON c.merchant_id = m.merchant_id
            LEFT JOIN transactions t ON t.cluster_id = c.cluster_id
            WHERE c.is_user_verified = 0 AND c.is_locked = 0
            GROUP BY c.cluster_id, c.cluster_name, c.sample_descriptions, m.name
            """
        )
        rows = cursor.fetchall()

        clusters = []
        for r in rows:
            total_count = r["transaction_count"]
            total_amount = r["total_amount"] or 0.0
            avg_amount = total_amount / total_count if total_count > 0 else 0.0
            
            # Parse sample descriptions from JSON cache
            try:
                samples = json.loads(r["sample_descriptions"]) if r["sample_descriptions"] else []
            except Exception:
                samples = []
                
            if not samples:
                samples = [r["cluster_name"]]

            # Threshold: meaningful enough to send to AI
            if total_count >= 3 or abs(total_amount) >= 100.0:
                merchant_display = r["merchant_name"] or normalize_merchant_name(r["cluster_name"])
                clusters.append({
                    "cluster_id": r["cluster_id"],
                    "merchant": merchant_display, # maps to AI prompt variable "merchant"
                    "transaction_count": total_count,
                    "average_amount": round(avg_amount, 2),
                    "total_amount": round(total_amount, 2),
                    "sample_patterns": samples,
                })

        logger.info(f"Built {len(clusters)} merchant clusters for AI review from new schema.")
        return clusters

    except Exception as e:
        logger.error(f"Error building merchant clusters: {e}")
        return []
