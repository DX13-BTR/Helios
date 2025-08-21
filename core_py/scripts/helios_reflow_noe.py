#!/usr/bin/env python3
"""
Reflow the current Helios suggestion block:
- Finds the Helios-created event that is happening *right now* in your Suggestions calendar
- Shortens it to end "now"
- Creates a new Helios block from now → original end, pulling the next best tasks
  from the SAME bucket (client/systems/marketing/admin/personal)

Usage (Windows):
  set HELIOS_GCAL_TOKEN_FILE=C:\Helios\core_py\helios_token_rw.json
  python -m core_py.scripts.helios_reflow_now --calendar-id "%FLEXIBLE_CALENDAR_ID%"

Optional flags:
  --min-chunk 15           # don't reflow if <15 min left (default 15)
  --per-task-cap 60        # cap minutes a single task can claim in the new block (default 60; 0 = no cap)
  --dry-run                # show what would happen
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
from typing import List, Dict, Any, Optional

# ClickUp grouped-task source
from core_py.integrations.clickup_client import ClickUpClient

# ---- Google Calendar minimal client (read/update/insert) ----

class CalendarClient:
    def __init__(self, calendar_id: str):
        self.calendar_id = calendar_id
        self._svc = None

    def _service(self):
        if self._svc is not None:
            return self._svc
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from google.auth.transport.requests import Request as GoogleRequest

        token_candidates = [
            os.environ.get("HELIOS_GCAL_TOKEN_FILE") or "",
            os.path.join(os.path.dirname(__file__), "..", "helios_token_rw.json"),
            os.path.join(os.path.dirname(__file__), "..", "core_py", "helios_token_rw.json"),
            os.path.join(os.path.dirname(__file__), "helios_token_rw.json"),
        ]
        token_file = next((p for p in token_candidates if p and os.path.exists(p)), None)
        if not token_file:
            raise RuntimeError("Google token not found; set HELIOS_GCAL_TOKEN_FILE or place helios_token_rw.json nearby")
        scopes = ["https://www.googleapis.com/auth/calendar"]
        creds = Credentials.from_authorized_user_file(token_file, scopes)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(GoogleRequest())
                with open(token_file, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            else:
                raise RuntimeError("Invalid/expired Google credentials")
        self._svc = build("calendar", "v3", credentials=creds)
        return self._svc

    @staticmethod
    def _rfc3339(d: dt.datetime) -> str:
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.isoformat().replace("+00:00", "Z")

    def list_events(self, time_min: dt.datetime, time_max: dt.datetime) -> List[dict]:
        svc = self._service()
        events, page_token = [], None
        while True:
            res = svc.events().list(
                calendarId=self.calendar_id,
                timeMin=self._rfc3339(time_min),
                timeMax=self._rfc3339(time_max),
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
            ).execute()
            events.extend(res.get("items", []))
            page_token = res.get("nextPageToken")
            if not page_token:
                break
        return events

    def patch_event_end(self, event_id: str, new_end: dt.datetime) -> dict:
        svc = self._service()
        body = {"end": {"dateTime": self._rfc3339(new_end), "timeZone": "UTC"}}
        return svc.events().patch(calendarId=self.calendar_id, eventId=event_id, body=body).execute()

    def insert_event(self, event_body: dict) -> dict:
        svc = self._service()
        return svc.events().insert(calendarId=self.calendar_id, body=event_body).execute()

# ---- Helpers ----

LABELS = {
    "client_deep_work": "Client Deep Work",
    "systems_development": "Systems Development",
    "marketing_creative": "Marketing Creative",
    "admin_processing": "Admin Processing",
    "personal": "Personal",
}

def _parse_dt(x: Any) -> Optional[dt.datetime]:
    if not x:
        return None
    if isinstance(x, str):
        try:
            return dt.datetime.fromisoformat(x.replace("Z", "+00:00"))
        except Exception:
            return None
    if isinstance(x, dict) and "dateTime" in x:
        try:
            return dt.datetime.fromisoformat(x["dateTime"].replace("Z", "+00:00"))
        except Exception:
            return None
    return None

def _mins(d1: dt.datetime, d2: dt.datetime) -> int:
    return int((d2 - d1).total_seconds() // 60)

def _pick_next_tasks(
    bucket_key: str,
    minutes_needed: int,
    exclude_ids: set[str],
    per_task_cap: int,
) -> tuple[list[str], list[str]]:
    """
    Returns (task_ids, task_titles) to fill ~minutes_needed from the bucket,
    skipping exclude_ids. Cap each task's contribution by per_task_cap if >0.
    """
    cu = ClickUpClient()
    grouped = cu.fetch_tasks_grouped()  # plain dicts
    candidates = grouped.get(bucket_key, []) or []

    # sort by (priority, due_date)
    def _due_val(d):
        try: return int(d.get("due_date") or 0)
        except Exception: return 0
    candidates.sort(key=lambda d: ((d.get("priority") or 99), _due_val(d)))

    remaining = max(0, int(minutes_needed))
    picked_ids: list[str] = []
    picked_titles: list[str] = []

    for t in candidates:
        tid = str(t.get("id") or "")
        if not tid or tid in exclude_ids:
            continue
        rem = t.get("remaining_minutes")
        try:
            rem = int(rem) if rem is not None else None
        except Exception:
            rem = None
        if rem is None or rem <= 0:
            continue

        take = min(rem, remaining)
        if per_task_cap > 0:
            take = min(take, per_task_cap)
        if take <= 0:
            continue

        picked_ids.append(tid)
        picked_titles.append(str(t.get("name") or "(Untitled)"))
        remaining -= take
        if remaining <= 0:
            break

    return picked_ids, picked_titles

def _summary(bucket_key: str, titles: list[str], minutes: int) -> str:
    label = LABELS.get(bucket_key, bucket_key)
    h, m = divmod(max(0, int(minutes)), 60)
    dur = (f"{h}h " if h else "") + (f"{m}m" if m else "")
    if not titles:
        return f"[BLOCK] {label} (pull-forward) ({dur.strip()})"
    if len(titles) == 1:
        return f"[BLOCK] {label}: {titles[0]} ({dur.strip()})"
    if len(titles) == 2:
        return f"[BLOCK] {label}: {titles[0]}; {titles[1]} ({dur.strip()})"
    return f"[BLOCK] {label}: {titles[0]}; {titles[1]} +{len(titles)-2} more ({dur.strip()})"

def _description(bucket_key: str, task_ids: list[str], titles: list[str]) -> str:
    pairs = [f"{tid} :: {ttl}" for tid, ttl in zip(task_ids, titles)]
    return (
        "Auto-reflowed block (finished early).\n"
        f"Bucket: {bucket_key}\n"
        "Pulled forward:\n  - " + "\n  - ".join(pairs)
    )

# ---- Main ----

def main():
    ap = argparse.ArgumentParser(description="Reflow current Helios block by pulling next tasks forward")
    ap.add_argument("--calendar-id", type=str, default=os.getenv("FLEXIBLE_CALENDAR_ID"), help="Suggestions calendar ID")
    ap.add_argument("--min-chunk", type=int, default=15, help="Minimum minutes left to reflow")
    ap.add_argument("--per-task-cap", type=int, default=60, help="Max minutes a single task can claim in new block (0 = unlimited)")
    ap.add_argument("--dry-run", action="store_true", help="Preview only")
    args = ap.parse_args()

    if not args.calendar_id:
        raise SystemExit("Missing --calendar-id (or FLEXIBLE_CALENDAR_ID env)")

    now = dt.datetime.now(dt.timezone.utc)
    cal = CalendarClient(args.calendar_id)

    # Search a small window around 'now' to find the current Helios suggestion
    window_start = now - dt.timedelta(hours=6)
    window_end = now + dt.timedelta(hours=6)
    events = cal.list_events(window_start, window_end)

    current: Optional[dict] = None
    for e in events:
        start = _parse_dt(e.get("start"))
        end = _parse_dt(e.get("end"))
        if not start or not end:
            continue
        if not (start <= now < end):
            continue
        priv = ((e.get("extendedProperties") or {}).get("private") or {})
        if str(priv.get("helios_generated", "")).lower() != "true":
            continue
        current = e
        break

    if not current:
        print("No current Helios suggestion event found.")
        return

    start = _parse_dt(current.get("start"))
    end = _parse_dt(current.get("end"))
    if not start or not end:
        print("Current event has no parsable start/end; aborting.")
        return

    left_mins = _mins(now, end)
    if left_mins < args.min_chunk:
        print(f"Less than min-chunk left ({left_mins}m < {args.min_chunk}m). Nothing to do.")
        return

    priv = ((current.get("extendedProperties") or {}).get("private") or {})
    bucket_key = str(priv.get("helios_block_type") or "").strip()  # e.g., client_deep_work
    old_ids_str = str(priv.get("helios_task_ids") or "")
    already_ids = set([x for x in old_ids_str.split(",") if x])

    if not bucket_key:
        print("Current event is Helios-generated but has no block type; aborting.")
        return

    # Choose new tasks for remainder
    new_ids, new_titles = _pick_next_tasks(bucket_key, left_mins, exclude_ids=already_ids, per_task_cap=max(0, args.per_task_cap))
    if not new_ids:
        print("No candidate tasks to pull forward. Keeping the original event as-is.")
        return

    # Prepare new event body
    summary = _summary(bucket_key, new_titles, left_mins)
    description = _description(bucket_key, new_ids, new_titles)
    new_body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": CalendarClient._rfc3339(now), "timeZone": "UTC"},
        "end": {"dateTime": CalendarClient._rfc3339(end), "timeZone": "UTC"},
        "extendedProperties": {
            "private": {
                "helios_generated": "true",
                "helios_version": "v1",
                "helios_block_type": bucket_key,
                "helios_task_ids": ",".join(new_ids),
                "helios_idem": f"reflow:{bucket_key}:{now.isoformat()}",
            }
        },
    }

    print(f"Reflowing current block '{current.get('summary','(no title)')}'")
    print(f"- Original: {start.isoformat()} → {end.isoformat()}")
    print(f"- Now:      {now.isoformat()}  (left {left_mins} min)")
    print(f"- New tasks: {', '.join(new_titles)}")

    if args.dry_run:
        print("DRY RUN: not patching calendar.")
        return

    # 1) Shorten current event to end 'now'
    cal.patch_event_end(current["id"], now)

    # 2) Insert new event for the remaining window
    created = cal.insert_event(new_body)
    print(f"Created new Helios block: {created.get('id')}")

if __name__ == "__main__":
    main()
