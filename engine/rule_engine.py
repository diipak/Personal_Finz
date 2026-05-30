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

import re

def categorize(description):
    desc = str(description).lower() if description is not None else ""

    for word in transfer_keywords:
        if re.search(rf"\b{re.escape(word)}\b", desc):
            return "Transfer"

    merchant = normalize(desc)

    # First, try strict regex matching if the rule is defined as a regex pattern
    for pattern, category in merchant_categories.items():
        if not pattern: continue
        # Simple heuristic: if pattern contains special regex characters, compile as regex
        if any(c in pattern for c in [".*", "^", "$", "\\", "(", "["]):
            try:
                if re.search(pattern, merchant, re.IGNORECASE):
                    return category
            except re.error:
                pass
        
        # Fallback to word boundary match
        if re.search(rf"\b{re.escape(pattern)}\b", merchant, re.IGNORECASE):
            return category

    return None