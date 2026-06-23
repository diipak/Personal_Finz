import sqlite3
import os
import sys

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_PATH
from db.database import get_db
from engine.merchant_normalizer import normalize_pattern_name

def migrate():
    print("Running Merchant Memory Engine migration...")
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 1. Create table if not exists (insurance backup)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS merchant_signatures (
            signature_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_string       TEXT NOT NULL UNIQUE,
            merchant_id          INTEGER NOT NULL,
            signature_type       TEXT NOT NULL,
            source_action        TEXT NOT NULL,
            is_user_verified     BOOLEAN DEFAULT 0,
            confidence_score     REAL NOT NULL DEFAULT 0.5,
            match_count          INTEGER DEFAULT 0,
            last_matched_at      TIMESTAMP,
            created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (merchant_id) REFERENCES merchants(merchant_id) ON DELETE CASCADE
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_signatures_pattern ON merchant_signatures(pattern_string);")
        
        # 2. Backfill from verified/locked merchant_clusters
        cursor.execute("""
            SELECT cluster_name, merchant_id, is_user_verified, confidence_score, is_locked
            FROM merchant_clusters
            WHERE merchant_id IS NOT NULL
        """)
        clusters = cursor.fetchall()
        
        inserted_count = 0
        for c in clusters:
            pattern = c["cluster_name"].strip().lower()
            if not pattern:
                continue
            
            is_verified = 1 if (c["is_user_verified"] == 1 or c["is_locked"] == 1) else 0
            conf = 1.0 if is_verified else c["confidence_score"]
            sig_type = "EXACT"
            source = "workbench_promote" if is_verified else "ai_review"
            
            cursor.execute("""
                INSERT OR IGNORE INTO merchant_signatures (
                    pattern_string, merchant_id, signature_type, source_action, is_user_verified, confidence_score
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (pattern, c["merchant_id"], sig_type, source, is_verified, conf))
            if cursor.rowcount > 0:
                inserted_count += 1
                
        # 3. Backfill from merchants directly
        cursor.execute("SELECT merchant_id, name, is_verified FROM merchants")
        merchants = cursor.fetchall()
        for m in merchants:
            pattern = m["name"].strip().lower()
            if not pattern:
                continue
            is_verified = m["is_verified"] or 0
            conf = 1.0 if is_verified else 0.5
            sig_type = "EXACT"
            source = "user_verify" if is_verified else "ai_review"
            
            cursor.execute("""
                INSERT OR IGNORE INTO merchant_signatures (
                    pattern_string, merchant_id, signature_type, source_action, is_user_verified, confidence_score
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (pattern, m["merchant_id"], sig_type, source, is_verified, conf))
            if cursor.rowcount > 0:
                inserted_count += 1
                
        conn.commit()
        print(f"Migration successful. Seeded {inserted_count} signatures into merchant_signatures.")
    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
