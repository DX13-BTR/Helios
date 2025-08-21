import requests

BASE_URL = "https://api.starlingbank.com/api/v2"

def get_headers(token: str):
    return {"Authorization": f"Bearer {token}"}

def get_accounts(token: str):
    url = f"{BASE_URL}/accounts"
    res = requests.get(url, headers=get_headers(token))
    res.raise_for_status()
    return res.json()

def get_account_balance(account_uid: str, token: str):
    url = f"{BASE_URL}/accounts/{account_uid}/balance"
    res = requests.get(url, headers=get_headers(token))
    res.raise_for_status()
    return res.json()

def get_spaces(account_uid: str, token: str, account_type: str):
    # Always use savings-goals for both account types
    url = f"{BASE_URL}/account/{account_uid}/savings-goals"
    res = requests.get(url, headers=get_headers(token))
    res.raise_for_status()
    return res.json()

