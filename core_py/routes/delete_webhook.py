import os
import requests
import sys
from dotenv import load_dotenv

load_dotenv()

CLICKUP_API_TOKEN = os.getenv("CLICKUP_API_KEY")

if not CLICKUP_API_TOKEN:
    print("❌ CLICKUP_API_TOKEN not found in .env")
    sys.exit(1)

if len(sys.argv) < 2:
    print("❌ Usage: python delete_webhook.py <WEBHOOK_ID>")
    sys.exit(1)

webhook_id = sys.argv[1]

url = f"https://api.clickup.com/api/v2/webhook/{webhook_id}"
headers = {
    "Authorization": CLICKUP_API_TOKEN
}

response = requests.delete(url, headers=headers)

if response.status_code == 204:
    print(f"✅ Webhook {webhook_id} deleted successfully.")
else:
    print(f"❌ Failed to delete webhook {webhook_id}: {response.status_code} {response.text}")