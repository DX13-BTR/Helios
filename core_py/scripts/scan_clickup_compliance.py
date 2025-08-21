# core_py/scripts/scan_clickup_compliance.py
"""
Scan your entire ClickUp workspace, detect compliance-type tasks,
optionally consolidate to one-per client × period × type inside a time window,
and (optionally) upsert the consolidated set into SQLite task_meta.

Usage (Windows CMD):
  (venv) C:\Helios> set PYTHONPATH=%CD%
  # Dry run (no DB writes, no raw dump, no previews)
  (venv) C:\Helios> python -m core_py.scripts.scan_clickup_compliance --window-days 540 --no-dump
  # Apply to DB (write consolidated set)
  (venv) C:\Helios> python -m core_py.scripts.scan_clickup_compliance --window-days 540 --apply --no-dump
  # Include closed tasks and subtasks if needed
  (venv) C:\Helios> python -m core_py.scripts.scan_clickup_compliance --include-closed --include-subtasks
  # If you want previews for audit
  (venv) C:\Helios> python -m core_py.scripts.scan_clickup_compliance --preview
"""

from __future__ import annotations

import os
import re
import csv
import json
import time
import math
import argparse
import sqlite3
import requests
from typing import Dict, List, Any, Iterable, Optional, Tuple
from pathlib import Path
from datetime import datetime, timezone, timedelta

# --- load .env for CLICKUP_API_KEY, CLICKUP_TEAM_ID, HELIOS_DB_PATH ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# --- ENV ---
CLICKUP_API_KEY = os.getenv("CLICKUP_API_KEY")
CLICKUP_TEAM_ID = os.getenv("CLICKUP_TEAM_ID")  # optional; we can auto-detect if missing
DB_PATH = os.getenv("HELIOS_DB_PATH", r"C:\Helios\core_py\db\helios.db")

# --- HTTP ---
BASE = "https://api.clickup.com/api/v2"
HEADERS = {"Authorization": CLICKUP_API_KEY} if CLICKUP_API_KEY else {}

# --- Classification rules ---
RULES: List[Tuple[str, re.Pattern]] = [
    ("vat_return",      re.compile(r"\bvat\b|\bmtd\b|\bvat\s*return\b", re.I)),
    ("payroll",         re.compile(r"\bpayroll\b|\beps\b|\bfps\b|\bpaye\b|\bp60\b|\bp11d\b", re.I)),
    ("ct600",           re.compile(r"\bct\s*600\b|\bct600\b", re.I)),
    ("cs01",            re.compile(r"\bcs01\b|\bconfirmation\s+statement\b", re.I)),
    ("sa100",           re.compile(r"\bsa\s*100\b|\bself\s+assessment\b", re.I)),
    ("sa800",           re.compile(r"\bsa\s*800\b|\bpartnership\s+return\b", re.I)),
    ("cis_return",      re.compile(r"\bcis\b", re.I)),
]

RECURRENCE_DEFAULT: Dict[str, str] = {
    "vat_return":  "quarterly",
    "payroll":     "monthly",
    "ct600":       "annual",
    "cs01":        "annual",
    "sa100":       "annual",
    "sa800":       "annual",
    "cis_return":  "monthly",
}

# --- ClickUp API helpers ---
def _get(url: str, **params) -> Dict[str, Any]:
    if not CLICKUP_API_KEY:
        raise SystemExit("Missing CLICKUP_API_KEY in environment (.env)")
    for attempt in range(6):
        r = requests.get(url, headers=HEADERS, params=params, timeout=60)
        if r.status_code == 429:
            time.sleep(min(30, 2 ** attempt))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()  # pragma: no cover

def _list_paginated(url: str, key: str, page_param="page", limit=100, **params) -> Iterable[Dict[str, Any]]:
    page = 0
    while True:
        data = _get(url, **{**params, page_param: page, "limit": limit})
        items = data.get(key) or data.get("tasks") or []
        if not items:
            break
        for it in items:
            yield it
        if len(items) < limit:
            break
        page += 1

def get_team_id() -> str:
    """Auto-detect a team ID if not provided."""
    if CLICKUP_TEAM_ID:
        return str(CLICKUP_TEAM_ID)
    teams = _get(f"{BASE}/team")
    ts = teams.get("teams") or []
    if not ts:
        raise SystemExit("No ClickUp teams found for the provided API key.")
    return str(ts[0]["id"])

def get_spaces(team_id: str) -> List[Dict[str, Any]]:
    data = _get(f"{BASE}/team/{team_id}/space")
    return data.get("spaces", [])

def get_folders(space_id: str) -> List[Dict[str, Any]]:
    data = _get(f"{BASE}/space/{space_id}/folder")
    return data.get("folders", [])

def get_lists_in_space(space_id: str) -> List[Dict[str, Any]]:
    data = _get(f"{BASE}/space/{space_id}/list")
    return data.get("lists", [])

def get_lists_in_folder(folder_id: str) -> List[Dict[str, Any]]:
    data = _get(f"{BASE}/folder/{folder_id}/list")
    return data.get("lists", [])

def iter_tasks_in_list(
    list_id: str,
    include_closed: bool = False,
    include_archived: bool = False,
    include_subtasks: bool = False,
) -> Iterable[Dict[str, Any]]:
    yield from _list_paginated(
        f"{BASE}/list/{list_id}/task",
        key="tasks",
        archived="true" if include_archived else "false",
        include_closed="true" if include_closed else "false",
        subtasks="true" if include_subtasks else "false",
    )

def scan_all_tasks(
    include_closed: bool = False,
    include_archived: bool = False,
    include_subtasks: bool = False,
) -> List[Dict[str, Any]]:
    team_id = get_team_id()
    all_tasks: List[Dict[str, Any]] = []
    for sp in get_spaces(team_id):
        # lists directly under space
        for lst in get_lists_in_space(sp["id"]):
            all_tasks.extend(
                iter_tasks_in_list(lst["id"], include_closed, include_archived, include_subtasks)
            )
        # lists inside folders
        for fol in get_folders(sp["id"]):
            for lst in get_lists_in_folder(fol["id"]):
                all_tasks.extend(
                    iter_tasks_in_list(lst["id"], include_closed, include_archived, include_subtasks)
                )
    # de-dup by id
    dedup = {str(t["id"]): t for t in all_tasks}
    return list(dedup.values())

# --- Utility + classification ---
def classify_deadline_type(name: str) -> Optional[str]:
    n = name or ""
    for kind, rx in RULES:
        if rx.search(n):
            return kind
    return None

def ms_to_iso(ms: Any) -> Optional[str]:
    if ms is None:
        return None
    try:
        v = int(float(ms))
        if v <= 0:
            return None
        # seconds vs ms heuristic; ClickUp uses ms but be defensive
        if v < 10**11:
            v *= 1000
        return datetime.fromtimestamp(v / 1000.0, tz=timezone.utc).isoformat()
    except Exception:
        return None

def guess_client_code(name: str) -> Optional[str]:
    if not name:
        return None
    # Heuristic: prefix before " - " OR token in [brackets]/(parens)
    if " - " in name:
        return name.split(" - ", 1)[0].strip()[:20] or None
    m = re.search(r"\[(.+?)\]|\((.+?)\)", name)
    if m:
        val = (m.group(1) or m.group(2) or "").strip()
        return val[:20] or None
    return None

def build_compliance(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for t in items:
        name = t.get("name") or ""
        typ = classify_deadline_type(name)
        if not typ:
            continue
        due_iso = ms_to_iso(t.get("due_date"))
        client_code = guess_client_code(name)
        if client_code:
            client_code = client_code[:20]
        out.append({
            "task_id": str(t["id"]),
            "task_type": "fixed_date",
            "deadline_type": typ,
            "fixed_date": due_iso,                              # can be None; UI will handle
            "client_code": client_code,
            "recurrence_pattern": RECURRENCE_DEFAULT.get(typ, "one_time"),
            "calendar_blocked": 0,
            # keep original name for debugging (not written to DB)
            "_name": name,
        })
    return out

# --- Consolidation (window + period bucketing + dedupe) ---
def parse_iso(dt: Optional[str]) -> Optional[datetime]:
    if not dt:
        return None
    try:
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    except Exception:
        return None

def quarter_key(dt: datetime) -> str:
    q = (dt.month - 1)//3 + 1
    return f"{dt.year}-Q{q}"

def month_key(dt: datetime) -> str:
    return f"{dt.year}-{dt.month:02d}"

def year_key(dt: datetime) -> str:
    return f"{dt.year}"

PERIOD_FN: Dict[str, Any] = {
    "vat_return": quarter_key,
    "payroll": month_key,
    "cis_return": month_key,
    "ct600": year_key,
    "cs01": year_key,
    "sa100": year_key,
    "sa800": year_key,
}

def period_key(deadline_type: str, dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    fn = PERIOD_FN.get(deadline_type)
    return fn(dt) if fn else None

def consolidate(items: List[Dict[str, Any]], window_days: int, include_undated: bool) -> List[Dict[str, Any]]:
    """
    - Filter to items with fixed_date within [now, now + window], unless include_undated is True.
    - Bucketize by (client_code, deadline_type, period_key) and keep the earliest fixed_date per bucket.
    """
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=window_days)

    enriched: List[Dict[str, Any]] = []
    for it in items:
        fi = it.get("fixed_date")
        dt = parse_iso(fi)
        if dt is None and not include_undated:
            continue
        if dt:
            if dt < now or dt > horizon:
                continue
        pk = period_key(it["deadline_type"], dt)
        cc = (it.get("client_code") or "").strip() or None
        if cc:
            cc = cc[:20]
        enriched.append({**it, "_dt": dt, "_pk": pk, "client_code": cc})

    buckets: Dict[Tuple[Optional[str], str, Optional[str]], Dict[str, Any]] = {}
    for it in enriched:
        key = (it["client_code"], it["deadline_type"], it["_pk"])
        existing = buckets.get(key)
        if not existing:
            buckets[key] = it
        else:
            a, b = existing.get("_dt"), it.get("_dt")
            if a and b and b < a:
                buckets[key] = it

    result: List[Dict[str, Any]] = []
    for it in buckets.values():
        it.pop("_dt", None)
        it.pop("_pk", None)
        # Drop debug name for DB upsert
        it.pop("_name", None)
        result.append(it)
    return result

# --- DB ---
def db_conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def upsert_task_meta(items: List[Dict[str, Any]]) -> int:
    con = db_conn()
    cur = con.cursor()
    cur.execute("""
      CREATE TABLE IF NOT EXISTS task_meta (
        task_id TEXT PRIMARY KEY,
        task_type TEXT DEFAULT 'flexible',
        deadline_type TEXT,
        fixed_date TEXT,
        calendar_blocked INTEGER DEFAULT 0,
        recurrence_pattern TEXT,
        client_code TEXT
      )
    """)
    n = 0
    for it in items:
        cur.execute("""
          INSERT INTO task_meta(task_id, task_type, deadline_type, fixed_date, calendar_blocked, recurrence_pattern, client_code)
          VALUES (?, ?, ?, ?, ?, ?, ?)
          ON CONFLICT(task_id) DO UPDATE SET
            task_type=excluded.task_type,
            deadline_type=excluded.deadline_type,
            fixed_date=excluded.fixed_date,
            calendar_blocked=excluded.calendar_blocked,
            recurrence_pattern=excluded.recurrence_pattern,
            client_code=excluded.client_code
        """, (
            it["task_id"],
            it.get("task_type", "fixed_date"),
            it.get("deadline_type"),
            it.get("fixed_date"),
            1 if it.get("calendar_blocked") else 0,
            it.get("recurrence_pattern"),
            (it.get("client_code") or None),
        ))
        n += 1
    con.commit()
    con.close()
    return n

# --- Preview writers (optional) ---
def write_preview(path_json: str, path_csv: str, items: List[Dict[str, Any]]) -> None:
    Path(path_json).parent.mkdir(parents=True, exist_ok=True)
    with open(path_json, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    with open(path_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["task_id","task_type","deadline_type","fixed_date","client_code","recurrence_pattern","calendar_blocked"])
        for it in items:
            w.writerow([
                it["task_id"],
                it.get("task_type","fixed_date"),
                it.get("deadline_type"),
                it.get("fixed_date"),
                it.get("client_code"),
                it.get("recurrence_pattern"),
                1 if it.get("calendar_blocked") else 0,
            ])

# --- Main ---
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Upsert into task_meta (otherwise dry-run)")
    ap.add_argument("--dump", default=r"C:\Helios\core_py\db\clickup_full_dump.json", help="Raw ClickUp dump path")
    ap.add_argument("--no-dump", action="store_true", help="Skip writing the raw ClickUp dump JSON")
    ap.add_argument("--preview", action="store_true", help="Write preview CSV/JSON of the consolidated set")
    ap.add_argument("--include-closed", action="store_true", help="Include closed/completed tasks")
    ap.add_argument("--include-archived", action="store_true", help="Include archived tasks")
    ap.add_argument("--include-subtasks", action="store_true", help="Include subtasks")
    ap.add_argument("--window-days", type=int, default=540, help="Include items within N days from today")
    ap.add_argument("--include-undated", action="store_true", help="Include items with no fixed/due date (default: exclude)")
    args = ap.parse_args()

    print("🔎 Scanning all ClickUp spaces/lists/tasks…")
    tasks = scan_all_tasks(
        include_closed=args.include_closed,
        include_archived=args.include_archived,
        include_subtasks=args.include_subtasks,
    )
    print(f"• fetched {len(tasks)} tasks total")

    if not args.no_dump:
        try:
            with open(args.dump, "w", encoding="utf-8") as f:
                json.dump(tasks, f, ensure_ascii=False, indent=2)
            print(f"• raw dump written: {args.dump}")
        except Exception as e:
            print(f"⚠️ raw dump skipped: {e}")

    comp = build_compliance(tasks)
    print(f"• detected compliance items: {len(comp)}")
    by_type: Dict[str, int] = {}
    for it in comp:
        by_type[it["deadline_type"]] = by_type.get(it["deadline_type"], 0) + 1
    for k, v in sorted(by_type.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  - {k}: {v}")

    cons = consolidate(comp, window_days=args.window_days, include_undated=args.include_undated)
    print(f"• consolidated for next {args.window_days}d: {len(cons)}")

    if args.preview:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        preview_dir = os.path.dirname(args.dump) or r"C:\Helios\core_py\db"
        preview_json = os.path.join(preview_dir, f"compliance_import_preview.{ts}.json")
        preview_csv  = os.path.join(preview_dir, f"compliance_import_preview.{ts}.csv")
        try:
            write_preview(preview_json, preview_csv, cons)
            print(f"• preview written:\n  - {preview_json}\n  - {preview_csv}")
        except PermissionError as e:
            print(f"⚠️ preview write skipped (PermissionError): {e}")
        except Exception as e:
            print(f"⚠️ preview write skipped: {e}")

    if not args.apply:
        print("💡 Dry run only. Re-run with --apply to upsert the consolidated set into task_meta.")
        return

    n = upsert_task_meta(cons)
    print(f"✅ Upserted into task_meta: {n}")

if __name__ == "__main__":
    main()
