import pandas as pd

def parse(file_path):
    # read without header first to find the correct header row
    df_raw = pd.read_excel(file_path, header=None)
    
    header_row = None
    for i, row in df_raw.iterrows():
        if "Narration" in [str(v) for v in row.values]:
            header_row = i
            break
            
    if header_row is None:
        raise ValueError("Could not find 'Narration' column in Excel file")

    # read again with the correct header row
    df = pd.read_excel(file_path, header=header_row)
    
    # Strip any extra whitespace from column names
    df.columns = [str(c).strip() for col in [df.columns] for c in col]

    # Map the specific HDFC columns
    # Withdrawal Amt. -> Debit
    # Deposit Amt. -> Credit
    
    df = df.rename(columns={
        "Date": "Completed Date",
        "Narration": "Description",
        "Withdrawal Amt.": "Debit",
        "Deposit Amt.": "Credit"
    })

    # Ensure Debit/Credit are numeric
    df["Credit"] = pd.to_numeric(df["Credit"], errors='coerce').fillna(0)
    df["Debit"] = pd.to_numeric(df["Debit"], errors='coerce').fillna(0)

    df["Amount"] = df["Credit"] - df["Debit"]

    # Keep only necessary columns
    result = df[[
        "Completed Date",
        "Description",
        "Amount"
    ]]
    
    # Drop rows where Date is missing (likely footer rows)
    result = result.dropna(subset=["Completed Date"])

    return result
