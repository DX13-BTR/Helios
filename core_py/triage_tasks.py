# core_py/triage_tasks.py
from __future__ import annotations
import os
import time
import sqlite3
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timezone

import requests
from requests import HTTPError
from dotenv import load_dotenv, find_dotenv

# ── Env ──────────────────────────────────────────────────────────────────────
env_ok = load_dotenv("C:/Helios/core_py/.env")
if not env_ok:
    load_dotenv(find_dotenv())

CLICKUP_API_KEY = (os.getenv("CLICKUP_API_KEY") or "").strip()
CLICKUP_TEAM_ID = (os.getenv("CLICKUP_TEAM_ID") or "").strip()
EMAIL_LIST_ID = (os.getenv("CLICKUP_EMAIL_LIST_ID") or "").strip()
PERSONAL_SPACE_ID = (os.getenv("CLICKUP_PERSONAL_SPACE_ID") or "").strip()
DB_PATH = (os.getenv("DB_PATH") or "C:/Helios/helios.db").strip()
MY_UID = (os.getenv("CLICKUP_ME_UID") or os.getenv("CLICKUP_USER_ID") or "").strip()

if not CLICKUP_API_KEY or not CLICKUP_TEAM_ID:
    raise SystemExit("Missing CLICKUP_API_KEY or CLICKUP_TEAM_ID. Fix .env.")

API = "https://api.clickup.com/api/v2"
HEADERS = {"Authorization": CLICKUP_API_KEY}
HTTP_TIMEOUT = 30
PAGE_SIZE = 100
TOP_N = 25
INCLUDE_UNASSIGNED = True  # per your preference

# Only pull actionable statuses server-side (reduces payload massively)
ACTIVE_STATUSES = ["to do", "in progress", "review", "blocked"]  # tweak if your workspace differs

# ── HTTP with backoff ────────────────────────────────────────────────────────
def _get(url: str, params: Optional[Dict[str, Any]] = None, max_retries: int = 5) -> Dict[str, Any]:
    attempt = 0
    while True:
        try:
            r = requests.get(url, headers=HEADERS, params=params or {}, timeout=HTTP_TIMEOUT)
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After")
                sleep_s = float(retry_after) if retry_after else min(2 ** attempt, 30)
                time.sleep(sleep_s)
                attempt += 1
                if attempt > max_retries:
                    r.raise_for_status()
                continue
            r.raise_for_status()
            return r.json()
        except HTTPError as e:
            if e.response is not None and 500 <= e.response.status_code < 600 and attempt < max_retries:
                time.sleep(min(2 ** attempt, 30))
                attempt += 1
                continue
            raise

# ── Team tasks fetch (assignee-aware, few calls) ─────────────────────────────
def fetch_team_tasks(assignees: Optional[List[str]]) -> List[Dict[str, Any]]:
    """
    Fetch tasks for the whole team (paginated).
    - Filters server-side by ACTIVE_STATUSES to avoid completed/archived.
    - If assignees provided, ClickUp filters to those users server-side.
    """
    params: Dict[str, Any] = {
        "page": 0,
        "subtasks": "true",
        "archived": "false",
        "statuses[]": ACTIVE_STATUSES,  # <-- server-side filter to exclude completed
    }
    if assignees:
        params["assignees[]"] = assignees  # requests expands list

    out: List[Dict[str, Any]] = []
    while True:
        data = _get(f"{API}/team/{CLICKUP_TEAM_ID}/task", params)
        batch = data.get("tasks", []) or []
        out.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        params["page"] = int(params["page"]) + 1
    return out

def get_all_tasks_mike_plus_unassigned() -> List[Dict[str, Any]]:
    """
    Two streams total:
      1) Mike tasks via assignees[] = MY_UID
      2) All active tasks (for unassigned local filter)
    Dedup by id.
    """
    mike_tasks: List[Dict[str, Any]] = fetch_team_tasks([MY_UID]) if MY_UID else []
    all_active: List[Dict[str, Any]] = fetch_team_tasks(None) if INCLUDE_UNASSIGNED else []
    unassigned = [t for t in all_active if not (t.get("assignees") or [])]

    by_id: Dict[str, Dict[str, Any]] = {}
    for t in mike_tasks + unassigned:
        by_id[str(t.get("id"))] = t
    return list(by_id.values())

# ── Filters ──────────────────────────────────────────────────────────────────
def is_completed(task: Dict[str, Any]) -> bool:
    status = (task.get("status") or {}).get("status") or ""
    s = status.lower()
    # Completed already filtered server-side, but keep defense-in-depth:
    return s in {"complete", "completed", "closed", "done", "cancelled", "archived"}

def in_personal_or_email(task: Dict[str, Any]) -> bool:
    list_id = str((task.get("list") or {}).get("id") or "")
    space_id = str((task.get("space") or {}).get("id") or "")
    if EMAIL_LIST_ID and list_id == str(EMAIL_LIST_ID):
        return True
    if PERSONAL_SPACE_ID and space_id == str(PERSONAL_SPACE_ID):
        return True
    return False

def assigned_kind(task: Dict[str, Any]) -> str:
    assignees = task.get("assignees") or []
    ids: Set[str] = {str(a.get("id")) for a in assignees if a and a.get("id") is not None}
    if MY_UID and MY_UID in ids:
        return "mike"
    if not ids:
        return "unassigned"
    return "other"

# ── Scoring ──────────────────────────────────────────────────────────────────
PRIORITY_RANK = {"urgent": 4, "high": 3, "normal": 2, "medium": 2, "low": 1}

def parse_due(task: Dict[str, Any]) -> Optional[datetime]:
    due = task.get("due_date")
    if not due:
        # fallback: start_date like the GH version
        due = task.get("start_date")
        if not due:
            return None
    try:
        return datetime.fromtimestamp(int(due) / 1000, tz=timezone.utc)
    except Exception:
        return None

def score_task(task: Dict[str, Any]) -> float:
    score = 0.0
    reason = {}  # optional; keep if you want to print/debug

    # Priority (GitHub: *40)
    priority_name = (
        ((task.get("priority") or {}).get("priority"))
        or ((task.get("priority") or {}).get("name"))
        or ""
    ).lower()
    priority_value = PRIORITY_RANK.get(priority_name, 1)  # default low
    score += priority_value * 40
    reason["priority"] = priority_name

    # Tags (GitHub boosts)
    raw_tags = task.get("tags", []) or []
    tags = [t.lower() if isinstance(t, str) else (t.get("name") or "").lower() for t in raw_tags]
    if "email" in tags:
        score += 50
    if "helios" in tags:
        score += 10
    if "urgent" in tags:
        score += 30

    # Due or start date (GitHub thresholds)
    due = parse_due(task)
    if due:
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        diff_days = (int(due.timestamp() * 1000) - now_ms) // (1000 * 60 * 60 * 24)
        if diff_days < 0:
            score += 100 if diff_days >= -13 else 60
        elif diff_days == 0:
            score += 80
        elif diff_days <= 3:
            score += 40

    # Name keywords (GitHub boosts)
    name = (task.get("name") or "").lower()
    if "urgent" in name:
        score += 30
    if "helios" in name:
        score += 10

    return float(int(score))  # GitHub stores as int; keep float if you prefer

# ── Persistence (no schema change) ───────────────────────────────────────────
DDL_BASE = """
CREATE TABLE IF NOT EXISTS triaged_tasks (
    id TEXT PRIMARY KEY,
    name TEXT,
    status TEXT,
    due_date TEXT,
    priority TEXT,
    score REAL,
    list_id TEXT,
    list_name TEXT,
    space_id TEXT,
    space_name TEXT,
    url TEXT,
    created_at TEXT,
    updated_at TEXT
);
"""

def open_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute(DDL_BASE)
    return conn

def replace_triaged(conn: sqlite3.Connection, rows: List[Dict[str, Any]]) -> None:
    conn.execute("DELETE FROM triaged_tasks;")
    conn.executemany(
        """
        INSERT OR REPLACE INTO triaged_tasks
        (id, name, status, due_date, priority, score, list_id, list_name, space_id, space_name, url, created_at, updated_at)
        VALUES
        (:id, :name, :status, :due_date, :priority, :score, :list_id, :list_name, :space_id, :space_name, :url, :created_at, :updated_at)
        """,
        rows,
    )
    conn.commit()

def fmt_row(task: Dict[str, Any]) -> Dict[str, Any]:
    due = parse_due(task)
    return {
        "id": str(task.get("id")),
        "name": task.get("name") or "",
        "status": ((task.get("status") or {}).get("status") or "").title(),
        "due_date": due.isoformat() if due else None,
        "priority": ((task.get("priority") or {}).get("priority")
                     or (task.get("priority") or {}).get("name") or "").title(),
        "score": float(task.get("__score__", 0.0)),
        "list_id": str((task.get("list") or {}).get("id") or ""),
        "list_name": (task.get("list") or {}).get("name") or "",
        "space_id": str((task.get("space") or {}).get("id") or ""),
        "space_name": (task.get("space") or {}).get("name") or "",
        "url": task.get("url") or task.get("url_path") or "",
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }

# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    print("🚀 Fetching tasks (Mike + unassigned)…")
    all_tasks = get_all_tasks_mike_plus_unassigned()
    print(f"🔍 Retrieved {len(all_tasks)} raw from ClickUp (active statuses only)")

    # Early, strict filtering BEFORE counts/scoring
    kept: List[Dict[str, Any]] = []
    c_mike = c_unassigned = c_other = c_completed = c_personal_email = 0

    for t in all_tasks:
        if in_personal_or_email(t):
            c_personal_email += 1
            continue
        if is_completed(t):
            c_completed += 1
            continue

        kind = assigned_kind(t)
        if kind == "mike":
            c_mike += 1
            kept.append(t)
        elif kind == "unassigned":
            c_unassigned += 1
            kept.append(t)
        else:
            c_other += 1  # should be near zero because server-side filters already scoped
            continue

    print(f"👤 Mike: {c_mike}   ◻️ Unassigned: {c_unassigned}   🗑️ Completed skipped: {c_completed}   📥 Personal/Email skipped: {c_personal_email}   🚫 Others: {c_other}")
    print(f"🧹 After filters: {len(kept)}")

    for t in kept:
        t["__score__"] = score_task(t)

    SENTINEL = datetime.max.replace(tzinfo=timezone.utc)
    kept.sort(key=lambda x: (-x["__score__"], (parse_due(x) or SENTINEL)))
    top = kept[:TOP_N]
    print(f"🏁 Taking top {len(top)} of {len(kept)} by score")

    rows = [fmt_row(t) for t in top]
    conn = open_db(DB_PATH)
    try:
        replace_triaged(conn, rows)
    finally:
        conn.close()
    print("✅ triaged_tasks updated.")

if __name__ == "__main__":
    main()
