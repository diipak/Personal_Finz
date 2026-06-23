import sqlite3
import os
import sys

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import get_db

def migrate():
    print("Running Import Summaries table migration...")
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS import_summaries (
            summary_id           INTEGER PRIMARY KEY AUTOINCREMENT,
            import_date          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            import_type          TEXT NOT NULL,
            institution_id       TEXT NOT NULL,
            total_imported       INTEGER NOT NULL,
            resolved_exact       INTEGER DEFAULT 0,
            resolved_prefix      INTEGER DEFAULT 0,
            resolved_rules       INTEGER DEFAULT 0,
            similarity_suggestions INTEGER DEFAULT 0,
            ai_suggestions       INTEGER DEFAULT 0,
            unknown_merchants    INTEGER DEFAULT 0,
            auto_resolved_rate   REAL DEFAULT 0.0
        );
        """)
        conn.commit()
        print("Migration successful. Table import_summaries is ready.")
    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
