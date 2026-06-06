import os

# Custom .env loader to ensure settings are loaded before any export
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

# Core configuration values
SELF_NAME = os.getenv("SELF_NAME", "deepak batham")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3.5:4b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://100.103.104.90:11434")

# SQLite Database Path
DEFAULT_DB_DIR = os.path.expanduser("~/.personalfinz")
os.makedirs(DEFAULT_DB_DIR, exist_ok=True)
DB_PATH = os.getenv("DB_PATH", os.path.join(DEFAULT_DB_DIR, "data.db"))

# ezBookkeeping integration settings
EZBOOKKEEPING_API_URL = os.getenv("EZBOOKKEEPING_API_URL", "http://100.115.35.4:8090/api/v1")
EZBOOKKEEPING_TOKEN = os.getenv("EZBOOKKEEPING_TOKEN", "")

# GoCardless PSD2 Sync settings
GOCARDLESS_SECRET_ID = os.getenv("GOCARDLESS_SECRET_ID", "")
GOCARDLESS_SECRET_KEY = os.getenv("GOCARDLESS_SECRET_KEY", "")

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
