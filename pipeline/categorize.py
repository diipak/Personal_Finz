import sys
import os
import pandas as pd
import json
import requests
import re

# allow imports from project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.rule_engine import categorize

# ==============================
# CONFIG
# ==============================

SELF_NAME = "deepak batham"
LLM_MODEL = "qwen2.5:7b"
OLLAMA_URL = "http://100.103.104.90:11434/api/generate"

ALLOWED_CATEGORIES = [
    "Groceries",
    "Travel",
    "Utilities",
    "Subscription",
    "Transfer",
    "Shopping",
    "Income",
    "Dining",
    "Fuel",
    "Rent",
    "Insurance",
    "Other"
]

LLM_CACHE = {}

# ==============================
# INPUT FILE
# ==============================

input_file = sys.argv[1]
output_file = sys.argv[2]

df = pd.read_csv(input_file)

# Normalize column names for internal use
# Common variations: 'Completed Date', 'Date' -> 'Completed Date'
# 'Description', 'Narration' -> 'Description'
# 'Amount' -> 'Amount'

col_map = {}
for col in df.columns:
    if col.lower() in ['date', 'completed date']:
        col_map[col] = 'Completed Date'
    if col.lower() in ['description', 'narration']:
        col_map[col] = 'Description'
    if col.lower() in ['amount']:
        col_map[col] = 'Amount'

df = df.rename(columns=col_map)

# Keep completed transactions only if State column exists
if "State" in df.columns:
    df = df[df["State"] == "COMPLETED"]

if "Amount" in df.columns:
    # Ensure amount is numeric (handle strings with commas if needed, though parsers should handle it)
    if df["Amount"].dtype == object:
        df["Amount"] = df["Amount"].astype(str).str.replace(",","").astype(float)
    df["Amount"] = df["Amount"].astype(float)

# Ensure essential columns exist
if "Completed Date" not in df.columns:
    df["Completed Date"] = "Unknown"
if "Description" not in df.columns:
    df["Description"] = "Unknown"
if "Amount" not in df.columns:
    df["Amount"] = 0.0
if "Currency" not in df.columns:
    df["Currency"] = "USD" # Default

# ==============================
# LOAD MERCHANT RULES
# ==============================

RULE_FILE = os.path.join(os.path.dirname(__file__), "merchant_rules.json")

with open(RULE_FILE, "r") as f:
    rules = json.load(f)

merchant_categories = rules.get("merchant_categories", {})

# ==============================
# HELPER FUNCTIONS
# ==============================

def extract_merchant(description):
    desc = str(description).lower() if description is not None else ""
    desc = re.sub(r'[^a-z\s]', ' ', desc)
    words = desc.split()

    for word in words:
        if len(word) > 2:
            return word

    return desc.strip()


def ask_llm(description, amount):
    desc_str = str(description)
    merchant_key = extract_merchant(description)
...
def determine_type(description, amount):

    desc = str(description).lower() if description is not None else ""

    if SELF_NAME in desc:
        return "Transfer"

    if amount > 0:
        return "Income"

    return "Expense"


def determine_category(description, amount):
    
    desc_str = str(description) if description is not None else ""

    # 1️⃣ rule engine
    rule_category = categorize(desc_str)

    if rule_category:
        return rule_category

    # 2️⃣ LLM fallback
    category = ask_llm(desc_str, amount)

    merchant_key = extract_merchant(desc_str)

    merchant_categories[merchant_key] = category

    return category


# ==============================
# APPLY CLASSIFICATION
# ==============================

df["Type"] = df.apply(lambda row: determine_type(row["Description"], row["Amount"]), axis=1)

df["Category"] = df.apply(
    lambda row: determine_category(row["Description"], row["Amount"]),
    axis=1
)

if "Account" not in df.columns:
    df["Account"] = "Statement"

# ==============================
# SAVE RULES
# ==============================

rules["merchant_categories"] = merchant_categories

with open(RULE_FILE, "w") as f:
    json.dump(rules, f, indent=2)

# ==============================
# EXPORT RESULT
# ==============================

final_df = df[
    [
        "Completed Date",
        "Description",
        "Amount",
        "Currency",
        "Account",
        "Type",
        "Category"
    ]
]

final_df.to_csv(output_file, index=False)

print("Processing complete.")
print(f"Saved to {output_file}")