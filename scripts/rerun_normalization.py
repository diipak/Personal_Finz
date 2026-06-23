"""
scripts/rerun_normalization.py

Full re-normalization pipeline:

1. Loads account_holder_name + aliases from settings table.
2. For every transaction in the DB:
   a. Runs transfer_classifier.classify_transfer() on the raw description.
   b. If transfer → sets transfer_subtype, sets normalized_merchant = '__TRANSFER_{SUBTYPE}__'
   c. If not transfer → runs merchant_normalizer.normalize_merchant_name()
      → if result is __BANKING_NOISE__ → sets transfer_subtype = 'BANKING_NOISE'
        (so it is filtered from merchant clusters but not confused with transfer events)
   d. Always sets normalized_pattern via normalize_pattern_name()
3. Rebuilds merchant_stats from scratch (DELETE + re-aggregate from transactions).

Safe to re-run repeatedly. Idempotent.
"""
import sqlite3
import sys
import os
import logging
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_PATH
from engine.transfer_classifier import classify_transfer, load_holder_settings
from engine.merchant_normalizer import (
    normalize_merchant_name,
    normalize_pattern_name,
    BANKING_NOISE_SENTINEL,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def rerun_normalization():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # ── 1. Load account holder settings ───────────────────────────────────────
    holder_name, aliases = load_holder_settings(conn)
    logger.info(f"Account holder: '{holder_name}' | Aliases: {aliases}")

    # ── 2. Fetch all transactions ──────────────────────────────────────────────
    c.execute("""
        SELECT transaction_id, description, amount
        FROM transactions
        ORDER BY transaction_id
    """)
    transactions = c.fetchall()
    logger.info(f"Processing {len(transactions)} transactions...")

    # Counters
    stats = defaultdict(int)

    updates = []
    for tx in transactions:
        raw = tx["description"] or ""
        amount = tx["amount"] or 0.0

        # ── a. Transfer classification ────────────────────────────────────────
        transfer_result = classify_transfer(raw, holder_name, aliases)

        if transfer_result:
            subtype = transfer_result.subtype
            normalized_merchant = f"__TRANSFER_{subtype}__"
            normalized_pattern = normalize_pattern_name(raw)
            transfer_subtype = subtype
            stats[f"transfer_{subtype}"] += 1
            stats["total_transfers"] += 1
        else:
            # ── b. Merchant normalization ─────────────────────────────────────
            normalized_merchant = normalize_merchant_name(raw)
            normalized_pattern = normalize_pattern_name(raw)

            if normalized_merchant == BANKING_NOISE_SENTINEL:
                transfer_subtype = "BANKING_NOISE"
                stats["banking_noise"] += 1
            else:
                transfer_subtype = None
                stats["merchants"] += 1

        updates.append((
            normalized_merchant,
            normalized_pattern,
            transfer_subtype,
            tx["transaction_id"],
        ))

    # ── 3. Batch-update transactions ──────────────────────────────────────────
    c.executemany(
        """
        UPDATE transactions
        SET normalized_merchant = ?,
            normalized_pattern  = ?,
            transfer_subtype    = ?
        WHERE transaction_id = ?
        """,
        updates,
    )
    conn.commit()
    logger.info(f"Updated {len(updates)} transaction rows.")

    # ── 4. Rebuild merchant_stats ──────────────────────────────────────────────
    logger.info("Rebuilding merchant_stats...")
    c.execute("DELETE FROM merchant_stats")

    c.execute("""
        SELECT
            normalized_merchant                AS merchant_key,
            normalized_merchant                AS parent_merchant,
            transfer_subtype,
            COUNT(*)                           AS transaction_count,
            SUM(amount)                        AS total_amount,
            AVG(amount)                        AS avg_amount,
            NULL                               AS known_category
        FROM transactions
        WHERE normalized_merchant IS NOT NULL
          AND normalized_merchant != ''
        GROUP BY normalized_merchant
    """)
    agg_rows = c.fetchall()

    c.executemany(
        """
        INSERT INTO merchant_stats (
            merchant_key, parent_merchant, transfer_subtype,
            transaction_count, total_amount, avg_amount, known_category
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                r["merchant_key"],
                r["parent_merchant"],
                r["transfer_subtype"],
                r["transaction_count"],
                round(r["total_amount"] or 0.0, 2),
                round(r["avg_amount"] or 0.0, 2),
                r["known_category"],
            )
            for r in agg_rows
        ],
    )
    conn.commit()
    logger.info(f"Rebuilt merchant_stats with {len(agg_rows)} distinct patterns.")

    # ── 5. Summary ─────────────────────────────────────────────────────────────
    logger.info("─" * 60)
    logger.info("NORMALIZATION SUMMARY")
    logger.info(f"  Total transactions     : {len(transactions)}")
    logger.info(f"  → Genuine merchants    : {stats['merchants']}")
    logger.info(f"  → Banking noise        : {stats['banking_noise']}")
    logger.info(f"  → Transfers (total)    : {stats['total_transfers']}")
    for subtype in [
        "SELF_TRANSFER", "CC_PAYMENT", "SAVINGS_TRANSFER",
        "CURRENCY_EXCHANGE", "HOUSEHOLD_TRANSFER", "EXTERNAL_TRANSFER",
    ]:
        count = stats.get(f"transfer_{subtype}", 0)
        if count:
            logger.info(f"      {subtype:<25}: {count}")
    logger.info("─" * 60)

    conn.close()
    logger.info("Done.")


if __name__ == "__main__":
    rerun_normalization()
