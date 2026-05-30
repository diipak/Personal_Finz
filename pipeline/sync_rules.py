import os
import sys
import json
import requests
import logging
from datetime import datetime, timedelta

# allow imports from project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.normalizer import normalize
from engine.rule_engine import categorize

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Custom .env loader to avoid python-dotenv dependency issues
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ[k] = v

EZBOOKKEEPING_API_URL = os.environ.get("EZBOOKKEEPING_API_URL", "http://localhost:8080/api/v1")
EZBOOKKEEPING_TOKEN = os.environ.get("EZBOOKKEEPING_TOKEN", "")

RULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "pipeline",
    "merchant_rules.json"
)

def sync_rules():
    """
    Fetches recent transactions from ezBookkeeping.
    If a transaction does NOT have 'Needs_Review', it implies the user has approved the category.
    Updates merchant_rules.json with new deterministic regex rules.
    """
    if not EZBOOKKEEPING_TOKEN:
        logger.warning("No EZBOOKKEEPING_TOKEN found. Cannot sync.")
        return

    headers = {
        "Authorization": f"Bearer {EZBOOKKEEPING_TOKEN}",
        "Content-Type": "application/json",
        "X-Timezone-Name": "Europe/Berlin",
        "X-Timezone-Offset": "120"
    }

    # In production, we should fetch transactions from the last 7 days
    # For now, we will fetch a recent window
    min_time = int((datetime.now() - timedelta(days=7)).timestamp() * 1000)

    try:
        res = requests.get(f"{EZBOOKKEEPING_API_URL}/transactions/list.json?count=100&minTime={min_time}", headers=headers)
        if res.status_code != 200:
            logger.error(f"Failed to fetch transactions: {res.text}")
            return
            
        data = res.json()
        transactions = data.get("data", {}).get("items", [])
    except Exception as e:
        logger.error(f"API request failed: {e}")
        return

    with open(RULE_PATH, "r") as f:
        rules = json.load(f)
    merchant_categories = rules.get("merchant_categories", {})

    updates_made = 0

    for tx in transactions:
        tags = tx.get("tags", [])
        
        # If the transaction is still under review, skip learning from it
        if "Needs_Review" in tags:
            continue

        desc = tx.get("comment", "")
        if not desc:
            continue
            
        category_id = tx.get("categoryId")
        # In a real implementation, we would map category_id back to category Name
        # For this prototype, we'll assume the category string is passed or fetched.
        # Here we mock it by fetching the resolved category name:
        category_name = f"Category_{category_id}" # Placeholder

        merchant = normalize(desc)
        
        # Check if our rule engine already matches this correctly
        current_prediction = categorize(desc)
        
        if current_prediction != category_name:
            # The rule engine missed it or was wrong, and the user has approved it in the UI.
            # Learn the rule using a precise word boundary pattern
            new_pattern = rf"\b{merchant}\b"
            if new_pattern not in merchant_categories:
                merchant_categories[new_pattern] = category_name
                logger.info(f"Learned new rule: {new_pattern} -> {category_name}")
                updates_made += 1

    if updates_made > 0:
        rules["merchant_categories"] = merchant_categories
        with open(RULE_PATH, "w") as f:
            json.dump(rules, f, indent=2)
        logger.info(f"Successfully learned {updates_made} new rules.")
    else:
        logger.info("No new rules to learn.")

if __name__ == "__main__":
    print("Starting Rule Sync from ezBookkeeping...")
    sync_rules()
