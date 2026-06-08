import os
import requests
import logging
from datetime import datetime
import time

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

# Category mapping from app categories to ezBookkeeping subcategory IDs
CATEGORY_MAP = {
    "Food": "3806661568322600988",
    "Drink": "3806661568322600989",
    "Fruit & Snack": "3806661568322600990",
    "Clothing": "3806661568322600991",
    "Jewelry": "3806661568322600992",
    "Cosmetic": "3806661568322600993",
    "Hair Cuts & Salon": "3806661568322600994",
    "Houseware": "3806661568322600995",
    "Electronics": "3806661568322600996",
    "Repairs & Maintenance": "3806661568322600997",
    "Utilities": "3806661568322600999",
    "Rent": "3806661568322601000",
    "Public Transit": "3806661568322601001",
    "Taxi & Car Rental": "3806661568322601002",
    "Personal Car Expense": "3806661568322601003",
    "Train Tickets": "3806661568322601004",
    "Airline Tickets": "3806661568322601005",
    "Telephone Bill": "3806661568322601006",
    "Internet Bill": "3806661568322601007",
    "Express Fee": "3806661568322601008",
    "Sports & Fitness": "3806661568322601009",
    "Party Expense": "3806661568322601010",
    "Movies & Shows": "3806661568322601011",
    "Toys & Games": "3806661568322601012",
    "Subscription": "3806661568322601013",
    "Pet Expense": "3806661568322601014",
    "Travel": "3806661568322601015",
    "Books & Magazines": "3806661568322601016",
    "Training Courses": "3806661568322601017",
    "Certification": "3806661568322601018",
    "Gifts": "3806661568322601019",
    "Donations": "3806661568322601020",
    "Diagnosis & Treatment": "3806661568322601021",
    "Medications": "3806661568322601022",
    "Medical Devices": "3806661568322601023",
    "Tax": "3806661568322601024",
    "Service Charge": "3806661568322601025",
    "Insurance": "3806661568322601026",
    "Interest Expense": "3806661568322601027",
    "Compensation & Fine": "3806661568322601028",
    "Transfer": "3806661568322601030",
    "Income": "3806661568322600987",
    "Other": "3806661568322601029",
    # Legacy fallbacks from old category names
    "Groceries": "3806661568322600988",  # -> Food
    "Shopping": "3806661568322600991",    # -> Clothing (closest general shopping)
    "Dining": "3806661568322600988",     # -> Food
    "Transport": "3806661568322601001",  # -> Public Transit
    "Entertainment": "3806661568322601011", # -> Movies & Shows
    "Fuel": "3806661568322601003",       # -> Personal Car Expense
    "Self Transfer": "3806661568322601030", # -> Bank Transfer (transfer category)
    "Utilities": "3806661568322600999",  # -> Utilities Expense
}

# Account mapping from statement names to ezBookkeeping account IDs
ACCOUNT_MAP = {
    "Revolut": "3806661759180210176",
    "HDFC": "3806661881586778112",
    "Commerzbank": "3806661791392464896",
    "Advanzia Bank credit card": "3806662012583280640",
    "Amazon Zinia credit": "3806662098482626560",
    "Wise": "3806661937421352960",
    "Trade Republic": "3806661847227039744",
    "Statement": "3806661759180210176"    # Default to Revolut if generic "Statement"
}

def parse_date_to_unix(date_str):
    """Parses various date formats to Unix timestamp in seconds."""
    date_str = str(date_str).strip()
    formats = [
        "%Y-%m-%d",          # e.g., 2023-05-31
        "%d.%m.%Y",          # e.g., 31.05.2023
        "%d/%m/%y",          # e.g., 04/04/20
        "%d/%m/%Y",          # e.g., 04/04/2020
        "%b %d, %Y",         # e.g., Apr 2, 2023
        "%B %d, %Y",         # e.g., April 2, 2023
        "%Y-%m-%d %H:%M:%S", # e.g., 2022-10-30 17:19:57
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return int(dt.timestamp())
        except Exception:
            pass
    return int(time.time())

def get_or_create_needs_review_tag(headers):
    """Retrieves the ID for the 'Needs_Review' tag, creating it if it doesn't exist."""
    try:
        res = requests.get(f"{EZBOOKKEEPING_API_URL}/transaction/tags/list.json", headers=headers, timeout=5)
        if res.status_code == 200:
            tags = res.json().get("result", [])
            for tag in tags:
                if tag.get("name") == "Needs_Review":
                    return tag.get("id")
        
        # Create it if not found
        payload = {"name": "Needs_Review"}
        res = requests.post(f"{EZBOOKKEEPING_API_URL}/transaction/tags/add.json", json=payload, headers=headers, timeout=5)
        if res.status_code == 200:
            return res.json().get("result", {}).get("id")
    except Exception as e:
        logger.error(f"Failed to get or create Needs_Review tag: {e}")
    return None

def push_to_ezbookkeeping(df):
    """
    Pushes a DataFrame of categorized transactions to the ezBookkeeping HTTP API.
    Uses active WSL/Tailscale endpoints, Unix times, cents-based amounts, and tags.
    """
    if not EZBOOKKEEPING_TOKEN:
        logger.warning("No EZBOOKKEEPING_TOKEN found. Cannot push to API.")
        return False
        
    headers = {
        "Authorization": f"Bearer {EZBOOKKEEPING_TOKEN}",
        "Content-Type": "application/json",
        "X-Timezone-Name": "Europe/Berlin",
        "X-Timezone-Offset": "120"
    }
    
    # Pre-fetch or create the Needs_Review tag ID
    needs_review_tag_id = get_or_create_needs_review_tag(headers)
    
    success_count = 0
    
    if "LLM_Guessed" not in df.columns:
        df["LLM_Guessed"] = False

    for _, row in df.iterrows():
        try:
            # Map type (2 = Income, 3 = Expense, 4 = Transfer)
            tx_type = 2 if row["Type"] == "Income" else 3 if row["Type"] == "Expense" else 4
            
            # Map category
            cat_name = row.get("Category", "Other")
            category_id = CATEGORY_MAP.get(cat_name, CATEGORY_MAP["Other"])
            
            # Safeguard category types based on transaction types
            income_category_ids = {
                "3806661568322600977", "3806661568322600978", "3806661568322600979", 
                "3806661568322600980", "3806661568322600981", "3806661568322600982", 
                "3806661568322600983", "3806661568322600984", "3806661568322600985", 
                "3806661568322600986", "3806661568322600987"
            }
            transfer_category_ids = {
                "3806661568322601030", "3806661568322601031", "3806661568322601032", 
                "3806661568322601033", "3806661568322601034", "3806661568322601035", 
                "3806661568322601036", "3806661568322601037", "3806661568322601038", 
                "3806661568322601039"
            }
            
            if tx_type == 2: # Income
                if category_id not in income_category_ids:
                    category_id = "3806661568322600987" # Other Income
            elif tx_type == 4: # Transfer
                if category_id not in transfer_category_ids:
                    category_id = "3806661568322601030" # Bank Transfer
            else: # Expense (tx_type == 3)
                # Ensure it's not an income or transfer category
                if category_id in income_category_ids or category_id in transfer_category_ids:
                    category_id = "3806661568322601029" # Other Expense
            
            # Map account
            acc_name = row.get("Account", "Revolut")
            source_acc_id = ACCOUNT_MAP.get(acc_name, ACCOUNT_MAP["Revolut"])
            
            # Convert amount to cents
            amount_cents = int(round(abs(float(row["Amount"])) * 100))
            
            # Convert date to Unix timestamp (seconds)
            unix_time = parse_date_to_unix(row["Completed Date"])
            
            tag_ids = []
            if row["LLM_Guessed"] and needs_review_tag_id:
                tag_ids.append(needs_review_tag_id)
                
            payload = {
                "type": tx_type,
                "categoryId": category_id,
                "sourceAmount": amount_cents,
                "time": unix_time,
                "utcOffset": 120,
                "comment": row["Description"][:250],
                "tagIds": tag_ids
            }
            
            # Handle source and destination accounts depending on type
            if tx_type == 4: # Transfer
                payload["sourceAccountId"] = source_acc_id
                
                # Try to detect destination account from description
                desc_lower = str(row["Description"]).lower()
                dest_acc_id = None
                
                if "wise" in desc_lower:
                    dest_acc_id = ACCOUNT_MAP["Wise"]
                elif "revolut" in desc_lower or "revolt" in desc_lower:
                    dest_acc_id = ACCOUNT_MAP["Revolut"]
                elif "commerzbank" in desc_lower:
                    dest_acc_id = ACCOUNT_MAP["Commerzbank"]
                elif "trade republic" in desc_lower or "republic" in desc_lower:
                    dest_acc_id = ACCOUNT_MAP["Trade Republic"]
                elif "hdfc" in desc_lower:
                    dest_acc_id = ACCOUNT_MAP["HDFC"]
                
                if dest_acc_id and dest_acc_id != source_acc_id:
                    payload["destinationAccountId"] = dest_acc_id
                    payload["destinationAmount"] = amount_cents
                else:
                    # Can't find a valid destination account — downgrade to Expense or Income
                    # but PRESERVE the original categorized category instead of falling to "Other"
                    original_cat_name = row.get("Category", "Other")
                    original_cat_id = CATEGORY_MAP.get(original_cat_name, CATEGORY_MAP["Other"])
                    
                    payload["type"] = 3 if float(row["Amount"]) < 0 else 2
                    if payload["type"] == 3:
                        # Keep original category if it's a valid expense category
                        if original_cat_id not in income_category_ids and original_cat_id not in transfer_category_ids:
                            payload["categoryId"] = original_cat_id
                        else:
                            payload["categoryId"] = "3806661568322601029" # Other Expense
                    else:
                        payload["categoryId"] = "3806661568322600987" # Other Income
            
            if payload["type"] != 4: # Income or Expense
                payload["sourceAccountId"] = source_acc_id

            res = requests.post(f"{EZBOOKKEEPING_API_URL}/transactions/add.json", json=payload, headers=headers, timeout=5)
            if res.status_code == 200 and res.json().get("success") == True:
                success_count += 1
            else:
                logger.error(f"Failed to insert transaction: {res.text}")
        except Exception as e:
            logger.error(f"API Request failed: {e}")
            
    logger.info(f"Successfully pushed {success_count} transactions to ezBookkeeping.")
    return True
