import pandas as pd
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = BASE_DIR / "api" / "uploads"

def load_preview(file_id):

    processed_file = os.path.join(UPLOAD_DIR, f"{file_id}_processed.csv")

    if not os.path.exists(processed_file):
        print(f"Preview file not found: {processed_file}")
        return None

    try:
        df = pd.read_csv(processed_file)
        return df.head(50).to_dict(orient="records")
    except Exception as e:
        print(f"Error reading preview file: {e}")
        return None