import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("CLICKUP_API_KEY")
if not API_TOKEN:
    print("❌ CLICKUP_API_TOKEN not loaded from .env")
    exit()

TEAM_ID = "9015119968"

headers = {
    "Authorization": API_TOKEN
}

url = f"https://api.clickup.com/api/v2/team/{TEAM_ID}/webhook"
response = requests.get(url, headers=headers)

if response.ok:
    print("✅ Registered Webhooks:")
    for hook in response.json().get("webhooks", []):
        print(f"→ {hook['id']} | {hook['endpoint']} | Events: {hook['events']}")
else:
    print("❌ Failed:", response.status_code, response.text)
