import hashlib
import requests
import logging
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import GOCARDLESS_SECRET_ID, GOCARDLESS_SECRET_KEY

logger = logging.getLogger(__name__)

class GoCardlessClient:
    def __init__(self, secret_id: str = GOCARDLESS_SECRET_ID, secret_key: str = GOCARDLESS_SECRET_KEY):
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.base_url = "https://bankaccountdata.gocardless.com/api/v2"
        self.token = None

    def authenticate(self):
        """Generates a new access token from GoCardless credentials."""
        url = f"{self.base_url}/token/new/"
        logger.info("Requesting fresh GoCardless access token...")
        try:
            res = requests.post(url, json={"secret_id": self.secret_id, "secret_key": self.secret_key}, timeout=15)
            res.raise_for_status()
            self.token = res.json()["access"]
            logger.info("Successfully authenticated with GoCardless API.")
        except Exception as e:
            logger.error(f"GoCardless authentication failure: {e}")
            raise

    def get_requisition_link(self, institution_id: str, redirect_uri: str, reference: str) -> str:
        """Initializes a bank requisition session and returns the user login link."""
        if not self.token:
            self.authenticate()
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.base_url}/requisitions/"
        payload = {
            "redirect": redirect_uri,
            "institutionId": institution_id,
            "reference": reference,
            "userLanguage": "EN"
        }
        res = requests.post(url, json=payload, headers=headers, timeout=15)
        res.raise_for_status()
        return res.json().get("link")

    def get_accounts(self, requisition_id: str) -> list:
        """Lists connected bank accounts for a successful requisition ID."""
        if not self.token:
            self.authenticate()
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.base_url}/requisitions/{requisition_id}/"
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        return res.json().get("accounts", [])

    def get_transactions(self, account_id: str) -> dict:
        """Fetches raw transactions JSON from GoCardless account endpoint."""
        if not self.token:
            self.authenticate()
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.base_url}/accounts/{account_id}/transactions/"
        res = requests.get(url, headers=headers, timeout=20)
        res.raise_for_status()
        return res.json().get("transactions", {})

def sync_account_transactions(account_id: str, account_name: str, secret_id: str = GOCARDLESS_SECRET_ID, secret_key: str = GOCARDLESS_SECRET_KEY):
    """
    Pulls recent transaction logs for an account, maps them to normalized dict structures.
    Wipes pending transactions first (done at the pipeline level), and handles shifting transaction IDs.
    """
    client = GoCardlessClient(secret_id, secret_key)
    try:
        raw_data = client.get_transactions(account_id)
    except Exception as e:
        logger.error(f"Failed to fetch transactions for GoCardless account {account_id}: {e}")
        raise
        
    normalized = []
    
    # Process both 'booked' (Settled) and 'pending' states
    for status in ["booked", "pending"]:
        tx_list = raw_data.get(status, [])
        is_pending = (status == "pending")
        
        for t in tx_list:
            ext_id = t.get("transactionId")
            
            # Deterministic fallback hashing if bank transactionId is absent
            if not ext_id:
                booking_date = t.get("bookingDate") or t.get("valueDate") or "Unknown"
                amount_val = t.get("transactionAmount", {}).get("amount", "0.0")
                desc_val = t.get("remittanceInformationUnstructured") or t.get("entryReference") or "Unknown"
                raw_str = f"{booking_date}_{amount_val}_{desc_val}"
                ext_id = f"gcl_fallback_{hashlib.sha256(raw_str.encode()).hexdigest()[:16]}"
                
            amount = float(t.get("transactionAmount", {}).get("amount", 0.0))
            currency = t.get("transactionAmount", {}).get("currency", "EUR")
            desc = t.get("remittanceInformationUnstructured") or t.get("entryReference") or "Unknown"
            date = t.get("bookingDate") or t.get("valueDate") or "Unknown"
            
            normalized.append({
                "external_sync_id": ext_id,
                "date": date,
                "description": desc,
                "amount": amount,
                "currency": currency,
                "account": account_name,
                "type": "Income" if amount > 0 else "Expense",
                "status": "PENDING" if is_pending else "SETTLED"
            })
            
    return normalized
