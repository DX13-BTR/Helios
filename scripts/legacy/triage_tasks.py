import os
import sqlite3
import requests
from dotenv import load_dotenv
from datetime import datetime

# ── Load Environment ─────────────────────────────────────
load_dotenv(dotenv_path="C:/Helios/core_py/.env")
CLICKUP_TOKEN = os.getenv("CLICKUP_API_KEY")
EMAIL_LIST_ID = os.getenv("CLICKUP_EMAIL_LIST_ID")
PERSONAL_SPACE_ID = os.getenv("CLICKUP_PERSONAL_SPACE_ID")
DB_PATH = os.getenv("DB_PATH")
CLICKUP_API_BASE = "https://api.clickup.com/api/v2"

HEADERS = {
    "Authorization": CLICKUP_TOKEN,
    "Content-Type": "application/json"
}

EXCLUDED_LIST_IDS = {EMAIL_LIST_ID}
EXCLUDED_SPACE_IDS = {PERSONAL_SPACE_ID}

# ── SQLite Setup ─────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute('''
    CREATE TABLE IF NOT EXISTS triaged_tasks (
        id TEXT PRIMARY KEY,
        name TEXT,
        due_date INTEGER,
        priority INTEGER,
        score INTEGER,
        status TEXT,
        space_id TEXT,
        space_name TEXT,
        list_id TEXT,
        list_name TEXT,
        is_urgent INTEGER DEFAULT 0,
        section TEXT DEFAULT '',
        reason TEXT DEFAULT '',
        date_updated INTEGER,
        agent_rank INTEGER DEFAULT 0,
        agent_reason TEXT DEFAULT '',
        raw_json TEXT
    )
''')
conn.commit()

# ── Helpers ──────────────────────────────────────────────

def fetch_tasks_from_list(list_id, list_name, space_id, space_name):
    url = f"{CLICKUP_API_BASE}/list/{list_id}/task?include_closed=false"
    tasks = []
    response = requests.get(url, headers=HEADERS).json()
    for task in response.get("tasks", []):
        task["list_id"] = list_id
        task["list_name"] = list_name
        task["space_id"] = space_id
        task["space_name"] = space_name
        tasks.append(task)
    return tasks

def get_all_tasks():
    all_tasks = []
    teams = requests.get(f"{CLICKUP_API_BASE}/team", headers=HEADERS).json().get("teams", [])

    for team in teams:
        team_id = team["id"]
        space_list = requests.get(f"{CLICKUP_API_BASE}/team/{team_id}/space", headers=HEADERS).json().get("spaces", [])

        for space in space_list:
            space_id = space["id"]
            space_name = space.get("name", "Unnamed Space")
            if space_id in EXCLUDED_SPACE_IDS:
                continue

            # Foldered lists
            folders = requests.get(f"{CLICKUP_API_BASE}/space/{space_id}/folder", headers=HEADERS).json().get("folders", [])
            for folder in folders:
                for lst in folder.get("lists", []):
                    list_id = lst["id"]
                    list_name = lst.get("name", "Unnamed List")
                    if list_id not in EXCLUDED_LIST_IDS:
                        all_tasks.extend(fetch_tasks_from_list(list_id, list_name, space_id, space_name))

            # Folderless lists
            lists = requests.get(f"{CLICKUP_API_BASE}/space/{space_id}/list", headers=HEADERS).json().get("lists", [])
            for lst in lists:
                list_id = lst["id"]
                list_name = lst.get("name", "Unnamed List")
                if list_id not in EXCLUDED_LIST_IDS:
                    all_tasks.extend(fetch_tasks_from_list(list_id, list_name, space_id, space_name))

    return all_tasks

def is_completed(task):
    status = task.get("status", {}).get("status", "").lower()
    return status in {"complete", "closed", "done", "cancelled", "archived"}

def score_task(task):
    score = 0.0
    reason = {}
    
    # --- Extract and normalize status ---
    raw_status = task.get("status")
    if isinstance(raw_status, dict):
        status = raw_status.get("status", "").lower()
    elif isinstance(raw_status, str):
        status = raw_status.lower()
    else:
        status = ""

    # --- Extract and normalize priority ---
    priority_obj = task.get("priority") or {}
    raw_priority = priority_obj.get("priority", "low").lower()

    priority_map = {
        "urgent": 4,
        "high": 3,
        "normal": 2,
        "low": 1
    }
    priority_value = priority_map.get(raw_priority, 1)  # Default to 1 (low)

    # Add priority-based score
    score += priority_value * 40  # Base multiplier to shift scale
    reason["priority"] = raw_priority

    # --- Tags (lowercased, tolerant of dict or string) ---
    raw_tags = task.get("tags", [])
    tags = [t.lower() if isinstance(t, str) else t.get("name", "").lower() for t in raw_tags]

    if "email" in tags:
        score += 50
        reason.setdefault("tags", []).append("email")
    if "helios" in tags:
        score += 10
        reason.setdefault("tags", []).append("helios")
    if "urgent" in tags:
        score += 30
        reason.setdefault("tags", []).append("urgent")

    # --- Due Date or Start Date Fallback ---
    due_timestamp = None
    if task.get("due_date"):
        due_timestamp = int(task["due_date"])
    elif task.get("start_date"):
        due_timestamp = int(task["start_date"])

    if due_timestamp:
        now = int(datetime.now().timestamp() * 1000)
        diff_days = (due_timestamp - now) // (1000 * 60 * 60 * 24)
        reason["diffDays"] = int(diff_days)

        if diff_days < 0:
            if diff_days >= -13:
                score += 100
                reason["overdue"] = "<14d"
            else:
                score += 60
                reason["overdue"] = ">=14d"
        elif diff_days == 0:
            score += 80
            reason["due"] = "today"
        elif diff_days <= 3:
            score += 40
            reason["due"] = "soon"

    # --- Name Keyword Boosts ---
    name = task.get("name", "").lower()
    if "urgent" in name:
        score += 30
        reason.setdefault("keywords", []).append("urgent")
    if "helios" in name:
        score += 10
        reason.setdefault("keywords", []).append("helios")

    return score, priority_value, reason

# ── Main ────────────────────────────────────────────────

def main():
    print("🚀 Fetching tasks...")
    tasks = get_all_tasks()
    print(f"🔍 Retrieved {len(tasks)} raw tasks.")

    # Score + filter
    scored = []
    for task in tasks:
        if is_completed(task):
            continue
        score, priority_value, reason = score_task(task)
        scored.append({
    "id": task["id"],
    "name": task.get("name", "Untitled"),
    "due_date": int(task["due_date"]) if task.get("due_date") else None,
    "priority": priority_value,
    "score": int(score),
    "status": task.get("status", {}).get("status", ""),
    "space_id": task.get("space_id"),
    "space_name": task.get("space_name", ""),
    "list_id": task.get("list_id"),
    "list_name": task.get("list_name", ""),
    "reason": str(reason),
    "raw_json": str(task)
})

    # Sort + truncate
    top_25 = sorted(scored, key=lambda x: x["score"], reverse=True)[:25]

    # Replace DB
    cur.execute("DELETE FROM triaged_tasks")
    for task in top_25:
               cur.execute('''
    INSERT OR REPLACE INTO triaged_tasks (
        id, name, due_date, priority, score, status,
        space_id, list_id, space_name, list_name,
        section, reason,
        date_updated, agent_rank, agent_reason
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (
    task["id"],
    task["name"],
    task["due_date"],
    task["priority"],
    task["score"],
    task["status"],
    task["space_id"],
    task["list_id"],
    task["space_name"],
    task["list_name"],
    task.get("section", ""),
    task.get("reason", ""),
    int(datetime.utcnow().timestamp()),
    0,
    ""
))
    conn.commit()
    print(f"✅ Scored and saved top {len(top_25)} tasks.")

if __name__ == "__main__":
    main()
    conn.close()
