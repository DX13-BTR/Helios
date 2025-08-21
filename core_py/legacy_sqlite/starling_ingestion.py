import os, sqlite3, requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from core_py.db.database import get_db_connection

BASE_URL = "https://api.starlingbank.com/api/v2"

load_dotenv()

ACCOUNTS = [
    {
        "name": "Efkaristo",
        "type": "business",
        "token": os.getenv("EFK_STARLING_TOKEN"),
        "account_uid": os.getenv("EFK_ACCOUNT_UID"),
        "tx_table": "transactions_efkaristo"
    },
    {
        "name": "Personal",
        "type": "personal",
        "token": os.getenv("PERS_STARLING_TOKEN"),
        "account_uid": os.getenv("PERS_ACCOUNT_UID"),
        "tx_table": "transactions_personal"
    }
]

def iso(days_ago=0):
    return (datetime.utcnow() - timedelta(days=days_ago)).isoformat(timespec='milliseconds') + "Z"

def fetch_balances_and_spaces(account):
    headers = {"Authorization": f"Bearer {account['token']}"}
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS balances (
            timestamp TEXT,
            account TEXT,
            space_name TEXT,
            balance REAL
        )
    """)

    # Main account balance
    bal_url = f"{BASE_URL}/accounts/{account['account_uid']}/balance"
    resp = requests.get(bal_url, headers=headers)
    resp.raise_for_status()
    bal = resp.json().get("effectiveBalance", {}).get("minorUnits", 0) / 100
    cur.execute("INSERT INTO balances VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(), account['name'], "Main Account", bal))

    # Spaces / Savings Goals
    spaces_url = (
        f"{BASE_URL}/account/{account['account_uid']}/spaces"
        if account['type'] == "personal"
        else f"{BASE_URL}/account/{account['account_uid']}/savings-goals"
    )
    resp = requests.get(spaces_url, headers=headers)
    resp.raise_for_status()
    raw = resp.json()
    spaces = raw.get("spaces") or raw.get("savingsGoals") or raw.get("savingsGoalList") or []

    for s in spaces:
        minor = (
            s.get("totalSaved", {}).get("minorUnits") or
            s.get("balance", {}).get("minorUnits") or 0
        )
        cur.execute("INSERT INTO balances VALUES (?, ?, ?, ?)",
                    (datetime.now().isoformat(), account['name'], s.get("name",""), minor/100))

    conn.commit()
    conn.close()
    print(f"✅ {account['name']} balances updated")

def fetch_transactions(account):
    headers = {"Authorization": f"Bearer {account['token']}"}
    start_iso, end_iso = iso(2), iso(0)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""CREATE TABLE IF NOT EXISTS {account['tx_table']} (
        date TEXT, amount REAL, direction TEXT, spaceName TEXT, spaceUid TEXT,
        reference TEXT, counterParty TEXT, spendingCategory TEXT,
        feedUid TEXT PRIMARY KEY, source TEXT, status TEXT
    )""")

    # Primary category
    acc_resp = requests.get(f"{BASE_URL}/accounts", headers=headers).json()
    primary_uid = acc_resp.get('accounts', [{}])[0].get('defaultCategory')
    categories = [("PRIMARY", primary_uid)]

    # Spaces / goals → for categoryUids
    space_url = (
        f"{BASE_URL}/account/{account['account_uid']}/spaces"
        if account['type'] == "personal"
        else f"{BASE_URL}/account/{account['account_uid']}/savings-goals"
    )
    raw = requests.get(space_url, headers=headers).json()
    spaces = raw.get("spaces") or raw.get("savingsGoals") or raw.get("savingsGoalList") or []
    for s in spaces:
        if s.get("categoryUid"):
            categories.append((s.get("name",""), s.get("categoryUid")))

    # Transactions ingestion
    new_count = 0
    for cat_name, cat_uid in categories:
        url = f"{BASE_URL}/feed/account/{account['account_uid']}/category/{cat_uid}/transactions-between"
        params = f"?minTransactionTimestamp={start_iso}&maxTransactionTimestamp={end_iso}"
        resp = requests.get(url+params, headers=headers)
        if resp.status_code != 200:
            print(f"⚠️ {account['name']} → {cat_name} failed: {resp.status_code}")
            continue
        for tx in resp.json().get("feedItems", []):
            row = (
                tx.get("transactionTime","").split("T")[0],
                (tx.get("amount",{}).get("minorUnits",0)/100),
                tx.get("direction",""),
                cat_name,
                cat_uid,
                tx.get("reference",""),
                tx.get("counterPartyName",""),
                tx.get("spendingCategory",""),
                tx.get("feedItemUid"),
                tx.get("source",""),
                tx.get("status","")
            )
            try:
                cur.execute(f"INSERT INTO {account['tx_table']} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
                new_count += 1
            except sqlite3.IntegrityError:
                pass
    conn.commit()
    conn.close()
    print(f"✅ {account['name']}: {new_count} new transactions")

if __name__ == "__main__":
    for acct in ACCOUNTS:
        fetch_balances_and_spaces(acct)
        fetch_transactions(acct)
    print("🎉 Starling ingestion complete")
