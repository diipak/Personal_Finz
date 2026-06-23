import os
import sys
import json
import logging
import sqlite3

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import ALLOWED_CATEGORIES, DB_PATH
from db.database import get_db
from engine.merchant_normalizer import normalize_pattern_name, normalize_merchant_name

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("db_migration")

# Map standard categories to flexibility tiers
DEFAULT_FLEXIBILITY_MAP = {
    # Fixed
    "Rent": "Fixed",
    "Utilities": "Fixed",
    "Telephone Bill": "Fixed",
    "Internet Bill": "Fixed",
    "Insurance": "Fixed",
    "Tax": "Fixed",
    
    # Income
    "Income": "Income",
    
    # Flexible (everything else defaults to Discretionary, but let's set key ones to Flexible)
    "Transfer": "Flexible",
    "Food": "Flexible",
    "Drink": "Flexible",
    "Fruit & Snack": "Flexible",
    "Clothing": "Flexible",
    "Public Transit": "Flexible",
    "Taxi & Car Rental": "Flexible",
    "Personal Car Expense": "Flexible",
    "Train Tickets": "Flexible",
    "Airline Tickets": "Flexible",
    "Express Fee": "Flexible",
    "Sports & Fitness": "Flexible",
    "Travel": "Flexible",
    "Diagnosis & Treatment": "Flexible",
    "Medications": "Flexible",
    "Medical Devices": "Flexible",
    "Service Charge": "Flexible",
    "Interest Expense": "Flexible",
    "Compensation & Fine": "Flexible",
}

def get_default_flexibility(category: str) -> str:
    return DEFAULT_FLEXIBILITY_MAP.get(category, "Discretionary")

def migrate_db():
    logger.info("Initializing Merchant Intelligence Database Migration...")
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 1. Create relational Category & Subcategory tables
        logger.info("Creating categories and subcategories tables...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            category_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT NOT NULL UNIQUE,
            flexibility_tier TEXT NOT NULL DEFAULT 'Flexible',
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS subcategories (
            subcategory_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id      INTEGER NOT NULL,
            name             TEXT NOT NULL,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories(category_id) ON DELETE CASCADE,
            UNIQUE (category_id, name)
        );
        """)
        
        # Seed standard categories
        logger.info("Seeding standard categories...")
        for cat in ALLOWED_CATEGORIES:
            flex = get_default_flexibility(cat)
            cursor.execute("""
            INSERT OR IGNORE INTO categories (name, flexibility_tier)
            VALUES (?, ?)
            """, (cat, flex))
            
        # Seed default subcategories
        logger.info("Seeding default subcategories...")
        subcat_seeds = {
            "Food": ["Groceries", "Restaurants & Dining", "Coffee & Snacks"],
            "Rent": ["Apartment Rent", "Office Rent", "Garage Rent"],
            "Utilities": ["Electricity", "Water & Gas", "Waste Management"],
            "Subscription": ["Streaming Video/Audio", "Cloud Storage", "Software Subscriptions"],
            "Travel": ["Hotel & Lodging", "Vacation", "Business Travel"],
            "Public Transit": ["Bus & Tram", "Subway", "Train"],
            "Income": ["Salary", "Investments Dividend", "Freelance / Side Income"]
        }
        for cat_name, subcats in subcat_seeds.items():
            cursor.execute("SELECT category_id FROM categories WHERE name = ?", (cat_name,))
            cat_row = cursor.fetchone()
            if cat_row:
                cat_id = cat_row["category_id"]
                for sub in subcats:
                    cursor.execute("""
                    INSERT OR IGNORE INTO subcategories (category_id, name)
                    VALUES (?, ?)
                    """, (cat_id, sub))
        
        # 2. Create Merchants & Clusters tables
        logger.info("Creating merchants and merchant_clusters tables...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS merchants (
            merchant_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name                 TEXT NOT NULL UNIQUE,
            parent_merchant_id   INTEGER,
            category_id          INTEGER,
            subcategory_id       INTEGER,
            confidence_score     REAL DEFAULT 1.0,
            is_verified          BOOLEAN DEFAULT 0,
            is_system            BOOLEAN DEFAULT 0,
            created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_merchant_id) REFERENCES merchants(merchant_id) ON DELETE SET NULL,
            FOREIGN KEY (category_id) REFERENCES categories(category_id) ON DELETE SET NULL,
            FOREIGN KEY (subcategory_id) REFERENCES subcategories(subcategory_id) ON DELETE SET NULL
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS merchant_clusters (
            cluster_id           INTEGER PRIMARY KEY AUTOINCREMENT,
            cluster_name         TEXT NOT NULL UNIQUE,
            merchant_id          INTEGER,
            confidence_score     REAL DEFAULT 0.0,
            is_locked            BOOLEAN DEFAULT 0,
            is_user_verified     BOOLEAN DEFAULT 0,
            sample_descriptions   TEXT,
            created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (merchant_id) REFERENCES merchants(merchant_id) ON DELETE SET NULL
        );
        """)
        
        # Create Merchant Stats cache table
        logger.info("Creating merchant_stats_new cache table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS merchant_stats_new (
            merchant_id          INTEGER PRIMARY KEY,
            transaction_count    INTEGER DEFAULT 0,
            total_spend          REAL DEFAULT 0.0,
            total_income         REAL DEFAULT 0.0,
            first_seen           TEXT,
            last_seen            TEXT,
            updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (merchant_id) REFERENCES merchants(merchant_id) ON DELETE CASCADE
        );
        """)
        
        # 3. Seed System Transfer Merchants
        logger.info("Seeding System Transfer Merchants...")
        cursor.execute("SELECT category_id FROM categories WHERE name = 'Transfer'")
        transfer_cat_id = cursor.fetchone()["category_id"]
        
        system_merchants = [
            "Self Transfer",
            "Credit Card Payment",
            "Savings Transfer",
            "Currency Exchange",
            "Person Transfer"
        ]
        system_merchant_ids = {}
        for name in system_merchants:
            cursor.execute("""
            INSERT OR IGNORE INTO merchants (name, category_id, is_verified, is_system, confidence_score)
            VALUES (?, ?, 1, 1, 1.0)
            """, (name, transfer_cat_id))
            cursor.execute("SELECT merchant_id FROM merchants WHERE name = ?", (name,))
            system_merchant_ids[name] = cursor.fetchone()["merchant_id"]

        # 4. Alter transactions table to include cluster_id
        cursor.execute("PRAGMA table_info(transactions)")
        txn_cols = [col["name"] for col in cursor.fetchall()]
        if "cluster_id" not in txn_cols:
            logger.info("Altering transactions table to add cluster_id column...")
            cursor.execute("ALTER TABLE transactions ADD COLUMN cluster_id INTEGER REFERENCES merchant_clusters(cluster_id) ON DELETE SET NULL;")
            
        # Alter regex_rules table to include target_merchant_id and target_cluster_id
        cursor.execute("PRAGMA table_info(regex_rules)")
        rules_cols = [col["name"] for col in cursor.fetchall()]
        if "target_merchant_id" not in rules_cols:
            logger.info("Altering regex_rules to add target_merchant_id column...")
            cursor.execute("ALTER TABLE regex_rules ADD COLUMN target_merchant_id INTEGER REFERENCES merchants(merchant_id) ON DELETE CASCADE;")
        if "target_cluster_id" not in rules_cols:
            logger.info("Altering regex_rules to add target_cluster_id column...")
            cursor.execute("ALTER TABLE regex_rules ADD COLUMN target_cluster_id INTEGER REFERENCES merchant_clusters(cluster_id) ON DELETE CASCADE;")

        # 5. Backfill Clusters and Merchants from existing transactions
        logger.info("Querying transactions to build initial clusters and merchants...")
        cursor.execute("""
        SELECT transaction_id, description, normalized_merchant, normalized_pattern, category, is_pinned, is_guess, amount, transfer_subtype 
        FROM transactions
        """)
        txns = cursor.fetchall()
        
        # Step A: Group transactions by pattern (for clusters) and merchant (for merchants)
        pattern_groups = {}
        merchant_groups = {}
        
        for t in txns:
            desc = t["description"]
            p_name = t["normalized_pattern"] or normalize_pattern_name(desc)
            m_name = t["normalized_merchant"] or normalize_merchant_name(desc)
            
            # Map transfer events to system merchants
            is_transfer = False
            assigned_system_merchant = None
            
            # Heuristics for transfer detection matching system merchants
            m_upper = m_name.upper()
            t_sub = t["transfer_subtype"] or ""
            if t_sub:
                is_transfer = True
                if t_sub == "card_payment":
                    assigned_system_merchant = "Credit Card Payment"
                elif t_sub == "savings":
                    assigned_system_merchant = "Savings Transfer"
                elif t_sub == "exchange":
                    assigned_system_merchant = "Currency Exchange"
                elif t_sub == "peer_to_peer":
                    assigned_system_merchant = "Person Transfer"
                else:
                    assigned_system_merchant = "Self Transfer"
            elif "__TRANSFER_" in m_upper or m_upper == "TRANSFER" or t["category"] == "Transfer":
                is_transfer = True
                assigned_system_merchant = "Self Transfer"
                if "SAVINGS" in m_upper:
                    assigned_system_merchant = "Savings Transfer"
                elif "CREDIT" in m_upper or "CARD" in m_upper:
                    assigned_system_merchant = "Credit Card Payment"
                elif "EXCHANGE" in m_upper:
                    assigned_system_merchant = "Currency Exchange"
                    
            if is_transfer and not assigned_system_merchant:
                assigned_system_merchant = "Self Transfer"
                
            if assigned_system_merchant:
                m_name = assigned_system_merchant
                
            if m_name not in merchant_groups:
                merchant_groups[m_name] = {
                    "transactions": [],
                    "patterns": set(),
                    "is_system": 1 if assigned_system_merchant else 0
                }
            merchant_groups[m_name]["transactions"].append(t)
            merchant_groups[m_name]["patterns"].add(p_name)
            
            if p_name not in pattern_groups:
                pattern_groups[p_name] = {
                    "merchant_name": m_name,
                    "transactions": [],
                    "sample_descriptions": set()
                }
            pattern_groups[p_name]["transactions"].append(t)
            pattern_groups[p_name]["sample_descriptions"].add(desc)

        logger.info(f"Grouping resolved to {len(merchant_groups)} merchants and {len(pattern_groups)} clusters.")
        
        # Step B: Create Merchants
        merchant_db_ids = {}
        for m_name, m_data in merchant_groups.items():
            if m_data["is_system"] == 1:
                # System merchants are already seeded, get ID
                merchant_db_ids[m_name] = system_merchant_ids[m_name]
                continue
                
            # Determine category from most frequent transaction category
            categories_in_group = [t["category"] for t in m_data["transactions"] if t["category"] and t["category"] not in ["Unsorted", "Uncategorized", ""]]
            resolved_cat_name = "Other"
            if categories_in_group:
                # Get the most common category name
                resolved_cat_name = max(set(categories_in_group), key=categories_in_group.count)
                
            cursor.execute("SELECT category_id FROM categories WHERE name = ?", (resolved_cat_name,))
            cat_id_row = cursor.fetchone()
            cat_id = cat_id_row["category_id"] if cat_id_row else None
            
            # Check verification (if any transaction is pinned, merchant is verified)
            is_verified = 1 if any(t["is_pinned"] == 1 for t in m_data["transactions"]) else 0
            confidence = 1.0 if is_verified else 0.5
            
            cursor.execute("""
            INSERT OR IGNORE INTO merchants (name, category_id, is_verified, confidence_score, is_system)
            VALUES (?, ?, ?, ?, 0)
            """, (m_name, cat_id, is_verified, confidence))
            
            cursor.execute("SELECT merchant_id FROM merchants WHERE name = ?", (m_name,))
            merchant_db_ids[m_name] = cursor.fetchone()["merchant_id"]
            
        # Step C: Create Clusters and link transactions
        cluster_db_ids = {}
        for p_name, p_data in pattern_groups.items():
            m_name = p_data["merchant_name"]
            m_id = merchant_db_ids.get(m_name)
            
            # Check user verification and locking (if any transaction in cluster is pinned, lock/verify cluster)
            is_pinned = any(t["is_pinned"] == 1 for t in p_data["transactions"])
            is_locked = 1 if is_pinned else 0
            is_verified = 1 if is_pinned else 0
            confidence = 1.0 if is_pinned else 0.5
            
            samples = json.dumps(list(p_data["sample_descriptions"])[:5])
            
            cursor.execute("""
            INSERT OR IGNORE INTO merchant_clusters (cluster_name, merchant_id, confidence_score, is_locked, is_user_verified, sample_descriptions)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (p_name, m_id, confidence, is_locked, is_verified, samples))
            
            cursor.execute("SELECT cluster_id FROM merchant_clusters WHERE cluster_name = ?", (p_name,))
            c_id = cursor.fetchone()["cluster_id"]
            cluster_db_ids[p_name] = c_id
            
            # Link transactions in this cluster
            tx_ids = [t["transaction_id"] for t in p_data["transactions"]]
            for tx_id in tx_ids:
                cursor.execute("UPDATE transactions SET cluster_id = ? WHERE transaction_id = ?", (c_id, tx_id))

        logger.info("Successfully populated clusters and linked all transactions.")
        
        # 6. Seed merchant_stats_new cache table
        logger.info("Calculating and seeding merchant_stats_new cache table...")
        cursor.execute("""
        INSERT OR REPLACE INTO merchant_stats_new (merchant_id, transaction_count, total_spend, total_income, first_seen, last_seen)
        SELECT 
            m.merchant_id,
            COUNT(t.transaction_id) as transaction_count,
            SUM(CASE WHEN t.amount < 0 THEN t.amount ELSE 0 END) as total_spend,
            SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END) as total_income,
            MIN(t.booking_date) as first_seen,
            MAX(t.booking_date) as last_seen
        FROM transactions t
        JOIN merchant_clusters c ON t.cluster_id = c.cluster_id
        JOIN merchants m ON c.merchant_id = m.merchant_id
        GROUP BY m.merchant_id
        """)
        
        # 7. Create v_transactions_resolved SQL view
        logger.info("Creating database view v_transactions_resolved...")
        cursor.execute("DROP VIEW IF EXISTS v_transactions_resolved;")
        cursor.execute("""
        CREATE VIEW v_transactions_resolved AS
        SELECT 
            t.transaction_id,
            t.account_id,
            t.booking_date,
            t.description,
            t.amount,
            t.currency,
            t.is_guess,
            t.is_pinned,
            t.is_ignored,
            t.status,
            t.cluster_id,
            c.cluster_name,
            m.merchant_id,
            COALESCE(m.name, t.display_name, t.description) AS resolved_merchant_name,
            parent.name AS parent_merchant_name,
            m.is_system AS is_system_merchant,
            COALESCE(cat.name, t.category, 'Unsorted') AS category,
            sc.name AS subcategory,
            COALESCE(cat.flexibility_tier, t.flexibility_tier, 'Flexible') AS flexibility_tier
        FROM transactions t
        LEFT JOIN merchant_clusters c ON t.cluster_id = c.cluster_id
        LEFT JOIN merchants m ON c.merchant_id = m.merchant_id
        LEFT JOIN merchants parent ON m.parent_merchant_id = parent.merchant_id
        LEFT JOIN categories cat ON m.category_id = cat.category_id
        LEFT JOIN subcategories sc ON m.subcategory_id = sc.subcategory_id;
        """)
        
        conn.commit()
        logger.info("Database migration completed successfully!")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_db()
