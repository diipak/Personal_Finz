"""
Step 1: DB schema migration.
- Adds transfer_subtype column to transactions (if missing)
- Seeds account_holder_name into settings (if missing)
Run once. Safe to re-run.
"""
import sqlite3, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH

HOLDER_NAME = "DEEPAK BATHAM"

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row
c = conn.cursor()

# 1. Add transfer_subtype to transactions
c.execute("PRAGMA table_info(transactions)")
tx_cols = [r["name"] for r in c.fetchall()]
if "transfer_subtype" not in tx_cols:
    c.execute("ALTER TABLE transactions ADD COLUMN transfer_subtype TEXT")
    print("Added transfer_subtype column to transactions")
else:
    print("transfer_subtype already exists")

# 2. Add transfer_subtype to merchant_stats (for cluster filtering)
c.execute("PRAGMA table_info(merchant_stats)")
ms_cols = [r["name"] for r in c.fetchall()]
if "transfer_subtype" not in ms_cols:
    c.execute("ALTER TABLE merchant_stats ADD COLUMN transfer_subtype TEXT")
    print("Added transfer_subtype column to merchant_stats")

# 3. Seed account_holder_name in settings
c.execute("SELECT value FROM settings WHERE key = 'account_holder_name'")
row = c.fetchone()
if not row:
    c.execute("INSERT INTO settings (key, value) VALUES ('account_holder_name', ?)", (HOLDER_NAME,))
    print(f"Seeded account_holder_name = '{HOLDER_NAME}'")
else:
    print(f"account_holder_name already set: {row['value']}")

# 4. Seed account_holder_aliases (JSON array)
c.execute("SELECT value FROM settings WHERE key = 'account_holder_aliases'")
row = c.fetchone()
if not row:
    import json
    aliases = json.dumps(["DEEPAK", "D BATHAM"])
    c.execute("INSERT INTO settings (key, value) VALUES ('account_holder_aliases', ?)", (aliases,))
    print(f"Seeded account_holder_aliases")

conn.commit()
conn.close()
print("Migration complete.")
