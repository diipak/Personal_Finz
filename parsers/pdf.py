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
        elif bank_type in ["Commerzbank", "Advanzia", "Amazon Visa"]:
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

def parse_advanzia(file_path):
    rows = []
    # Pattern to match date description and amount for Advanzia
    pattern = re.compile(r'^(\d{2}\.\d{2}\.\d{4})\s+(.+?)\s+(-?\s*\d{1,3}(?:\.\d{3})*(?:,\d{2}))\s*$')
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            for line in text.split('\n'):
                line = line.strip()
                match = pattern.match(line)
                if match:
                    date_str = match.group(1)
                    description = match.group(2).strip()
                    amount_str = match.group(3).strip()
                    
                    if description.upper() in ["ALTER SALDO", "NEUER SALDO"]:
                        continue
                        
                    try:
                        clean_amt_str = amount_str.replace(".", "").replace(",", ".").replace(" ", "")
                        val = float(clean_amt_str)
                        # Invert signs: credit card purchases are positive in statement but negative/expense in app.
                        # Payments/credits are negative in statement but positive/income in app.
                        val = -val
                        
                        iso_date = parse_date_to_iso(date_str, "Advanzia")
                        rows.append({
                            "Completed Date": iso_date,
                            "Description": description,
                            "Amount": val,
                            "Currency": "EUR",
                            "Account": "Advanzia Bank credit card"
                        })
                    except Exception:
                        pass
    return pd.DataFrame(rows)

def parse_openbank(file_path):
    rows = []
    # Pattern matches Date Card Description Amount Points
    # e.g., 08.06.2026 *********7419 GELDAUSZAHLUNG VON KARTE**7419 AUF KONTO -2.500,00 € +62
    pattern = re.compile(
        r'^(\d{2}\.\d{2}\.\d{4})\s+(\S+)\s+(.+?)\s+([+-]?\d{1,3}(?:\.\d{3})*(?:,\d{2}))\s*€(?:.*)$'
    )
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            # Reconstruct lines using layout coordinate grouping
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
                line_text = " ".join([w["text"] for w in line_words]).strip()
                
                match = pattern.match(line_text)
                if match:
                    date_str = match.group(1)
                    description = match.group(3).strip()
                    amount_str = match.group(4).strip()
                    
                    if description.upper() in ["ANFANGSSALDO", "ENDSALDO"]:
                        continue
                    
                    try:
                        # Convert amount: e.g. -2.500,00 -> -2500.00
                        clean_amt_str = amount_str.replace(".", "").replace(",", ".").replace(" ", "")
                        val = float(clean_amt_str)
                        
                        # Amazon Visa: no sign inversion is needed!
                        iso_date = parse_date_to_iso(date_str, "Amazon Visa")
                        
                        rows.append({
                            "Completed Date": iso_date,
                            "Description": description,
                            "Amount": val,
                            "Currency": "EUR",
                            "Account": "Amazon Visa"
                        })
                    except Exception:
                        pass
    return pd.DataFrame(rows)

def parse_trade_republic(file_path):
    rows = []
    
    # State tracking for vertically stacked date
    current_day = None
    current_month = None
    current_year = None
    
    # Track the active transaction being built
    current_tx = None
    
    # German Month mappings
    month_map = {
        "jan": "01", "feb": "02", "mär": "03", "mrz": "03", "apr": "04",
        "mai": "05", "jun": "06", "jul": "07", "aug": "08", "sep": "09",
        "okt": "10", "nov": "11", "dez": "12"
    }
    
    def finalize_transaction(tx):
        if not tx:
            return
        # Construct date
        d = tx.get("day")
        m = tx.get("month")
        y = tx.get("year")
        
        # Fallback date if any component is missing
        if d and m and y:
            d_clean = d.zfill(2)
            m_clean = month_map.get(m.lower().replace(".", "").strip()[:3], "01")
            date_iso = f"{y}-{m_clean}-{d_clean}"
        else:
            date_iso = datetime.now().strftime("%Y-%m-%d")
            
        desc = " ".join(tx.get("description_parts", [])).strip()
        amt = tx.get("amount")
        
        if amt is not None:
            rows.append({
                "Completed Date": date_iso,
                "Description": desc,
                "Amount": amt,
                "Currency": "EUR",
                "Account": "Trade Republic"
            })

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
                if not line_words:
                    continue
                
                first_w = line_words[0]
                first_text = first_w["text"].strip()
                
                # Check if this line is in the DATUM column (usually x0 < 60)
                if first_w["x0"] < 60:
                    # Case 1: Word is a Day (1 to 2 digits)
                    if re.match(r'^\d{1,2}$', first_text):
                        # Finalize previous transaction if any
                        finalize_transaction(current_tx)
                        
                        current_day = first_text
                        current_tx = {
                            "day": current_day,
                            "month": current_month,
                            "year": current_year,
                            "description_parts": [],
                            "amount": None
                        }
                        
                        # Process other columns on this same Day line
                        typ_part = ""
                        desc_parts = []
                        amt_str = None
                        
                        for w in line_words[1:]:
                            x0 = w["x0"]
                            if x0 < 140:
                                typ_part += " " + w["text"]
                            elif x0 < 380:
                                desc_parts.append(w["text"])
                            elif x0 < 500:
                                if amt_str is None:
                                    amt_str = w["text"]
                                else:
                                    amt_str += w["text"]
                        
                        typ_clean = typ_part.strip()
                        if typ_clean:
                            current_tx["description_parts"].append(typ_clean + ":")
                        if desc_parts:
                            current_tx["description_parts"].extend(desc_parts)
                        
                        # Parse amount
                        if amt_str:
                            try:
                                # Determine sign based on column alignment or description keyword
                                amt_words = [w for w in line_words if 380 <= w["x0"] < 500]
                                is_outflow = False
                                if amt_words:
                                    avg_x0 = sum([w["x0"] for w in amt_words]) / len(amt_words)
                                    if avg_x0 > 430:
                                        is_outflow = True
                                
                                # Fallback keyword check
                                desc_lower = " ".join(desc_parts).lower() + " " + typ_clean.lower()
                                if "buy" in desc_lower or "kauf" in desc_lower or "auszahlung" in desc_lower:
                                    is_outflow = True
                                elif "incoming" in desc_lower or "einzahlung" in desc_lower or "zinsen" in desc_lower or "interest" in desc_lower:
                                    is_outflow = False
                                    
                                clean_amt = amt_str.replace("€", "").replace(".", "").replace(",", ".").replace(" ", "").strip()
                                val = float(clean_amt)
                                if is_outflow:
                                    val = -abs(val)
                                else:
                                    val = abs(val)
                                current_tx["amount"] = val
                            except Exception:
                                pass
                                
                    # Case 2: Word is a Month (e.g. Sept., Okt.)
                    elif first_text.lower().replace(".", "")[:3] in month_map:
                        current_month = first_text
                        if current_tx:
                            current_tx["month"] = current_month
                            desc_parts = [w["text"] for w in line_words[1:] if 140 <= w["x0"] < 380]
                            if desc_parts:
                                current_tx["description_parts"].extend(desc_parts)
                                
                    # Case 3: Word is a Year (4 digits)
                    elif re.match(r'^\d{4}$', first_text):
                        current_year = first_text
                        if current_tx:
                            current_tx["year"] = current_year
                            desc_parts = [w["text"] for w in line_words[1:] if 140 <= w["x0"] < 380]
                            if desc_parts:
                                current_tx["description_parts"].extend(desc_parts)
                else:
                    # Description wrap
                    if current_tx:
                        desc_parts = [w["text"] for w in line_words if 140 <= w["x0"] < 380]
                        if desc_parts:
                            current_tx["description_parts"].extend(desc_parts)
                            
    # Finalize the last transaction of the document
    finalize_transaction(current_tx)
    
    return pd.DataFrame(rows)

def parse_pdf(file_path):
    # Detect bank type
    with pdfplumber.open(file_path) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        first_page_text_lower = first_page_text.lower()
        
    if "advanzia" in first_page_text_lower or "gebührenfrei" in first_page_text_lower:
        return parse_advanzia(file_path)
    elif "hdfc" in first_page_text_lower:
        return parse_hdfc(file_path)
    elif "commerzbank" in first_page_text_lower:
        return parse_commerzbank(file_path)
    elif "revolut" in first_page_text_lower or "revolt" in first_page_text_lower:
        return parse_revolut(file_path)
    elif "openbank" in first_page_text_lower or "amazon visa" in first_page_text_lower:
        return parse_openbank(file_path)
    elif "trade republic" in first_page_text_lower:
        return parse_trade_republic(file_path)
    else:
        # Fallback: try all and choose the one that extracts the most transactions
        df_openbank = parse_openbank(file_path)
        if len(df_openbank) > 0:
            return df_openbank
            
        df_tr = parse_trade_republic(file_path)
        if len(df_tr) > 0:
            return df_tr
            
        df_advanzia = parse_advanzia(file_path)
        if len(df_advanzia) > 0:
            return df_advanzia
            
        df_revolut = parse_revolut(file_path)
        if len(df_revolut) > 0:
            return df_revolut
            
        df_commerz = parse_commerzbank(file_path)
        df_hdfc = parse_hdfc(file_path)
        
        if len(df_commerz) >= len(df_hdfc):
            return df_commerz
        else:
            return df_hdfc

parse = parse_pdf
