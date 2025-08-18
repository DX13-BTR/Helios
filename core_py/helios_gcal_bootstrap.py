"""
helios_gcal_bootstrap.py

Purpose
- Upgrade Google Calendar auth to FULL read/write scope.
- Create or find these calendars:
    - "Helios Fixed Commitments"
    - "Helios Flexible Suggestions"
- Print their calendar IDs for Helios config.
- Sanity test write access (creates then deletes a 2-min event).

Prereqs
    pip install google-auth-oauthlib google-api-python-client

Files
- Put your OAuth Desktop App file beside this script as: credentials.json
- This script will create/overwrite: token.json

Usage (Windows CMD)
    cd C:\Helios
    python helios_gcal_bootstrap.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/calendar"]
HERE = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(HERE, "credentials.json")
TOKEN_FILE = os.path.join(HERE, "token.json")

def get_service():
    """Return an authenticated Calendar API service with write scope."""
    creds = None

    # If a token exists but doesn't include write scope, delete it to force re-consent
    if os.path.exists(TOKEN_FILE):
        try:
            tmp = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            token_scopes = set(getattr(tmp, "scopes", []) or [])
            if "https://www.googleapis.com/auth/calendar" not in token_scopes:
                print("Existing token is read-only; deleting token.json to re-consent...")
                os.remove(TOKEN_FILE)
        except Exception:
            # Corrupt token: remove it
            try:
                os.remove(TOKEN_FILE)
            except Exception:
                pass

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    else:
        if not os.path.exists(CREDENTIALS_FILE):
            print(f"Missing {CREDENTIALS_FILE}. Download your OAuth Desktop App JSON from Google Cloud Console.")
            sys.exit(1)
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        # Opens a localhost browser window to complete OAuth
        creds = flow.run_local_server(port=0, prompt="consent")
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        print(f"Saved new token with scopes: {creds.scopes} -> {TOKEN_FILE}")

    return build("calendar", "v3", credentials=creds)

def ensure_calendar(service, summary: str) -> str:
    """Find an existing calendar by summary; create if missing. Return calendarId."""
    page_token = None
    while True:
        res = service.calendarList().list(pageToken=page_token, maxResults=250).execute()
        for entry in res.get("items", []):
            if entry.get("summary") == summary:
                cal_id = entry["id"]
                print(f"Found calendar: '{summary}' -> {cal_id}")
                return cal_id
        page_token = res.get("nextPageToken")
        if not page_token:
            break

    created = service.calendars().insert(body={"summary": summary}).execute()
    cal_id = created["id"]
    print(f"Created calendar: '{summary}' -> {cal_id}")
    # Ensure it appears in the user's list
    service.calendarList().insert(body={"id": cal_id}).execute()
    return cal_id

def sanity_write_test(service, cal_id: str) -> None:
    """Create a tiny event starting 10 minutes from now, then delete it."""
    start = datetime.utcnow() + timedelta(minutes=10)
    end = start + timedelta(minutes=2)
    body = {
        "summary": "Helios Write Test (auto-delete)",
        "start": {"dateTime": start.isoformat() + "Z"},
        "end": {"dateTime": end.isoformat() + "Z"},
        "extendedProperties": {"private": {"helios_write_test": "1"}},
    }
    ev = service.events().insert(calendarId=cal_id, body=body).execute()
    print("Write test event created:", ev.get("id"))
    service.events().delete(calendarId=cal_id, eventId=ev["id"]).execute()
    print("Write test event deleted ✓")

def main():
    try:
        service = get_service()
        fixed_cal_id = ensure_calendar(service, "Helios Fixed Commitments")
        sugg_cal_id  = ensure_calendar(service, "Helios Flexible Suggestions")

        # Optional: verify write access on fixed calendar
        sanity_write_test(service, fixed_cal_id)

        out = {
            "fixed_calendar_id": fixed_cal_id,
            "suggestions_calendar_id": sugg_cal_id,
            "token_file": TOKEN_FILE,
            "credentials_file": CREDENTIALS_FILE,
            "scopes": SCOPES,
        }
        print("\n=== Helios Calendar Bootstrap Complete ===")
        print(json.dumps(out, indent=2))
    except HttpError as e:
        print("Google API error:", e)
        sys.exit(2)

if __name__ == "__main__":
    main()
