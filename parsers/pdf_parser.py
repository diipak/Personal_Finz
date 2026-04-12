import pdfplumber
import pandas as pd

def parse_pdf(file_path):
    rows = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                # Often the first row of a table is header, 
                # but if we're concatenating multiple pages, we might need to filter.
                for row in table:
                    # Filter out empty rows or header-looking rows if needed
                    if row and any(row):
                        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=["Completed Date", "Description", "Amount"])

    df = pd.DataFrame(rows)
    
    # Try to find header row if column names are not correct
    # This is a bit complex for PDF, but let's assume a standard format for now
    # or just use the first few columns.
    
    # Based on user's original code:
    # df.columns = ["Date","Description","Amount","Balance"]
    
    # More robust:
    if len(df.columns) >= 3:
        df = df.iloc[:, :3]
        df.columns = ["Completed Date", "Description", "Amount"]
    else:
        # Fallback
        return pd.DataFrame(columns=["Completed Date", "Description", "Amount"])

    # Clean amount
    def clean_amount(val):
        if pd.isna(val): return 0.0
        s = str(val).replace(",", "").replace("$", "").strip()
        try:
            return float(s)
        except:
            return 0.0

    df["Amount"] = df["Amount"].apply(clean_amount)
    
    # Drop rows where Date is clearly not a date (like headers)
    # Simple check: does it have at least one digit?
    df = df[df["Completed Date"].astype(str).str.contains(r'\d', na=False)]

    return df[[
        "Completed Date",
        "Description",
        "Amount"
    ]]
