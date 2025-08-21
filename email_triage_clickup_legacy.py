# C:\Helios\core_py\email_triage_clickup.py (revised)
import os, json, base64, sqlite3, time, sys, io, random
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

# Gmail
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Google Sheets (service account)
from google.oauth2.service_account import Credentials as SACreds
from googleapiclient.discovery import build as build_sheets

# --- Ensure UTF-8 safe stdout on Windows consoles / subprocess readers ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# -----------------------------------------------------------------------------
# ENV + CONFIG
# -----------------------------------------------------------------------------
load_dotenv(dotenv_path=r"C:\Helios\core_py\.env")

GMAIL_USER            = os.getenv("GMAIL_USER")
TOKEN_PATH            = os.getenv("GMAIL_TOKEN_PATH")
CRED_PATH             = os.getenv("GMAIL_CREDENTIALS_PATH")
SCOPES                = [s.strip() for s in os.getenv("GMAIL_SCOPES","").split(",") if s.strip()]

CLICKUP_TOKEN         = os.getenv("CLICKUP_API_KEY")
CLICKUP_LIST_ID       = os.getenv("CLICKUP_EMAIL_LIST_ID")
CLICKUP_ASSIGNEE_ID   = os.getenv("CLICKUP_USER_ID")

DB_PATH               = os.getenv("DB_PATH", r"C:\Helios\core_py\db\helios.db")
EMAIL_TRIAGE_MODE     = os.getenv("EMAIL_TRIAGE_MODE","allowlist-enforce").lower()  # off|shadow|allowlist-enforce
TRIAGE_VERBOSE        = os.getenv("TRIAGE_VERBOSE","0") == "1"

# Full sweep vs incremental
FULL                  = os.getenv("TRIAGE_FULL_RESYNC", "0") == "1"
LOOKBACK_DAYS         = int(os.getenv("TRIAGE_LOOKBACK_DAYS", "7"))

# Per-thread vs per-email
TRIAGE_THREAD_MODE    = os.getenv("TRIAGE_THREAD_MODE", "per_email")  # per_email | per_thread

# Sheets creds
GOOGLE_SA_JSON        = os.getenv("GOOGLE_SA_JSON")
TRIAGE_SHEET_ID       = os.getenv("TRIAGE_SHEET_ID")

required = {
    "GMAIL_USER": GMAIL_USER, "GMAIL_TOKEN_PATH": TOKEN_PATH, "GMAIL_CREDENTIALS_PATH": CRED_PATH, "GMAIL_SCOPES": SCOPES,
    "CLICKUP_API_KEY": CLICKUP_TOKEN, "CLICKUP_EMAIL_LIST_ID": CLICKUP_LIST_ID, "CLICKUP_USER_ID": CLICKUP_ASSIGNEE_ID,
    "GOOGLE_SA_JSON": GOOGLE_SA_JSON, "TRIAGE_SHEET_ID": TRIAGE_SHEET_ID
}
missing = [k for k,v in required.items() if not v]
if missing:
    raise EnvironmentError(f"Missing .env keys: {', '.join(missing)}")

# -----------------------------------------------------------------------------
# HTTP session (requests) with retries + backoff that respects Retry-After
# -----------------------------------------------------------------------------

def _make_retrying_session(total: int = 4, backoff: float = 0.6) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=total,
        read=total,
        connect=total,
        status=total,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET","POST","PUT","DELETE","PATCH","OPTIONS","HEAD"]),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

SESSION = _make_retrying_session()
CLICKUP_HEADERS = {"Authorization": CLICKUP_TOKEN, "Content-Type": "application/json"}


def clickup_request(method: str, url: str, *, max_loops: int = 5, min_sleep: float = 0.0, **kwargs) -> requests.Response:
    """Robust wrapper around ClickUp requests.
    - Uses a shared retrying SESSION (handles transient 5xx/429 with Retry-After)
    - Additionally loops on 429 to strictly honor Retry-After, with jitter
    - Optional min_sleep to pace consecutive calls
    """
    last: Optional[requests.Response] = None
    if min_sleep > 0:
        time.sleep(min_sleep)

    for attempt in range(1, max_loops + 1):
        resp = SESSION.request(method, url, timeout=60, **kwargs)
        # Success or non-429 error → return and let caller decide
        if resp.status_code != 429:
            return resp

        # 429 handling: respect Retry-After (seconds), fall back to exp backoff + jitter
        retry_after_hdr = resp.headers.get("Retry-After")
        if retry_after_hdr and retry_after_hdr.isdigit():
            sleep_s = int(retry_after_hdr)
        else:
            # exponential backoff with jitter
            sleep_s = min(30, (2 ** (attempt - 1)))
        # small jitter to avoid thundering herd
        sleep_s = sleep_s + random.uniform(0.25, 0.75)
        if TRIAGE_VERBOSE:
            print(f"⚠️ ClickUp 429 on {method} {url} — sleeping {sleep_s:.1f}s (attempt {attempt}/{max_loops})")
        time.sleep(sleep_s)
        last = resp

    return last if last is not None else resp  # return last response after exhausting loops

# Convenience wrappers

def cu_post(path: str, json_body: dict):
    return clickup_request(
        "POST",
        f"https://api.clickup.com/api/v2/{path}",
        headers=CLICKUP_HEADERS,
        json=json_body,
        min_sleep=0.1,  # tiny pacing between writes
    )


def cu_put(path: str, json_body: dict):
    return clickup_request(
        "PUT",
        f"https://api.clickup.com/api/v2/{path}",
        headers=CLICKUP_HEADERS,
        json=json_body,
        min_sleep=0.1,
    )

# -----------------------------------------------------------------------------
# DB (processed_emails + unknown capture + thread mapping)
# -----------------------------------------------------------------------------
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS processed_emails (
  message_id   TEXT PRIMARY KEY,
  thread_id    TEXT,
  label        TEXT,
  processed_at TIMESTAMP
)""")
cur.execute("""
CREATE TABLE IF NOT EXISTS triage_unknowns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT,
  domain TEXT NOT NULL,
  first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  seen_count INTEGER NOT NULL DEFAULT 1,
  last_subject TEXT
)""")
cur.execute("""
CREATE TABLE IF NOT EXISTS thread_tasks (
  thread_id     TEXT PRIMARY KEY,
  task_id       TEXT NOT NULL,
  last_email_at TIMESTAMP
)""")
conn.commit()


def upsert_unknown(sender_email: str, subject: str):
    email = (sender_email or "").strip().lower()
    domain = email.split("@")[-1] if "@" in email else email
    cur.execute("SELECT id, seen_count FROM triage_unknowns WHERE email = ?", (email,))
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE triage_unknowns SET seen_count=?, last_seen_at=CURRENT_TIMESTAMP, last_subject=? WHERE id=?",
            (row[1]+1, subject[:200] if subject else None, row[0])
        )
    else:
        cur.execute(
            "INSERT INTO triage_unknowns (email, domain, last_subject) VALUES (?,?,?)",
            (email or None, domain, subject[:200] if subject else None)
        )
    conn.commit()


def get_thread_task(thread_id: str):
    cur.execute("SELECT task_id FROM thread_tasks WHERE thread_id=?", (thread_id,))
    row = cur.fetchone()
    return row[0] if row else None


def set_thread_task(thread_id: str, task_id: str, email_dt: datetime):
    cur.execute("""INSERT INTO thread_tasks (thread_id, task_id, last_email_at)
                   VALUES (?,?,?)
                   ON CONFLICT(thread_id) DO UPDATE SET task_id=excluded.task_id, last_email_at=excluded.last_email_at""",
                (thread_id, task_id, email_dt))
    conn.commit()


def add_comment_to_task(task_id: str, text: str):
    cu_post(f"task/{task_id}/comment", {"comment_text": text, "notify_all": True})


def reopen_task(task_id: str, new_due_ts: Optional[int] = None):
    body = {"status": "to do"}  # change if your open status differs
    if new_due_ts is not None:
        body["due_date"] = new_due_ts
    return cu_put(f"task/{task_id}", body)

# -----------------------------------------------------------------------------
# Allow-list from Google Sheets
# -----------------------------------------------------------------------------

def load_allowlist():
    sa = SACreds.from_service_account_info(
        json.loads(GOOGLE_SA_JSON),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly"
        ],
    )
    svc = build_sheets("sheets", "v4", credentials=sa)
    rng = "Client Directory!A:H"  # Emails / Domains tab
    values = svc.spreadsheets().values().get(
        spreadsheetId=TRIAGE_SHEET_ID, range=rng
    ).execute().get("values", [])
    if not values:
        return set(), set()
    header = [h.strip().lower() for h in values[0]]
    ix_e = header.index("emails")  if "emails"  in header else None
    ix_d = header.index("domains") if "domains" in header else None

    emails, domains = set(), set()
    for row in values[1:]:
        if ix_e is not None and ix_e < len(row) and row[ix_e]:
            for e in row[ix_e].split(","):
                e = e.strip().lower()
                if e: emails.add(e)
        if ix_d is not None and ix_d < len(row) and row[ix_d]:
            for d in row[ix_d].split(","):
                d = d.strip().lower()
                if d: domains.add(d)
    return emails, domains


ALLOW_EMAILS, ALLOW_DOMAINS = load_allowlist()
ALLOW_TS = time.time()
print(f"✅ Allow-list loaded: {len(ALLOW_EMAILS)} emails, {len(ALLOW_DOMAINS)} domains")


def refresh_allowlist_if_needed():
    global ALLOW_EMAILS, ALLOW_DOMAINS, ALLOW_TS
    if time.time() - ALLOW_TS > 300:  # refresh every 5 min
        ALLOW_EMAILS, ALLOW_DOMAINS = load_allowlist()
        ALLOW_TS = time.time()
        print(f"🔄 Allow-list refreshed: {len(ALLOW_EMAILS)} emails, {len(ALLOW_DOMAINS)} domains")


def is_allowed(sender_email: str) -> bool:
    if not sender_email: return False
    email = sender_email.strip().lower()
    domain = email.split("@")[-1] if "@" in email else email
    if email in ALLOW_EMAILS:
        return True
    parts = domain.split(".")
    for i in range(len(parts)-1):             # subdomain suffix match
        d = ".".join(parts[i:])
        if d in ALLOW_DOMAINS:
            return True
    if domain in ALLOW_DOMAINS:
        return True
    return False

# -----------------------------------------------------------------------------
# Gmail auth + labels
# -----------------------------------------------------------------------------
creds = None
if os.path.exists(TOKEN_PATH):
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(CRED_PATH, SCOPES)
        creds = flow.run_local_server(port=0)
    with open(TOKEN_PATH, "w") as token:
        token.write(creds.to_json())

gmail_service = build("gmail", "v1", credentials=creds)

label_results = gmail_service.users().labels().list(userId="me").execute()
label_map = {l["name"]: l["id"] for l in label_results.get("labels", [])}
target_labels = ["1: to respond", "2: FYI", "4: notification"]
label_ids = {l: label_map[l] for l in target_labels if l in label_map}
if TRIAGE_VERBOSE:
    print("Labels found →", label_ids)

# -----------------------------------------------------------------------------
# Fetch messages (FULL rescan or incremental with pagination)
# -----------------------------------------------------------------------------

def fetch_messages(service, label_id):
    q = None                               # FULL rescan = no query
    if not FULL and LOOKBACK_DAYS > 0:     # incremental
        q = f"newer_than:{LOOKBACK_DAYS}d"

    results = []
    req = service.users().messages().list(userId="me", labelIds=[label_id], q=q)
    while True:
        resp = req.execute()
        results.extend(resp.get("messages", []))
        token = resp.get("nextPageToken")
        if not token:
            break
        req = service.users().messages().list(userId="me", labelIds=[label_id], q=q, pageToken=token)
    return results


def extract_text_body(payload):
    parts = []
    def walk(p):
        if p.get("mimeType") == "text/plain":
            data = p.get("body", {}).get("data")
            if data:
                parts.append(base64.urlsafe_b64decode(data).decode(errors="ignore"))
        elif "parts" in p:
            for sub in p["parts"]:
                walk(sub)
    walk(payload)
    return "\n".join(parts).strip()


def pick_sender(headers):
    # Prefer human sender: From → Reply-To → Sender
    h = {x["name"].lower(): x["value"] for x in headers}
    for key in ("From","Reply-To","Sender","from","reply-to","sender"):
        if key in h:
            addr = parseaddr(h[key])[1].lower()
            if addr:
                return addr
    return ""

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

total_created = 0
total_skipped = 0
total_bumped  = 0

for label_name, label_id in label_ids.items():
    refresh_allowlist_if_needed()
    messages = fetch_messages(gmail_service, label_id)
    print(f"📩 {label_name}: {len(messages)} messages to scan "
          f"({'FULL' if FULL else f'last {LOOKBACK_DAYS}d'})")

    for m in messages:
        msg_id = m["id"]; thread_id = m["threadId"]

        # De-dupe per message
        cur.execute("SELECT 1 FROM processed_emails WHERE message_id = ?", (msg_id,))
        if cur.fetchone():
            continue

        try:
            msg = gmail_service.users().messages().get(userId="me", id=msg_id, format="full").execute()
        except Exception as e:
            print(f"❌ Fetch error {msg_id}: {e}")
            continue

        payload = msg.get("payload", {})
        headers = payload.get("headers", [])
        subject   = next((h["value"] for h in headers if h["name"]=="Subject"), "(No Subject)")
        date_str  = next((h["value"] for h in headers if h["name"]=="Date"), None)
        sender    = pick_sender(headers)

        if TRIAGE_VERBOSE:
            print(f"— {label_name} :: {sender} :: {subject[:80]}")

        # Enforce allow-list
        allowed = is_allowed(sender)
        if EMAIL_TRIAGE_MODE in ("allowlist-enforce", "shadow") and not allowed:
            upsert_unknown(sender, subject)
            total_skipped += 1
            if EMAIL_TRIAGE_MODE == "shadow":
                print(f"👀 SHADOW: would skip {sender} :: {subject}")
            else:
                print(f"🚫 Skipped (not allowed): {sender} :: {subject}")
                cur.execute(
                    "INSERT INTO processed_emails (message_id, thread_id, label, processed_at) VALUES (?,?,?,?)",
                    (msg_id, thread_id, label_name, datetime.now(timezone.utc))
                )
                conn.commit()
                continue

        # Timing & body
        email_date = parsedate_to_datetime(date_str) if date_str else datetime.now(timezone.utc)
        start_ts = int(email_date.replace(hour=9, minute=0).timestamp() * 1000)
        due_ts   = int((email_date + timedelta(days=1)).replace(hour=17, minute=0).timestamp() * 1000)
        body     = extract_text_body(payload)

        # Gmail thread link for this message
        gmail_link = f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"

        # Per-thread behavior
        if TRIAGE_THREAD_MODE == "per_thread":
            existing = get_thread_task(thread_id)
            if existing:
                # Reopen/update; if missing, recreate
                preview = (body or "").strip().replace("\r"," ").replace("\n"," ")
                if len(preview) > 200: preview = preview[:200] + "…"
                rr = reopen_task(existing, new_due_ts=due_ts)
                if rr.status_code == 404:  # task deleted? create again
                    task_data = {
                        "name": f"{sender} - {subject[:120]}",
                        "content": f"Reply in Gmail: {gmail_link}\n\n{body}",
                        "assignees": [CLICKUP_ASSIGNEE_ID],
                        "tags": ["email"],
                        "start_date": start_ts,
                        "due_date": due_ts,
                        "status": "to do"
                    }
                    cr = cu_post(f"list/{CLICKUP_LIST_ID}/task", task_data)
                    if cr.ok:
                        new_task_id = cr.json().get("id")
                        set_thread_task(thread_id, new_task_id, email_date)
                        print(f"✅ Task re-created for thread (prior task missing): {subject}")
                    else:
                        print(f"❌ ClickUp create after missing task failed: {cr.status_code} - {cr.text}")
                else:
                    # include Gmail link in the bump comment
                    add_comment_to_task(
                        existing,
                        f"New email on thread from **{sender}** · **{subject}**\n"
                        f"Reply in Gmail: {gmail_link}\n\n{preview}"
                    )
                    print(f"🔁 Bumped existing task {existing}: {subject}")
                    total_bumped += 1

                # mark processed
                cur.execute(
                    "INSERT INTO processed_emails (message_id, thread_id, label, processed_at) VALUES (?,?,?,?)",
                    (msg_id, thread_id, label_name, datetime.now(timezone.utc))
                )
                conn.commit()
                continue  # next message

        # First message in thread OR per_email mode → create task
        preview = (body or "").strip().replace("\r"," ").replace("\n"," ")
        if len(preview) > 400:
            preview = preview[:400] + "…"

        task_data = {
            "name": f"{sender} - {subject[:120]}",
            "content": f"Reply in Gmail: {gmail_link}\n\n{preview}",
            "assignees": [CLICKUP_ASSIGNEE_ID],
            "tags": ["email"],
            "start_date": start_ts,
            "due_date": due_ts,
            "status": "to do"
        }
        r = cu_post(f"list/{CLICKUP_LIST_ID}/task", task_data)
        if r.ok:
            task_id = r.json().get("id")
            print(f"✅ Task created: {subject}")
            if TRIAGE_THREAD_MODE == "per_thread":
                set_thread_task(thread_id, task_id, email_date)
            cur.execute(
                "INSERT INTO processed_emails (message_id, thread_id, label, processed_at) VALUES (?,?,?,?)",
                (msg_id, thread_id, label_name, datetime.now(timezone.utc))
            )
            conn.commit()
            total_created += 1
        else:
            print(f"❌ ClickUp error: {r.status_code} - {r.text}")

print(f"\nDone. Created {total_created} task(s); Bumped {total_bumped}; Skipped {total_skipped} (not allowed).")
conn.close()
