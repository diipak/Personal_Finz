import json
import os
from .normalizer import normalize

RULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "pipeline",
    "merchant_rules.json"
)

with open(RULE_PATH) as f:
    RULES = json.load(f)

transfer_keywords = RULES.get("transfer_keywords", [])
merchant_categories = RULES.get("merchant_categories", {})

def categorize(description):

    desc = str(description).lower() if description is not None else ""

    for word in transfer_keywords:
        if word in desc:
            return "Transfer"

    merchant = normalize(desc)

    if merchant in merchant_categories:
        return merchant_categories[merchant]

    return None