"""
helios_gcal_sync_fixed.py  — throttled + fast dry-run

Sync fixed commitments from Helios task_meta → Google Calendar (Helios Fixed Commitments).

Key features:
- Throttled writes (QPS with jitter) to stay under Google quota
- Fast dry-run: bulk prefetch once; avoid per-row lookups
- Count-only mode: zero Google API calls
- Idempotent upserts via extendedProperties.private.helios_task_id

Usage:
  python helios_gcal_sync_fixed.py --db "C:/Helios/core_py/db/helios.db" --window-days 365 --dry-run --fast-dry-run
  python helios_gcal_sync_fixed.py --db "C:/Helios/core_py/db/helios.db" --window-days 365 --apply --qps 3.5

.env required keys:
  CALENDAR_TOKEN_PATH
  CALENDAR_SCOPES = https://www.googleapis.com/auth/calendar
  FIXED_CALENDAR_ID
"""

from __future__ import annotations
import os, sys, sqlite3, argparse, time, random
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pytz

LON = pytz.timezone("Europe/London")
DEFAULT_SCOPE = "https://www.googleapis.com/auth/calendar"

# ---------------- Duration & summary rules ---------------- #

DURATION_RULES = {
    "health_routine": {
        "insulin_rybelsus_morning": 15,
        "meds_morning": 10,
        "bsl_morning": 10,
        "bsl_lunch": 10,
        "bsl_predinner": 10,
        "meds_insulin_evening": 10,
        "bsl_bedtime": 10,
        "_default": 10,
    },
    "pet_care": {
        "loki_breakfast": 10,
        "loki_snack_1": 5,
        "loki_snack_2": 5,
        "loki_snack_3": 5,
        "loki_dinner": 15,
        "litter_tray_scoop": 10,
        "_default": 10,
    },
    "school_run": {"morning": 40, "afternoon": 35, "_default": 35},
    "bs_school_run": 40,
    "school_exception": {"earlyfinish": 0, "closure": 0, "_default": 0},
    "daily_checkin": {"morning": 30, "midday": 15, "eod": 30, "_default": 15},
    "client_block": {"kasorb": 120, "lpfa": 240, "_default": 60},
    "payroll": 60,
    "_default": 30,
}

# ---------------- Helpers ---------------- #

def parse_iso_with_tz(iso_str: str) -> datetime:
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = LON.localize(dt)
    return dt

def task_id_parts(task_id: str) -> List[str]:
    return (task_id or "").split(":")

def duration_for(row: Dict[str, Any]) -> int:
    dtype = row.get("deadline_type") or ""
    tid = row.get("task_id") or ""
    parts = task_id_parts(tid)
    rules = DURATION_RULES.get(dtype, DURATION_RULES["_default"])

    def pick(mapping, key, default):
        if isinstance(mapping, int): return mapping
        if isinstance(mapping, dict):
            if key in mapping: return mapping[key]
            return mapping.get("_default", default)
        return default

    if dtype in ("daily_checkin","school_run","client_block","health_routine","pet_care","school_exception"):
        for idx in (2, 3):
            if len(parts) > idx:
                key = parts[idx]
                m = pick(rules, key, DURATION_RULES["_default"])
                if isinstance(m, int): return m
    if isinstance(rules, int): return rules
    return DURATION_RULES["_default"]

def summary_for(row: Dict[str, Any]) -> str:
    dtype = row.get("deadline_type") or ""
    parts = task_id_parts(row.get("task_id",""))
    seg = lambda i, d="": parts[i] if len(parts) > i else d

    if dtype == "health_routine":
        return {
            "insulin_rybelsus_morning": "Morning Insulin + Rybelsus",
            "meds_morning": "Morning Medications",
            "bsl_morning": "BSL (Morning)",
            "bsl_lunch": "BSL (Lunch)",
            "bsl_predinner": "BSL (Pre-Dinner)",
            "meds_insulin_evening": "Evening Medications + Insulin",
            "bsl_bedtime": "BSL (Bedtime)",
        }.get(seg(2), "Health Routine")

    if dtype == "pet_care":
        return {
            "loki_breakfast": "Loki Breakfast",
            "loki_snack_1": "Loki Snack #1",
            "loki_snack_2": "Loki Snack #2",
            "loki_snack_3": "Loki Snack #3",
            "loki_dinner": "Loki Dinner",
            "litter_tray_scoop": "Litter Tray — Daily Scoop",
        }.get(seg(2), "Loki Care")

    if dtype == "school_run":
        return "School Run (Morning)" if seg(2)=="morning" else ("School Run (PM)" if seg(2)=="afternoon" else "School Run")

    if dtype == "bs_school_run":
        return "BS School Run"

    if dtype == "school_exception":
        if seg(3) == "earlyfinish":
            try:
                t = parse_iso_with_tz(row["fixed_date"]).astimezone(LON).strftime("%H:%M")
                return f"School: Early Finish {t}"
            except Exception:
                return "School: Early Finish"
        if seg(3) == "closure": return "School: Closed (INSET/Closure)"
        return "School Exception"

    if dtype == "daily_checkin":
        return {"morning":"Morning Check-in with Vizzy","midday":"Midday Check-in with Vizzy","eod":"End-of-Day Check-in with Vizzy"}.get(seg(2),"Check-in")

    if dtype == "client_block":
        return {"kasorb":"Kasorb Client Block","lpfa":"LPFA Client Block"}.get(seg(2),"Client Block")

    if dtype == "payroll":
        return f"Payroll — {row.get('client_code','')}" or "Payroll"

    return dtype.replace("_"," ").title() or "Helios Fixed"

def iso_rfc3339(dt: datetime) -> str:
    if dt.tzinfo is None: dt = LON.localize(dt)
    return dt.isoformat()

def get_service_from_env():
    token_path = os.getenv("CALENDAR_TOKEN_PATH", "token.json")
    scopes = [os.getenv("CALENDAR_SCOPES", DEFAULT_SCOPE)]
    if "," in scopes[0]:
        scopes = [s.strip() for s in scopes[0].split(",")]
    creds = Credentials.from_authorized_user_file(token_path, scopes)
    service = build("calendar", "v3", credentials=creds)
    cal_id = os.getenv("FIXED_CALENDAR_ID")
    if not cal_id:
        print("ERROR: FIXED_CALENDAR_ID missing in .env"); sys.exit(2)
    return service, cal_id

# -------- Bulk fetch & throttling -------- #

def bulk_fetch_existing_map(service, calendar_id: str, time_min: datetime, time_max: datetime) -> Dict[str, Dict[str,Any]]:
    """Return map: helios_task_id -> event"""
    events_map: Dict[str, Dict[str,Any]] = {}
    page_token = None
    while True:
        res = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min.astimezone(timezone.utc).isoformat().replace("+00:00","Z"),
            timeMax=time_max.astimezone(timezone.utc).isoformat().replace("+00:00","Z"),
            singleEvents=True,
            maxResults=2500,
            pageToken=page_token,
            orderBy="startTime",
        ).execute()
        for ev in res.get("items", []):
            priv = (ev.get("extendedProperties") or {}).get("private") or {}
            hid = priv.get("helios_task_id")
            if hid: events_map[hid] = ev
        page_token = res.get("nextPageToken")
        if not page_token: break
    return events_map

def throttle(qps: float):
    """Sleep to keep API under quota; add jitter to avoid bursts."""
    if qps <= 0: qps = 3.0
    base = 1.0 / qps
    time.sleep(base + random.uniform(0, base * 0.4))

# -------- Core upsert helpers -------- #

def build_event_body(row: Dict[str,Any]) -> Dict[str,Any]:
    tid = row["task_id"]
    dt  = parse_iso_with_tz(row["fixed_date"])
    minutes = duration_for(row)
    start, end = dt, dt + timedelta(minutes=minutes)
    return {
        "summary": summary_for(row),
        "start": {"dateTime": iso_rfc3339(start)},
        "end":   {"dateTime": iso_rfc3339(end)},
        "extendedProperties": {"private": {"helios_task_id": tid}},
        "description": f"Helios fixed commitment ({row.get('deadline_type','')})",
    }

def needs_update(existing: Dict[str,Any], body: Dict[str,Any]) -> bool:
    def get_dt(ev, which):
        return ev.get(which, {}).get("dateTime") or ev.get(which, {}).get("date")
    fields = [
        ("summary", existing.get("summary"), body.get("summary")),
        ("start",   get_dt(existing,"start"), get_dt(body,"start")),
        ("end",     get_dt(existing,"end"),   get_dt(body,"end")),
    ]
    return any(a != b for _, a, b in fields)

# -------- DB -------- #

def fetch_task_meta(conn, window_days: int):
    cur = conn.cursor()
    cur.execute("""
        SELECT task_id, task_type, deadline_type, fixed_date, client_code, calendar_blocked
        FROM task_meta
        WHERE task_type='fixed_date'
          AND calendar_blocked=1
          AND datetime(fixed_date) BETWEEN datetime('now','localtime','-1 day')
                                       AND datetime('now','localtime', ?)
        ORDER BY fixed_date ASC
    """, (f"+{window_days} days",))
    return [
        dict(task_id=r[0], task_type=r[1], deadline_type=r[2],
             fixed_date=r[3], client_code=r[4], calendar_blocked=r[5])
        for r in cur.fetchall()
    ]

# -------- Main -------- #

def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to helios.db (SQLite)")
    ap.add_argument("--window-days", type=int, default=365)
    ap.add_argument("--apply", action="store_true", help="Write to Google Calendar")
    ap.add_argument("--dry-run", action="store_true", help="Force dry run")
    ap.add_argument("--fast-dry-run", action="store_true", help="Bulk prefetch instead of per-row lookups")
    ap.add_argument("--count-only", action="store_true", help="No Google API calls; just count DB rows")
    ap.add_argument("--qps", type=float, default=3.5, help="Max write queries per second (apply mode)")
    args = ap.parse_args()

    dry_run = (not args.apply) or args.dry_run

    if not os.path.exists(args.db):
        print(f"ERROR: DB not found: {args.db}"); sys.exit(2)
    conn = sqlite3.connect(args.db)

    service, calendar_id = get_service_from_env()
    rows = fetch_task_meta(conn, args.window_days)
    print(f"Loaded fixed commitments in window: {len(rows)}")

    now_local = datetime.now(LON)
    time_min = now_local - timedelta(days=1)
    time_max = now_local + timedelta(days=args.window_days)

    if args.count_only:
        print(f"[COUNT-ONLY] rows in window: {len(rows)} (no Google calls)"); return

    # Fast DRY-RUN path (bulk fetch once; classify create vs exists)
    if dry_run and args.fast_dry_run:
        print("FAST DRY-RUN: bulk fetching existing Helios events …")
        existing_map = bulk_fetch_existing_map(service, calendar_id, time_min, time_max)
        existing_ids = set(existing_map.keys())
        creates = sum(1 for r in rows if r["task_id"] not in existing_ids)
        exists  = len(rows) - creates
        print(f"[DRY RUN/FAST] would create: {creates}, already-exist (skip/update): {exists}")
        print("Use --apply to write changes, or run precise dry-run without --fast-dry-run for update counts.")
        return

    # Precise DRY-RUN or APPLY — still efficient: bulk prefetch map once
    print("Prefetching existing events map …")
    existing_map = bulk_fetch_existing_map(service, calendar_id, time_min, time_max)

    creates = updates = skips = 0
    for row in rows:
        try:
            body = build_event_body(row)
            existing = existing_map.get(row["task_id"])
            if existing:
                if needs_update(existing, body):
                    if dry_run:
                        updates += 1
                    else:
                        service.events().patch(calendarId=calendar_id, eventId=existing["id"], body=body).execute()
                        updates += 1
                        throttle(args.qps)
                else:
                    skips += 1
            else:
                if dry_run:
                    creates += 1
                else:
                    ev = service.events().insert(calendarId=calendar_id, body=body).execute()
                    creates += 1
                    # track in map so subsequent rows with same ID (shouldn't happen) won't re-create
                    existing_map[row["task_id"]] = ev
                    throttle(args.qps)
        except HttpError as e:
            print(f"Google API error on task_id={row['task_id']}: {e}")

    if dry_run:
        print(f"[DRY RUN] would create: {creates}, update: {updates}, skip: {skips}")
        print("Use --apply to write changes.")
    else:
        print(f"Applied — created: {creates}, updated: {updates}, skipped: {skips}")

if __name__ == "__main__":
    main()
