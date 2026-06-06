import os
import sys
import requests
import logging
from datetime import datetime
import time

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import EZBOOKKEEPING_API_URL, EZBOOKKEEPING_TOKEN
from db.database import get_db
from db.api_writer import CATEGORY_MAP, ACCOUNT_MAP, parse_date_to_unix, get_or_create_needs_review_tag

logger = logging.getLogger(__name__)

def sync_new_transactions():
    """
    Fetches unsynced transactions from the local SQLite database,
    pushes them to ezBookkeeping, and updates their ez_synced status.
    """
    if not EZBOOKKEEPING_TOKEN:
        logger.warning("No EZBOOKKEEPING_TOKEN set. Skipping ezBookkeeping push.")
        return 0

    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Load all unsynced transactions
        cursor.execute("SELECT * FROM transactions WHERE ez_synced = 0 AND status = 'SETTLED'")
        rows = cursor.fetchall()
        
        if not rows:
            logger.info("No unsynced transactions found for ezBookkeeping.")
            return 0
            
        logger.info(f"Found {len(rows)} unsynced settled transactions. Pushing to ezBookkeeping...")
        
        headers = {
            "Authorization": f"Bearer {EZBOOKKEEPING_TOKEN}",
            "Content-Type": "application/json",
            "X-Timezone-Name": "Europe/Berlin",
            "X-Timezone-Offset": "120"
        }
        
        needs_review_tag_id = get_or_create_needs_review_tag(headers)
        success_count = 0
        
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
        
        for row in rows:
            try:
                # Map type (2 = Income, 3 = Expense, 4 = Transfer)
                tx_type = 2 if row["type"] == "Income" else 3 if row["type"] == "Expense" else 4
                
                # Map category
                cat_name = row["category"] or "Other"
                category_id = CATEGORY_MAP.get(cat_name, CATEGORY_MAP["Other"])
                
                # Type boundaries safeguard
                if tx_type == 2: # Income
                    if category_id not in income_category_ids:
                        category_id = "3806661568322600987" # Other Income
                elif tx_type == 4: # Transfer
                    if category_id not in transfer_category_ids:
                        category_id = "3806661568322601030" # Bank Transfer
                else: # Expense
                    if category_id in income_category_ids or category_id in transfer_category_ids:
                        category_id = "3806661568322601029" # Other Expense
                
                # Map account
                acc_name = row["account"]
                source_acc_id = ACCOUNT_MAP.get(acc_name, ACCOUNT_MAP["Revolut"])
                
                # Convert amount to cents
                amount_cents = int(round(abs(float(row["amount"])) * 100))
                
                # Convert date to unix time
                unix_time = parse_date_to_unix(row["date"])
                
                tag_ids = []
                if row["is_guess"] and needs_review_tag_id:
                    tag_ids.append(needs_review_tag_id)
                    
                payload = {
                    "type": tx_type,
                    "categoryId": category_id,
                    "sourceAmount": amount_cents,
                    "time": unix_time,
                    "utcOffset": 120,
                    "comment": row["description"],
                    "tagIds": tag_ids
                }
                
                if tx_type == 4: # Transfer
                    payload["sourceAccountId"] = source_acc_id
                    
                    desc_lower = str(row["description"]).lower()
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
                        # Fallback downgrade transfer to normal expense or income
                        original_cat_name = row["category"] or "Other"
                        original_cat_id = CATEGORY_MAP.get(original_cat_name, CATEGORY_MAP["Other"])
                        
                        payload["type"] = 3 if float(row["amount"]) < 0 else 2
                        if payload["type"] == 3:
                            if original_cat_id not in income_category_ids and original_cat_id not in transfer_category_ids:
                                payload["categoryId"] = original_cat_id
                            else:
                                payload["categoryId"] = "3806661568322601029"
                        else:
                            payload["categoryId"] = "3806661568322600987"
                            
                if payload["type"] != 4:
                    payload["sourceAccountId"] = source_acc_id
                    
                res = requests.post(f"{EZBOOKKEEPING_API_URL}/transactions/add.json", json=payload, headers=headers, timeout=10)
                if res.status_code == 200 and res.json().get("success") == True:
                    cursor.execute("UPDATE transactions SET ez_synced = 1 WHERE id = ?", (row["id"],))
                    success_count += 1
                else:
                    logger.error(f"Failed to push txn {row['id']} to ezBookkeeping: {res.text}")
                    
            except Exception as ex:
                logger.error(f"Error processing row {row['id']} push: {ex}")
                
        conn.commit()
        logger.info(f"Successfully pushed {success_count} transactions to ezBookkeeping.")
        return success_count
        
    except Exception as e:
        logger.error(f"Database error during ezBookkeeping sync: {e}")
        return 0
    finally:
        conn.close()
