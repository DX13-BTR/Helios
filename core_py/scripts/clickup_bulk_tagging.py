#!/usr/bin/env python3
"""
ClickUp bulk tagging helper

Usage (Windows CMD):
  set CLICKUP_API_KEY=...           # required
  set CLICKUP_TEAM_ID=...           # required
  set CLICKUP_ME_UID=...            # optional, to scope to you
  set CLICKUP_SPACE_ID_CLIENTS=...  # optional (for auto_suggest)
  set CLICKUP_SPACE_ID_MARKETING=...
  set CLICKUP_SPACE_ID_EFKARISTO=...
  set CLICKUP_EMAIL_LIST_ID=...     # optional, excluded from export if set
  set CLICKUP_PERSONAL_SPACE_ID=... # optional, excluded from export if set

  python clickup_bulk_tagging.py export --out tasks_export.csv
  # -> Open CSV, fill/adjust the Category column for each task (Client/Systems/Marketing/Admin/Personal/Other)

  python clickup_bulk_tagging.py apply --csv tasks_export.csv --column Category --dry-run
  # -> shows planned operations

  python clickup_bulk_tagging.py apply --csv tasks_export.csv --column Category
  # -> actually adds tags to tasks based on your chosen categories
"""

from __future__ import annotations
import csv, os, time, typing as t, argparse, json
import requests

API_BASE = "https://api.clickup.com/api/v2"

# --------- helpers ---------
class ClickUpError(RuntimeError): ...

def _env(name: str, required=False, default: t.Optional[str]=None) -> str | None:
    v = os.getenv(name, default)
    if required and not v:
        raise ClickUpError(f"Missing {name} in environment.")
    return v

def _headers() -> dict:
    key = _env("CLICKUP_API_KEY", required=True)
    return {"Authorization": key, "Content-Type": "application/json"}

def _retry(method: str, url: str, *, params=None, json_body=None, expected=(200,201,204)) -> requests.Response:
    h = _headers()
    backoff = 1.0
    for attempt in range(8):
        try:
            r = requests.request(method, url, headers=h, params=params, json=json_body, timeout=30)
        except requests.RequestException as e:
            if attempt >= 7: raise
            time.sleep(backoff); backoff = min(backoff*2, 8); continue
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After", backoff))
            time.sleep(max(0.5, wait)); backoff = min(backoff*2, 8); continue
        if r.status_code in expected:
            return r
        # bubble message for diagnostics
        try: payload = r.json()
        except Exception: payload = r.text
        raise ClickUpError(f"{method} {url} -> {r.status_code}: {payload}")
    raise ClickUpError(f"Failed after retries: {method} {url}")

def _ms(v):
    try:
        v = int(v or 0)
        return v*1000 if v and v < 10_000_000_000 else v
    except Exception:
        return 0

def _flatten_task(tk: dict) -> dict:
    prio = None
    if isinstance(tk.get("priority"), dict):
        try: prio = int(tk["priority"].get("priority"))
        except Exception: prio = None

    tags = []
    for tg in (tk.get("tags") or []):
        if isinstance(tg, dict) and "name" in tg: tags.append(str(tg["name"]).lower())
        elif isinstance(tg, str): tags.append(tg.lower())

    # normalize nested ids
    space_id = (tk.get("space") or {}).get("id") if isinstance(tk.get("space"), dict) else tk.get("space_id")
    list_id  = (tk.get("list")  or {}).get("id") if isinstance(tk.get("list"),  dict) else tk.get("list_id")
    due_ms = _ms(tk.get("due_date") or tk.get("due"))

    return {
        "id": str(tk.get("id") or tk.get("task_id") or ""),
        "name": tk.get("name") or tk.get("title") or "(Untitled)",
        "status": (tk.get("status") or {}).get("status") if isinstance(tk.get("status"), dict) else tk.get("status"),
        "priority": prio,
        "due_date_ms": due_ms,
        "space_id": str(space_id or ""),
        "list_id": str(list_id or ""),
        "url": tk.get("url") or "",
        "tags": ",".join(tags),
    }

# --------- data fetch ---------
def fetch_all_tasks() -> list[dict]:
    team_id = _env("CLICKUP_TEAM_ID", required=True)
    me_uid  = _env("CLICKUP_ME_UID") or _env("CLICKUP_USER_ID")
    email_list_id = _env("CLICKUP_EMAIL_LIST_ID")
    personal_space_id = _env("CLICKUP_PERSONAL_SPACE_ID")

    url = f"{API_BASE}/team/{team_id}/task"
    page = 0
    items: list[dict] = []
    while True:
        params: dict[str,t.Any] = {
            "page": page,
            "page_size": 100,
            "order_by": "due_date",
            "reverse": False,
            "subtasks": True,
            "include_subtasks": True,
            # We’ll include everything (including closed) so you can tag comprehensively.
        }
        if me_uid:
            params["assignees[]"] = me_uid
        r = _retry("GET", url, params=params)
        data = r.json() or {}
        chunk = data.get("tasks") or []
        if not chunk:
            break
        # Filter out email list and personal space if configured (usually not relevant to work buckets)
        for tk in chunk:
            list_id  = str(((tk.get("list") or {}).get("id")) or tk.get("list_id") or "")
            space_id = str(((tk.get("space") or {}).get("id")) or tk.get("space_id") or "")
            if email_list_id and list_id == str(email_list_id):
                continue
            if personal_space_id and space_id == str(personal_space_id):
                continue
            items.append(_flatten_task(tk))
        if len(chunk) < 100:
            break
        page += 1
        if page > 100:  # safety
            break
    return items

# --------- export CSV ---------
DEFAULT_HEADERS = [
    "id","name","status","priority","due_date_ms","space_id","list_id","tags","url","Category","AutoSuggest"
]

def _auto_suggest(row: dict) -> str:
    """Heuristic suggestion based on space IDs and name keywords."""
    space_clients   = str(_env("CLICKUP_SPACE_ID_CLIENTS") or "")
    space_marketing = str(_env("CLICKUP_SPACE_ID_MARKETING") or "")
    space_systems   = str(_env("CLICKUP_SPACE_ID_EFKARISTO") or "")

    n = (row.get("name") or "").lower()
    sid = str(row.get("space_id") or "")
    if sid and sid == space_clients:   return "Client"
    if sid and sid == space_marketing: return "Marketing"
    if sid and sid == space_systems:   return "Systems"

    # keyword nudge
    if any(k in n for k in ["invoice","receipt","reconcile","vat","payroll","statement"]): return "Admin"
    if any(k in n for k in ["landing","adset","campaign","newsletter","seo","press"]):      return "Marketing"
    if any(k in n for k in ["bug","deploy","refactor","schema","pipeline","token","oauth"]):return "Systems"
    if any(k in n for k in ["ethan","school","gp","family","home"]):                        return "Personal"
    return ""

def cmd_export(out_path: str) -> None:
    rows = fetch_all_tasks()
    for r in rows:
        r["Category"] = ""                 # you will fill this
        r["AutoSuggest"] = _auto_suggest(r)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DEFAULT_HEADERS)
        w.writeheader()
        w.writerows(rows)
    print(f"Exported {len(rows)} tasks -> {out_path}")
    print("Open the CSV and set 'Category' per row to one of: Client, Systems, Marketing, Admin, Personal, Other")

# --------- apply tags from CSV ---------
CATEGORY_TO_TAG = {
    "client":   "client",
    "systems":  "systems",
    "marketing":"marketing",
    "admin":    "admin",
    "personal": "personal",
    "other":    "other",
}

def _add_tag_to_task(task_id: str, tag: str) -> None:
    """
    Adds a tag to a task. If the tag doesn't exist in that space/list, the API will create it in context.
    Endpoint: POST /task/{task_id}/tag/{tag}
    """
    url = f"{API_BASE}/task/{task_id}/tag/{tag}"
    _retry("POST", url, expected=(200, 204))

def cmd_apply(csv_path: str, column: str, dry_run: bool=False, limit: int|None=None) -> None:
    with open(csv_path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        rows = list(r)

    applied = 0
    for i, row in enumerate(rows, 1):
        if limit and applied >= limit:
            break
        cat_raw = (row.get(column) or "").strip()
        if not cat_raw:
            continue
        tag = CATEGORY_TO_TAG.get(cat_raw.lower())
        if not tag:
            # accept arbitrary labels: normalize to slug
            tag = cat_raw.strip().lower().replace(" ", "_")
        task_id = row.get("id")
        if not task_id:
            continue

        if dry_run:
            print(f"[DRY] Would add tag '{tag}' to task {task_id} :: {row.get('name')}")
        else:
            _add_tag_to_task(task_id, tag)
            print(f"[OK] Added tag '{tag}' -> {task_id} :: {row.get('name')}")
            # gentle pacing to be nice to the API
            time.sleep(0.1)
        applied += 1

    if dry_run:
        print(f"[DRY] Planned {applied} tag applications.")
    else:
        print(f"Applied {applied} tags.")

# --------- CLI ---------
def main():
    ap = argparse.ArgumentParser(description="Bulk classify + tag ClickUp tasks via CSV")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_exp = sub.add_parser("export", help="Export tasks to CSV to label")
    ap_exp.add_argument("--out", required=True, help="Output CSV path")

    ap_apply = sub.add_parser("apply", help="Apply tags from labeled CSV")
    ap_apply.add_argument("--csv", required=True, help="Input CSV with Category column")
    ap_apply.add_argument("--column", required=True, help="CSV column name to use as category (e.g., Category)")
    ap_apply.add_argument("--dry-run", action="store_true")
    ap_apply.add_argument("--limit", type=int, default=None, help="Max rows to apply (safety)")

    args = ap.parse_args()
    if args.cmd == "export":
        cmd_export(args.out)
    elif args.cmd == "apply":
        cmd_apply(args.csv, args.column, dry_run=args.dry_run, limit=args.limit)

if __name__ == "__main__":
    main()
