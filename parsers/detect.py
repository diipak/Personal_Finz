import os
import sys
import pandas as pd
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers import hdfc, revolut, pdf

import pdfplumber

def detect_bank_type(file_path: str) -> str:
    """
    Analyzes file contents to detect the bank.
    Returns: 'Revolut', 'Commerzbank', 'HDFC', 'Advanzia Bank credit card' or raises ValueError.
    """
    ext = Path(file_path).suffix.lower()
    
    if ext in [".xls", ".xlsx"]:
        try:
            # Check sheet contents for "narration" to identify HDFC Excel
            df_raw = pd.read_excel(file_path, header=None, nrows=30)
            for _, row in df_raw.iterrows():
                row_vals = [str(v).lower().strip() for v in row.values if pd.notna(v)]
                if "narration" in row_vals:
                    return "HDFC"
        except Exception:
            pass
        return "HDFC" # Fallback default
        
    elif ext == ".pdf":
        try:
            with pdfplumber.open(file_path) as pdf_obj:
                # Read first page text to inspect string signatures
                first_page_text = pdf_obj.pages[0].extract_text() or ""
                first_page_text_lower = first_page_text.lower()
                
            if "advanzia" in first_page_text_lower or "gebührenfrei" in first_page_text_lower:
                return "Advanzia Bank credit card"
            elif "commerzbank" in first_page_text_lower:
                return "Commerzbank"
            elif "hdfc" in first_page_text_lower:
                return "HDFC"
            elif "revolut" in first_page_text_lower or "revolt" in first_page_text_lower:
                return "Revolut"
            elif "openbank" in first_page_text_lower or "amazon visa" in first_page_text_lower:
                return "Amazon Visa"
            elif "trade republic" in first_page_text_lower:
                return "Trade Republic"
        except Exception as e:
            raise ValueError(f"Failed to extract PDF text: {e}")
            
    elif ext == ".csv":
        try:
            # Check Revolut CSV column signature
            df_raw = pd.read_csv(file_path, nrows=2)
            cols = [str(c).lower().strip() for c in df_raw.columns]
            if "started date" in cols or "completed date" in cols or "state" in cols:
                return "Revolut"
        except Exception:
            pass
        return "Revolut" # Fallback default
        
    raise ValueError("Could not automatically identify the bank statement format.")

def parse_file(file_path: str, bank_type: str = None) -> pd.DataFrame:
    """
    Detects the file format (Excel, CSV, PDF) and parses it using the appropriate parser.
    Returns a standardized pandas DataFrame.
    """
    if not bank_type:
        bank_type = detect_bank_type(file_path)
        
    ext = Path(file_path).suffix.lower()
    
    if bank_type == "HDFC":
        if ext == ".pdf":
            return pdf.parse_hdfc(file_path)
        else:
            return hdfc.parse(file_path)
    elif bank_type == "Commerzbank":
        if ext == ".pdf":
            return pdf.parse_commerzbank(file_path)
        else:
            raise ValueError("Commerzbank statement must be a PDF file.")
    elif bank_type == "Revolut":
        if ext == ".csv":
            return revolut.parse(file_path)
        elif ext == ".pdf":
            return pdf.parse_revolut(file_path)
        else:
            raise ValueError("Unsupported file format for Revolut.")
    elif bank_type == "Advanzia Bank credit card":
        if ext == ".pdf":
            return pdf.parse_advanzia(file_path)
        else:
            raise ValueError("Advanzia statement must be a PDF file.")
    elif bank_type == "Amazon Visa":
        if ext == ".pdf":
            return pdf.parse_openbank(file_path)
        else:
            raise ValueError("Amazon Visa statement must be a PDF file.")
    elif bank_type == "Trade Republic":
        if ext == ".pdf":
            return pdf.parse_trade_republic(file_path)
        else:
            raise ValueError("Trade Republic statement must be a PDF file.")
    else:
        raise ValueError(f"Unsupported bank type: {bank_type}")
