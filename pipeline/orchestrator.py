import sys
import os
import pandas as pd
from pathlib import Path

# allow imports from project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.excel_parser import parse_excel
from parsers.pdf_parser import parse_pdf
from parsers.revolut_parser import parse as parse_revolut

def process_file(input_file):
    """
    Detects file type, parses it, and returns a standardized DataFrame.
    Guaranteed columns: ["Completed Date", "Description", "Amount", "Currency"]
    """
    ext = Path(input_file).suffix.lower()
    
    if ext in [".xls", ".xlsx"]:
        df = parse_excel(input_file)
    elif ext == ".pdf":
        df = parse_pdf(input_file)
    elif ext == ".csv":
        df = parse_revolut(input_file)
    else:
        raise ValueError(f"Unsupported file type: {ext}")
        
    # Standardize column mappings if the parser didn't fully handle it
    col_map = {}
    for col in df.columns:
        if str(col).lower() in ['date', 'completed date']:
            col_map[col] = 'Completed Date'
        if str(col).lower() in ['description', 'narration']:
            col_map[col] = 'Description'
        if str(col).lower() in ['amount']:
            col_map[col] = 'Amount'

    df = df.rename(columns=col_map)

    # Ensure essential columns exist
    if "Completed Date" not in df.columns:
        df["Completed Date"] = "Unknown"
    if "Description" not in df.columns:
        df["Description"] = "Unknown"
    if "Amount" not in df.columns:
        df["Amount"] = 0.0
    if "Currency" not in df.columns:
        df["Currency"] = "EUR" # Default to EUR for standard
        
    # Clean amount formatting just in case
    if df["Amount"].dtype == object:
        df["Amount"] = df["Amount"].astype(str).str.replace(",", "").astype(float)
    df["Amount"] = df["Amount"].astype(float)
    
    return df

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python orchestrator.py <input_file> <output_file>")
        sys.exit(1)
        
    in_file = sys.argv[1]
    out_file = sys.argv[2]
    
    result_df = process_file(in_file)
    
    # Save the parsed, standardized data to an intermediate CSV
    result_df.to_csv(out_file, index=False)
    print(f"Orchestrated output saved to {out_file}")
