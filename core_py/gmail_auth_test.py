from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
import os

load_dotenv(dotenv_path="C:/Helios/core_py/.env")
SCOPES = [s.strip() for s in os.getenv("GMAIL_SCOPES", "").split(",") if s.strip()]
CRED_PATH = os.getenv("GMAIL_CREDENTIALS_PATH")
TOKEN_PATH = os.getenv("GMAIL_TOKEN_PATH")

print("SCOPES:", SCOPES)

if not SCOPES:
    raise ValueError("Missing or malformed GMAIL_SCOPES")

flow = InstalledAppFlow.from_client_secrets_file(CRED_PATH, SCOPES)
creds = flow.run_local_server(port=0)

with open(TOKEN_PATH, "w") as token_file:
    token_file.write(creds.to_json())

print("✅ Gmail OAuth completed. Token saved.")
