import os
import sys
import logging
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import EUR_INR_RATE
from db.database import get_db

logger = logging.getLogger(__name__)

def get_normalized_sum(cursor, where_clause: str, params: tuple = ()) -> float:
    """Helper to get SUM(amount) normalized to EUR, using EUR_INR_RATE for INR transactions."""
    query = f"""
        SELECT 
            SUM(CASE WHEN currency = 'INR' THEN amount / {EUR_INR_RATE} ELSE amount END) as total
        FROM transactions
        WHERE {where_clause}
    """
    cursor.execute(query, params)
    res = cursor.fetchone()
    return float(res["total"] or 0.0)

def get_financial_summary() -> dict:
    """
    Computes overall balance, spending trends, and category breakdown.
    All outputs normalized to EUR.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Total Net Worth (Cash Balance)
        total_balance = get_normalized_sum(cursor, "is_ignored = 0 AND status = 'SETTLED'")
        
        # Total Income (all time)
        total_income = get_normalized_sum(cursor, "type = 'Income' AND is_ignored = 0 AND status = 'SETTLED'")
        
        # Total Expenses (all time)
        total_expenses = abs(get_normalized_sum(cursor, "type = 'Expense' AND is_ignored = 0 AND status = 'SETTLED'"))
        
        # Category Breakdown
        cursor.execute(
            f"""
            SELECT 
                category,
                SUM(CASE WHEN currency = 'INR' THEN amount / {EUR_INR_RATE} ELSE amount END) as total
            FROM transactions
            WHERE type = 'Expense' AND is_ignored = 0 AND status = 'SETTLED'
            GROUP BY category
            ORDER BY total ASC
            """
        )
        categories = [{"category": row["category"] or "Uncategorized", "amount": abs(float(row["total"]))} for row in cursor.fetchall()]
        
        # Flexibility Breakdown
        cursor.execute(
            f"""
            SELECT 
                flexibility,
                SUM(CASE WHEN currency = 'INR' THEN amount / {EUR_INR_RATE} ELSE amount END) as total
            FROM transactions
            WHERE type = 'Expense' AND is_ignored = 0 AND status = 'SETTLED'
            GROUP BY flexibility
            """
        )
        flexibility = {row["flexibility"]: abs(float(row["total"])) for row in cursor.fetchall()}
        
        return {
            "total_balance_eur": total_balance,
            "total_income_eur": total_income,
            "total_expenses_eur": total_expenses,
            "category_breakdown": categories,
            "flexibility_breakdown": {
                "Fixed": flexibility.get("Fixed", 0.0),
                "Flexible": flexibility.get("Flexible", 0.0),
                "Discretionary": flexibility.get("Discretionary", 0.0)
            }
        }
    except Exception as e:
        logger.error(f"Error compiling financial summary: {e}")
        return {}
    finally:
        conn.close()

def get_health_metrics() -> dict:
    """
    Calculates Liquidity Runway, Savings Rate, and FIRE targets.
    All outputs normalized to EUR.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Get net cash balance
        cash_reserves = get_normalized_sum(cursor, "is_ignored = 0 AND status = 'SETTLED'")
        
        # Calculate average monthly Fixed + Flexible expenses over last 3 months (90 days)
        # Find date 90 days ago
        cursor.execute("SELECT date('now', '-90 days') as cut_date")
        cut_date = cursor.fetchone()["cut_date"]
        
        # Monthly fixed + flexible expense average
        fixed_flex_sum = abs(get_normalized_sum(
            cursor, 
            "type = 'Expense' AND flexibility IN ('Fixed', 'Flexible') AND date >= ? AND is_ignored = 0 AND status = 'SETTLED'",
            (cut_date,)
        ))
        avg_monthly_essential = fixed_flex_sum / 3.0 if fixed_flex_sum > 0 else 0.0
        
        # Liquidity Runway in months
        runway_months = cash_reserves / avg_monthly_essential if avg_monthly_essential > 0 else 999.0
        
        # Savings Rate in the last 90 days
        income_90d = get_normalized_sum(cursor, "type = 'Income' AND date >= ? AND is_ignored = 0 AND status = 'SETTLED'", (cut_date,))
        expense_90d = abs(get_normalized_sum(cursor, "type = 'Expense' AND date >= ? AND is_ignored = 0 AND status = 'SETTLED'", (cut_date,)))
        savings_rate = (1.0 - (expense_90d / income_90d)) * 100.0 if income_90d > 0 else 0.0
        
        # FIRE Targets (based on average monthly expenses of all types in last 90 days)
        total_exp_90d = abs(get_normalized_sum(cursor, "type = 'Expense' AND date >= ? AND is_ignored = 0 AND status = 'SETTLED'", (cut_date,)))
        avg_monthly_exp = total_exp_90d / 3.0
        annual_exp = avg_monthly_exp * 12.0
        
        # FIRE Target (25x annual expenses)
        fire_target = annual_exp * 25.0
        
        return {
            "cash_reserves_eur": cash_reserves,
            "avg_monthly_essential_eur": avg_monthly_essential,
            "runway_months": round(runway_months, 2),
            "savings_rate_percent": round(savings_rate, 2),
            "avg_monthly_expense_eur": round(avg_monthly_exp, 2),
            "annual_expense_eur": round(annual_exp, 2),
            "fire_target_eur": round(fire_target, 2),
            "fire_progress_percent": round((cash_reserves / fire_target * 100.0), 2) if fire_target > 0 else 0.0
        }
    except Exception as e:
        logger.error(f"Error calculating health metrics: {e}")
        return {}
    finally:
        conn.close()
