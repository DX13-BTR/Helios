# /mnt/c/Helios/core_py/email_triage_clickup.py
# Gmail API → Helios: pull from specific triage labels only (read-only), allowlist, POST to /api/tasks/from-email.
# No label mutations. No spool. Idempotent via Helios' processed_emails table.

import os, re, base64, requests, argparse
from typing import Dict, Tuple, Optional, List

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

HELIOS_API   = os.getenv("HELIOS_API", "http://127.0.0.1:8000")
TIMEOUT      = int(os.getenv("HELIOS_HTTP_TIMEOUT", "20"))
GMAIL_TOKEN  = os.getenv("GMAIL_TOKEN", "/mnt/c/Helios/secrets/gmail_token.json")

# Comma-separated Gmail label names to pull from (exact names in your mailbox)
TRIAGE_LABELS = os.getenv("TRIAGE_LABELS", "1- to respond,2- FYI,4 - Notifications")

# Optional Gmail search bound to limit churn (keeps queries fast)
GMAIL_Q = os.getenv("GMAIL_Q", "newer_than:30d")

MAX_RESULTS = int(os.getenv("GMAIL_MAX_RESULTS", "100"))  # per label per page

def _h():
    h = {"Content-Type": "application/json"}
    tok = os.getenv("HELIOS_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h

def _allowlist() -> Tuple[set, set]:
    r = requests.get(f"{HELIOS_API}/api/allowlist", headers=_h(), timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    emails = {e.lower() for e in d.get("emails", []) if isinstance(e, str)}
    doms = set()
    for val in d.get("domains", []):
        if isinstance(val, str):
            doms.add(val.lower())
        elif isinstance(val, dict):
            v = (val.get("domain") or val.get("value") or "").lower()
            if v:
                doms.add(v)
    return emails, doms

def _allowed(addr: str, emails: set, doms: set) -> bool:
    if not addr:
        return False
    addr = addr.lower()
    if addr in emails:
        return True
    m = re.search(r'@([^> )]+)', addr)
    dom = m.group(1) if m else addr.split("@")[-1]
    return dom in doms

def _svc():
    if not os.path.exists(GMAIL_TOKEN):
        raise RuntimeError(f"GMAIL_TOKEN not found at {GMAIL_TOKEN}")
    # Token must already have scope: https://www.googleapis.com/auth/gmail.modify
    creds = Credentials.from_authorized_user_file(GMAIL_TOKEN, ["https://www.googleapis.com/auth/gmail.modify"])
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

def _label_map(service) -> Dict[str, str]:
    """name (lowercase) -> id"""
    items = service.users().labels().list(userId="me").execute().get("labels", [])
    return {l["name"].lower(): l["id"] for l in items}

def _hdr(msg: Dict, key: str) -> Optional[str]:
    for h in msg.get("payload", {}).get("headers", []):
        if h.get("name", "").lower() == key.lower():
            return h.get("value")
    return None

def _body_text(msg: Dict) -> str:
    def _dec(b64: str) -> str:
        try:
            return base64.urlsafe_b64decode(b64).decode("utf-8", "ignore")
        except Exception:
            return ""
    pl = msg.get("payload", {})
    if pl.get("mimeType") == "text/plain" and pl.get("body", {}).get("data"):
        return _dec(pl["body"]["data"])
    for p in pl.get("parts", []) or []:
        if p.get("mimeType") == "text/plain" and p.get("body", {}).get("data"):
            return _dec(p["body"]["data"])
    for p in pl.get("parts", []) or []:
        if p.get("mimeType") == "text/html" and p.get("body", {}).get("data"):
            import re as _re
            return _re.sub(r"<[^>]+>", " ", _dec(p["body"]["data"]))
    return msg.get("snippet", "")

def _post(payload: Dict) -> Dict:
    r = requests.post(f"{HELIOS_API}/api/tasks/from-email", headers=_h(), json=payload, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def run_once() -> int:
    emails, doms = _allowlist()
    service = _svc()
    name_to_id = _label_map(service)

    wanted_names = [s.strip() for s in TRIAGE_LABELS.split(",") if s.strip()]
    label_ids: List[Tuple[str, str]] = []
    for name in wanted_names:
        lid = name_to_id.get(name.lower())
        if not lid:
            print(f"[warn] Gmail label not found: {name}")
            continue
        label_ids.append((name, lid))
    if not label_ids:
        print("[error] No matching Gmail labels. Check TRIAGE_LABELS and mailbox labels.")
        return 1

    seen = set()
    created = dup = rej = fail = 0

    for (label_name, lid) in label_ids:
        try:
            page_token = None
            while True:
                res = service.users().messages().list(
                    userId="me",
                    labelIds=[lid],            # single label per request (OR across labels via loop)
                    q=GMAIL_Q,
                    maxResults=MAX_RESULTS,
                    pageToken=page_token
                ).execute()

                for m in res.get("messages", []):
                    mid = m["id"]
                    if mid in seen:  # if message appears under multiple triage labels, avoid double posting
                        continue
                    seen.add(mid)

                    msg = service.users().messages().get(
                        userId="me", id=mid, format="full",
                        metadataHeaders=["From","Subject","Message-Id","Date"]
                    ).execute()

                    from_full = _hdr(msg, "From") or ""
                    maddr = re.search(r"<([^>]+)>", from_full)
                    from_email = (maddr.group(1) if maddr else from_full).strip()

                    if not _allowed(from_email, emails, doms):
                        rej += 1
                        continue

                    subject = _hdr(msg, "Subject") or "(no subject)"
                    body    = _body_text(msg)
                    rfc_id  = _hdr(msg, "Message-Id")
                    recv_ms = int(msg.get("internalDate")) if msg.get("internalDate") else None
                    thread  = msg.get("threadId")
                    message_id = f"rfc:{rfc_id.strip('<>')}" if rfc_id else f"gmail:{mid}"

                    payload = {
                        "message_id": message_id,
                        "sender": from_email,
                        "subject": subject,
                        "content": body,
                        "gmail_link": None,
                        "thread_id": thread,
                        "received_ts": recv_ms,
                        "source_label": label_name,   # reflect your triage bucket exactly
                        "priority": "normal",
                        "client_hint": None,
                        "start_ts": None,
                        "due_ts": None,
                        "dry_run": False,
                        "dual_write_clickup": False,
                    }

                    try:
                        resp = _post(payload)
                        reason = (resp or {}).get("reason")
                        if reason == "duplicate":
                            dup += 1
                        elif reason == "rejected_allowlist":
                            rej += 1
                        else:
                            created += 1
                    except requests.HTTPError:
                        fail += 1
                    except Exception:
                        fail += 1

                page_token = res.get("nextPageToken")
                if not page_token:
                    break
        except HttpError:
            fail += 1
        except Exception:
            fail += 1

    print({"created": created, "duplicate": dup, "rejected": rej, "failed": fail})
    return 0 if fail == 0 else 1

def main():
    # Accept (and ignore) legacy flags like --spool so the scheduler doesn’t have to change immediately.
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--spool", action="store_true")
    _ = parser.parse_args()
    raise SystemExit(run_once())

if __name__ == "__main__":
    main()
