# core_py/integrations/email/email_triage_clickup_legacy.py
"""
Legacy email triage client.
- Fetches allowlist from Helios:  GET {HELIOS_API}/api/allowlist
- Posts normalized email payloads: POST {HELIOS_API}/api/tasks/from-email
- Supports CLI args to test with real senders, and --debug to print loaded allowlist.
"""

import os
import time
import argparse
from typing import Tuple, Dict, Any, Iterable
import requests

HELIOS_API = os.getenv("HELIOS_API", "http://localhost:3333")
HELIOS_TOKEN = os.getenv("HELIOS_TOKEN", "")
TIMEOUT = int(os.getenv("HELIOS_HTTP_TIMEOUT", "20"))


def _headers() -> Dict[str, str]:
    hdrs = {"Content-Type": "application/json"}
    if HELIOS_TOKEN:
        hdrs["Authorization"] = f"Bearer {HELIOS_TOKEN}"
    return hdrs


def _to_lower_set(items: Iterable[str]) -> set:
    return {(s or "").strip().lower() for s in items if isinstance(s, str) and s}


def load_allowlist_from_helios(debug: bool = False) -> Tuple[set, set]:
    """
    Returns (emails_set, domains_set), all lowercased.
    API shape:
      {
        "emails": ["a@b.com", ...],
        "domains": [{"domain":"example.com","wildcard":false}, ...],
        ...
      }
    """
    url = f"{HELIOS_API}/api/allowlist"
    r = requests.get(url, headers=_headers(), timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()

    emails = _to_lower_set(data.get("emails", []))

    raw_domains = data.get("domains", [])
    domain_strings = []
    for d in raw_domains:
        if isinstance(d, str):
            domain_strings.append(d)
        elif isinstance(d, dict):
            val = d.get("domain") or d.get("value")
            if isinstance(val, str):
                domain_strings.append(val)
    domains = _to_lower_set(domain_strings)

    if debug:
        # Print a small, readable summary without flooding output
        print(f"[debug] loaded {len(emails)} emails, {len(domains)} domains")
        show_e = sorted(list(emails))[:10]
        show_d = sorted(list(domains))[:10]
        if show_e:
            print("[debug] sample emails:", ", ".join(show_e))
        if show_d:
            print("[debug] sample domains:", ", ".join(show_d))

    return emails, domains


def is_allowed(sender_email: str, emails: set, domains: set) -> bool:
    s = (sender_email or "").strip().lower()
    if not s:
        return False
    if s in emails:
        return True
    dom = s.split("@")[-1] if "@" in s else ""
    # NOTE: exact domain match only; wildcard=False in your API currently.
    return dom in domains


def create_helios_task(
    *,
    message_id: str,
    sender: str,
    subject: str,
    content: str,
    gmail_link: str | None = None,
    thread_id: str | None = None,
    start_ts: int | None = None,
    due_ts: int | None = None,
    source_label: str | None = None,
    dry_run: bool = False,
    dual_write_clickup: bool = False,
    priority: str = "normal",
    client_hint: str | None = None,
) -> Dict[str, Any]:
    url = f"{HELIOS_API}/api/tasks/from-email"
    payload = {
        "message_id": message_id,
        "sender": sender,
        "subject": subject or "(no subject)",
        "content": content or "",
        "gmail_link": gmail_link,
        "thread_id": thread_id,
        "received_ts": int(time.time() * 1000),
        "start_ts": start_ts,
        "due_ts": due_ts,
        "source_label": source_label,
        "dry_run": dry_run,
        "dual_write_clickup": dual_write_clickup,
        "priority": priority,
        "client_hint": client_hint,
    }
    r = requests.post(url, headers=_headers(), json=payload, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def main():
    parser = argparse.ArgumentParser(description="Legacy Email Triage → Helios forwarder")
    parser.add_argument("--sender", default="example@clientdomain.com", help="From email to test with")
    parser.add_argument("--subject", default="Demo subject", help="Subject line")
    parser.add_argument("--content", default="Body text", help="Email content/text")
    parser.add_argument("--gmail-link", default="https://mail.google.com/mail/u/0/#inbox/XYZ", help="Gmail link")
    parser.add_argument("--thread-id", default="gmail-thread-XYZ", help="Gmail thread id")
    parser.add_argument("--label", default="triage/inbox", help="Source label")
    parser.add_argument("--message-id", default="demo-msg-123", help="Message id (use a unique value when not in dry_run)")
    parser.add_argument("--priority", default="normal", choices=["low", "normal", "high"])
    parser.add_argument("--client-hint", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no DB write)")
    parser.add_argument("--dual-write", action="store_true", help="Also create a ClickUp task (if server supports)")
    parser.add_argument("--debug", action="store_true", help="Print loaded allowlist summary")
    args = parser.parse_args()

    emails, domains = load_allowlist_from_helios(debug=args.debug)
    if is_allowed(args.sender, emails, domains):
        print("Allowed — forwarding to Helios.")
        resp = create_helios_task(
            message_id=args.message_id,
            sender=args.sender,
            subject=args.subject,
            content=args.content,
            gmail_link=args.gmail_link,
            thread_id=args.thread_id,
            source_label=args.label,
            dry_run=args.dry_run,
            dual_write_clickup=args.dual_write,
            priority=args.priority,
            client_hint=args.client_hint,
        )
        print("Response:", resp)
    else:
        print(f"Sender not in allowlist — skipping. (sender={args.sender})")


if __name__ == "__main__":
    main()
