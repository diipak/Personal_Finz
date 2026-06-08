import os
import sys
import tempfile
import sqlite3
import hashlib
import unittest

# Setup temporary DB path in environment before importing modules
temp_db_fd, temp_db_path = tempfile.mkstemp(suffix=".db")
os.environ["DB_PATH"] = temp_db_path

# Add project root to sys.path dynamically
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from db.database import init_db, get_db, clear_pending_transactions, upsert_api_transaction, upsert_manual_transaction
from engine.rules import match_rule, apply_rules_to_unpinned_transactions
from api.services.analytics import get_financial_summary, get_health_metrics

class TestPersonalFinzCore(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM transactions")
        cursor.execute("DELETE FROM rules")
        cursor.execute("DELETE FROM sync_logs")
        cursor.execute("DELETE FROM sync_history")
        cursor.execute("DELETE FROM linked_accounts")
        cursor.execute("DELETE FROM settings")
        cursor.execute("INSERT INTO settings (key, value) VALUES ('auto_sync_enabled', 'true')")
        conn.commit()
        conn.close()

    def tearDown(self):
        pass

    @classmethod
    def tearDownClass(cls):
        os.close(temp_db_fd)
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)

    def test_pending_wipe(self):
        """Verify that clearing pending transactions removes only PENDING items for that account."""
        conn = get_db()
        
        upsert_api_transaction(conn, {
            "date": "2026-06-01",
            "description": "Settled Tx",
            "amount": -10.0,
            "currency": "EUR",
            "account": "Revolut A",
            "type": "Expense",
            "status": "SETTLED",
            "external_sync_id": "tx-settled-1"
        })
        
        upsert_api_transaction(conn, {
            "date": "2026-06-02",
            "description": "Pending Tx",
            "amount": -20.0,
            "currency": "EUR",
            "account": "Revolut A",
            "type": "Expense",
            "status": "PENDING",
            "external_sync_id": "tx-pending-1"
        })
        
        upsert_api_transaction(conn, {
            "date": "2026-06-02",
            "description": "Pending Tx B",
            "amount": -30.0,
            "currency": "EUR",
            "account": "Revolut B",
            "type": "Expense",
            "status": "PENDING",
            "external_sync_id": "tx-pending-2"
        })
        
        clear_pending_transactions(conn, "Revolut A")
        
        cursor = conn.cursor()
        cursor.execute("SELECT id, status, account FROM transactions")
        rows = cursor.fetchall()
        
        self.assertEqual(len(rows), 2)
        
        accounts_status = {(r["account"], r["status"]) for r in rows}
        self.assertIn(("Revolut A", "SETTLED"), accounts_status)
        self.assertIn(("Revolut B", "PENDING"), accounts_status)
        self.assertNotIn(("Revolut A", "PENDING"), accounts_status)
        conn.close()

    def test_enable_banking_deterministic_id_fallback(self):
        """Verify that when external_sync_id is missing, a fallback hash is generated deterministically."""
        date_val = "2026-06-03"
        amount_val = 15.50
        remit = "Lunch"
        
        raw_str = f"{date_val}_{amount_val}_{remit}"
        expected_hash = "gcl_fallback_" + hashlib.sha256(raw_str.encode()).hexdigest()[:16]
        
        conn = get_db()
        txn = {
            "date": date_val,
            "description": remit,
            "amount": amount_val,
            "currency": "EUR",
            "account": "Revolut A",
            "type": "Income",
            "status": "SETTLED",
            "external_sync_id": expected_hash
        }
        
        self.assertTrue(upsert_api_transaction(conn, txn))
        self.assertTrue(upsert_api_transaction(conn, txn))
        
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM transactions WHERE external_sync_id = ?", (expected_hash,))
        self.assertEqual(cursor.fetchone()["cnt"], 1)
        conn.close()

    def test_enable_banking_jwt_generation(self):
        """Verify that EnableBankingClient correctly generates RS256 JWT auth headers."""
        from parsers.enable_banking_sync import EnableBankingClient
        client = EnableBankingClient(app_id="test-app-id")
        headers = client.get_headers()
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("Bearer "))
        token = headers["Authorization"].split(" ")[1]
        
        import jwt
        decoded = jwt.decode(token, options={"verify_signature": False})
        self.assertEqual(decoded["iss"], "enablebanking.com")
        self.assertEqual(decoded["aud"], "api.enablebanking.com")
        self.assertIn("iat", decoded)
        self.assertIn("exp", decoded)
        
        unverified_header = jwt.get_unverified_header(token)
        self.assertEqual(unverified_header["alg"], "RS256")
        self.assertEqual(unverified_header["typ"], "JWT")
        self.assertEqual(unverified_header["kid"], "test-app-id")

    def test_enable_banking_sync_mapping(self):
        """Verify that sync_account_transactions correctly maps raw API response to database schema."""
        from unittest.mock import patch
        from parsers.enable_banking_sync import sync_account_transactions
        
        mock_raw_txns = [
            {
                "transactionId": "tx-123",
                "bookingDate": "2026-06-05T12:00:00Z",
                "transactionAmount": {
                    "amount": "-50.00",
                    "currency": "EUR"
                },
                "remittanceInformationUnstructured": "Groceries Store",
                "status": "BOOKED"
            },
            {
                "entryReference": "entry-456",
                "valueDate": "2026-06-06",
                "transactionAmount": {
                    "amount": "100.50",
                    "currency": "EUR"
                },
                "description": "Salary payment",
                "status": "PENDING"
            },
            {
                "bookingDate": "2026-06-07",
                "transactionAmount": {
                    "amount": "-15.20",
                    "currency": "EUR"
                },
                "remittanceInformation": "Coffee shop",
                "status": "PDNG"
            }
        ]
        
        with patch("parsers.enable_banking_sync.EnableBankingClient.get_transactions") as mock_get:
            mock_get.return_value = mock_raw_txns
            
            normalized = sync_account_transactions("acc-999", "Mock Bank Account")
            
            self.assertEqual(len(normalized), 3)
            
            # Tx 1
            self.assertEqual(normalized[0]["external_sync_id"], "tx-123")
            self.assertEqual(normalized[0]["date"], "2026-06-05")
            self.assertEqual(normalized[0]["description"], "Groceries Store")
            self.assertEqual(normalized[0]["amount"], -50.0)
            self.assertEqual(normalized[0]["status"], "SETTLED")
            self.assertEqual(normalized[0]["account"], "Mock Bank Account")
            
            # Tx 2
            self.assertEqual(normalized[1]["external_sync_id"], "entry-456")
            self.assertEqual(normalized[1]["date"], "2026-06-06")
            self.assertEqual(normalized[1]["description"], "Salary payment")
            self.assertEqual(normalized[1]["amount"], 100.5)
            self.assertEqual(normalized[1]["status"], "PENDING")
            self.assertEqual(normalized[1]["type"], "Income")
            
            # Tx 3 (fallback ID)
            expected_raw = "2026-06-07_-15.2_Coffee shop"
            expected_fallback = "gcl_fallback_" + hashlib.sha256(expected_raw.encode()).hexdigest()[:16]
            self.assertEqual(normalized[2]["external_sync_id"], expected_fallback)
            self.assertEqual(normalized[2]["date"], "2026-06-07")
            self.assertEqual(normalized[2]["amount"], -15.2)
            self.assertEqual(normalized[2]["status"], "PENDING")

    def test_rules_propagation(self):
        """Verify that rule propagation applies only to unpinned (is_pinned=0) guess/uncategorized transactions."""
        conn = get_db()
        
        # 1. Insert unpinned guess transactions
        upsert_manual_transaction(conn, {
            "date": "2026-06-01",
            "description": "AMAZON CO UK DEALS",
            "amount": -54.20,
            "currency": "EUR",
            "account": "HDFC",
            "type": "Expense",
            "category": "Other",
            "flexibility": "Flexible",
            "is_guess": 1,
            "hash": "hash-1"
        })
        
        # 2. Insert guess transaction that we will explicitly PIN (is_pinned = 1)
        upsert_manual_transaction(conn, {
            "date": "2026-06-02",
            "description": "AMAZON SELLER SVCS",
            "amount": -22.10,
            "currency": "EUR",
            "account": "HDFC",
            "type": "Expense",
            "category": "Other",
            "flexibility": "Flexible",
            "is_guess": 1,
            "hash": "hash-2"
        })
        
        # Manually force pin the second transaction to simulate user review
        cursor = conn.cursor()
        cursor.execute("UPDATE transactions SET is_pinned = 1 WHERE description = 'AMAZON SELLER SVCS'")
        
        # 3. Create a matching rule for Amazon -> Shopping/Flexible
        cursor.execute(
            """
            INSERT INTO rules (pattern, match_type, category, display_name, flexibility)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("amazon", "substring", "Shopping", "Amazon UK", "Flexible")
        )
        conn.commit()
        conn.close()
        
        # 4. Trigger rules propagation sweep
        updated = apply_rules_to_unpinned_transactions()
        self.assertEqual(updated, 1) # Only the unpinned Amazon transaction should be updated
        
        # 5. Verify results
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT description, category, display_name, is_guess, is_pinned FROM transactions ORDER BY date ASC")
        rows = cursor.fetchall()
        
        # Row 1 (unpinned) should be updated to Shopping
        self.assertEqual(rows[0]["description"], "AMAZON CO UK DEALS")
        self.assertEqual(rows[0]["category"], "Shopping")
        self.assertEqual(rows[0]["display_name"], "Amazon UK")
        self.assertEqual(rows[0]["is_guess"], 0)
        self.assertEqual(rows[0]["is_pinned"], 0)
        
        # Row 2 (pinned) should remain unchanged
        self.assertEqual(rows[1]["description"], "AMAZON SELLER SVCS")
        self.assertEqual(rows[1]["category"], "Other")
        self.assertEqual(rows[1]["is_guess"], 1)
        self.assertEqual(rows[1]["is_pinned"], 1)
        conn.close()

    def test_multi_currency_exchange_rates(self):
        """Verify that multi-currency analytics correctly aggregates HDFC INR transactions using EUR_INR_RATE."""
        conn = get_db()
        
        # Insert a EUR transaction
        upsert_manual_transaction(conn, {
            "date": "2026-06-01",
            "description": "EUR Expense",
            "amount": -100.0,
            "currency": "EUR",
            "account": "Revolut Main",
            "type": "Expense",
            "category": "Rent",
            "flexibility": "Fixed",
            "hash": "hash-eur"
        })
        
        # Insert an INR transaction: -9000.0 INR. With exchange rate 90.0, this should equal -100.0 EUR
        upsert_manual_transaction(conn, {
            "date": "2026-06-01",
            "description": "INR Expense",
            "amount": -9000.0,
            "currency": "INR",
            "account": "HDFC Account",
            "type": "Expense",
            "category": "Utilities",
            "flexibility": "Fixed",
            "hash": "hash-inr"
        })
        
        # Insert an Income transaction: 450.0 EUR
        upsert_manual_transaction(conn, {
            "date": "2026-06-01",
            "description": "Salary",
            "amount": 450.0,
            "currency": "EUR",
            "account": "Revolut Main",
            "type": "Income",
            "category": "Income",
            "flexibility": "Flexible",
            "hash": "hash-salary"
        })
        
        conn.close()
        
        # Get financial summary (which computes aggregates)
        summary = get_financial_summary()
        
        # Total Expenses: 100 EUR + (9000 INR / 90.0) = 200.0 EUR
        # Total Income: 450.0 EUR
        
        self.assertAlmostEqual(summary["total_expenses_eur"], 200.0, places=2)
        self.assertAlmostEqual(summary["total_income_eur"], 450.0, places=2)
        
        # Get health metrics to verify Savings Rate (90d)
        health = get_health_metrics()
        # Savings Rate: (1.0 - (200.0 / 450.0)) * 100.0 = 55.56%
        self.assertAlmostEqual(health["savings_rate_percent"], 55.56, places=2)

    def test_settings_endpoints(self):
        """Verify that GET /api/settings/auto-sync and POST /api/settings/auto-sync function correctly."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        # 1. Get default setting (should be enabled=True since we seed it)
        resp = client.get("/api/settings/auto-sync")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"enabled": True})

        # 2. Disable setting
        resp = client.post("/api/settings/auto-sync", json={"enabled": False})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "success", "enabled": False})

        # 3. Get setting again to confirm update
        resp = client.get("/api/settings/auto-sync")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"enabled": False})

    def test_auto_sync_due_accounts_selection(self):
        """Verify that the background scheduler query correctly identifies accounts due for auto-sync."""
        conn = get_db()
        cursor = conn.cursor()

        # Insert bank accounts with different sync times
        # 1. Never synced (last_synced_at IS NULL) -> should be due
        cursor.execute(
            "INSERT INTO linked_accounts (resource_id, institution_id, display_name, currency) VALUES (?, ?, ?, ?)",
            ("acc-never", "MockBank", "Never Synced Account", "EUR")
        )
        # 2. Synced 25 hours ago -> should be due
        cursor.execute(
            """
            INSERT INTO linked_accounts (resource_id, institution_id, display_name, currency, last_synced_at) 
            VALUES (?, ?, ?, ?, datetime('now', '-25 hours'))
            """,
            ("acc-due", "MockBank", "Due Account", "EUR")
        )
        # 3. Synced 2 hours ago -> should NOT be due
        cursor.execute(
            """
            INSERT INTO linked_accounts (resource_id, institution_id, display_name, currency, last_synced_at) 
            VALUES (?, ?, ?, ?, datetime('now', '-2 hours'))
            """,
            ("acc-fresh", "MockBank", "Fresh Account", "EUR")
        )
        conn.commit()

        # Run query used in scheduler loop
        cursor.execute(
            """
            SELECT resource_id FROM linked_accounts 
            WHERE last_synced_at IS NULL 
               OR datetime(last_synced_at) <= datetime('now', '-24 hours')
            """
        )
        due_ids = [row["resource_id"] for row in cursor.fetchall()]
        conn.close()

        self.assertIn("acc-never", due_ids)
        self.assertIn("acc-due", due_ids)
        self.assertNotIn("acc-fresh", due_ids)
        self.assertEqual(len(due_ids), 2)

if __name__ == "__main__":
    unittest.main()

