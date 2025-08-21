import os
import requests
from dotenv import load_dotenv

load_dotenv()

CLICKUP_API_TOKEN = os.getenv("CLICKUP_API_KEY")
TEAM_ID = os.getenv("CLICKUP_TEAM_ID")
WEBHOOK_URL = os.getenv("CLICKUP_WEBHOOK_URL")
WEBHOOK_SECRET = os.getenv("CLICKUP_WEBHOOK_SECRET")

headers = {
    "Authorization": CLICKUP_API_TOKEN,
    "Content-Type": "application/json"
}

payload = {
    "endpoint": WEBHOOK_URL,
    "events": [
        "taskUpdated"
    ],
    "secret": WEBHOOK_SECRET
}

url = f"https://api.clickup.com/api/v2/team/{TEAM_ID}/webhook"

response = requests.post(url, json=payload, headers=headers)

if response.status_code == 200:
    data = response.json()
    print(f"✅ Webhook created:\n→ ID: {data['id']}\n→ URL: {data['webhook']['endpoint']}")
else:
    print(f"❌ Failed to create webhook: {response.status_code} {response.text}")
