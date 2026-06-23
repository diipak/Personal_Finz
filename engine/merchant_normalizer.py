"""
engine/merchant_normalizer.py

Two public functions:
    normalize_merchant_name(description)  → parent merchant cluster key  (e.g. "NETFLIX", "__BANKING_NOISE__")
    normalize_pattern_name(description)   → detailed behavioral pattern   (e.g. "PAYPAL NETFLIX")

Rules:
- Returns "__BANKING_NOISE__" when the description resolves to a pure banking
  process word (TRANSFER, PAYMENT, FROM, etc.) with no real merchant identity.
- Transfer classification is the responsibility of transfer_classifier.py,
  not this module. This module only strips and normalises.
"""
import re

# ─── Legal entity suffixes ────────────────────────────────────────────────────
LEGAL_SUFFIXES = [
    r"\bGMBH\b", r"\bSARL\b", r"\bLTD\b", r"\bINC\b", r"\bKG\b",
    r"\bCO\b", r"\bCORP\b", r"\bLLC\b", r"\bS\.A\.?\b", r"\bS\.A\.R\.L\.?\b",
    r"\bS\.E\.?\b", r"\bAG\b", r"\bPLC\b", r"\bKGAA\b", r"\bGBR\b",
    r"\bE\.V\.\b", r"\bAB\b", r"\bINTL\b", r"\bINTERNATIONAL\b",
    r"\bLIMITADA\b", r"\bCO\s+KG\b", r"\bOHG\b", r"\bUAB\b",
]

# ─── Payment processor prefixes / gateway noise ───────────────────────────────
PAYMENT_NOISE = [
    r"\bPAYPAL\b\s*\*?", r"\bSUMUP\b\s*\*?", r"\bSTRIPE\b\s*\*?",
    r"\bIZETTLE\b\s*\*?", r"\bGOPAY\b\s*\*?", r"\bPAYME\b\s*\*?",
    r"\bVISA\b", r"\bMASTERCARD\b", r"\bMC\b",
    r"\bSEPA\b", r"\bPOS\b", r"\bTERMINAL\b", r"\bDIRECT\s+DEBIT\b",
    r"\bKARTENZAHLUNG\b",
]

# ─── Abbreviation expansions ──────────────────────────────────────────────────
ABBREVIATION_MAP = {
    r"\bAMZN\b": "AMAZON",
    r"\bNFLX\b": "NETFLIX",
    r"\bSPTF\b": "SPOTIFY",
    r"\bMSFT\b": "MICROSOFT",
    r"\bGOOG\b": "GOOGLE",
    r"\bMKT\b":  "MARKETPLACE",
    r"\bSQSP\b": "SQUARESPACE",
    r"\bYT\b":   "YOUTUBE",
}

# ─── BANKING STOPLIST ─────────────────────────────────────────────────────────
# If the normalised cluster name resolves to one of these words/phrases,
# the description is a banking process event, NOT a merchant transaction.
# The caller should treat "__BANKING_NOISE__" as a sentinel and skip clustering.
#
# Guiding principle: these are VERBS, PREPOSITIONS, or INFRASTRUCTURE terms
# that describe HOW money moved — never WHERE it was spent.
BANKING_STOPLIST: frozenset = frozenset({
    # ── English motion verbs ──────────────────────────────────────────────────
    "transfer", "transfers",
    "payment", "payments", "pay",
    "sent", "send", "received", "receive",
    "credit", "debit",
    "charge", "charged",
    "refund", "return", "reversal",
    "deposit", "withdrawal",
    "top up", "topup",
    "cash",

    # ── Prepositions / linking words ──────────────────────────────────────────
    "from", "to", "an",                # "FROM NAVEEN", "TO POOJA"

    # ── German banking verbs ──────────────────────────────────────────────────
    "einzahlung",       # deposit
    "auszahlung",       # withdrawal
    "geldauszahlung",   # cash withdrawal
    "überweisung",      # wire transfer
    "lastschrift",      # direct debit
    "gutschrift",       # credit entry
    "sollzinsen",       # debit interest
    "standardzinsen",   # standard interest
    "zinsen",           # interest
    "entgelt",          # fee/charge
    "kartenabrechnung", # card statement
    "rechnungsnr",      # invoice number
    "kdnr",             # customer number
    "kontoführung",     # account management

    # ── German noise fragments ────────────────────────────────────────────────
    "eingel",           # truncation of "eingeleitet"
    "mein",             # "mein" = my (e.g. "MEIN HVV")
    "ihre",             # "ihre" = your
    "ste",              # artifact

    # ── Banking infrastructure words ─────────────────────────────────────────
    "sepa", "bic", "iban",
    "direct debit", "standing order",
    "dauerauftrag",

    # ── Ambiguous single words that collapse real clusters ───────────────────
    "open",             # "OPEN BANKING", "OPEN BANK"
    "plus",             # "PLUS PLAN FEE", "EUROPLUS"
    "card",             # "CARD PAYMENT"
})

# Sentinel value returned when a description resolves to banking noise
BANKING_NOISE_SENTINEL = "__BANKING_NOISE__"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def clean_common_noise(text: str) -> str:
    """Strips card numbers, dates, reference codes, URL extensions, location codes."""
    text = text.upper().strip()

    # URL extensions
    text = re.sub(r"\b\w+\.(COM|DE|ORG|NET|IO|CO\.UK|IN|FR|IT|ES|EU)\b", " ", text)
    text = re.sub(r"\.COM\b|\.DE\b|\.ORG\b|\.NET\b", " ", text)

    # Masked card details
    text = re.sub(r"\bCARD\b\s*[\d*X-]{4,}", " ", text)
    text = re.sub(r"\bCARD\s+\d{4}\b", " ", text)
    text = re.sub(r"[\d*X-]{12,19}", " ", text)
    text = re.sub(r"\bX{2,}\d*\b", " ", text)

    # Dates
    text = re.sub(r"\b\d{2}[-./]\d{2}[-./]\d{2,4}\b", " ", text)
    text = re.sub(r"\b\d{4}[-./]\d{2}[-./]\d{2}\b", " ", text)
    text = re.sub(r"\b\d{2}[-./]\d{2}\b", " ", text)

    # Reference / order codes
    text = re.sub(r"#\w+", " ", text)
    text = re.sub(r"\b(REF|INV|ID|INVOICE|ORDER|NO)[:\s]*\w+", " ", text)

    # German owner prefix
    text = re.sub(r"\bINH\b\.?", " ", text)

    # Country/state noise
    for loc in [r"\bDE\b", r"\bUS\b", r"\bUK\b", r"\bFR\b", r"\bCA\b",
                r"\bIN\b", r"\bEU\b", r"\bIE\b"]:
        text = re.sub(loc, " ", text)

    # Numeric / alphanumeric artifact codes
    text = re.sub(r"\b\w*\d+\w*\b", " ", text)

    # Expand abbreviations
    for abbr, expanded in ABBREVIATION_MAP.items():
        text = re.sub(abbr, expanded, text)

    return text


def _is_banking_noise(cluster_name: str) -> bool:
    """
    Returns True when the proposed cluster name is a banking process word,
    not a merchant identity.
    Checks single words AND multi-word phrases against BANKING_STOPLIST.
    """
    name = cluster_name.lower().strip()
    if name in BANKING_STOPLIST:
        return True
    # Also check each individual word — single-word resolutions like "FROM"
    for token in name.split():
        if token in BANKING_STOPLIST:
            return True
    return False


# ─── Public API ───────────────────────────────────────────────────────────────

def normalize_merchant_name(description: str) -> str:
    """
    Returns the base merchant cluster key for grouping.

    Special return values:
        "__BANKING_NOISE__"  — description is a banking process event, not a merchant
        "UNKNOWN"            — description could not be resolved to anything meaningful

    Caller should:
        - Skip "__BANKING_NOISE__" entries when building merchant clusters.
        - Route to transfer_classifier.py BEFORE calling this function for
          proper transfer subtype assignment.
    """
    if not description:
        return "UNKNOWN"

    text = clean_common_noise(description)

    # Strip payment processor prefixes
    for pat in PAYMENT_NOISE:
        text = re.sub(pat, " ", text)

    # Strip legal suffixes
    for pat in LEGAL_SUFFIXES:
        text = re.sub(pat, " ", text)

    # Replace non-alphanumeric (keep &)
    text = re.sub(r"[^A-Z0-9\s&]", " ", text)
    text = " ".join(text.split()).strip()

    # Fallback if empty
    if not text:
        text = " ".join(re.sub(r"[^A-Z\s]", " ", description.upper()).split()).strip()

    # Extract primary identifier (first 1-2 words)
    words = text.split()
    if not words:
        return "UNKNOWN"

    # Short leading tokens (≤3 chars) or known short-name merchants → take 2 words
    SHORT_BRANDS = {"H&M", "C&A", "OBI", "DM", "IKEA", "KFC", "TGI", "FIT"}
    if len(words[0]) <= 3 or words[0] in SHORT_BRANDS:
        base = " ".join(words[:2]) if len(words) >= 2 else words[0]
    else:
        base = words[0]

    # Alias normalisation
    ALIASES = {
        "AMZN": "AMAZON", "AMAZONCOM": "AMAZON", "AMAZONDE": "AMAZON",
        "NFLX": "NETFLIX",
        "LFG": "LFG FITNESS",   # keep "LFG FITNESS" together
    }
    base = ALIASES.get(base, base)

    # ── BANKING STOPLIST CHECK ─────────────────────────────────────────────────
    # If the resolved base name is a banking process word, signal the caller.
    if _is_banking_noise(base):
        return BANKING_NOISE_SENTINEL

    return base


def normalize_pattern_name(description: str) -> str:
    """
    Returns a detailed, clean behavioral pattern for rule creation.
    More permissive than normalize_merchant_name — preserves payment processor
    context and multi-word patterns.

    Examples:
        "PAYPAL *NETFLIX"      → "PAYPAL NETFLIX"
        "APPLE.COM/BILL"       → "APPLE COM BILL"
        "AMZN PRIME DE"        → "AMAZON PRIME"
    """
    if not description:
        return "UNKNOWN"

    text = clean_common_noise(description)

    # Replace punctuation delimiters with space (preserve structure)
    text = text.replace("*", " ").replace("/", " ").replace("-", " ")

    # Strip legal suffixes
    for pat in LEGAL_SUFFIXES:
        text = re.sub(pat, " ", text)

    # Replace non-alphanumeric (keep &)
    text = re.sub(r"[^A-Z0-9\s&]", " ", text)

    # Drop isolated single-letter noise (except A, I, &)
    words = text.split()
    cleaned = [w for w in words if len(w) > 1 or w in ("A", "I", "&")]
    text = " ".join(cleaned).strip()

    # Fallback
    if not text:
        text = " ".join(re.sub(r"[^A-Z\s]", " ", description.upper()).split()).strip()

    return text
