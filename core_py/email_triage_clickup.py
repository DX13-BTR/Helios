"""
Email triage → Helios (Postgres) forwarder.

Modes:
  1) single message (default via CLI args)
  2) spool mode (--spool): read JSON files from spool/incoming, post to /api/tasks/from-email,
     and move files to processed/duplicate/rejected/failed.

Environment:
  HELIOS_API           default: http://127.0.0.1:8000
  HELIOS_TOKEN         optional bearer token (not required locally)
  HELIOS_HTTP_TIMEOUT  default: 20 (seconds)
  HELIOS_SMOKE         "1" to emit one synthetic message (single mode only)

Spool locations (auto-detect WSL vs Windows):
  Windows: C:\Helios\spool\emails\{incoming,processed,duplicate,rejected,failed}
  WSL:     /mnt/c/Helios/spool/emails/{incoming,processed,duplicate,rejected,failed}
"""

import argparse
import glob
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Tuple

import requests

# ---- Config ----
HELIOS_API = os.getenv("HELIOS_API", "http://127.0.0.1:8000")
HELIOS_TOKEN = os.getenv("HELIOS_TOKEN", "")
TIMEOUT = int(os.getenv("HELIOS_HTTP_TIMEOUT", "20"))

WIN_BASE = r"C:\Helios\spool\emails"
WSL_BASE = "/mnt/c/Helios/spool/emails"
BASE = WSL_BASE if os.path.exists(WSL_BASE) else WIN_BASE
INCOMING = os.path.join(BASE, "incoming")
PROCESSED = os.path.join(BASE, "processed")
DUPLICATE = os.path.join(BASE, "duplicate")
REJECTED = os.path.join(BASE, "rejected")
FAILED = os.path.join(BASE, "failed")


def _headers() -> Dict[str, str]:
    hdrs = {"Content-Type": "application/json"}
    if HELIOS_TOKEN:
        hdrs["Authorization"] = f"Bearer {HELIOS_TOKEN}"
    return hdrs


def _to_lower_set(items: Iterable[str]) -> set:
    return {(s or "").strip().lower() for s in items if isinstance(s, str) and s}


def load_allowlist_from_helios(debug: bool = False) -> Tuple[set, set]:
    """
    GET {HELIOS_API}/api/allowlist → returns (emails_set, domains_set), lowercased.
    """
    url = f"{HELIOS_API}/api/allowlist"
    r = requests.get(url, headers=_headers(), timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()

    # API returns "emails": [...], "domains": either strings or {domain: "..."}; normalize
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
        print(f"[debug] loaded {len(emails)} emails, {len(domains)} domains")
        if emails:
            print("[debug] sample emails:", ", ".join(sorted(list(emails))[:10]))
        if domains:
            print("[debug] sample domains:", ", ".join(sorted(list(domains))[:10]))
    return emails, domains


def is_allowed(sender_email: str, emails: set, domains: set) -> bool:
    s = (sender_email or "").strip().lower()
    if not s:
        return False
    if s in emails:
        return True
    dom = s.split("@")[-1] if "@" in s else ""
    return dom in domains  # exact match; wildcard not used currently


def _now_ms() -> int:
    return int(time.time() * 1000)


def create_helios_task(
    *,
    message_id: str,
    sender: str,
    subject: str,
    content: str,
    gmail_link: Optional[str] = None,
    thread_id: Optional[str] = None,
    start_ts: Optional[int] = None,
    due_ts: Optional[int] = None,
    source_label: Optional[str] = None,
    dry_run: bool = False,
    dual_write_clickup: bool = False,
    priority: str = "normal",
    client_hint: Optional[str] = None,
    received_ts: Optional[int] = None,
) -> Dict[str, Any]:
    """
    POST to Helios ingestion endpoint (idempotent by message_id).
    """
    url = f"{HELIOS_API}/api/tasks/from-email"
    payload = {
        "message_id": message_id,
        "sender": sender,
        "subject": subject or "(no subject)",
        "content": content or "",
        "gmail_link": gmail_link,
        "thread_id": thread_id,
        "received_ts": received_ts or _now_ms(),
        "start_ts": start_ts,
        "due_ts": due_ts,
        "source_label": source_label,
        "dry_run": dry_run,
        "dual_write_clickup": dual_write_clickup,  # ignored by API now
        "priority": priority,
        "client_hint": client_hint,
    }
    r = requests.post(url, headers=_headers(), json=payload, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


# ---------- Single-message (CLI) ----------
def run_single(args) -> int:
    emails, domains = load_allowlist_from_helios(debug=args.debug)

    # Smoke message if requested
    if os.getenv("HELIOS_SMOKE") == "1":
        now = datetime.now(timezone.utc)
        args.message_id = args.message_id or f"smoke:{int(now.timestamp())}"
        args.sender = args.sender or "ops@example.com"
        args.subject = args.subject or "Scheduler smoke test"
        args.content = args.content or "hello from scheduled task"

    if not is_allowed(args.sender, emails, domains):
        print(f"[skip] sender not in allowlist: {args.sender}")
        return 0

    resp = create_helios_task(
        message_id=args.message_id,
        sender=args.sender,
        subject=args.subject,
        content=args.content,
        gmail_link=args.gmail_link,
        thread_id=args.thread_id,
        start_ts=args.start_ts,
        due_ts=args.due_ts,
        source_label=args.label,
        dry_run=args.dry_run,
        dual_write_clickup=args.dual_write,
        priority=args.priority,
        client_hint=args.client_hint,
        received_ts=args.received_ts,
    )
    print(resp)
    return 0


# ---------- Spool mode ----------
def _ensure_dirs():
    for d in (INCOMING, PROCESSED, DUPLICATE, REJECTED, FAILED):
        os.makedirs(d, exist_ok=True)


def _move(src: str, dst_dir: str):
    base = os.path.basename(src)
    dst = os.path.join(dst_dir, base)
    try:
        shutil.move(src, dst)
    except Exception:
        # worst case try copy+remove
        try:
            shutil.copy2(src, dst)
            os.remove(src)
        except Exception:
            pass


def run_spool(args) -> int:
    _ensure_dirs()
    emails, domains = load_allowlist_from_helios(debug=args.debug)

    files = sorted(glob.glob(os.path.join(INCOMING, "*.json")))
    created = dup = rej = fail = 0

    for path in files:
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                msg = json.load(f)

            sender = msg.get("from") or msg.get("sender") or ""
            if not is_allowed(sender, emails, domains):
                rej += 1
                print(f"[rejected] {path} sender={sender}")
                _move(path, REJECTED)
                continue

            # Map fields; tolerate different keys
            message_id = str(msg.get("id") or msg.get("message_id") or f"spool:{int(time.time()*1000)}")
            subject = msg.get("subject") or ""
            content = msg.get("text") or msg.get("body") or msg.get("html_stripped") or ""
            gmail_link = msg.get("gmail_link")
            thread_id = msg.get("thread_id")
            label = msg.get("label") or msg.get("folder")
            priority = msg.get("priority") or "normal"
            client_hint = msg.get("client_code") or msg.get("client_hint")

            # received_ts: prefer ms if present; otherwise try ISO string
            received_ts = msg.get("received_ts_ms")
            if not received_ts and isinstance(msg.get("received_at"), str):
                try:
                    received_ts = int(datetime.fromisoformat(msg["received_at"]).timestamp() * 1000)
                except Exception:
                    received_ts = None

            resp = create_helios_task(
                message_id=message_id,
                sender=sender,
                subject=subject,
                content=content,
                gmail_link=gmail_link,
                thread_id=thread_id,
                start_ts=msg.get("start_ts_ms"),
                due_ts=msg.get("due_ts_ms"),
                source_label=label,
                dry_run=False,
                dual_write_clickup=False,
                priority=priority,
                client_hint=client_hint,
                received_ts=received_ts,
            )

            reason = (resp or {}).get("reason")
            if reason == "duplicate":
                dup += 1
                _move(path, DUPLICATE)
            elif reason == "rejected_allowlist":
                rej += 1
                _move(path, REJECTED)
            else:
                created += 1
                _move(path, PROCESSED)

        except requests.HTTPError as e:
            fail += 1
            body = e.response.text if e.response is not None else str(e)
            print(f"[http_error] {path} status={getattr(e.response,'status_code',None)} body={body}", file=sys.stderr)
            _move(path, FAILED)
        except Exception as e:
            fail += 1
            print(f"[error] {path} err={e}", file=sys.stderr)
            _move(path, FAILED)

    print({"created": created, "duplicate": dup, "rejected": rej, "failed": fail})
    return 0 if fail == 0 else 1


def main():
    p = argparse.ArgumentParser(description="Email → Helios task ingester (scheduler friendly)")
    # single message flags (handy for smoke tests)
    p.add_argument("--sender", default="ops@example.com")
    p.add_argument("--subject", default="Demo subject")
    p.add_argument("--content", default="Body text")
    p.add_argument("--gmail-link", default=None)
    p.add_argument("--thread-id", default=None)
    p.add_argument("--label", default="triage/inbox")
    p.add_argument("--message-id", default=None)
    p.add_argument("--priority", default="normal", choices=["low", "normal", "high"])
    p.add_argument("--client-hint", default=None)
    p.add_argument("--start-ts", dest="start_ts", type=int, default=None)
    p.add_argument("--due-ts", dest="due_ts", type=int, default=None)
    p.add_argument("--received-ts", dest="received_ts", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--dual-write", action="store_true")
    p.add_argument("--debug", action="store_true")
    # spool mode
    p.add_argument("--spool", action="store_true", help="Process JSON files from the spool directory")

    args = p.parse_args()
    if args.spool:
        sys.exit(run_spool(args))
    else:
        sys.exit(run_single(args))


if __name__ == "__main__":
    main()
