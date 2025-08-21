from datetime import datetime
import sqlite3

# Use Helios' connection helper so we target the same DB the app uses
from core_py.db.sqlite_conn import get_conn  # Helios v8 style

FIXED_KEYWORDS = {
    "vat_return": ["vat return", "vat"],
    "payroll": ["payroll", "fps", "eps"],
    "ct600": ["ct600", "corporation tax"],
    "cs01": ["cs01", "confirmation statement"],
    "sa100": ["sa100", "self assessment"],
    "sa800": ["sa800", "partnership return"],
    "cis_return": ["cis return", "cis"],
}

def guess_deadline_type(name: str) -> str | None:
    n = (name or "").lower()
    for dtype, kws in FIXED_KEYWORDS.items():
        if any(kw in n for kw in kws):
            return dtype
    return None

def run():
    con = get_conn()
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Ensure task_meta exists (in case Alembic pointed to a different DB)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS task_meta (
            task_id TEXT PRIMARY KEY,
            task_type TEXT DEFAULT 'flexible',
            deadline_type TEXT,
            fixed_date TEXT,
            calendar_blocked INTEGER DEFAULT 0,
            recurrence_pattern TEXT,
            client_code TEXT
        )
    """)

    # Pull the current triage snapshot
    cur.execute("SELECT id, name, due_date FROM triaged_tasks")
    rows = cur.fetchall()

    upserts = 0
    for r in rows:
        task_id = str(r["id"])
        dtype = guess_deadline_type(r["name"])
        is_fixed = dtype is not None

        fixed_iso = None
        if is_fixed and r["due_date"]:
            try:
                fixed_iso = datetime.utcfromtimestamp(int(r["due_date"]) / 1000.0).isoformat()
            except Exception:
                fixed_iso = None

        # UPSERT into SQLite (requires PRIMARY KEY on task_id)
        cur.execute("""
            INSERT INTO task_meta (task_id, task_type, deadline_type, fixed_date, calendar_blocked, recurrence_pattern, client_code)
            VALUES (?, ?, ?, ?, 0, NULL, NULL)
            ON CONFLICT(task_id) DO UPDATE SET
                task_type=excluded.task_type,
                deadline_type=COALESCE(excluded.deadline_type, task_meta.deadline_type),
                fixed_date=COALESCE(excluded.fixed_date, task_meta.fixed_date)
        """, (task_id, "fixed_date" if is_fixed else "flexible", dtype, fixed_iso))
        upserts += 1

    con.commit()
    try:
        con.close()
    except Exception:
        pass
    print(f"Seeded/updated task_meta rows: {upserts}")

if __name__ == "__main__":
    run()
