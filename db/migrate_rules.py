import json
import os
import sys
# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import get_db, init_db

# Category to flexibility default mapping
FLEXIBILITY_MAP = {
    # Fixed
    "Rent": "Fixed",
    "Utilities": "Fixed",
    "Telephone Bill": "Fixed",
    "Internet Bill": "Fixed",
    "Insurance": "Fixed",
    "Tax": "Fixed",
    
    # Flexible
    "Food": "Flexible",
    "Drink": "Flexible",
    "Fruit & Snack": "Flexible",
    "Clothing": "Flexible",
    "Public Transit": "Flexible",
    "Train Tickets": "Flexible",
    "Personal Car Expense": "Flexible",
    "Medications": "Flexible",
    "Diagnosis & Treatment": "Flexible",
    
    # Discretionary (all others default to Discretionary)
}

def get_default_flexibility(category: str) -> str:
    if category in ["Transfer", "Income"]:
        return "Flexible" # Or leave as Flexible
    return FLEXIBILITY_MAP.get(category, "Discretionary")

def migrate():
    # Ensure database is initialized
    init_db()
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(base_dir, "pipeline", "merchant_rules.json")
    
    if not os.path.exists(json_path):
        print(f"JSON rules file not found at {json_path}")
        return
        
    with open(json_path, "r") as f:
        rules_data = json.load(f)
        
    conn = get_db()
    cursor = conn.cursor()
    
    # Clear existing rules
    cursor.execute("DELETE FROM rules")
    
    from engine.normalizer import normalize

    # Migrate transfer_keywords
    for pattern in rules_data.get("transfer_keywords", []):
        flex = get_default_flexibility("Transfer")
        norm_pattern = normalize(pattern)
        cursor.execute(
            """
            INSERT INTO rules (pattern, match_type, category, flexibility, priority)
            VALUES (?, 'substring', 'Transfer', ?, 10)
            """,
            (norm_pattern, flex)
        )
        
    # Migrate income_keywords
    for pattern in rules_data.get("income_keywords", []):
        flex = get_default_flexibility("Income")
        norm_pattern = normalize(pattern)
        cursor.execute(
            """
            INSERT INTO rules (pattern, match_type, category, flexibility, priority)
            VALUES (?, 'substring', 'Income', ?, 10)
            """,
            (norm_pattern, flex)
        )
        
    # Migrate merchant_categories
    for pattern, rule_val in rules_data.get("merchant_categories", {}).items():
        if not pattern:
            continue
            
        if isinstance(rule_val, dict):
            category = rule_val.get("category")
            display_name = rule_val.get("display_name")
        else:
            category = rule_val
            display_name = None
            
        # Check if it looks like a regex pattern
        match_type = 'substring'
        if any(c in pattern for c in [".*", "^", "$", "\\", "(", "["]):
            match_type = 'regex'
            
        # Normalize pattern if not a regex
        final_pattern = pattern if match_type == 'regex' else normalize(pattern)
            
        flex = get_default_flexibility(category)
        
        # Determine priority: regex usually has higher priority
        priority = 5 if match_type == 'regex' else 1
        
        cursor.execute(
            """
            INSERT INTO rules (pattern, match_type, category, display_name, flexibility, priority)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (final_pattern, match_type, category, display_name, flex, priority)
        )
        
    conn.commit()
    conn.close()
    print("Successfully migrated rules to SQLite database.")

if __name__ == "__main__":
    migrate()
