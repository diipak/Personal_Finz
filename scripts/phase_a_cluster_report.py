"""Phase A: Top 100 Merchant Cluster Report — for manual inspection before stoplist build."""
import sqlite3, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("""
    SELECT 
        COALESCE(parent_merchant, merchant_key) as cluster,
        COUNT(DISTINCT merchant_key)            as pattern_count,
        SUM(transaction_count)                  as txn_count,
        GROUP_CONCAT(merchant_key, ' || ')      as sample_keys
    FROM merchant_stats
    GROUP BY COALESCE(parent_merchant, merchant_key)
    ORDER BY txn_count DESC
    LIMIT 100
""")
rows = c.fetchall()
conn.close()

print(f"{'#':<4} {'CLUSTER':<30} {'TXNS':>6}  {'PATTERNS':>8}  SAMPLE RAW KEYS")
print("-" * 120)
for i, r in enumerate(rows, 1):
    samples = (r['sample_keys'] or '')[:100]
    print(f"{i:<4} {r['cluster']:<30} {r['txn_count']:>6}  {r['pattern_count']:>8}  {samples}")
