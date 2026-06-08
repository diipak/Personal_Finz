import time
import hashlib
import requests
import logging
import jwt
import re

from config import ENABLE_BANKING_APP_ID, ENABLE_BANKING_PRIVATE_KEY

logger = logging.getLogger(__name__)

class EnableBankingClient:
    def __init__(self, app_id: str = ENABLE_BANKING_APP_ID, private_key: bytes = ENABLE_BANKING_PRIVATE_KEY):
        self.app_id = app_id
        self.private_key = private_key
        self.base_url = "https://api.enablebanking.com"

    def get_headers(self) -> dict:
        """Generates an RS256 JWT signed with the private key and returns auth headers."""
        now = int(time.time())
        payload = {
            "iss": "enablebanking.com",
            "aud": "api.enablebanking.com",
            "iat": now,
            "exp": now + 3600
        }
        headers = {
            "typ": "JWT",
            "alg": "RS256",
            "kid": self.app_id
        }
        token = jwt.encode(payload, self.private_key, algorithm="RS256", headers=headers)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def get_auth_link(self, institution_id: str, redirect_uri: str, state: str) -> str:
        """Calls POST /auth to generate user redirect link for authorization."""
        headers = self.get_headers()
        url = f"{self.base_url}/auth"
        
        # Parse institution e.g. "Nordea (FI)" -> name: "Nordea", country: "FI"
        match = re.search(r"^(.*?)\s*\((.*?)\)$", institution_id.strip())
        if match:
            aspsp_name = match.group(1).strip()
            aspsp_country = match.group(2).strip().upper()
        else:
            aspsp_name = institution_id.strip()
            aspsp_country = "DE"  # Local default country
            
        import datetime
        valid_until = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")

        payload = {
            "access": {
                "balances": True,
                "transactions": True,
                "valid_until": valid_until
            },
            "aspsp": {
                "name": aspsp_name,
                "country": aspsp_country
            },
            "state": state,
            "redirect_url": redirect_uri
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=15)
            res.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error(f"Enable Banking /auth HTTPError response: {res.text}")
            raise
        return res.json().get("url")

    def create_session(self, code: str) -> dict:
        """Exchanges authorization code from callback for session credentials."""
        headers = self.get_headers()
        url = f"{self.base_url}/sessions"
        payload = {
            "code": code
        }
        res = requests.post(url, json=payload, headers=headers, timeout=15)
        res.raise_for_status()
        return res.json()

    def get_transactions(self, account_id: str) -> list:
        """Fetches transactions for the given account from Enable Banking API with pagination support."""
        headers = self.get_headers()
        url = f"{self.base_url}/accounts/{account_id}/transactions"
        
        all_transactions = []
        continuation_key = None
        
        while True:
            params = {}
            if continuation_key:
                params["continuation_key"] = continuation_key
                
            res = requests.get(url, headers=headers, params=params, timeout=20)
            res.raise_for_status()
            data = res.json()
            
            txns = data.get("transactions", [])
            all_transactions.extend(txns)
            
            continuation_key = data.get("continuation_key")
            if not continuation_key:
                break
                
        return all_transactions

def sync_account_transactions(account_id: str, account_name: str, app_id: str = ENABLE_BANKING_APP_ID, private_key: bytes = ENABLE_BANKING_PRIVATE_KEY) -> list:
    """
    Pulls recent transactions via Enable Banking, maps them to normalized dict structures.
    """
    client = EnableBankingClient(app_id, private_key)
    try:
        raw_txns = client.get_transactions(account_id)
    except Exception as e:
        logger.error(f"Failed to fetch transactions for Enable Banking account {account_id}: {e}")
        raise
        
    normalized = []
    for t in raw_txns:
        ext_id = (
            t.get("transaction_id") or t.get("transactionId") or 
            t.get("entry_reference") or t.get("entryReference")
        )
        
        date_str = (
            t.get("booking_date") or t.get("bookingDate") or 
            t.get("booking_date_time") or t.get("bookingDateTime") or 
            t.get("value_date") or t.get("valueDate") or 
            t.get("value_date_time") or t.get("valueDateTime") or "Unknown"
        )
        if len(date_str) > 10:
            date_str = date_str[:10]
            
        amount_struct = t.get("transaction_amount") or t.get("transactionAmount") or {}
        amount_val = amount_struct.get("amount")
        amount = float(amount_val) if amount_val is not None else 0.0
        currency = amount_struct.get("currency", "EUR")
        
        # Check credit/debit indicator to set the correct sign
        indicator = (t.get("credit_debit_indicator") or t.get("creditDebitIndicator") or "").upper()
        if indicator == "DBIT":
            amount = -abs(amount)
        elif indicator == "CRDT":
            amount = abs(amount)
        
        desc = (
            t.get("remittance_information_unstructured") or t.get("remittanceInformationUnstructured") or 
            t.get("remittance_information") or t.get("remittanceInformation") or 
            t.get("description") or t.get("entry_reference") or t.get("entryReference") or "Unknown"
        )
        if isinstance(desc, list):
            desc = " ".join(desc)
            
        # Deterministic fallback hashing if bank transactionId/entryReference is absent
        if not ext_id:
            raw_str = f"{date_str}_{amount}_{desc}"
            ext_id = f"gcl_fallback_{hashlib.sha256(raw_str.encode()).hexdigest()[:16]}"
            
        status = t.get("status", "BOOKED")
        is_pending = status.upper() in ["PDNG", "PENDING"]
        
        normalized.append({
            "external_sync_id": ext_id,
            "date": date_str,
            "description": desc,
            "amount": amount,
            "currency": currency,
            "account": account_name,
            "type": "Income" if amount > 0 else "Expense",
            "status": "PENDING" if is_pending else "SETTLED"
        })
        
    return normalized
