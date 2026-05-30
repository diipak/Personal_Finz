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
LLM_MODEL = "qwen3.5:4b"
OLLAMA_URL = "http://100.103.104.90:11434/api/generate"

ALLOWED_CATEGORIES = [
    "Food",
    "Drink",
    "Fruit & Snack",
    "Clothing",
    "Jewelry",
    "Cosmetic",
    "Hair Cuts & Salon",
    "Houseware",
    "Electronics",
    "Repairs & Maintenance",
    "Utilities",
    "Rent",
    "Public Transit",
    "Taxi & Car Rental",
    "Personal Car Expense",
    "Train Tickets",
    "Airline Tickets",
    "Telephone Bill",
    "Internet Bill",
    "Express Fee",
    "Sports & Fitness",
    "Party Expense",
    "Movies & Shows",
    "Toys & Games",
    "Subscription",
    "Pet Expense",
    "Travel",
    "Books & Magazines",
    "Training Courses",
    "Certification",
    "Gifts",
    "Donations",
    "Diagnosis & Treatment",
    "Medications",
    "Medical Devices",
    "Tax",
    "Service Charge",
    "Insurance",
    "Interest Expense",
    "Compensation & Fine",
    "Transfer",
    "Income",
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

IGNORE_WORDS = {
    "debit", "credit", "transfer", "payment", "refund", "www", "inst", "pos", "nan", "card", "online"
}

def extract_merchant(description):
    desc = str(description).lower() if description is not None else ""
    desc = re.sub(r'[^a-z\s]', ' ', desc)
    words = desc.split()

    for word in words:
        if len(word) > 2 and word not in IGNORE_WORDS:
            return word

    # Fallback to the first word of length > 2 even if ignored
    for word in words:
        if len(word) > 2:
            return word

    return desc.strip()


def ask_llm(description, amount):
    desc_str = str(description)
    merchant_key = extract_merchant(description)
    
    if merchant_key in LLM_CACHE:
        return LLM_CACHE[merchant_key]
        
    prompt = f"""You are a precise personal finance assistant.
Categorize the following bank transaction:
Description: "{desc_str}"
Amount: {amount}

Allowed categories:
{", ".join(ALLOWED_CATEGORIES)}

Respond with ONLY one of the allowed categories. Do not include any other text, explanation, or punctuation."""

    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=10)
        if response.status_code == 200:
            result = response.json()
            category = result.get("response", "").strip()
            for cat in ALLOWED_CATEGORIES:
                if cat.lower() in category.lower():
                    LLM_CACHE[merchant_key] = cat
                    return cat
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error calling LLM: {e}")
        
    LLM_CACHE[merchant_key] = "Other"
    return "Other"
def determine_type(description, amount):

    desc = str(description).lower() if description is not None else ""

    # Commerzbank prefix patterns
    if desc.startswith("transfer:"):
        return "Transfer"
    if desc.startswith("credit:"):
        return "Income"
    if desc.startswith("debit:"):
        return "Expense"
    if desc.startswith("interest/charges:"):
        return "Expense"

    # Self-transfer detection (but not salary/income credits that mention your name)
    if SELF_NAME in desc:
        # If amount is positive and description suggests incoming money, it's Income
        if amount > 0:
            return "Income"
        return "Transfer"

    if amount > 0:
        return "Income"

    return "Expense"


def determine_category(description, amount):
    
    desc_str = str(description) if description is not None else ""

    # 1️⃣ rule engine
    rule_category = categorize(desc_str)

    if rule_category:
        return rule_category, False

    # 2️⃣ LLM fallback
    category = ask_llm(desc_str, amount)

    merchant_key = extract_merchant(desc_str)
    merchant_categories[merchant_key] = category

    return category, True


# ==============================
# APPLY CLASSIFICATION
# ==============================

df["Type"] = df.apply(lambda row: determine_type(row["Description"], row["Amount"]), axis=1)

# Unpack the tuple returned by determine_category into two columns
cat_results = df.apply(lambda row: determine_category(row["Description"], row["Amount"]), axis=1)
df["Category"] = [res[0] for res in cat_results]
df["LLM_Guessed"] = [res[1] for res in cat_results]

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
        "Category",
        "LLM_Guessed"
    ]
]

final_df.to_csv(output_file, index=False)

# Push to ezBookkeeping API
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.api_writer import push_to_ezbookkeeping

print("Pushing to ezBookkeeping API...")
push_to_ezbookkeeping(final_df)

print("Processing complete.")
print(f"Saved to {output_file}")