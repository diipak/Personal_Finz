import shutil
import uuid
import os
import logging
import sys
import asyncio
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form, Body, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import BaseModel
from typing import Optional
from config import ENABLE_BANKING_APP_ID, ENABLE_BANKING_REDIRECT_URI, ALLOWED_CATEGORIES, DEFAULT_DB_DIR
from db.database import get_db, init_db
from pipeline import process_manual_file, process_enable_banking_sync
from api.services.analytics import get_financial_summary, get_health_metrics
from agent.assistant import ask_assistant
from parsers.enable_banking_sync import EnableBankingClient
from parsers.detect import detect_bank_type

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOAD_DIR = BASE_DIR / "api" / "uploads"

os.makedirs(UPLOAD_DIR, exist_ok=True)

# Initialize database tables on startup
init_db()

async def auto_sync_scheduler_loop():
    """Background task to perform automated sync every 24 hours per account."""
    logger.info("Auto-sync background scheduler loop started.")
    while True:
        try:
            # Check if auto-sync is enabled in database settings
            conn = get_db()
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT value FROM settings WHERE key = 'auto_sync_enabled'")
                row = cursor.fetchone()
                enabled = (row and row["value"] == 'true')
            except Exception as db_err:
                logger.error(f"Scheduler failed to read settings: {db_err}")
                enabled = False
            finally:
                conn.close()

            if enabled:
                logger.info("Auto-sync is enabled. Checking for due accounts...")
                conn = get_db()
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        """
                        SELECT account_id as resource_id, account_name as display_name, last_synchronized as last_synced_at 
                        FROM accounts 
                        WHERE (last_synchronized = '1970-01-01 00:00:00' 
                           OR datetime(last_synchronized) <= datetime('now', '-24 hours'))
                           AND account_type = 'Automated (PSD2)'
                        """
                    )
                    due_accounts = [dict(row) for row in cursor.fetchall()]
                except Exception as db_err:
                    logger.error(f"Scheduler failed to query due accounts: {db_err}")
                    due_accounts = []
                finally:
                    conn.close()

                for acc in due_accounts:
                    resource_id = acc["resource_id"]
                    display_name = acc["display_name"]
                    logger.info(f"Auto-sync: Account '{display_name}' ({resource_id}) is due for sync. Triggering background sync...")
                    try:
                        # Run sync in thread pool to not block main thread
                        res = await asyncio.to_thread(
                            run_sync_for_account, 
                            account_id=resource_id, 
                            account_name=display_name, 
                            initiated_by="CRON"
                        )
                        logger.info(f"Auto-sync result for '{display_name}': {res}")
                    except Exception as sync_err:
                        logger.error(f"Auto-sync execution error for '{display_name}': {sync_err}")
            else:
                logger.info("Auto-sync is currently disabled via settings.")
        except Exception as e:
            logger.error(f"Unexpected error in auto-sync scheduler loop: {e}")
        
        # Sleep for 1 hour (3600 seconds) before checking again
        await asyncio.sleep(3600)

@app.on_event("startup")
async def startup_diagnostics():
    from api.services.diagnostics import run_diagnostics
    result = run_diagnostics()
    
    print("\n" + "="*60)
    print("        PERSONAL FINZ - STARTUP DEPENDENCY CHECKLIST")
    print("="*60)
    
    for name, check in result["checks"].items():
        status = check["status"]
        msg = check["message"]
        
        if status == "OK":
            icon = "✅"
        elif status == "WARNING":
            icon = "⚠️ "
        else:
            icon = "❌"
            
        print(f" {icon} {name.replace('_', ' ').title():<20} : {msg}")
    print("="*60 + "\n")
    
    # Start the background auto-sync scheduler loop
    asyncio.create_task(auto_sync_scheduler_loop())


app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")

@app.get("/")
def dashboard():
    return FileResponse(FRONTEND_DIR / "dashboard.html")

@app.get("/overview")
def overview_ui():
    return FileResponse(FRONTEND_DIR / "dashboard.html")

@app.get("/transactions")
def transactions_ui():
    return FileResponse(FRONTEND_DIR / "dashboard.html")

@app.get("/budgets")
def budgets_ui():
    return FileResponse(FRONTEND_DIR / "dashboard.html")

@app.get("/investments")
def investments_ui():
    return FileResponse(FRONTEND_DIR / "dashboard.html")

@app.get("/goals")
def goals_ui():
    return FileResponse(FRONTEND_DIR / "dashboard.html")

@app.get("/insights")
def insights_ui():
    return FileResponse(FRONTEND_DIR / "dashboard.html")

@app.get("/automation")
def automation_ui():
    return FileResponse(FRONTEND_DIR / "dashboard.html")

@app.get("/accounts")
def accounts_ui():
    return FileResponse(FRONTEND_DIR / "dashboard.html")

@app.get("/import-ui")
def import_ui():
    return FileResponse(FRONTEND_DIR / "dashboard.html")

@app.get("/rules")
def rules_ui():
    return FileResponse(FRONTEND_DIR / "dashboard.html")

@app.get("/review")
def review_ui():
    return FileResponse(FRONTEND_DIR / "unknown_merchant_review.html")

# Rules API Endpoint: Retrieve rules from SQLite
@app.get("/api/rules")
def get_rules():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT 
                rule_id as id, 
                pattern_string as pattern, 
                match_type, 
                target_category as category, 
                display_name, 
                flexibility_tier as flexibility, 
                amount_min, 
                amount_max, 
                priority 
            FROM regex_rules 
            ORDER BY priority DESC, rule_id ASC
            """
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching rules: {e}")
        raise HTTPException(status_code=500, detail="Database error fetching rules")
    finally:
        conn.close()

# Rules API Endpoint: Create or Update rule in SQLite
@app.post("/api/rules")
def save_rule(rule: dict = Body(...)):
    mapped = {
        "rule_id": rule.get("id"),
        "pattern_string": rule.get("pattern"),
        "match_type": rule.get("match_type") or "regex",
        "target_category": rule.get("category"),
        "display_name": rule.get("display_name"),
        "flexibility_tier": rule.get("flexibility") or "Flexible",
        "amount_min": rule.get("amount_min"),
        "amount_max": rule.get("amount_max"),
        "priority": rule.get("priority") or 0
    }
    conn = get_db()
    cursor = conn.cursor()
    try:
        if "rule_id" in mapped and mapped["rule_id"]:
            cursor.execute(
                """
                UPDATE regex_rules SET 
                    pattern_string = :pattern_string,
                    match_type = :match_type,
                    target_category = :target_category,
                    display_name = :display_name,
                    flexibility_tier = :flexibility_tier,
                    amount_min = :amount_min,
                    amount_max = :amount_max,
                    priority = :priority
                WHERE rule_id = :rule_id
                """,
                mapped
            )
        else:
            cursor.execute(
                """
                INSERT INTO regex_rules (
                    pattern_string, match_type, target_category, display_name, flexibility_tier, amount_min, amount_max, priority
                ) VALUES (
                    :pattern_string, :match_type, :target_category, :display_name, :flexibility_tier, :amount_min, :amount_max, :priority
                )
                ON CONFLICT(pattern_string) DO UPDATE SET
                    match_type = excluded.match_type,
                    target_category = excluded.target_category,
                    display_name = excluded.display_name,
                    flexibility_tier = excluded.flexibility_tier,
                    amount_min = excluded.amount_min,
                    amount_max = excluded.amount_max,
                    priority = excluded.priority
                """,
                mapped
            )
        conn.commit()
        
        # Retroactively apply rules to local unpinned transactions
        from engine.rules import apply_rules_to_unpinned_transactions
        apply_rules_to_unpinned_transactions()
        
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error saving rule: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error saving rule: {e}")
    finally:
        conn.close()

@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: int):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM regex_rules WHERE rule_id = ?", (rule_id,))
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error deleting rule: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail="Database error deleting rule")
    finally:
        conn.close()

# In-memory Manual File Ingestion (no subprocesses)
@app.post("/import")
def import_file(
    file: UploadFile = File(...), 
    bank_type: Optional[str] = Form(None)
):
    file_id = str(uuid.uuid4())
    extension = Path(file.filename).suffix.lower()
    
    input_path = UPLOAD_DIR / f"{file_id}{extension}"
    logger.info(f"Importing manual statement {file.filename} as {file_id} (optional bank_type: {bank_type})")

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    resolved_bank = bank_type
    if not resolved_bank:
        try:
            resolved_bank = detect_bank_type(str(input_path))
        except ValueError as detect_err:
            # Clean up local file before returning ambiguous response
            if input_path.exists():
                os.remove(input_path)
            return {
                "status": "ambiguous",
                "message": str(detect_err),
                "options": ["Revolut", "Commerzbank", "Advanzia Bank credit card", "HDFC", "Amazon Visa", "Trade Republic"]
            }

    # Query accounts for the detected bank to find matched display name
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT account_name as display_name FROM accounts 
            WHERE LOWER(account_name) = LOWER(?) 
               OR LOWER(account_id) = LOWER(?)
               OR LOWER(account_name) LIKE ?
            """,
            (resolved_bank, resolved_bank, f"%{resolved_bank.lower()}%")
        )
        row = cursor.fetchone()
    except Exception as db_err:
        logger.error(f"Failed to check linked accounts: {db_err}")
        row = None
    finally:
        conn.close()

    if not row:
        if input_path.exists():
            os.remove(input_path)
        raise HTTPException(
            status_code=400,
            detail=f"Bank identified as {resolved_bank}, but no corresponding feed is linked in your Accounts panel."
        )

    target_account_name = row["display_name"]
    inserted = 0
    try:
        inserted = process_manual_file(str(input_path), target_account_name, bank_type=resolved_bank)
        
        # Log successful manual import to sync_history
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO sync_history (institution_id, status, transactions_fetched)
                VALUES (?, 'SUCCESS', ?)
                """,
                (resolved_bank, inserted)
            )
            conn.commit()
        except Exception as log_err:
            logger.error(f"Failed to log manual import: {log_err}")
        finally:
            conn.close()

        return {
            "status": "success",
            "file_id": file_id,
            "inserted_count": inserted,
            "detected_bank": resolved_bank,
            "account_name": target_account_name
        }
    except Exception as e:
        logger.error(f"Error processing manual import: {e}")
        # Log failed manual import to sync_history
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO sync_history (institution_id, status, transactions_fetched, error_details)
                VALUES (?, 'FAILED', 0, ?)
                """,
                (resolved_bank or "Unknown Bank", str(e))
            )
            conn.commit()
        except Exception as log_err:
            logger.error(f"Failed to log manual import failure: {log_err}")
        finally:
            conn.close()
            
        return {
            "status": "error", 
            "error": "Import processing failed", 
            "details": str(e), 
            "detected_bank": resolved_bank
        }
    finally:
        # Clean up local file after processing
        if input_path.exists():
            os.remove(input_path)

@app.get("/api/ledger")
def get_ledger():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT 
                t.transaction_id as id,
                t.booking_date as date,
                t.account_id,
                a.account_name,
                t.description,
                COALESCE(t.resolved_merchant_name, t.description) as display_name,
                t.flexibility_tier as flexibility,
                COALESCE(t.category, 'Unsorted') as category,
                t.amount,
                t.currency
            FROM v_transactions_resolved t
            LEFT JOIN accounts a ON t.account_id = a.account_id
            WHERE t.is_ignored = 0
            ORDER BY t.booking_date DESC, t.transaction_id DESC
            """
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching ledger transactions: {e}")
        raise HTTPException(status_code=500, detail="Database error fetching ledger")
    finally:
        conn.close()

class TransactionCreateRequest(BaseModel):
    transaction_id: Optional[str] = None
    account_id: str
    booking_date: str
    description: str
    display_name: Optional[str] = None
    category: Optional[str] = "Unsorted"
    flexibility_tier: Optional[str] = "Flexible"
    amount: float
    currency: str

@app.post("/api/transactions")
def create_transaction(req: TransactionCreateRequest):
    conn = get_db()
    try:
        tx_id = req.transaction_id or f"manual-{uuid.uuid4()}"
        txn = {
            "transaction_id": tx_id,
            "account_id": req.account_id,
            "booking_date": req.booking_date,
            "description": req.description,
            "display_name": req.display_name or req.description,
            "category": req.category or "Unsorted",
            "flexibility_tier": req.flexibility_tier or "Flexible",
            "amount": req.amount,
            "currency": req.currency,
            "status": "SETTLED",
            "is_pinned": 1
        }
        from db.database import upsert_manual_transaction
        success = upsert_manual_transaction(conn, txn)
        if not success:
            raise HTTPException(status_code=500, detail="Database insertion failed")
            
        # Try to sync to ezBookkeeping fallback if applicable
        try:
            from db.sync_ez import push_transaction_to_ez
            push_transaction_to_ez(txn)
        except Exception as sync_err:
            logger.error(f"Failed to sync manual transaction to ezBookkeeping: {sync_err}")
            
        return {"status": "success", "transaction_id": tx_id}
    except Exception as e:
        logger.error(f"Error creating transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.delete("/api/transactions/{transaction_id}")
def delete_transaction(transaction_id: str):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM transactions WHERE transaction_id = ?", (transaction_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Transaction not found")
        cursor.execute("DELETE FROM transactions WHERE transaction_id = ?", (transaction_id,))
        conn.commit()
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting transaction: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail="Database error deleting transaction")
    finally:
        conn.close()

@app.get("/api/transactions")
def get_transactions(cluster_id: Optional[int] = None, merchant_id: Optional[int] = None):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if cluster_id is not None:
            cursor.execute("""
                SELECT 
                    transaction_id,
                    account_id,
                    booking_date,
                    description,
                    amount,
                    currency,
                    is_guess,
                    is_pinned,
                    is_ignored,
                    status,
                    cluster_id
                FROM transactions
                WHERE cluster_id = ? AND is_ignored = 0
                ORDER BY booking_date DESC, transaction_id DESC
            """, (cluster_id,))
        elif merchant_id is not None:
            cursor.execute("""
                SELECT 
                    t.transaction_id,
                    t.account_id,
                    t.booking_date,
                    t.description,
                    t.amount,
                    t.currency,
                    t.is_guess,
                    t.is_pinned,
                    t.is_ignored,
                    t.status,
                    t.cluster_id
                FROM transactions t
                JOIN merchant_clusters c ON t.cluster_id = c.cluster_id
                WHERE c.merchant_id = ? AND t.is_ignored = 0
                ORDER BY t.booking_date DESC, t.transaction_id DESC
            """, (merchant_id,))
        else:
            cursor.execute("""
                SELECT 
                    transaction_id,
                    account_id,
                    booking_date,
                    description,
                    amount,
                    currency,
                    is_guess,
                    is_pinned,
                    is_ignored,
                    status,
                    cluster_id
                FROM transactions
                WHERE is_ignored = 0
                ORDER BY booking_date DESC, transaction_id DESC
            """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching transactions: {e}")
        raise HTTPException(status_code=500, detail="Database error fetching transactions")
    finally:
        conn.close()

@app.get("/api/accounts")
def get_linked_accounts():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT 
                account_id as resource_id,
                account_name as display_name,
                account_type,
                current_balance,
                native_currency as currency,
                psd2_resource_hash,
                last_synchronized as last_synced_at
            FROM accounts 
            ORDER BY last_synchronized DESC, account_name ASC
            """
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching linked accounts: {e}")
        raise HTTPException(status_code=500, detail="Database error fetching linked accounts")
    finally:
        conn.close()

class AccountCreateRequest(BaseModel):
    account_id: str
    account_name: str
    account_type: str  # 'Automated (PSD2)', 'Manual Fallback', 'Manual Asset'
    current_balance: float
    native_currency: str  # 'EUR' or 'INR'

@app.post("/api/accounts")
def create_account(req: AccountCreateRequest):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO accounts (account_id, account_name, account_type, current_balance, native_currency, last_synchronized)
            VALUES (?, ?, ?, ?, ?, '1970-01-01 00:00:00')
            ON CONFLICT(account_id) DO UPDATE SET
                account_name = excluded.account_name,
                account_type = excluded.account_type,
                current_balance = excluded.current_balance,
                native_currency = excluded.native_currency
            """,
            (req.account_id, req.account_name, req.account_type, req.current_balance, req.native_currency)
        )
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error creating account: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        conn.close()

@app.delete("/api/accounts/{account_id}")
def delete_account(account_id: str):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM accounts WHERE account_id = ?", (account_id,))
        cursor.execute("DELETE FROM transactions WHERE account_id = ?", (account_id,))
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error deleting account: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        conn.close()

class ExchangeRateRequest(BaseModel):
    source_currency: str
    target_currency: str
    spot_rate: float

@app.get("/api/exchange-rates")
def get_exchange_rates():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM exchange_rates")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching exchange rates: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        conn.close()

@app.post("/api/exchange-rates")
def save_exchange_rate(req: ExchangeRateRequest):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO exchange_rates (source_currency, target_currency, spot_rate, last_api_update)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(source_currency, target_currency) DO UPDATE SET
                spot_rate = excluded.spot_rate,
                last_api_update = excluded.last_api_update
            """,
            (req.source_currency, req.target_currency, req.spot_rate)
        )
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error saving exchange rate: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        conn.close()

from fastapi import Request
from fastapi.responses import JSONResponse
from db.database import is_vault_locked, set_vault_lock, verify_vault_passcode, set_vault_passcode

@app.middleware("http")
async def vault_middleware(request: Request, call_next):
    # Intercept all /api/* requests except status and unlock
    if request.url.path.startswith("/api/") and not any(p in request.url.path for p in ["/vault/status", "/vault/unlock"]):
        if is_vault_locked():
            return JSONResponse(status_code=401, content={"detail": "Vault is locked"})
    response = await call_next(request)
    # Prevent browser caching for development
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/api/vault/status")
def get_vault_status():
    return {"locked": is_vault_locked()}

class UnlockRequest(BaseModel):
    passcode: str

@app.post("/api/vault/unlock")
def unlock_vault(req: UnlockRequest):
    if verify_vault_passcode(req.passcode):
        set_vault_lock(False)
        return {"status": "success", "locked": False}
    raise HTTPException(status_code=401, detail="Invalid passcode")

@app.post("/api/vault/lock")
def lock_vault():
    set_vault_lock(True)
    return {"status": "success", "locked": True}

@app.get("/api/sync/history")
def get_sync_history(limit: int = 20):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, 
                   strftime('%Y-%m-%d %H:%M', executed_at) as executed_at,
                   institution_id,
                   status,
                   transactions_fetched,
                   error_details
            FROM sync_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching sync history: {e}")
        raise HTTPException(status_code=500, detail="Database error fetching sync history")
    finally:
        conn.close()

class LinkRequest(BaseModel):
    institution_id: str
    redirect_uri: Optional[str] = None

class SettingsRequest(BaseModel):
    enabled: bool

class GenericSettingRequest(BaseModel):
    value: str

# Enable Banking Get Supported Banks (ASPSPs) Endpoint with 24h caching
@app.get("/api/sync/banks")
def get_supported_banks(country: str = "DE"):
    import re
    import time
    import json
    import requests
    
    country = country.strip().upper()
    if country != "ALL" and not re.match(r"^[A-Z]{2}$", country):
        raise HTTPException(status_code=400, detail="Invalid country code. Must be a 2-letter ISO code or 'ALL'.")
        
    if not ENABLE_BANKING_APP_ID:
        raise HTTPException(status_code=400, detail="Enable Banking APP ID not set in environment.")

    cache_file = os.path.join(DEFAULT_DB_DIR, f"aspsps_cache_{country}.json")
    
    # Check if cache exists and is fresh (< 24 hours)
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                cached = json.load(f)
            if time.time() - cached.get("timestamp", 0) < 86400:
                return cached.get("aspsps", [])
        except Exception as cache_err:
            logger.warning(f"Failed to read ASPSPs cache: {cache_err}")

    # Fetch from Enable Banking
    client = EnableBankingClient()
    headers = client.get_headers()
    url = f"{client.base_url}/aspsps"
    params = {}
    if country != "ALL":
        params["country"] = country
    
    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
        res.raise_for_status()
        data = res.json()
        aspsps_list = data.get("aspsps", [])
        
        # Save to cache
        try:
            with open(cache_file, "w") as f:
                json.dump({"timestamp": time.time(), "aspsps": aspsps_list}, f)
        except Exception as cache_err:
            logger.warning(f"Failed to write ASPSPs cache: {cache_err}")
            
        return aspsps_list
    except Exception as e:
        logger.error(f"Failed to fetch ASPSPs from Enable Banking for country {country}: {e}")
        # Fallback to expired cache if available
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    cached = json.load(f)
                logger.info(f"Returning expired cache for country {country} due to Enable Banking API error")
                return cached.get("aspsps", [])
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to fetch supported banks: {e}")

# Enable Banking Link Endpoint
@app.post("/api/sync/link")
def get_sync_link(req: LinkRequest):
    if not ENABLE_BANKING_APP_ID:
        raise HTTPException(status_code=400, detail="Enable Banking APP ID not set in environment.")
        
    redirect_uri = req.redirect_uri or ENABLE_BANKING_REDIRECT_URI
    if not redirect_uri:
        raise HTTPException(
            status_code=400,
            detail="redirect_uri not provided and ENABLE_BANKING_REDIRECT_URI is not configured in .env"
        )
        
    client = EnableBankingClient()
    try:
        reference = str(uuid.uuid4())
        link = client.get_auth_link(req.institution_id, redirect_uri, reference)
        return {"link": link, "reference": reference}
    except Exception as e:
        logger.error(f"Error generating Enable Banking connection link: {e}")
        raise HTTPException(status_code=500, detail=f"Enable Banking error: {e}")

# Enable Banking OAuth Callback Handler
@app.get("/callback")
def auth_callback(code: str, state: str = None):
    """Exchanges temporary OAuth redirect code for active bank session items."""
    if not ENABLE_BANKING_APP_ID:
        raise HTTPException(status_code=400, detail="Enable Banking APP ID not set in environment.")
        
    client = EnableBankingClient()
    try:
        session_data = client.create_session(code)
        accounts = session_data.get("accounts", [])
        
        conn = get_db()
        cursor = conn.cursor()
        try:
            for acc in accounts:
                resource_id = acc.get("uid")
                aspsp = acc.get("aspsp", {})
                institution_id = aspsp.get("name", "Unknown Bank")
                currency = acc.get("currency", "EUR")
                iban = acc.get("iban") or ""
                display_name = f"{institution_id} ({iban})" if iban else institution_id
                
                cursor.execute(
                    """
                    INSERT INTO accounts (account_id, account_name, account_type, current_balance, native_currency, psd2_resource_hash, last_synchronized)
                    VALUES (?, ?, 'Automated (PSD2)', 0.0, ?, ?, '1970-01-01 00:00:00')
                    ON CONFLICT(account_id) DO UPDATE SET
                        account_name = COALESCE(excluded.account_name, account_name),
                        native_currency = COALESCE(excluded.native_currency, native_currency),
                        psd2_resource_hash = COALESCE(excluded.psd2_resource_hash, psd2_resource_hash)
                    """,
                    (resource_id, display_name, currency, resource_id)
                )
            conn.commit()
        finally:
            conn.close()
            
        return RedirectResponse(url="/accounts?success=true")
    except Exception as e:
        logger.error(f"Failed to exchange callback code: {e}")
        return RedirectResponse(url=f"/accounts?error={str(e)}")

def run_sync_for_account(account_id: str, account_name: Optional[str] = None, initiated_by: str = "USER_BUTTON") -> dict:
    if account_id and account_id.endswith("-manual-id"):
        return {"status": "SKIPPED", "message": "Manual offline account - sync skipped."}
    if not ENABLE_BANKING_APP_ID:
        return {"status": "FAILED", "error": "Enable Banking APP ID not set in environment."}

    # Try to resolve display name and institution from accounts
    resolved_name = account_name
    institution_id = "Unknown Bank"
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT account_name FROM accounts WHERE account_id = ?", (account_id,))
        row = cursor.fetchone()
        if row:
            if not resolved_name:
                resolved_name = row["account_name"]
            institution_id = row["account_name"]
    except Exception as db_err:
        logger.error(f"Failed to look up account info: {db_err}")
    finally:
        conn.close()
        
    if not resolved_name:
        resolved_name = "Bank Feed"
        
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Rate Limit Safeguard (max 4 calls per 24 hours per account)
    try:
        cursor.execute(
            """
            SELECT COUNT(*) as count FROM sync_logs 
            WHERE account_id = ? 
              AND sync_source = 'enable_banking' 
              AND status = 'SUCCESS' 
              AND timestamp >= datetime('now', '-24 hours')
            """,
            (account_id,)
        )
        res = cursor.fetchone()
        
        if res["count"] >= 4:
            # Block the sync and log the skipped state to BOTH tables
            cursor.execute(
                """
                INSERT INTO sync_logs (account_id, sync_source, status, initiated_by, error_message)
                VALUES (?, 'enable_banking', 'SKIPPED', ?, 'Rate limit reached: Max 4 successful syncs per 24h')
                """,
                (account_id, initiated_by)
            )
            cursor.execute(
                """
                INSERT INTO sync_history (institution_id, status, transactions_fetched, error_details)
                VALUES (?, 'SKIPPED', 0, 'Rate limit reached: Max 4 successful syncs per 24h')
                """,
                (institution_id,)
            )
            conn.commit()
            return {
                "status": "SKIPPED",
                "message": "Sync skipped: Enable Banking rate limit reached (Max 4 successful calls per 24 hours allowed)."
            }
    except Exception as log_err:
        logger.error(f"Failed to check rate limit logs: {log_err}")
        return {"status": "FAILED", "error": "Sync logs rate limit check failed"}
    finally:
        conn.close()

    # 2. Perform automated sync
    conn = get_db()
    cursor = conn.cursor()
    try:
        inserted = process_enable_banking_sync(account_id, resolved_name)
        
        # Log successful sync to BOTH tables
        cursor.execute(
            """
            INSERT INTO sync_logs (account_id, sync_source, status, initiated_by)
            VALUES (?, 'enable_banking', 'SUCCESS', ?)
            """,
            (account_id, initiated_by)
        )
        cursor.execute(
            """
            INSERT INTO sync_history (institution_id, status, transactions_fetched)
            VALUES (?, 'SUCCESS', ?)
            """,
            (institution_id, inserted)
        )
        # Update last_synchronized in accounts
        cursor.execute(
            """
            UPDATE accounts 
            SET last_synchronized = CURRENT_TIMESTAMP 
            WHERE account_id = ?
            """,
            (account_id,)
        )
        conn.commit()
        return {
            "status": "SUCCESS",
            "inserted_count": inserted
        }
    except Exception as e:
        logger.error(f"Sync execution failure: {e}")
        # Log failed sync to BOTH tables
        cursor.execute(
            """
            INSERT INTO sync_logs (account_id, sync_source, status, initiated_by, error_message)
            VALUES (?, 'enable_banking', 'FAILED', ?, ?)
            """,
            (account_id, initiated_by, str(e))
        )
        cursor.execute(
            """
            INSERT INTO sync_history (institution_id, status, transactions_fetched, error_details)
            VALUES (?, 'FAILED', 0, ?)
            """,
            (institution_id, str(e))
        )
        conn.commit()
        return {"status": "FAILED", "error": str(e)}
    finally:
        conn.close()

# Enable Banking Automated Sync with PSD2 Rate Limit Guard
@app.post("/api/sync/auto")
def trigger_sync(
    account_id: str = Body(embed=True), 
    account_name: Optional[str] = Body(default=None, embed=True), 
    initiated_by: str = Body(default="USER_BUTTON", embed=True)
):
    res = run_sync_for_account(account_id, account_name, initiated_by)
    if res.get("status") == "FAILED":
        if "Enable Banking APP ID not set" in res.get("error", ""):
            raise HTTPException(status_code=400, detail=res["error"])
        if "Sync logs rate limit check failed" in res.get("error", ""):
            raise HTTPException(status_code=500, detail=res["error"])
    return res

@app.get("/api/settings/auto-sync")
def get_auto_sync_setting():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT value FROM settings WHERE key = 'auto_sync_enabled'")
        row = cursor.fetchone()
        enabled = (row and row["value"] == 'true')
        return {"enabled": enabled}
    except Exception as e:
        logger.error(f"Error fetching auto-sync setting: {e}")
        raise HTTPException(status_code=500, detail="Database error fetching setting")
    finally:
        conn.close()

@app.post("/api/settings/auto-sync")
def set_auto_sync_setting(req: SettingsRequest):
    conn = get_db()
    cursor = conn.cursor()
    try:
        val = 'true' if req.enabled else 'false'
        cursor.execute(
            """
            INSERT INTO settings (key, value) VALUES ('auto_sync_enabled', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (val,)
        )
        conn.commit()
        return {"status": "success", "enabled": req.enabled}
    except Exception as e:
        logger.error(f"Error setting auto-sync: {e}")
        raise HTTPException(status_code=500, detail="Database error setting auto-sync")
    finally:
        conn.close()

@app.get("/api/settings/{key}")
def get_generic_setting(key: str):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        val = row["value"] if row else None
        return {"key": key, "value": val}
    except Exception as e:
        logger.error(f"Error fetching setting {key}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error fetching setting {key}")
    finally:
        conn.close()

@app.post("/api/settings/{key}")
def set_generic_setting(key: str, req: GenericSettingRequest):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, req.value)
        )
        conn.commit()
        return {"status": "success", "key": key, "value": req.value}
    except Exception as e:
        logger.error(f"Error setting {key}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error setting {key}")
    finally:
        conn.close()


# Financial Analytics Routes
@app.get("/api/analytics/summary")
def get_summary():
    data = get_financial_summary()
    if not data:
        raise HTTPException(status_code=500, detail="Error compiling summary data")
    return data

@app.get("/api/analytics/health")
def get_health():
    data = get_health_metrics()
    if not data:
        raise HTTPException(status_code=500, detail="Error compiling health metrics")
    return data

# AI Assistant Route
@app.post("/api/ask")
def ask_question(question: str = Body(embed=True)):
    answer = ask_assistant(question)
    return {"response": answer}

@app.get("/api/diagnostics")
def get_diagnostics():
    from api.services.diagnostics import run_diagnostics
    return run_diagnostics()

# Review Queue APIs
@app.get("/api/categories")
def get_categories():
    return ALLOWED_CATEGORIES

@app.get("/api/recent-imports")
def get_recent_imports():
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Get the latest execution log for each institution_id
        cursor.execute(
            """
            SELECT 
                h1.id, 
                strftime('%Y-%m-%d %H:%M', h1.executed_at) as date,
                h1.institution_id as account,
                h1.transactions_fetched as transactions,
                h1.status
            FROM sync_history h1
            INNER JOIN (
                SELECT institution_id, MAX(executed_at) as max_exec
                FROM sync_history
                GROUP BY institution_id
            ) h2 ON h1.institution_id = h2.institution_id AND h1.executed_at = h2.max_exec
            ORDER BY h1.executed_at DESC
            LIMIT 10
            """
        )
        rows = cursor.fetchall()
        
        imports = []
        for r in rows:
            imports.append({
                "id": r["id"],
                "date": r["date"],
                "account": r["account"],
                "transactions": r["transactions"]
            })
        return imports
    except Exception as e:
        logger.error(f"Error fetching recent imports: {e}")
        return []
    finally:
        conn.close()

@app.get("/api/unknown")
def get_unknown_transactions():
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Fetch transactions that are guesses or uncategorized, not pinned, and not ignored
        cursor.execute(
            """
            SELECT 
                t.transaction_id as id, 
                t.account_id as account, 
                t.booking_date as date, 
                t.description, 
                COALESCE(t.resolved_merchant_name, t.description) as display_name, 
                COALESCE(t.category, 'Unsorted') as category, 
                t.flexibility_tier as flexibility, 
                t.amount, 
                t.currency, 
                t.is_guess, 
                t.is_pinned, 
                t.is_ignored, 
                t.status 
            FROM v_transactions_resolved t
            WHERE (t.is_guess = 1 OR t.category IS NULL OR t.category = '' OR t.category = 'Uncategorized' OR t.category = 'Unsorted')
              AND t.is_pinned = 0
              AND t.is_ignored = 0
            ORDER BY t.booking_date DESC, t.transaction_id DESC
            """
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching unknown transactions: {e}")
        raise HTTPException(status_code=500, detail="Database error fetching unknown transactions")
    finally:
        conn.close()

@app.post("/api/unknown/resolve")
def resolve_unknown_transactions(payload: dict = Body(...)):
    resolutions = payload.get("resolutions", [])
    if not resolutions:
        raise HTTPException(status_code=400, detail="No resolutions provided")
    
    conn = get_db()
    cursor = conn.cursor()
    
    updated_count = 0
    rules_created = 0
    
    try:
        for res in resolutions:
            tx_id = res.get("id")
            category = res.get("category")
            flexibility = res.get("flexibility", "Flexible")
            display_name = res.get("display_name")
            is_ignored = res.get("is_ignored", False)
            create_rule = res.get("create_rule", False)
            
            if not tx_id:
                continue
            
            # Update transaction
            cursor.execute(
                """
                UPDATE transactions SET
                    category = ?,
                    flexibility_tier = ?,
                    display_name = ?,
                    is_guess = 0,
                    is_pinned = 1,
                    is_ignored = ?
                WHERE transaction_id = ?
                """,
                (category, flexibility, display_name, 1 if is_ignored else 0, tx_id)
            )
            updated_count += 1
            
            if create_rule:
                rule_data = res.get("rule", {})
                pattern = rule_data.get("pattern")
                if pattern:
                    # Check if matching rule already exists to prevent duplicates
                    cursor.execute(
                        "SELECT rule_id FROM regex_rules WHERE pattern_string = ? AND match_type = ?",
                        (pattern, rule_data.get("match_type", "substring"))
                    )
                    if not cursor.fetchone():
                        cursor.execute(
                            """
                            INSERT INTO regex_rules (
                                pattern_string, match_type, target_category, display_name, flexibility_tier, amount_min, amount_max, priority
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                pattern,
                                rule_data.get("match_type", "substring"),
                                rule_data.get("category", category),
                                rule_data.get("display_name", display_name),
                                rule_data.get("flexibility", flexibility),
                                rule_data.get("amount_min"),
                                rule_data.get("amount_max"),
                                rule_data.get("priority", 0)
                            )
                        )
                        rules_created += 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Error resolving transactions: {e}")
        raise HTTPException(status_code=500, detail=f"Database error during resolution: {e}")
    finally:
        conn.close()
        
    if rules_created > 0:
        try:
            from engine.rules import apply_rules_to_unpinned_transactions
            apply_rules_to_unpinned_transactions()
        except Exception as e:
            logger.error(f"Failed to apply new rules: {e}")
            
    return {
        "status": "success",
        "updated_count": updated_count,
        "rules_created": rules_created
    }

# --- MERCHANT INTELLIGENCE ENGINE ENDPOINTS ---

@app.get("/api/merchant-intelligence/suggestions")
def get_merchant_suggestions():
    import json
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT 
                suggestion_id, merchant_name, pattern_string, match_type, 
                suggested_category, suggested_display_name, flexibility_tier, 
                amount_min, amount_max, confidence_score, status, 
                transaction_count, sample_descriptions, created_at
            FROM ai_suggested_rules
            WHERE status = 'PENDING'
            ORDER BY transaction_count DESC, confidence_score DESC
            """
        )
        rows = cursor.fetchall()
        
        levels = {
            "Level 1 (High Confidence)": [],
            "Level 2 (Quick Approval)": [],
            "Level 3 (Needs Attention)": [],
            "Level 4 (Ambiguous)": []
        }
        
        known_keywords = [
            "netflix", "spotify", "google", "youtube", "icloud", "github", 
            "microsoft", "amazon", "aws", "apple", "disney", "adobe", 
            "chatgpt", "openai", "dropbox", "heroku", "slack", "zoom"
        ]
        
        for r in rows:
            sug = dict(r)
            # Parse sample descriptions from JSON string
            try:
                sug["sample_descriptions"] = json.loads(sug["sample_descriptions"])
            except Exception:
                sug["sample_descriptions"] = [sug["sample_descriptions"]] if sug["sample_descriptions"] else []
                
            conf = sug["confidence_score"] or 0.0
            name = sug["merchant_name"].lower()
            pattern = sug["pattern_string"].lower()
            
            is_known = any(kw in name or kw in pattern for kw in known_keywords)
            
            if conf >= 0.95 or (conf >= 0.90 and is_known):
                level = "Level 1 (High Confidence)"
            elif conf >= 0.85:
                level = "Level 2 (Quick Approval)"
            elif conf >= 0.60:
                level = "Level 3 (Needs Attention)"
            else:
                level = "Level 4 (Ambiguous)"
                
            levels[level].append(sug)
            
        return levels
    except Exception as e:
        logger.error(f"Error fetching merchant suggestions: {e}")
        raise HTTPException(status_code=500, detail=f"Database error fetching suggestions: {e}")
    finally:
        conn.close()

@app.post("/api/merchant-intelligence/suggestions/resolve")
def resolve_merchant_suggestions(payload: dict = Body(...)):
    resolutions = payload.get("resolutions", [])
    if not resolutions:
        raise HTTPException(status_code=400, detail="No resolutions provided")
        
    conn = get_db()
    cursor = conn.cursor()
    
    rules_created = 0
    suggestions_approved = 0
    suggestions_rejected = 0
    
    try:
        for res in resolutions:
            sug_id = res.get("suggestion_id")
            action = res.get("action", "approve").lower()
            
            if not sug_id:
                continue
                
            if action == "approve":
                pattern = res.get("pattern_string")
                match_type = res.get("match_type", "substring")
                category = res.get("category")
                display_name = res.get("display_name")
                flexibility = res.get("flexibility", "Flexible")
                amount_min = res.get("amount_min")
                amount_max = res.get("amount_max")
                priority = res.get("priority", 0)
                
                if not pattern or not category:
                    continue
                
                # Fetch merchant name from suggestion
                cursor.execute("SELECT merchant_name FROM ai_suggested_rules WHERE suggestion_id = ?", (sug_id,))
                sug_row = cursor.fetchone()
                merchant_name = sug_row["merchant_name"] if sug_row else (display_name or pattern.upper())
                
                # Resolve category_id
                cursor.execute("SELECT category_id FROM categories WHERE name = ?", (category,))
                cat_row = cursor.fetchone()
                if cat_row:
                    cat_id = cat_row["category_id"]
                else:
                    cursor.execute("INSERT INTO categories (name, flexibility_tier) VALUES (?, ?)", (category, flexibility))
                    cat_id = cursor.lastrowid
                
                # Create or update merchant in the merchants table
                cursor.execute(
                    """
                    INSERT INTO merchants (name, category_id, is_verified, confidence_score)
                    VALUES (?, ?, 1, 1.0)
                    ON CONFLICT(name) DO UPDATE SET category_id = excluded.category_id, is_verified = 1
                    """,
                    (merchant_name, cat_id)
                )
                cursor.execute("SELECT merchant_id FROM merchants WHERE name = ?", (merchant_name,))
                merchant_id = cursor.fetchone()["merchant_id"]
                
                # Check if identical rule already exists in regex_rules
                cursor.execute(
                    "SELECT rule_id FROM regex_rules WHERE pattern_string = ? AND match_type = ?",
                    (pattern, match_type)
                )
                if not cursor.fetchone():
                    cursor.execute(
                        """
                        INSERT INTO regex_rules (
                            pattern_string, match_type, target_category, display_name, flexibility_tier, 
                            amount_min, amount_max, priority, target_merchant_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (pattern, match_type, category, display_name, flexibility, amount_min, amount_max, priority, merchant_id)
                    )
                    rules_created += 1
                
                # Add memory signature
                sig_type = "EXACT"
                if match_type == "regex":
                    sig_type = "REGEX"
                elif match_type == "substring":
                    sig_type = "USER_CREATED"
                
                cursor.execute(
                    """
                    INSERT INTO merchant_signatures (
                        pattern_string, merchant_id, signature_type, source_action, is_user_verified, confidence_score
                    ) VALUES (?, ?, ?, 'user_verify', 1, 1.0)
                    ON CONFLICT(pattern_string) DO UPDATE SET
                        merchant_id = excluded.merchant_id,
                        signature_type = excluded.signature_type,
                        is_user_verified = 1,
                        confidence_score = 1.0,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (pattern.lower(), merchant_id, sig_type)
                )
                
                # Update merchant_clusters matching this pattern or merchant to point to new merchant
                cursor.execute(
                    """
                    UPDATE merchant_clusters SET
                        merchant_id = ?,
                        confidence_score = 1.0,
                        is_locked = 1,
                        is_user_verified = 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE cluster_name = ? OR (merchant_id IS NULL AND cluster_name LIKE ?)
                    """,
                    (merchant_id, pattern, f"%{pattern}%")
                )
                    
                cursor.execute(
                    "UPDATE ai_suggested_rules SET status = 'APPROVED' WHERE suggestion_id = ?",
                    (sug_id,)
                )
                suggestions_approved += 1
                
            else:
                cursor.execute(
                    "UPDATE ai_suggested_rules SET status = 'REJECTED' WHERE suggestion_id = ?",
                    (sug_id,)
                )
                suggestions_rejected += 1
                
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Error resolving merchant suggestions: {e}")
        raise HTTPException(status_code=500, detail=f"Database error during resolution: {e}")
    finally:
        conn.close()
        
    # Propagate the rules to unpinned transactions and update stats
    updated_txns = 0
    if rules_created > 0:
        try:
            from engine.rules import apply_rules_to_unpinned_transactions
            updated_txns = apply_rules_to_unpinned_transactions()
            
            # Incrementally sync the known_category on merchant_stats
            conn = get_db()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    UPDATE merchant_stats SET 
                        known_category = (
                            SELECT category FROM transactions 
                            WHERE transactions.normalized_pattern = merchant_stats.merchant_key 
                              AND category IS NOT NULL 
                              AND category NOT IN ('Unsorted', 'Uncategorized', '')
                            ORDER BY booking_date DESC LIMIT 1
                        )
                        WHERE known_category IS NULL 
                           OR known_category = 'Unsorted' 
                           OR known_category = 'Uncategorized' 
                           OR known_category = ''
                    """
                )
                conn.commit()
            except Exception as stat_err:
                logger.error(f"Failed to update known_categories in merchant_stats: {stat_err}")
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"Failed to apply new rules or update stats: {e}")
            
    return {
        "status": "success",
        "rules_created": rules_created,
        "suggestions_approved": suggestions_approved,
        "suggestions_rejected": suggestions_rejected,
        "transactions_updated": updated_txns
    }

@app.post("/api/merchant-intelligence/run")
def run_merchant_intelligence(background_tasks: BackgroundTasks):
    def run_bg():
        logger.info("Starting background execution of Merchant Intelligence Engine.")
        conn = get_db()
        try:
            from engine.cluster_ai_review import run_cluster_ai_review
            run_cluster_ai_review(conn)
        except Exception as e:
            logger.error(f"Background Merchant Intelligence Engine error: {e}")
        finally:
            conn.close()
            
    background_tasks.add_task(run_bg)
    return {
        "status": "running",
        "message": "Merchant Intelligence Engine triggered in background."
    }

@app.get("/api/merchant-intelligence/stats")
def get_merchant_intelligence_stats():
    """Return dashboard-level counters for the Merchant Intelligence Review Queue card."""
    conn = get_db()
    try:
        cursor = conn.cursor()

        # Pending clusters = distinct parent_merchant groups with unknown_category in merchant_stats
        cursor.execute(
            """
            SELECT COUNT(DISTINCT COALESCE(parent_merchant, merchant_key))
            FROM merchant_stats
            WHERE known_category IS NULL OR known_category = '' OR known_category = 'Unsorted'
            """
        )
        pending_clusters = cursor.fetchone()[0] or 0

        # Uncategorised transactions = is_guess=1 OR category IS NULL
        cursor.execute(
            """
            SELECT COUNT(*) FROM transactions
            WHERE is_guess = 1 OR category IS NULL OR category = 'Unsorted'
            """
        )
        uncategorised_txns = cursor.fetchone()[0] or 0

        # AI suggestions ready for review (PENDING status)
        cursor.execute(
            "SELECT COUNT(*) FROM ai_suggested_rules WHERE status = 'PENDING'"
        )
        ai_suggestions = cursor.fetchone()[0] or 0

        # Active rules count (regex_rules has no is_active column — all rows are active)
        cursor.execute("SELECT COUNT(*) FROM regex_rules")
        active_rules = cursor.fetchone()[0] or 0

        return {
            "pending_clusters": pending_clusters,
            "uncategorised_txns": uncategorised_txns,
            "ai_suggestions": ai_suggestions,
            "active_rules": active_rules
        }
    except Exception as e:
        logger.error(f"Error fetching merchant intelligence stats: {e}")
        return {"pending_clusters": 0, "uncategorised_txns": 0, "ai_suggestions": 0, "active_rules": 0}
    finally:
        conn.close()


# --- RELATIONAL MERCHANT INTELLIGENCE ENDPOINTS ---

@app.get("/api/categories")
def get_categories_new():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT c.category_id, c.name as category_name, c.flexibility_tier,
                   s.subcategory_id, s.name as subcategory_name
            FROM categories c
            LEFT JOIN subcategories s ON s.category_id = c.category_id
            ORDER BY c.name, s.name
        """)
        rows = cursor.fetchall()
        tree = {}
        for r in rows:
            cat_name = r["category_name"]
            if cat_name not in tree:
                tree[cat_name] = {
                    "category_id": r["category_id"],
                    "flexibility_tier": r["flexibility_tier"],
                    "subcategories": []
                }
            if r["subcategory_name"]:
                tree[cat_name]["subcategories"].append({
                    "subcategory_id": r["subcategory_id"],
                    "name": r["subcategory_name"]
                })
        return tree
    except Exception as e:
        logger.error(f"Error fetching categories: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        conn.close()

@app.post("/api/categories/{category_id}/subcategories")
def create_subcategory(category_id: int, payload: dict = Body(...)):
    name = payload.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Subcategory name is required")
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO subcategories (category_id, name)
            VALUES (?, ?)
            ON CONFLICT(category_id, name) DO UPDATE SET name = name
        """, (category_id, name))
        conn.commit()
        cursor.execute("SELECT subcategory_id FROM subcategories WHERE category_id = ? AND name = ?", (category_id, name))
        sub_id = cursor.fetchone()["subcategory_id"]
        return {"status": "success", "subcategory_id": sub_id, "name": name}
    except Exception as e:
        logger.error(f"Error creating subcategory: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        conn.close()

@app.get("/api/merchants")
def get_merchants():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                m.merchant_id, m.name, m.parent_merchant_id, m.confidence_score, m.is_verified, m.is_system,
                p.name as parent_name,
                c.name as category,
                s.name as subcategory,
                COALESCE(st.transaction_count, 0) as transaction_count,
                COALESCE(st.total_spend, 0.0) as total_spend,
                COALESCE(st.total_income, 0.0) as total_income,
                st.first_seen, st.last_seen
            FROM merchants m
            LEFT JOIN merchants p ON m.parent_merchant_id = p.merchant_id
            LEFT JOIN categories c ON m.category_id = c.category_id
            LEFT JOIN subcategories s ON m.subcategory_id = s.subcategory_id
            LEFT JOIN merchant_stats_new st ON m.merchant_id = st.merchant_id
            ORDER BY m.is_system ASC, transaction_count DESC, m.name ASC
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching merchants: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        conn.close()

@app.get("/api/merchants/{merchant_id}")
def get_merchant_profile(merchant_id: int):
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Basic details
        cursor.execute("""
            SELECT 
                m.merchant_id, m.name, m.parent_merchant_id, m.confidence_score, m.is_verified, m.is_system,
                p.name as parent_name,
                c.name as category,
                s.name as subcategory
            FROM merchants m
            LEFT JOIN merchants p ON m.parent_merchant_id = p.merchant_id
            LEFT JOIN categories c ON m.category_id = c.category_id
            LEFT JOIN subcategories s ON m.subcategory_id = s.subcategory_id
            WHERE m.merchant_id = ?
        """, (merchant_id,))
        m_row = cursor.fetchone()
        if not m_row:
            raise HTTPException(status_code=404, detail="Merchant not found")
        merchant = dict(m_row)

        # Monthly spend and count trend (last 12 months)
        cursor.execute("""
            SELECT 
                strftime('%Y-%m', t.booking_date) as month,
                COUNT(t.transaction_id) as transaction_count,
                SUM(CASE WHEN t.amount < 0 THEN t.amount ELSE 0 END) as total_spend,
                SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END) as total_income
            FROM transactions t
            JOIN merchant_clusters c ON t.cluster_id = c.cluster_id
            WHERE c.merchant_id = ?
            GROUP BY month
            ORDER BY month DESC
            LIMIT 12
        """, (merchant_id,))
        trends = [dict(row) for row in cursor.fetchall()]
        
        # Accounts used
        cursor.execute("""
            SELECT 
                a.account_name,
                COUNT(t.transaction_id) as transaction_count,
                SUM(t.amount) as total_amount
            FROM transactions t
            JOIN merchant_clusters c ON t.cluster_id = c.cluster_id
            JOIN accounts a ON t.account_id = a.account_id
            WHERE c.merchant_id = ?
            GROUP BY a.account_name
        """, (merchant_id,))
        accounts = [dict(row) for row in cursor.fetchall()]

        # Child services (sub-merchants)
        cursor.execute("""
            SELECT merchant_id, name, confidence_score, is_verified
            FROM merchants
            WHERE parent_merchant_id = ?
        """, (merchant_id,))
        child_merchants = [dict(row) for row in cursor.fetchall()]

        # Example transactions (recent 10)
        cursor.execute("""
            SELECT 
                t.transaction_id, t.booking_date as date, t.description, t.amount, t.currency, t.is_pinned, a.account_name
            FROM transactions t
            JOIN merchant_clusters c ON t.cluster_id = c.cluster_id
            JOIN accounts a ON t.account_id = a.account_id
            WHERE c.merchant_id = ?
            ORDER BY t.booking_date DESC
            LIMIT 10
        """, (merchant_id,))
        transactions = [dict(row) for row in cursor.fetchall()]

        # Rules history / matched regex
        cursor.execute("""
            SELECT rule_id, pattern_string, match_type, priority
            FROM regex_rules
            WHERE target_merchant_id = ?
        """, (merchant_id,))
        rules = [dict(row) for row in cursor.fetchall()]

        return {
            "merchant": merchant,
            "trends": trends,
            "accounts": accounts,
            "child_merchants": child_merchants,
            "transactions": transactions,
            "rules": rules
        }
    except Exception as e:
        logger.error(f"Error fetching merchant profile: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        conn.close()

@app.post("/api/merchants")
def save_merchant(payload: dict = Body(...)):
    merchant_id = payload.get("merchant_id")
    name = payload.get("name")
    parent_merchant_id = payload.get("parent_merchant_id")
    category_name = payload.get("category")
    subcategory_name = payload.get("subcategory")
    is_verified = payload.get("is_verified", False)
    
    if not name:
        raise HTTPException(status_code=400, detail="Merchant name is required")
        
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Resolve category_id
        cat_id = None
        if category_name:
            cursor.execute("SELECT category_id FROM categories WHERE name = ?", (category_name,))
            cat_row = cursor.fetchone()
            if cat_row:
                cat_id = cat_row["category_id"]
                
        # Resolve subcategory_id
        sub_id = None
        if subcategory_name and cat_id:
            cursor.execute("""
                INSERT OR IGNORE INTO subcategories (category_id, name)
                VALUES (?, ?)
            """, (cat_id, subcategory_name))
            conn.commit()
            cursor.execute("SELECT subcategory_id FROM subcategories WHERE category_id = ? AND name = ?", (cat_id, subcategory_name))
            sub_row = cursor.fetchone()
            if sub_row:
                sub_id = sub_row["subcategory_id"]
                
        if merchant_id:
            cursor.execute("""
                UPDATE merchants SET
                    name = ?,
                    parent_merchant_id = ?,
                    category_id = ?,
                    subcategory_id = ?,
                    is_verified = ?,
                    confidence_score = 1.0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE merchant_id = ?
            """, (name, parent_merchant_id, cat_id, sub_id, 1 if is_verified else 0, merchant_id))
            m_id = merchant_id
        else:
            cursor.execute("""
                INSERT INTO merchants (name, parent_merchant_id, category_id, subcategory_id, is_verified, confidence_score)
                VALUES (?, ?, ?, ?, ?, 1.0)
            """, (name, parent_merchant_id, cat_id, sub_id, 1 if is_verified else 0))
            m_id = cursor.lastrowid
            
        # Propagate changes to transactions physically
        cursor.execute("""
            SELECT c.cluster_id FROM merchant_clusters c WHERE c.merchant_id = ?
        """, (m_id,))
        cluster_rows = cursor.fetchall()
        cluster_ids = [r["cluster_id"] for r in cluster_rows]
        
        if cluster_ids:
            for c_id in cluster_ids:
                cursor.execute("""
                    UPDATE transactions SET
                        category = ?,
                        display_name = ?
                    WHERE cluster_id = ?
                """, (category_name or 'Unsorted', name, c_id))
                
        # Recalculate stats cache
        from db.database import update_merchant_stats_new
        update_merchant_stats_new(conn, m_id)
        
        conn.commit()
        return {"status": "success", "merchant_id": m_id}
    except Exception as e:
        conn.rollback()
        logger.error(f"Error saving merchant: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        conn.close()

@app.delete("/api/merchants/{merchant_id}")
def delete_merchant(merchant_id: int):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE merchants SET parent_merchant_id = NULL WHERE parent_merchant_id = ?", (merchant_id,))
        cursor.execute("UPDATE merchant_clusters SET merchant_id = NULL WHERE merchant_id = ?", (merchant_id,))
        cursor.execute("DELETE FROM merchants WHERE merchant_id = ?", (merchant_id,))
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        conn.rollback()
        logger.error(f"Error deleting merchant: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        conn.close()

@app.get("/api/merchant-clusters/workbench")
def get_workbench_clusters():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                c.cluster_id, c.cluster_name, c.confidence_score, c.is_locked, c.is_user_verified, c.sample_descriptions,
                COUNT(t.transaction_id) as transaction_count,
                SUM(t.amount) as total_amount,
                m.name as resolved_merchant_name,
                m.merchant_id
            FROM merchant_clusters c
            LEFT JOIN transactions t ON t.cluster_id = c.cluster_id
            LEFT JOIN merchants m ON c.merchant_id = m.merchant_id
            GROUP BY c.cluster_id, c.cluster_name, c.confidence_score, c.is_locked, c.is_user_verified, c.sample_descriptions, m.name, m.merchant_id
            ORDER BY transaction_count DESC
        """)
        rows = cursor.fetchall()
        clusters = []
        for r in rows:
            sug = dict(r)
            try:
                sug["sample_descriptions"] = json.loads(sug["sample_descriptions"])
            except Exception:
                sug["sample_descriptions"] = [sug["sample_descriptions"]] if sug["sample_descriptions"] else []
            clusters.append(sug)
        return clusters
    except Exception as e:
        logger.error(f"Error fetching workbench clusters: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        conn.close()

@app.post("/api/merchant-clusters/merge")
def merge_merchant_clusters(payload: dict = Body(...)):
    source_ids = payload.get("source_cluster_ids", [])
    target_id = payload.get("target_cluster_id")
    
    if not source_ids or not target_id:
        raise HTTPException(status_code=400, detail="source_cluster_ids and target_cluster_id are required")
        
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT cluster_name, merchant_id FROM merchant_clusters WHERE cluster_id = ?", (target_id,))
        target_row = cursor.fetchone()
        if not target_row:
            raise HTTPException(status_code=404, detail="Target cluster not found")
            
        target_merchant_id = target_row["merchant_id"]

        for src_id in source_ids:
            cursor.execute("UPDATE transactions SET cluster_id = ? WHERE cluster_id = ?", (target_id, src_id))
            cursor.execute("DELETE FROM merchant_clusters WHERE cluster_id = ?", (src_id,))
            
        if target_merchant_id:
            from db.database import update_merchant_stats_new
            update_merchant_stats_new(conn, target_merchant_id)
            
        conn.commit()
        return {"status": "success", "target_cluster_id": target_id}
    except Exception as e:
        conn.rollback()
        logger.error(f"Error merging clusters: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        conn.close()

@app.post("/api/merchant-clusters/split")
def split_merchant_cluster(payload: dict = Body(...)):
    source_cluster_id = payload.get("source_cluster_id")
    transaction_ids = payload.get("transaction_ids", [])
    new_cluster_name = payload.get("new_cluster_name")
    
    if not source_cluster_id or not transaction_ids or not new_cluster_name:
        raise HTTPException(status_code=400, detail="source_cluster_id, transaction_ids, and new_cluster_name are required")
        
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT merchant_id FROM merchant_clusters WHERE cluster_id = ?", (source_cluster_id,))
        src_row = cursor.fetchone()
        src_merchant_id = src_row["merchant_id"] if src_row else None
        
        cursor.execute("""
            INSERT INTO merchant_clusters (cluster_name, merchant_id, confidence_score, is_locked, is_user_verified)
            VALUES (?, ?, 1.0, 1, 1)
        """, (new_cluster_name, src_merchant_id))
        new_cluster_id = cursor.lastrowid
        
        for tx_id in transaction_ids:
            cursor.execute("UPDATE transactions SET cluster_id = ? WHERE transaction_id = ?", (new_cluster_id, tx_id))
            
        if src_merchant_id:
            from db.database import update_merchant_stats_new
            update_merchant_stats_new(conn, src_merchant_id)
            
        conn.commit()
        return {"status": "success", "new_cluster_id": new_cluster_id}
    except Exception as e:
        conn.rollback()
        logger.error(f"Error splitting cluster: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        conn.close()

@app.post("/api/merchant-clusters/move-transaction")
def move_cluster_transaction(payload: dict = Body(...)):
    transaction_ids = payload.get("transaction_ids", [])
    target_cluster_id = payload.get("target_cluster_id")
    
    if not transaction_ids or not target_cluster_id:
        raise HTTPException(status_code=400, detail="transaction_ids and target_cluster_id are required")
        
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT DISTINCT c.merchant_id 
            FROM transactions t
            JOIN merchant_clusters c ON t.cluster_id = c.cluster_id
            WHERE t.transaction_id IN ({})
        """.format(",".join("?" for _ in transaction_ids)), transaction_ids)
        old_merchants = [r["merchant_id"] for r in cursor.fetchall() if r["merchant_id"]]
        
        for tx_id in transaction_ids:
            cursor.execute("UPDATE transactions SET cluster_id = ? WHERE transaction_id = ?", (target_cluster_id, tx_id))
            
        cursor.execute("SELECT merchant_id FROM merchant_clusters WHERE cluster_id = ?", (target_cluster_id,))
        t_row = cursor.fetchone()
        target_merchant_id = t_row["merchant_id"] if t_row else None
        
        from db.database import update_merchant_stats_new
        for m_id in old_merchants:
            update_merchant_stats_new(conn, m_id)
        if target_merchant_id:
            update_merchant_stats_new(conn, target_merchant_id)
            
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        conn.rollback()
        logger.error(f"Error moving transactions: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        conn.close()

@app.post("/api/merchant-clusters/promote")
def promote_merchant_cluster(payload: dict = Body(...)):
    cluster_id = payload.get("cluster_id")
    merchant_name = payload.get("merchant_name")
    category_name = payload.get("category")
    subcategory_name = payload.get("subcategory")
    parent_merchant_id = payload.get("parent_merchant_id")
    
    if not cluster_id or not merchant_name:
        raise HTTPException(status_code=400, detail="cluster_id and merchant_name are required")
        
    conn = get_db()
    cursor = conn.cursor()
    try:
        cat_id = None
        if category_name:
            cursor.execute("SELECT category_id FROM categories WHERE name = ?", (category_name,))
            cat_row = cursor.fetchone()
            if cat_row:
                cat_id = cat_row["category_id"]
                
        sub_id = None
        if subcategory_name and cat_id:
            cursor.execute("INSERT OR IGNORE INTO subcategories (category_id, name) VALUES (?, ?)", (cat_id, subcategory_name))
            conn.commit()
            cursor.execute("SELECT subcategory_id FROM subcategories WHERE category_id = ? AND name = ?", (cat_id, subcategory_name))
            sub_row = cursor.fetchone()
            if sub_row:
                sub_id = sub_row["subcategory_id"]
                
        cursor.execute("""
            INSERT INTO merchants (name, parent_merchant_id, category_id, subcategory_id, is_verified, confidence_score)
            VALUES (?, ?, ?, ?, 1, 1.0)
            ON CONFLICT(name) DO UPDATE SET is_verified = 1
        """, (merchant_name, parent_merchant_id, cat_id, sub_id))
        
        cursor.execute("SELECT merchant_id FROM merchants WHERE name = ?", (merchant_name,))
        merchant_id = cursor.fetchone()["merchant_id"]
        
        cursor.execute("""
            UPDATE merchant_clusters SET
                merchant_id = ?,
                confidence_score = 1.0,
                is_locked = 1,
                is_user_verified = 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE cluster_id = ?
        """, (merchant_id, cluster_id))
        
        # Add memory signature on workbench promotion
        cursor.execute("SELECT cluster_name FROM merchant_clusters WHERE cluster_id = ?", (cluster_id,))
        c_row = cursor.fetchone()
        c_name = c_row["cluster_name"] if c_row else merchant_name
        
        cursor.execute(
            """
            INSERT INTO merchant_signatures (
                pattern_string, merchant_id, signature_type, source_action, is_user_verified, confidence_score
            ) VALUES (?, ?, 'EXACT', 'workbench_promote', 1, 1.0)
            ON CONFLICT(pattern_string) DO UPDATE SET
                merchant_id = excluded.merchant_id,
                signature_type = 'EXACT',
                is_user_verified = 1,
                confidence_score = 1.0,
                updated_at = CURRENT_TIMESTAMP
            """,
            (c_name.lower(), merchant_id)
        )
        
        cursor.execute("""
            UPDATE transactions SET
                category = ?,
                display_name = ?
            WHERE cluster_id = ?
        """, (category_name or 'Unsorted', merchant_name, cluster_id))
        
        from db.database import update_merchant_stats_new
        update_merchant_stats_new(conn, merchant_id)
        
        conn.commit()
        return {"status": "success", "merchant_id": merchant_id}
    except Exception as e:
        conn.rollback()
        logger.error(f"Error promoting cluster: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        conn.close()

@app.post("/api/merchant-clusters/lock")
def lock_merchant_cluster(payload: dict = Body(...)):
    cluster_id = payload.get("cluster_id")
    is_locked = payload.get("is_locked", True)
    
    if not cluster_id:
        raise HTTPException(status_code=400, detail="cluster_id is required")
        
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE merchant_clusters SET
                is_locked = ?,
                is_user_verified = 1,
                confidence_score = 1.0,
                updated_at = CURRENT_TIMESTAMP
            WHERE cluster_id = ?
        """, (1 if is_locked else 0, cluster_id))
        
        # Save signature on lock if merchant_id is present
        if is_locked:
            cursor.execute("SELECT cluster_name, merchant_id FROM merchant_clusters WHERE cluster_id = ?", (cluster_id,))
            c_row = cursor.fetchone()
            if c_row and c_row["merchant_id"]:
                cursor.execute(
                    """
                    INSERT INTO merchant_signatures (
                        pattern_string, merchant_id, signature_type, source_action, is_user_verified, confidence_score
                    ) VALUES (?, ?, 'EXACT', 'workbench_lock', 1, 1.0)
                    ON CONFLICT(pattern_string) DO UPDATE SET
                        merchant_id = excluded.merchant_id,
                        signature_type = 'EXACT',
                        is_user_verified = 1,
                        confidence_score = 1.0,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (c_row["cluster_name"].lower(), c_row["merchant_id"])
                )
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        conn.rollback()
        logger.error(f"Error locking cluster: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        conn.close()

@app.get("/api/merchant-intelligence/dashboard")
def get_merchant_dashboard_metrics():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM merchants WHERE is_system = 0")
        total_merchants = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM merchant_clusters")
        total_clusters = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT COUNT(*) FROM merchants 
            WHERE is_system = 0 AND (category_id IS NULL OR category_id IN (SELECT category_id FROM categories WHERE name IN ('Unsorted', 'Other')))
        """)
        uncategorized_merchants = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT m.name, SUM(ABS(t.amount)) as total_spend
            FROM transactions t
            JOIN merchant_clusters c ON t.cluster_id = c.cluster_id
            JOIN merchants m ON c.merchant_id = m.merchant_id
            WHERE t.amount < 0 AND m.is_system = 0 AND t.booking_date >= date('now', '-30 days')
            GROUP BY m.merchant_id
            ORDER BY total_spend DESC
            LIMIT 5
        """)
        largest_by_spend = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT m.name, COUNT(t.transaction_id) as count
            FROM transactions t
            JOIN merchant_clusters c ON t.cluster_id = c.cluster_id
            JOIN merchants m ON c.merchant_id = m.merchant_id
            WHERE m.is_system = 0
            GROUP BY m.merchant_id
            ORDER BY count DESC
            LIMIT 5
        """)
        largest_by_count = [dict(row) for row in cursor.fetchall()]

        cursor.execute("""
            SELECT 
                SUM(CASE WHEN confidence_score >= 0.9 THEN 1 ELSE 0 END) as high,
                SUM(CASE WHEN confidence_score >= 0.6 AND confidence_score < 0.9 THEN 1 ELSE 0 END) as medium,
                SUM(CASE WHEN confidence_score < 0.6 THEN 1 ELSE 0 END) as low,
                COUNT(*) as total
            FROM merchant_clusters
        """)
        conf_row = cursor.fetchone()
        confidence_distribution = dict(conf_row) if conf_row else {"high": 0, "medium": 0, "low": 0, "total": 0}

        cursor.execute("""
            SELECT 
                SUM(CASE WHEN is_user_verified = 1 OR is_locked = 1 THEN 1 ELSE 0 END) as verified,
                COUNT(*) as total
            FROM merchant_clusters
        """)
        quality_row = cursor.fetchone()
        quality_score = round((quality_row["verified"] / quality_row["total"]) * 100, 2) if quality_row and quality_row["total"] > 0 else 100.0

        cursor.execute("""
            SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as new_merchants
            FROM merchants
            WHERE is_system = 0
            GROUP BY month
            ORDER BY month DESC
            LIMIT 6
        """)
        growth_trends = [dict(row) for row in cursor.fetchall()]

        return {
            "total_merchants": total_merchants,
            "total_clusters": total_clusters,
            "uncategorized_merchants": uncategorized_merchants,
            "largest_by_spend": largest_by_spend,
            "largest_by_count": largest_by_count,
            "confidence_distribution": confidence_distribution,
            "cluster_quality_score": quality_score,
            "growth_trends": growth_trends
        }
    except Exception as e:
        logger.error(f"Error fetching dashboard metrics: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)