import shutil
import uuid
import os
import logging
import sys
import asyncio
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form, Body, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import BaseModel
from typing import Optional
from config import ENABLE_BANKING_APP_ID, ENABLE_BANKING_REDIRECT_URI, ALLOWED_CATEGORIES
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
    return FileResponse(FRONTEND_DIR / "dashboard.html")

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
                "options": ["Revolut", "Commerzbank", "Advanzia Bank credit card", "HDFC"]
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
                a.account_name,
                t.description,
                t.display_name,
                t.flexibility_tier as flexibility,
                t.category,
                t.amount,
                t.currency
            FROM transactions t
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
    return await call_next(request)

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
                transaction_id as id, 
                account_id as account, 
                booking_date as date, 
                description, 
                display_name, 
                category, 
                flexibility_tier as flexibility, 
                amount, 
                currency, 
                is_guess, 
                is_pinned, 
                is_ignored, 
                status 
            FROM transactions
            WHERE (is_guess = 1 OR category IS NULL OR category = '' OR category = 'Uncategorized' OR category = 'Unsorted')
              AND is_pinned = 0
              AND is_ignored = 0
            ORDER BY booking_date DESC, transaction_id DESC
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)