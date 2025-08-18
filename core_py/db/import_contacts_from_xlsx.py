
"""
Import contacts from "Client Directory.xlsx" into Helios SQLite DB.

Mapping (from the uploaded sheet "Client Directory"):
- Client Name        -> clients.name
- Emails             -> client_emails.email (split on comma/semicolon/whitespace)
- Domains            -> client_domains.domain (supports "*.domain.com" for wildcard)
- Initials           -> folded into clients.notes (append line)
- Client Number      -> folded into clients.notes (append line)
- Unique Tag         -> appended to clients.tags_json list
- Clickup Folder Name-> folded into clients.notes (append line)
- Default List       -> folded into clients.notes (append line)

Prereqs:
- You already ran the migration creating clients, client_emails, client_domains, unknown_senders, allowlist_meta.
- Place this script next to your helios.db and "Client Directory.xlsx" (or adjust paths below).

Usage (PowerShell):
    python import_contacts_from_xlsx.py

Safe to re-run: uses INSERT OR IGNORE for emails/domains; updates client if name exists.
"""

import sqlite3, pathlib, uuid, json, re
from datetime import datetime
import pandas as pd

DB_PATH  = pathlib.Path("helios.db")
XLSX_PATH = pathlib.Path("Client Directory.xlsx")
SHEET_NAME = "Client Directory"  # inferred from your upload

def uuid4(): return str(uuid.uuid4())
def now_iso(): return datetime.utcnow().replace(microsecond=0).isoformat()

def normalize_email(addr: str) -> str:
    addr = (addr or "").strip().lower()
    if not addr: return ""
    if "@" not in addr: return ""
    local, domain = addr.split("@", 1)
    if "+" in local:
        local = local.split("+", 1)[0]
    return f"{local}@{domain}"

def normalize_domain(domain: str) -> str:
    return (domain or "").strip().lower()

def split_multi(value: str) -> list[str]:
    if not value: return []
    # split on commas, semicolons, or whitespace
    parts = re.split(r"[,\s;]+", value)
    return [p for p in (x.strip() for x in parts) if p]

def ensure_tables(conn: sqlite3.Connection):
    # quick sanity check
    need = {"clients","client_emails","client_domains","allowlist_meta"}
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    missing = need - have
    if missing:
        raise SystemExit(f"❌ DB is missing required tables: {sorted(missing)}.\nRun the migration first.")

def upsert_client(conn: sqlite3.Connection, name: str, notes_lines: list[str], tags: list[str]) -> str:
    now = now_iso()
    row = conn.execute("SELECT id, tags_json, notes FROM clients WHERE name = ?", (name,)).fetchone()
    if row:
        cid = row[0]
        # merge tags (unique, case-sensitive)
        old_tags = []
        try:
            old_tags = json.loads(row[1] or "[]")
        except Exception:
            old_tags = []
        merged = sorted(set([t for t in old_tags + (tags or []) if t]))
        # append notes (non-dup roughly)
        old_notes = row[2] or ""
        extra = "\n".join([ln for ln in notes_lines if ln and ln not in old_notes])
        new_notes = (old_notes + ("\n" if old_notes and extra else "") + extra) if extra else old_notes
        conn.execute("UPDATE clients SET tags_json=?, notes=?, updated_at=? WHERE id=?",
                     (json.dumps(merged), new_notes, now, cid))
        return cid
    else:
        cid = uuid4()
        conn.execute("""INSERT INTO clients (id, name, phone, notes, tags_json, active, created_at, updated_at)
                        VALUES (?,?,?,?,?,?,?,?)""",
                     (cid, name, None, "\n".join([ln for ln in notes_lines if ln]), json.dumps(tags or []), 1, now, now))
        return cid

def bump_allowlist_version(conn: sqlite3.Connection):
    conn.execute("UPDATE allowlist_meta SET version = version + 1, updated_at = ?", (now_iso(),))

def run():
    if not DB_PATH.exists():
        raise SystemExit(f"❌ DB not found: {DB_PATH.resolve()}")
    if not XLSX_PATH.exists():
        raise SystemExit(f"❌ Excel not found: {XLSX_PATH.resolve()}")

    df = pd.read_excel(XLSX_PATH, sheet_name=SHEET_NAME)
    # Normalize expected columns
    cols = {c.lower().strip(): c for c in df.columns}
    col = lambda key: cols.get(key)

    want = ["client name","emails","domains"]
    for w in want:
        if col(w) is None:
            raise SystemExit(f"❌ Expected column '{w}' not found in sheet. Found columns: {list(df.columns)}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    ensure_tables(conn)

    added_clients = 0
    updated_clients = 0
    added_emails = 0
    added_domains = 0

    for _, r in df.iterrows():
        name = str(r[col("client name")]).strip() if not pd.isna(r[col("client name")]) else ""
        if not name: 
            continue

        # Build notes and tags from auxiliary columns if present
        notes_lines = []
        tags = []

        for aux_name in ["Initials","Client Number","Clickup Folder Name","Default List"]:
            k = aux_name.lower()
            if col(k) and not pd.isna(r[col(k)]):
                notes_lines.append(f"{aux_name}: {str(r[col(k)])}")

        if col("unique tag") and not pd.isna(r[col("unique tag")]):
            tags.append(str(r[col("unique tag")]).strip())

        # Upsert client
        cur = conn.execute("SELECT id FROM clients WHERE name=?", (name,)).fetchone()
        cid_before = cur[0] if cur else None
        cid = upsert_client(conn, name, notes_lines, tags)
        if cid_before:
            updated_clients += 1
        else:
            added_clients += 1

        # Emails
        emails_val = r[col("emails")]
        for e in split_multi("" if pd.isna(emails_val) else str(emails_val)):
            e_norm = normalize_email(e)
            if not e_norm: 
                continue
            try:
                conn.execute("""INSERT OR IGNORE INTO client_emails (id, client_id, email, created_at)
                                VALUES (?,?,?,?)""", (uuid4(), cid, e_norm, now_iso()))
                added_emails += 1
            except sqlite3.IntegrityError:
                pass

        # Domains
        domains_val = r[col("domains")]
        for d in split_multi("" if pd.isna(domains_val) else str(domains_val)):
            wildcard = 1 if d.startswith("*.") else 0
            dom = d[2:] if d.startswith("*.") else d
            dom = normalize_domain(dom)
            if not dom:
                continue
            try:
                conn.execute("""INSERT OR IGNORE INTO client_domains (id, client_id, domain, wildcard, created_at)
                                VALUES (?,?,?,?,?)""", (uuid4(), cid, dom, wildcard, now_iso()))
                added_domains += 1
            except sqlite3.IntegrityError:
                pass

    bump_allowlist_version(conn)
    conn.commit()
    conn.close()

    print("✅ Import complete")
    print(f"Clients: +{added_clients} added, ~{updated_clients} updated")
    print(f"Emails added:   +{added_emails}")
    print(f"Domains added:  +{added_domains}")

if __name__ == "__main__":
    run()
