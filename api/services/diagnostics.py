import os
import requests
import sqlite3
import logging
from config import DB_PATH, EZBOOKKEEPING_API_URL, EZBOOKKEEPING_TOKEN, OLLAMA_URL, LLM_MODEL, ENABLE_BANKING_KEY_PATH, ENABLE_BANKING_APP_ID

logger = logging.getLogger(__name__)

def check_enable_banking_key() -> dict:
    """Checks if the Enable Banking private key is present and readable."""
    _base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _key_path = os.path.join(_base_dir, ENABLE_BANKING_KEY_PATH) if not os.path.isabs(ENABLE_BANKING_KEY_PATH) else ENABLE_BANKING_KEY_PATH
    
    if not ENABLE_BANKING_APP_ID:
        return {"status": "CRITICAL", "message": "ENABLE_BANKING_APP_ID not set in .env"}
        
    if not os.path.exists(_key_path):
        return {"status": "CRITICAL", "message": f"Private key not found at: {ENABLE_BANKING_KEY_PATH}"}
        
    if not os.access(_key_path, os.R_OK):
        return {"status": "CRITICAL", "message": "Private key file is not readable"}
        
    try:
        with open(_key_path, "rb") as f:
            content = f.read()
            if not content.strip():
                return {"status": "CRITICAL", "message": "Private key file is empty"}
        return {"status": "OK", "message": "Key is readable and valid"}
    except Exception as e:
        return {"status": "CRITICAL", "message": f"Error reading key: {str(e)}"}

def check_sqlite_db() -> dict:
    """Checks if the SQLite database is initialized and readable/writable."""
    if not os.path.exists(DB_PATH):
        return {"status": "WARNING", "message": "Database file does not exist yet"}
        
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")
        table_exists = cursor.fetchone()
        conn.close()
        
        if not table_exists:
            return {"status": "CRITICAL", "message": "Missing transactions schema table"}
        return {"status": "OK", "message": "Database is connected and initialized"}
    except Exception as e:
        return {"status": "CRITICAL", "message": f"Database error: {str(e)}"}

def check_ezbookkeeping() -> dict:
    """Checks if the ezBookkeeping server is online and responding to authorized requests."""
    if not EZBOOKKEEPING_TOKEN:
        return {"status": "WARNING", "message": "EZBOOKKEEPING_TOKEN not set in .env"}
        
    headers = {
        "Authorization": f"Bearer {EZBOOKKEEPING_TOKEN}",
        "Content-Type": "application/json"
    }
    url = f"{EZBOOKKEEPING_API_URL}/transaction/tags/list.json"
    
    try:
        res = requests.get(url, headers=headers, timeout=3)
        if res.status_code == 200:
            return {"status": "OK", "message": "Server online, API token authorized"}
        elif res.status_code == 401:
            return {"status": "CRITICAL", "message": "Server online, but API token is unauthorized"}
        else:
            return {"status": "CRITICAL", "message": f"Server responded with status {res.status_code}"}
    except requests.exceptions.Timeout:
        return {"status": "CRITICAL", "message": "Connection timed out (server is offline)"}
    except Exception as e:
        return {"status": "CRITICAL", "message": f"Connection failed: {type(e).__name__}"}

def check_ollama() -> dict:
    """Checks if the Ollama service is running and if the configured model is available."""
    if not OLLAMA_URL:
        return {"status": "WARNING", "message": "OLLAMA_URL not configured"}
        
    tags_url = f"{OLLAMA_URL}/api/tags"
    try:
        res = requests.get(tags_url, timeout=3)
        if res.status_code != 200:
            return {"status": "CRITICAL", "message": f"Ollama returned status {res.status_code}"}
            
        models = [m.get("name") for m in res.json().get("models", [])]
        
        matched_model = None
        for m in models:
            if m.lower() == LLM_MODEL.lower() or m.lower().startswith(LLM_MODEL.lower() + ":"):
                matched_model = m
                break
                
        if matched_model:
            return {"status": "OK", "message": f"Ollama online, model '{matched_model}' is active"}
        else:
            available = ", ".join(models) if models else "none"
            return {"status": "WARNING", "message": f"Model '{LLM_MODEL}' missing. Available: {available}"}
    except requests.exceptions.Timeout:
        return {"status": "CRITICAL", "message": "Connection timed out (Ollama is offline)"}
    except Exception:
        return {"status": "CRITICAL", "message": "Ollama service is offline"}

def run_diagnostics() -> dict:
    """Runs all health check validation diagnostics."""
    eb_key = check_enable_banking_key()
    db = check_sqlite_db()
    ez = check_ezbookkeeping()
    oll = check_ollama()
    
    statuses = [eb_key["status"], db["status"], ez["status"], oll["status"]]
    if "CRITICAL" in statuses:
        overall = "CRITICAL"
    elif "WARNING" in statuses:
        overall = "WARNING"
    else:
        overall = "OK"
        
    return {
        "status": overall,
        "checks": {
            "sqlite_database": db,
            "enable_banking_key": eb_key,
            "ezbookkeeping": ez,
            "ollama_ai": oll
        }
    }
