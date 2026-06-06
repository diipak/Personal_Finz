import shutil
import uuid
import os
import logging
import sys
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form, Body, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import GOCARDLESS_SECRET_ID, GOCARDLESS_SECRET_KEY, ALLOWED_CATEGORIES
from db.database import get_db, init_db
from pipeline import process_manual_file, process_gocardless_sync
from api.services.analytics import get_financial_summary, get_health_metrics
from agent.assistant import ask_assistant
from parsers.gocardless_sync import GoCardlessClient

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

app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")

@app.get("/")
def dashboard():
    return FileResponse(FRONTEND_DIR / "dashboard.html")

@app.get("/import-ui")
def import_ui():
    return FileResponse(FRONTEND_DIR / "import_statement.html")

@app.get("/rules")
def rules_ui():
    return FileResponse(FRONTEND_DIR / "merchant_rule_manager.html")

@app.get("/review")
def review_ui():
    return FileResponse(FRONTEND_DIR / "unknown_merchant_review.html")

# Rules API Endpoint: Retrieve rules from SQLite
@app.get("/api/rules")
def get_rules():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM rules ORDER BY priority DESC, id ASC")
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
    conn = get_db()
    cursor = conn.cursor()
    try:
        if "id" in rule and rule["id"]:
            cursor.execute(
                """
                UPDATE rules SET 
                    pattern = :pattern,
                    match_type = :match_type,
                    category = :category,
                    display_name = :display_name,
                    flexibility = :flexibility,
                    tags = :tags,
                    amount_min = :amount_min,
                    amount_max = :amount_max,
                    priority = :priority
                WHERE id = :id
                """,
                rule
            )
        else:
            cursor.execute(
                """
                INSERT INTO rules (
                    pattern, match_type, category, display_name, flexibility, tags, amount_min, amount_max, priority
                ) VALUES (
                    :pattern, :match_type, :category, :display_name, :flexibility, :tags, :amount_min, :amount_max, :priority
                )
                """,
                rule
            )
        conn.commit()
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
        cursor.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
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
def import_file(file: UploadFile = File(...), account: str = Form("Statement")):
    file_id = str(uuid.uuid4())
    extension = Path(file.filename).suffix.lower()
    
    input_path = UPLOAD_DIR / f"{file_id}{extension}"
    logger.info(f"Importing manual statement {file.filename} as {file_id} for account {account}")

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        inserted = process_manual_file(str(input_path), account)
        return {
            "status": "success",
            "file_id": file_id,
            "inserted_count": inserted
        }
    except Exception as e:
        logger.error(f"Error processing manual import: {e}")
        return {"status": "error", "error": "Import processing failed", "details": str(e)}
    finally:
        # Clean up local file after processing
        if input_path.exists():
            os.remove(input_path)

# GoCardless Link Endpoint
@app.post("/api/sync/link")
def get_sync_link(institution_id: str = Body(embed=True), redirect_uri: str = Body(embed=True)):
    if not GOCARDLESS_SECRET_ID or not GOCARDLESS_SECRET_KEY:
        raise HTTPException(status_code=400, detail="GoCardless API credentials not set in environment.")
        
    client = GoCardlessClient(GOCARDLESS_SECRET_ID, GOCARDLESS_SECRET_KEY)
    try:
        reference = str(uuid.uuid4())
        link = client.get_requisition_link(institution_id, redirect_uri, reference)
        return {"link": link, "reference": reference}
    except Exception as e:
        logger.error(f"Error generating GoCardless connection link: {e}")
        raise HTTPException(status_code=500, detail=f"GoCardless error: {e}")

# GoCardless Automated Sync with PSD2 Rate Limit Guard
@app.post("/api/sync/auto")
def trigger_sync(account_id: str = Body(embed=True), account_name: str = Body(embed=True), initiated_by: str = Body(default="USER_BUTTON", embed=True)):
    if not GOCARDLESS_SECRET_ID or not GOCARDLESS_SECRET_KEY:
        raise HTTPException(status_code=400, detail="GoCardless credentials missing.")

    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Rate Limit Safeguard (max 4 calls per 24 hours per account)
    try:
        cursor.execute(
            """
            SELECT COUNT(*) as count FROM sync_logs 
            WHERE account_id = ? 
              AND sync_source = 'gocardless' 
              AND status = 'SUCCESS' 
              AND timestamp >= datetime('now', '-24 hours')
            """,
            (account_id,)
        )
        res = cursor.fetchone()
        
        if res["count"] >= 4:
            # Block the sync and log the skipped state
            cursor.execute(
                """
                INSERT INTO sync_logs (account_id, sync_source, status, initiated_by, error_message)
                VALUES (?, 'gocardless', 'SKIPPED', ?, 'Rate limit reached: Max 4 successful syncs per 24h')
                """,
                (account_id, initiated_by)
            )
            conn.commit()
            return {
                "status": "SKIPPED",
                "message": "Sync skipped: GoCardless rate limit reached (Max 4 successful calls per 24 hours allowed)."
            }
    except Exception as log_err:
        logger.error(f"Failed to check rate limit logs: {log_err}")
        raise HTTPException(status_code=500, detail="Sync logs rate limit check failed")
    finally:
        conn.close()

    # 2. Perform automated sync
    conn = get_db()
    cursor = conn.cursor()
    try:
        inserted = process_gocardless_sync(account_id, account_name, GOCARDLESS_SECRET_ID, GOCARDLESS_SECRET_KEY)
        
        # Log successful sync
        cursor.execute(
            """
            INSERT INTO sync_logs (account_id, sync_source, status, initiated_by)
            VALUES (?, 'gocardless', 'SUCCESS', ?)
            """,
            (account_id, initiated_by)
        )
        conn.commit()
        return {
            "status": "SUCCESS",
            "inserted_count": inserted
        }
    except Exception as e:
        logger.error(f"Sync execution failure: {e}")
        # Log failed sync
        cursor.execute(
            """
            INSERT INTO sync_logs (account_id, sync_source, status, initiated_by, error_message)
            VALUES (?, 'gocardless', 'FAILED', ?, ?)
            """,
            (account_id, initiated_by, str(e))
        )
        conn.commit()
        return {"status": "FAILED", "error": str(e)}
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

# Review Queue APIs
@app.get("/api/categories")
def get_categories():
    return ALLOWED_CATEGORIES

@app.get("/api/unknown")
def get_unknown_transactions():
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Fetch transactions that are guesses or uncategorized, not pinned, and not ignored
        cursor.execute(
            """
            SELECT * FROM transactions
            WHERE (is_guess = 1 OR category IS NULL OR category = '' OR category = 'Uncategorized')
              AND is_pinned = 0
              AND is_ignored = 0
            ORDER BY date DESC, id DESC
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
                    flexibility = ?,
                    display_name = ?,
                    is_guess = 0,
                    is_pinned = 1,
                    is_ignored = ?
                WHERE id = ?
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
                        "SELECT id FROM rules WHERE pattern = ? AND match_type = ?",
                        (pattern, rule_data.get("match_type", "substring"))
                    )
                    if not cursor.fetchone():
                        cursor.execute(
                            """
                            INSERT INTO rules (
                                pattern, match_type, category, display_name, flexibility, tags, amount_min, amount_max, priority
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                pattern,
                                rule_data.get("match_type", "substring"),
                                rule_data.get("category", category),
                                rule_data.get("display_name", display_name),
                                rule_data.get("flexibility", flexibility),
                                rule_data.get("tags"),
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