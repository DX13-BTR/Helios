import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

REQUIRED_KEYS = [
    "DB_PATH", "GMAIL_USER", "GMAIL_TOKEN_PATH", "GMAIL_CREDENTIALS_PATH",
    "GMAIL_SCOPES", "CLICKUP_API_KEY", "CLICKUP_LIST_ID", "CLICKUP_USER_ID"
]

print("\n🔍 Validating .env variables:\n")

for key in REQUIRED_KEYS:
    value = os.getenv(key)
    if not value:
        print(f"❌ MISSING: {key}")
    else:
        print(f"✅ {key} = {value}")
