# calendar_routes.py
# Updated to add /calendar/today_normalized with link extraction AND client matches

from fastapi import APIRouter
from fastapi.responses import RedirectResponse, JSONResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
import os
from datetime import datetime
import pytz
import re
from typing import List, Dict
import requests  # used to call contacts lookup

router = APIRouter()

URL_RE = re.compile(r"(https?://[^\s)<>]+)")
CONTACTS_LOOKUP_URL = "http://localhost:3333/api/contacts/lookup-by-attendees"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET_FILE = os.path.abspath(os.path.join(BASE_DIR, "..", "client_secret.json"))
TOKEN_FILE = os.path.join(BASE_DIR, "helios_token_rw.json")
SCOPES = ["https://www.googleapis.com/auth/calendar"]
REDIRECT_URI = "http://localhost:3333/api/calendar/callback"


@router.get("/auth")
def initiate_oauth():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    auth_url, _ = flow.authorization_url(prompt="consent")
    return RedirectResponse(auth_url)


@router.get("/callback")
def oauth_callback(code: str):
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    with open(TOKEN_FILE, "w") as token_file:
        token_file.write(creds.to_json())
    return JSONResponse({"message": "Authorization complete."})


@router.get("/events")
def list_calendar_events():
    if not os.path.exists(TOKEN_FILE):
        return JSONResponse({"error": "No token found. Please authenticate first."}, status_code=401)

    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(GoogleRequest())
                with open(TOKEN_FILE, "w") as token_file:
                    token_file.write(creds.to_json())
            except Exception as e:
                return JSONResponse({"error": f"Token refresh failed: {str(e)}"}, status_code=403)
        else:
            return JSONResponse({"error": "Invalid or expired credentials."}, status_code=403)

    service = build("calendar", "v3", credentials=creds)
    try:
        events_result = service.events().list(
            calendarId="primary",
            maxResults=10,
            singleEvents=True,
            orderBy="startTime",
            fields="items(id,summary,start,end,location,description)",
        ).execute()
        events = events_result.get("items", [])
        return JSONResponse({"events": events})
    except Exception as e:
        return JSONResponse({"error": f"Failed to fetch events: {str(e)}"}, status_code=500)


def _extract_links(text: str) -> List[str]:
    if not text:
        return []
    # strip simple HTML and normalize whitespace
    clean = re.sub(r"<[^>]*>", " ", text or "")
    clean = clean.replace("\xa0", " ")
    clean = re.sub(r"\s+", " ", clean).strip()
    urls = list(dict.fromkeys(URL_RE.findall(clean)))  # dedupe, preserve order
    return urls


def _origins(urls: List[str]) -> List[str]:
    out = []
    for u in urls:
        if "clickup.com" in u:
            out.append("clickup")
        elif "todoist.com" in u:
            out.append("todoist")
        elif "reclaim.ai" in u:
            out.append("reclaim")
        else:
            out.append("web")
    # stable unique with mild preference (clickup>todoist>reclaim>web)
    pref = {"clickup": 3, "todoist": 2, "reclaim": 1, "web": 0}
    uniq, seen = [], set()
    for o in out:
        if o not in seen:
            seen.add(o)
            uniq.append(o)
    uniq.sort(key=lambda o: pref.get(o, 0), reverse=True)
    return uniq


@router.get("/today_normalized")
def today_normalized():
    if not os.path.exists(TOKEN_FILE):
        return JSONResponse({"error": "No token found. Please authenticate first."}, status_code=401)

    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(GoogleRequest())
                with open(TOKEN_FILE, "w") as token_file:
                    token_file.write(creds.to_json())
            except Exception as e:
                return JSONResponse({"error": f"Token refresh failed: {e}"}, status_code=403)
        else:
            return JSONResponse({"error": "Invalid or expired credentials."}, status_code=403)

    service = build("calendar", "v3", credentials=creds)
    tz = pytz.timezone("Europe/London")
    now = datetime.now(tz)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

    try:
        events_result = service.events().list(
            calendarId="primary",
            timeMin=start_of_day,
            timeMax=end_of_day,
            singleEvents=True,
            orderBy="startTime",
            fields=(
                "items(id,summary,start,end,location,description,"
                "attendees(email,responseStatus),recurringEventId,hangoutLink,updated)"
            ),
        ).execute()
    except Exception as e:
        return JSONResponse({"error": f"Failed to fetch today events: {e}"}, status_code=500)

    items = events_result.get("items", [])
    out: List[Dict] = []

    for e in items:
        start = e.get("start", {})
        end = e.get("end", {})
        links = _extract_links(e.get("description") or "")
        attendees = [a.get("email") for a in (e.get("attendees") or []) if a.get("email")]

        # Optional: call contacts API to enrich with matched clients
        matched_clients = []
        if attendees:
            try:
                resp = requests.get(CONTACTS_LOOKUP_URL, params=[("emails", em) for em in attendees], timeout=3.5)
                if resp.ok:
                    matched_clients = resp.json().get("matches", [])
            except Exception:
                # fail-soft; we still return the event even if contacts lookup fails
                matched_clients = []

        out.append(
            {
                "id": e.get("id"),
                "title": e.get("summary"),
                "start": start.get("dateTime") or start.get("date"),  # note: all-day events return date only
                "end": end.get("dateTime") or end.get("date"),
                "location": e.get("location"),
                "source_links": links,
                "origin": _origins(links),
                "attendees": attendees,
                "matched_clients": matched_clients,
                "recurringEventId": e.get("recurringEventId"),
                "hangoutLink": e.get("hangoutLink"),
                "updated": e.get("updated"),
            }
        )

    return JSONResponse({"events": out})


@router.get("/today")
def calendar_today():
    try:
        if not os.path.exists(TOKEN_FILE):
            return JSONResponse({"error": "No token found. Please authenticate first."}, status_code=401)

        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(GoogleRequest())
                    with open(TOKEN_FILE, "w") as token_file:
                        token_file.write(creds.to_json())
                except Exception as e:
                    return JSONResponse({"error": f"Token refresh failed: {e}"}, status_code=403)
            else:
                return JSONResponse({"error": "Invalid or expired credentials."}, status_code=403)

        service = build("calendar", "v3", credentials=creds)
        tz = pytz.timezone("Europe/London")
        now = datetime.now(tz)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

        events_result = service.events().list(
            calendarId="primary",
            timeMin=start_of_day,
            timeMax=end_of_day,
            singleEvents=True,
            orderBy="startTime",
            fields="items(id,summary,start,end,location,description)",
        ).execute()

        return JSONResponse({"events": events_result.get("items", [])})

    except Exception as e:
        return JSONResponse({"error": f"Failed to fetch today events: {str(e)}"}, status_code=500)
