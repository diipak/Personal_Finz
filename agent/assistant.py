import os
import sys
import requests
import json
import logging

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import OLLAMA_URL, LLM_MODEL
from db.database import get_db
from api.services.analytics import get_health_metrics, get_financial_summary

logger = logging.getLogger(__name__)

def build_context() -> str:
    """Builds a plain-text context summarizing financial state for the LLM."""
    metrics = get_health_metrics()
    summary = get_financial_summary()
    
    conn = get_db()
    cursor = conn.cursor()
    
    recent_txns = []
    try:
        # Get last 20 settled transactions
        cursor.execute(
            "SELECT date, description, display_name, amount, currency, account, category, flexibility FROM transactions WHERE status = 'SETTLED' ORDER BY date DESC, id DESC LIMIT 20"
        )
        for row in cursor.fetchall():
            recent_txns.append(
                f"{row['date']} | {row['display_name'] or row['description']} | {row['amount']} {row['currency']} | {row['account']} | {row['category']} | {row['flexibility']}"
            )
    except Exception as e:
        logger.error(f"Error fetching recent txns for assistant: {e}")
    finally:
        conn.close()
        
    context = []
    context.append("### FINANCIAL SUMMARY & HEALTH METRICS")
    context.append(f"Net Worth (Cash Reserves): {metrics.get('cash_reserves_eur', 0.0):.2f} EUR")
    context.append(f"Average Monthly Essential Expenses (Fixed+Flexible): {metrics.get('avg_monthly_essential_eur', 0.0):.2f} EUR")
    context.append(f"Liquidity Runway: {metrics.get('runway_months', 0.0)} months")
    context.append(f"Savings Rate (Last 90 Days): {metrics.get('savings_rate_percent', 0.0)}%")
    context.append(f"FIRE Target Capital: {metrics.get('fire_target_eur', 0.0):.2f} EUR (Current Progress: {metrics.get('fire_progress_percent', 0.0)}%)")
    context.append("")
    
    context.append("### SPENDING BY CATEGORY (ALL TIME)")
    for cat in summary.get("category_breakdown", []):
        context.append(f"- {cat['category']}: {cat['amount']:.2f} EUR")
    context.append("")
    
    context.append("### SPENDING BY FLEXIBILITY LAYER")
    flex = summary.get("flexibility_breakdown", {})
    context.append(f"- Fixed (Structural Needs): {flex.get('Fixed', 0.0):.2f} EUR")
    context.append(f"- Flexible (Variable Needs): {flex.get('Flexible', 0.0):.2f} EUR")
    context.append(f"- Discretionary (Lifestyle Wants): {flex.get('Discretionary', 0.0):.2f} EUR")
    context.append("")
    
    context.append("### RECENT TRANSACTIONS (Date | Merchant | Amount | Account | Category | Flexibility)")
    context.extend(recent_txns)
    
    return "\n".join(context)

def ask_assistant(question: str) -> str:
    """Sends financial context + natural language query to the local Ollama LLM."""
    context = build_context()
    
    prompt = f"""You are a helpful, private personal finance advisor.
Here is the user's current financial database context:

{context}

Question: {question}

Provide a concise, clear, and action-oriented response. Refer directly to the numbers in the context when answering. Do not speculate or make up transactions. If you do not find the answer, state that the database context does not contain enough information."""

    try:
        url = f"{OLLAMA_URL}/api/generate"
        res = requests.post(
            url,
            json={
                "model": LLM_MODEL,
                "prompt": prompt,
                "stream": False
            },
            timeout=30
        )
        res.raise_for_status()
        return res.json().get("response", "").strip()
    except Exception as e:
        logger.error(f"Ollama assistant error: {e}")
        return f"Sorry, I encountered an error communicating with the local AI model: {e}"
