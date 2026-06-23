"""
engine/transfer_classifier.py

Transfer classification layer.
Runs BEFORE merchant normalization.
Returns a TransferResult(subtype, confidence) or None if not a transfer.

Subtypes (all stored under Category = "Transfer"):
    SELF_TRANSFER       — moving money between own accounts
    CC_PAYMENT          — credit card statement payment
    SAVINGS_TRANSFER    — deposit to savings/investment account
    CURRENCY_EXCHANGE   — Wise/Revolut FX conversion
    HOUSEHOLD_TRANSFER  — transfer to household member (future: known_persons table)
    EXTERNAL_TRANSFER   — transfer to any other external person/entity
"""
import re
import json
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Trigger words that mark a description as a money-movement event ──────────
TRANSFER_TRIGGERS = frozenset([
    "TRANSFER", "ÜBERWEISUNG", "SENT", "RECEIVED",
    "CC PAYMENT", "KARTENABRECHNUNG", "KREDITKARTENABRECHNUNG",
    "KREDITKARTE", "GELDAUSZAHLUNG", "EINZAHLUNG",
    "TOP UP", "TOPUP", "DAUERAUFTRAG",
])

# ─── Phrases that signal a CC/card statement payment ─────────────────────────
CC_PAYMENT_PHRASES = [
    r"\bCC\s+PAYMENT\b",
    r"\bKARTENABRECHNUNG\b",
    r"\bKREDITKARTENABRECHNUNG\b",
    r"\bKREDITKARTE\b",
    r"\bCARD\s+PAYMENT\b",
    r"\bCARD\s+BILL\b",
]

# ─── Savings / investment routing ─────────────────────────────────────────────
SAVINGS_PHRASES = [
    r"\bSAVINGS\b",
    r"\bTAGESGELD\b",
    r"\bFESTGELD\b",
    r"\bTRADE\s+REPUBLIC\b",
    r"\bSPARKONTO\b",
]

# ─── Currency exchange services ───────────────────────────────────────────────
FX_MERCHANTS = frozenset(["WISE", "REVOLUT", "CURRENCYFAIR", "TRANSFERWISE"])

# ─── Prepositions that introduce a person name ────────────────────────────────
PERSON_PREPOSITIONS = re.compile(
    r"\b(?:TO|FROM|AN|VON|NACH|BEI)\s+([A-Z][A-Z\s]{2,40})$",
    re.IGNORECASE
)


@dataclass
class TransferResult:
    subtype: str      # SELF_TRANSFER | CC_PAYMENT | SAVINGS_TRANSFER | CURRENCY_EXCHANGE | HOUSEHOLD_TRANSFER | EXTERNAL_TRANSFER
    confidence: float
    matched_signal: str  # human-readable debug label


def _upper(text: str) -> str:
    return text.upper().strip()


def _contains_any(text: str, patterns: list) -> bool:
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


def _is_transfer_trigger(text: str) -> bool:
    """Returns True if the description contains at least one transfer trigger word."""
    up = _upper(text)
    return any(t in up for t in TRANSFER_TRIGGERS)


def _contains_own_name(text: str, holder_name: str, aliases: list[str]) -> bool:
    """Returns True if the account holder's name or any alias appears in text."""
    up = _upper(text)
    names_to_check = [_upper(holder_name)] + [_upper(a) for a in aliases]
    return any(name in up for name in names_to_check if name)


def classify_transfer(
    raw_description: str,
    account_holder_name: str,
    account_holder_aliases: Optional[list] = None,
) -> Optional[TransferResult]:
    """
    Analyses a raw bank transaction description and returns a TransferResult
    if it represents an internal money-movement event, or None if it is a
    genuine merchant transaction.

    Args:
        raw_description:        Raw bank statement description string.
        account_holder_name:    Full name of account holder (e.g. "DEEPAK BATHAM").
        account_holder_aliases: Optional list of shorter aliases (e.g. ["DEEPAK"]).

    Returns:
        TransferResult or None.
    """
    if not raw_description:
        return None

    aliases = account_holder_aliases or []
    up = _upper(raw_description)

    # ── Rule 1: CC Payment ────────────────────────────────────────────────────
    # Any description mentioning a credit card statement payment phrase
    if _contains_any(up, CC_PAYMENT_PHRASES):
        return TransferResult(
            subtype="CC_PAYMENT",
            confidence=0.97,
            matched_signal="CC_PAYMENT_PHRASE"
        )

    # ── Rule 2: Only proceed if a transfer trigger is present ─────────────────
    if not _is_transfer_trigger(up):
        return None

    # ── Rule 3: Savings / investment transfer ─────────────────────────────────
    if _contains_any(up, SAVINGS_PHRASES):
        return TransferResult(
            subtype="SAVINGS_TRANSFER",
            confidence=0.92,
            matched_signal="SAVINGS_PHRASE"
        )

    # ── Rule 4: Currency exchange (Wise, Revolut in FX context) ───────────────
    # Wise transfers are always cross-currency; treat as CURRENCY_EXCHANGE
    # Revolut top-ups are SELF_TRANSFER unless FX is clearly involved
    if any(fx in up for fx in FX_MERCHANTS):
        # If own name is also present → self-transfer via FX service
        if _contains_own_name(up, account_holder_name, aliases):
            return TransferResult(
                subtype="CURRENCY_EXCHANGE",
                confidence=0.90,
                matched_signal="FX_MERCHANT_OWN_NAME"
            )
        # Otherwise it might be sending to someone else via Wise
        # Fall through to person-detection rules below

    # ── Rule 5: Own-name transfers (SELF_TRANSFER) ────────────────────────────
    if _contains_own_name(up, account_holder_name, aliases):
        return TransferResult(
            subtype="SELF_TRANSFER",
            confidence=0.95,
            matched_signal="OWN_NAME_IN_TRANSFER"
        )

    # ── Rule 6: Transfer to/from a named person (EXTERNAL_TRANSFER) ──────────
    # Pattern: TRANSFER TO [PERSON NAME] or FROM [PERSON NAME]
    person_match = PERSON_PREPOSITIONS.search(up)
    if person_match:
        person_name = person_match.group(1).strip()
        # Guard: must be at least 2 tokens and not a bank/institution
        tokens = person_name.split()
        if len(tokens) >= 2:
            # NOTE: HOUSEHOLD_TRANSFER classification is reserved for future
            # known_persons table lookup. For now, all non-own-name persons = EXTERNAL.
            return TransferResult(
                subtype="EXTERNAL_TRANSFER",
                confidence=0.80,
                matched_signal=f"PERSON_NAME:{person_name}"
            )

    # ── Rule 7: Generic money-movement with no further context ────────────────
    # Contains a trigger but no person name and no own name
    # Examples: "EINZAHLUNG AUF KARTE", "TOP UP BY", "GELDAUSZAHLUNG VON KARTE AUF"
    # These are banking mechanics — classify as SELF_TRANSFER (own-account ops)
    GENERIC_SELF_TRIGGERS = frozenset([
        "EINZAHLUNG", "GELDAUSZAHLUNG", "TOP UP", "TOPUP",
        "CASH DEPOSIT", "BARGELDAUSZAHLUNG",
    ])
    if any(t in up for t in GENERIC_SELF_TRIGGERS):
        return TransferResult(
            subtype="SELF_TRANSFER",
            confidence=0.75,
            matched_signal="GENERIC_SELF_TRIGGER"
        )

    # ── Rule 8: SENT FROM REVOLUT / received from known service ───────────────
    # "SENT FROM REVOLUT TO ..." with no own name → EXTERNAL_TRANSFER
    if "SENT" in up or "RECEIVED" in up:
        return TransferResult(
            subtype="EXTERNAL_TRANSFER",
            confidence=0.70,
            matched_signal="SENT_RECEIVED_NO_PERSON"
        )

    # Transfer trigger present but subtype indeterminate → EXTERNAL_TRANSFER fallback
    return TransferResult(
        subtype="EXTERNAL_TRANSFER",
        confidence=0.55,
        matched_signal="TRANSFER_TRIGGER_FALLBACK"
    )


def load_holder_settings(db_conn) -> tuple[str, list]:
    """
    Reads account_holder_name and account_holder_aliases from the settings table.
    Returns (holder_name, aliases_list).
    """
    c = db_conn.cursor()
    c.execute("SELECT key, value FROM settings WHERE key IN ('account_holder_name', 'account_holder_aliases')")
    rows = {r["key"]: r["value"] for r in c.fetchall()}

    holder_name = rows.get("account_holder_name", "")
    aliases_raw = rows.get("account_holder_aliases", "[]")
    try:
        aliases = json.loads(aliases_raw)
    except Exception:
        aliases = []
    return holder_name, aliases
