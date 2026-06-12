import os

# Custom .env loader to ensure settings are loaded before any export
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                k = k.strip()
                v = v.strip()
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                os.environ.setdefault(k, v)

# Core configuration values
SELF_NAME = os.getenv("SELF_NAME", "deepak batham")
LLM_MODEL = os.getenv("LLM_MODEL", "gemma4:12b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://100.103.104.90:11434")

# SQLite Database Path
DEFAULT_DB_DIR = os.path.expanduser("~/.personalfinz")
os.makedirs(DEFAULT_DB_DIR, exist_ok=True)
DB_PATH = os.getenv("DB_PATH", os.path.join(DEFAULT_DB_DIR, "personal_finz.db"))

# ezBookkeeping integration settings
EZBOOKKEEPING_API_URL = os.getenv("EZBOOKKEEPING_API_URL", "http://100.115.35.4:8090/api/v1")
EZBOOKKEEPING_TOKEN = os.getenv("EZBOOKKEEPING_TOKEN", "")

# Enable Banking PSD2 Sync settings
ENABLE_BANKING_APP_ID = os.getenv("ENABLE_BANKING_APP_ID", "")
ENABLE_BANKING_KEY_PATH = os.getenv("ENABLE_BANKING_KEY_PATH", "pipeline/enable_banking_key.pem")
ENABLE_BANKING_REDIRECT_URI = os.getenv("ENABLE_BANKING_REDIRECT_URI", "").strip("'\"")
ENABLE_BANKING_PRIVATE_KEY = b""

if ENABLE_BANKING_KEY_PATH:
    # Resolve relative path from project root
    _base_dir = os.path.dirname(os.path.abspath(__file__))
    _key_path = os.path.join(_base_dir, ENABLE_BANKING_KEY_PATH) if not os.path.isabs(ENABLE_BANKING_KEY_PATH) else ENABLE_BANKING_KEY_PATH
    
    if not os.path.exists(_key_path):
        raise FileNotFoundError(f"Enable Banking Private Key file not found at: {_key_path}")
    if not os.access(_key_path, os.R_OK):
        raise PermissionError(f"Enable Banking Private Key file at {_key_path} is not readable.")
    
    try:
        with open(_key_path, "rb") as key_file:
            ENABLE_BANKING_PRIVATE_KEY = key_file.read()
            if not ENABLE_BANKING_PRIVATE_KEY.strip():
                raise ValueError("Enable Banking Private Key file is empty.")
    except Exception as e:
        raise ValueError(f"Failed to read Enable Banking Private Key: {e}")
else:
    raise ValueError("ENABLE_BANKING_KEY_PATH environment variable is not set.")


# Currency conversion rate (1 EUR = X INR)
EUR_INR_RATE = float(os.getenv("EUR_INR_RATE", "90.0"))

# Standard Allowed Categories
ALLOWED_CATEGORIES = [
    "Food",
    "Drink",
    "Fruit & Snack",
    "Clothing",
    "Jewelry",
    "Cosmetic",
    "Hair Cuts & Salon",
    "Houseware",
    "Electronics",
    "Repairs & Maintenance",
    "Utilities",
    "Rent",
    "Public Transit",
    "Taxi & Car Rental",
    "Personal Car Expense",
    "Train Tickets",
    "Airline Tickets",
    "Telephone Bill",
    "Internet Bill",
    "Express Fee",
    "Sports & Fitness",
    "Party Expense",
    "Movies & Shows",
    "Toys & Games",
    "Subscription",
    "Pet Expense",
    "Travel",
    "Books & Magazines",
    "Training Courses",
    "Certification",
    "Gifts",
    "Donations",
    "Diagnosis & Treatment",
    "Medications",
    "Medical Devices",
    "Tax",
    "Service Charge",
    "Insurance",
    "Interest Expense",
    "Compensation & Fine",
    "Transfer",
    "Income",
    "Other"
]
