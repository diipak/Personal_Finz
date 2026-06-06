import os
import sys
import pandas as pd
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers import hdfc, revolut, pdf

def parse_file(file_path: str) -> pd.DataFrame:
    """
    Detects the file format (Excel, CSV, PDF) and parses it using the appropriate parser.
    Returns a standardized pandas DataFrame.
    """
    ext = Path(file_path).suffix.lower()
    
    if ext in [".xls", ".xlsx"]:
        return hdfc.parse(file_path)
    elif ext == ".pdf":
        return pdf.parse(file_path)
    elif ext == ".csv":
        return revolut.parse(file_path)
    else:
        raise ValueError(f"Unsupported file format: {ext}")
