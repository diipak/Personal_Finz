import shutil
import subprocess
import uuid
import os
import json
import pandas as pd
import logging
import sys
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Body
from api.services.preview_service import load_preview
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOAD_DIR = BASE_DIR / "api" / "uploads"
RULE_FILE = BASE_DIR / "pipeline" / "merchant_rules.json"
VENV_PYTHON = sys.executable

os.makedirs(UPLOAD_DIR, exist_ok=True)

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

@app.get("/api/rules")
def get_rules():
    with open(RULE_FILE, "r") as f:
        return json.load(f)

@app.post("/api/rules")
def save_rules(rules: dict = Body(...)):
    with open(RULE_FILE, "w") as f:
        json.dump(rules, f, indent=2)
    return {"status": "success"}

@app.get("/api/recent-imports")
def get_recent_imports():
    imports = []
    if not UPLOAD_DIR.exists():
        return []
    for f in os.listdir(UPLOAD_DIR):
        if f.endswith("_processed.csv"):
            file_id = f.replace("_processed.csv", "")
            file_path = UPLOAD_DIR / f
            stats = os.stat(file_path)
            
            try:
                df = pd.read_csv(file_path)
                account_val = "Unknown"
                if "Account" in df.columns and not df.empty:
                    val = df["Account"].iloc[0]
                    if pd.notna(val):
                        account_val = str(val)
                imports.append({
                    "id": file_id,
                    "filename": f,
                    "date": pd.to_datetime(stats.st_mtime, unit='s').strftime('%Y-%m-%d %H:%M:%S'),
                    "transactions": len(df),
                    "account": account_val
                })
            except Exception as e:
                logger.error(f"Error reading {f}: {e}")
                
    imports.sort(key=lambda x: x["date"], reverse=True)
    return imports

@app.get("/preview/{file_id}")
def preview(file_id: str):
    data = load_preview(file_id)
    if data is None:
        return {"error": "file not found"}
    return {"transactions": data}

@app.post("/import")
def import_file(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    extension = Path(file.filename).suffix.lower()
    
    input_path = UPLOAD_DIR / f"{file_id}{extension}"
    parsed_path = UPLOAD_DIR / f"{file_id}_parsed.csv"
    output_path = UPLOAD_DIR / f"{file_id}_processed.csv"

    logger.info(f"Importing {file.filename} as {file_id}")

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # 1. Parsing Phase (Unified Orchestrator)
        orchestrator_script = BASE_DIR / "pipeline" / "orchestrator.py"
        result = subprocess.run([str(VENV_PYTHON), str(orchestrator_script), str(input_path), str(parsed_path)], 
                             cwd=str(BASE_DIR), capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Orchestrator failed: {result.stderr}")
            return {"error": "Parsing failed", "details": result.stderr}

        # 2. Categorization Phase
        categorize_script = BASE_DIR / "pipeline" / "categorize.py"
        result = subprocess.run(
            [str(VENV_PYTHON), str(categorize_script), str(parsed_path), str(output_path)],
            cwd=str(BASE_DIR), capture_output=True, text=True
        )
        if result.returncode != 0:
            logger.error(f"Categorization failed: {result.stderr}")
            return {"error": "Categorization failed", "details": result.stderr}

        if not output_path.exists():
            logger.error(f"Output file not created at {output_path}")
            return {"error": "Output file not created"}

        return {
            "file_id": file_id,
            "processed_file": str(output_path)
        }
    except Exception as e:
        logger.error(f"Unexpected error during import: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)