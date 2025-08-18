# core_py/routes/schedule_routes.py
from __future__ import annotations

from fastapi import APIRouter, Query
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List
import os

# ---------------- Env & TZ ----------------
try:
    from dotenv import load_dotenv  # optional
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except Exception:
    pass

try:
    from zoneinfo import ZoneInfo  # py>=3.9
    TZ = ZoneInfo(os.getenv("HELIOS_TZ", "Europe/London"))
except Exception:
    TZ = None  # fallback

def _now() -> datetime:
    return datetime.now(TZ) if TZ else datetime.now()

def _iso(dt: datetime) -> str:
    return (dt if TZ is None else dt.astimezone(TZ)).isoformat()

router = APIRouter()

# ---------------- Helpers ----------------
def _mock_payload() -> Dict[str, Any]:
    now = _now()
    start_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "date": start_day.date().isoformat(),
        "timezone": os.getenv("HELIOS_TZ", "Europe/London"),
        "now": _iso(now),
        "calendar_source": "mock",
        "blocks": [],
        "tasks": [],
        "unallocatedTaskIds": [],
    }

def _context_from_title(title: str) -> str:
    t = (title or "").lower()
    if "deep work" in t: return "DeepWork"
    if "admin" in t: return "Admin"
    if "meeting" in t: return "Meeting"
    if "school run" in t or "bsl" in t or "med" in t: return "Personal"
    return "Comm"

def _event_time_iso(ev_time: Dict[str, Any]) -> str:
    # ev_time is either {"dateTime": "..."} or {"date": "YYYY-MM-DD"} for all-day
    if "dateTime" in ev_time and ev_time["dateTime"]:
        return ev_time["dateTime"]
    if "date" in ev_time and ev_time["date"]:
        d = ev_time["date"]
        if TZ:
            # treat all-day as midnight in TZ
            return _iso(datetime.fromisoformat(d + "T00:00:00").replace(tzinfo=TZ))
        return d + "T00:00:00"
    return _iso(_now())

def _first_existing_path(*env_names: str) -> Path | None:
    for name in env_names:
        val = os.getenv(name)
        if not val:
            continue
        p = Path(val.strip().strip('"').replace("\\\\", "\\"))
        if p.exists():
            return p
    return None

def _scopes_from_env() -> List[str]:
    # e.g. "https://www.googleapis.com/auth/calendar" or comma/space separated
    raw = os.getenv("CALENDAR_SCOPES") or os.getenv("HELIOS_GCAL_SCOPES")
    if raw:
        parts = [s.strip() for s in raw.replace(",", " ").split() if s.strip()]
        return parts or ["https://www.googleapis.com/auth/calendar"]
    # default to full scope (matches your existing token)
    return ["https://www.googleapis.com/auth/calendar"]

def _collect_calendar_ids() -> List[str]:
    ids: List[str] = []
    for key in ("FLEXIBLE_CALENDAR_ID", "FIXED_CALENDAR_ID", "GOOGLE_CALENDAR_ID"):
        v = os.getenv(key)
        if v:
            ids.append(v.strip())
    if not ids:
        ids.append("primary")
    return ids

# ---------------- Route ----------------
@router.get("/schedule/today")
def schedule_today(
    debug: bool = Query(default=False, description="Return raw event sample when true"),
):
    """
    Returns today's work blocks and tasks for the 'Today’s Schedule' UI.

    Env:
      HELIOS_GCAL_TOKEN_FILE / CALENDAR_TOKEN_PATH / GOOGLE_TOKEN_PATH -> token JSON
      CALENDAR_SCOPES (or HELIOS_GCAL_SCOPES) -> space/comma-separated scopes
      FLEXIBLE_CALENDAR_ID, FIXED_CALENDAR_ID, GOOGLE_CALENDAR_ID -> calendars to read
      HELIOS_ACCEPT_ALL_EVENTS=1 -> treat ALL events as blocks (for testing)
      HELIOS_TZ -> timezone, default Europe/London
      HELIOS_SCHEDULE_MODE=mock -> force mock
    """
    if os.getenv("HELIOS_SCHEDULE_MODE", "").lower() == "mock":
        return _mock_payload()

    token_path = _first_existing_path(
        "HELIOS_GCAL_TOKEN_FILE", "CALENDAR_TOKEN_PATH", "GOOGLE_TOKEN_PATH"
    )
    if not token_path:
        payload = _mock_payload()
        payload["calendar_source"] = "mock_fallback"
        payload["error"] = (
            "Token file not found via HELIOS_GCAL_TOKEN_FILE / CALENDAR_TOKEN_PATH / GOOGLE_TOKEN_PATH"
        )
        return payload

    try:
        from googleapiclient.discovery import build  # type: ignore
        from google.oauth2.credentials import Credentials  # type: ignore

        SCOPES = _scopes_from_env()
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        service = build("calendar", "v3", credentials=creds)

        cal_ids = _collect_calendar_ids()
        now = _now()
        # Midnight..midnight with buffer to avoid tz edge cases / cross-midnight events
        start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=2)
        end = start + timedelta(days=1, hours=4)

        all_events: List[Dict[str, Any]] = []
        per_cal_counts: Dict[str, int] = {}

        for cal_id in cal_ids:
            resp = service.events().list(
                calendarId=cal_id,
                timeMin=_iso(start),
                timeMax=_iso(end),
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            events = resp.get("items", [])
            per_cal_counts[cal_id] = len(events)

            # annotate source calendar on each event
            for e in events:
                e["_helios_calendar_id"] = cal_id
            all_events.extend(events)

        if debug:
            sample = [
                {
                    "calendar": e.get("_helios_calendar_id"),
                    "summary": e.get("summary"),
                    "start": e.get("start"),
                    "end": e.get("end"),
                    "ext_private": (e.get("extendedProperties") or {}).get("private", {}),
                }
                for e in all_events
            ]
            return {
                "date": start.date().isoformat(),
                "timezone": os.getenv("HELIOS_TZ", "Europe/London"),
                "now": _iso(now),
                "calendar_source": "google",
                "calendars": cal_ids,
                "events_found_total": len(all_events),
                "events_found_by_calendar": per_cal_counts,
                "sample": sample[:50],
            }

        accept_all = os.getenv("HELIOS_ACCEPT_ALL_EVENTS", "0") == "1"

        blocks: List[Dict[str, Any]] = []
        for ev in all_events:
            summary: str = ev.get("summary", "") or ""
            ext_private: Dict[str, Any] = (ev.get("extendedProperties") or {}).get("private") or {}

            is_block = (
                accept_all
                or ext_private.get("helios_block") == "true"
                or summary.startswith("[BLOCK]")
            )
            if not is_block:
                continue

            blocks.append({
                "id": ev.get("id"),
                "title": summary.replace("[BLOCK]", "").strip(),
                "context": _context_from_title(summary),
                "calendarEventId": ev.get("id"),
                "calendarUrl": ev.get("htmlLink"),
                "start": _event_time_iso(ev.get("start", {})),
                "end": _event_time_iso(ev.get("end", {})),
                "color": None,
                "assignedTaskIds": [],
                "notes": (ev.get("description") or "").strip(),
                "extended": {
                    "helios_origin": "gcal",
                    "calendar_id": ev.get("_helios_calendar_id"),
                    **ext_private,
                },
            })

        return {
            "date": (now.replace(hour=0, minute=0, second=0, microsecond=0)).date().isoformat(),
            "timezone": os.getenv("HELIOS_TZ", "Europe/London"),
            "now": _iso(now),
            "calendar_source": "google",
            "blocks": blocks,
            "tasks": [],
            "unallocatedTaskIds": [],
            "source_calendars": cal_ids,
        }

    except Exception as e:
        payload = _mock_payload()
        payload["calendar_source"] = "mock_fallback"
        payload["error"] = f"{type(e).__name__}: {e}"
        return payload
