import pdfplumber
import pandas as pd
import re
from datetime import datetime

def parse_date_to_iso(date_str, bank_type):
    """Converts various date formats to standardized YYYY-MM-DD format."""
    date_str = str(date_str).strip()
    try:
        if bank_type == "HDFC":
            # format 04/04/20 -> 2020-04-04
            dt = datetime.strptime(date_str, "%d/%m/%y")
            return dt.strftime("%Y-%m-%d")
        elif bank_type == "Commerzbank":
            # format 31.05.2023 -> 2023-05-31
            dt = datetime.strptime(date_str, "%d.%m.%Y")
            return dt.strftime("%Y-%m-%d")
        elif bank_type == "Revolut":
            # format Apr 2, 2023 -> 2023-04-02
            dt = datetime.strptime(date_str, "%b %d, %Y")
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return date_str

def parse_hdfc(file_path):
    rows = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            lines = {}
            for w in words:
                top = round(w["top"], 1)
                matched_top = None
                for t in lines:
                    if abs(t - top) < 3:
                        matched_top = t
                        break
                if matched_top is None:
                    lines[top] = [w]
                else:
                    lines[matched_top].append(w)
            
            for top in sorted(lines.keys()):
                line_words = sorted(lines[top], key=lambda x: x["x0"])
                if len(line_words) < 5:
                    continue
                
                first_word = line_words[0]["text"]
                if not re.match(r'^\d{2}/\d{2}/\d{2}$', first_word):
                    continue
                
                # Check for Value Date to identify the structure
                val_date_idx = None
                for i in range(len(line_words) - 1, 0, -1):
                    if re.match(r'^\d{2}/\d{2}/\d{2}$', line_words[i]["text"]):
                        val_date_idx = i
                        break
                
                if val_date_idx is None or val_date_idx < 2:
                    continue
                
                try:
                    narration = " ".join([w["text"] for w in line_words[1 : val_date_idx - 1]])
                    amount_word = line_words[val_date_idx + 1]["text"]
                    
                    # Determine withdrawal vs deposit using coordinates of the amount word
                    amount_w = line_words[val_date_idx + 1]
                    center_x = (amount_w["x0"] + amount_w["x1"]) / 2.0
                    
                    val = float(amount_word.replace(",", ""))
                    # WithdrawalAmt is around x = 400. DepositAmt is around x = 468.
                    if center_x < 438:
                        val = -abs(val)
                    else:
                        val = abs(val)
                        
                    iso_date = parse_date_to_iso(first_word, "HDFC")
                    rows.append({
                        "Completed Date": iso_date,
                        "Description": narration,
                        "Amount": val,
                        "Currency": "INR",
                        "Account": "HDFC"
                    })
                except Exception:
                    pass
    return pd.DataFrame(rows)

def parse_commerzbank(file_path):
    rows = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            lines = {}
            for w in words:
                top = round(w["top"], 1)
                matched_top = None
                for t in lines:
                    if abs(t - top) < 3:
                        matched_top = t
                        break
                if matched_top is None:
                    lines[top] = [w]
                else:
                    lines[matched_top].append(w)
            
            for top in sorted(lines.keys()):
                line_words = sorted(lines[top], key=lambda x: x["x0"])
                if len(line_words) < 5:
                    continue
                
                first_word = line_words[0]["text"]
                if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', first_word):
                    continue
                
                last_word = line_words[-1]["text"]
                if last_word != "EUR":
                    continue
                
                try:
                    sign_word = line_words[-3]["text"]
                    amount_word = line_words[-2]["text"]
                    tx_type = line_words[1]["text"]
                    description = " ".join([w["text"] for w in line_words[2:-3]])
                    
                    val = float(amount_word.replace(",", ""))
                    if sign_word == "-":
                        val = -abs(val)
                    elif sign_word == "+":
                        val = abs(val)
                        
                    iso_date = parse_date_to_iso(first_word, "Commerzbank")
                    rows.append({
                        "Completed Date": iso_date,
                        "Description": f"{tx_type}: {description}",
                        "Amount": val,
                        "Currency": "EUR",
                        "Account": "Commerzbank"
                    })
                except Exception:
                    pass
    return pd.DataFrame(rows)

def parse_revolut(file_path):
    rows = []
    date_pattern = re.compile(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\s+(.*)')
    amount_pattern = re.compile(r'([€$£-]?\s*\d{1,3}(?:,\d{3})*(?:\.\d{2}))')

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue
            
            for line in text.split('\n'):
                line = line.strip()
                match = date_pattern.match(line)
                if match:
                    date_str = line[:12].strip()
                    remainder = line[12:].strip()
                    
                    amounts = amount_pattern.findall(remainder)
                    if not amounts:
                        continue
                        
                    description = remainder
                    for amt in amounts:
                        description = description.replace(amt, "")
                    description = description.strip()
                    
                    tx_amount_str = amounts[0]
                    val = float(tx_amount_str.replace("€", "").replace("$", "").replace("£", "").replace(",", "").strip())
                    
                    if "To " in description or "fee" in description.lower() or "apple.com" in description.lower() or "lycamobille" in description.lower():
                        val = -abs(val)
                    else:
                        if "top-up" in description.lower() or "salary" in description.lower() or "payment from" in description.lower() or "refund" in description.lower():
                            val = abs(val)
                        else:
                            val = -abs(val)

                    iso_date = parse_date_to_iso(date_str, "Revolut")
                    rows.append({
                        "Completed Date": iso_date,
                        "Description": description,
                        "Amount": val,
                        "Currency": "EUR",
                        "Account": "Revolut"
                    })
    return pd.DataFrame(rows)

def parse_pdf(file_path):
    # Detect bank type
    with pdfplumber.open(file_path) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        
    if "hdfc" in first_page_text.lower():
        return parse_hdfc(file_path)
    elif "commerzbank" in first_page_text.lower():
        return parse_commerzbank(file_path)
    elif "revolut" in first_page_text.lower() or "revolt" in first_page_text.lower():
        return parse_revolut(file_path)
    else:
        # Fallback: try all three and choose the one that extracts the most transactions
        df_revolut = parse_revolut(file_path)
        if len(df_revolut) > 0:
            return df_revolut
            
        df_commerz = parse_commerzbank(file_path)
        df_hdfc = parse_hdfc(file_path)
        
        if len(df_commerz) >= len(df_hdfc):
            return df_hdfc

parse = parse_pdf
