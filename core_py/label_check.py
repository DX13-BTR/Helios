from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import os
from dotenv import load_dotenv

load_dotenv()
SCOPES = [os.getenv("GMAIL_SCOPES")]
TOKEN_PATH = os.getenv("GMAIL_TOKEN_PATH")

creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
service = build('gmail', 'v1', credentials=creds)

labels = service.users().labels().list(userId='me').execute().get('labels', [])
for l in labels:
    print(f"{l['name']:30} -> {l['id']}")