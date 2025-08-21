import sqlite3, os, sys

DB = r"C:\Helios\core_py\db\helios.db"

DDL_NEW = """
CREATE TABLE IF NOT EXISTS unknown_senders_new (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  message_id TEXT NOT NULL,
  subject TEXT DEFAULT '',
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  hits INTEGER NOT NULL DEFAULT 1,
  resolved INTEGER NOT NULL DEFAULT 0
);
"""

# Copy while filling defaults for missing columns
COPY_SQL = """
INSERT INTO unknown_senders_new (id,email,message_id,subject,first_seen,last_seen,hits,resolved)
SELECT
  id,
  lower(trim(email)),
  COALESCE(message_id, ''),                      -- default for legacy rows
  COALESCE(subject, ''),
  COALESCE(first_seen, datetime('now')),
  COALESCE(last_seen, first_seen, datetime('now')),
  COALESCE(hits, 1),
  COALESCE(resolved, 0)
FROM unknown_senders;
"""

RENAME_SQL = """
DROP TABLE unknown_senders;
ALTER TABLE unknown_senders_new RENAME TO unknown_senders;
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_unknown_email ON unknown_senders(email);",
    "CREATE INDEX IF NOT EXISTS idx_unknown_last_seen ON unknown_senders(last_seen);",
    "CREATE UNIQUE INDEX IF NOT EXISTS uniq_unknown_email_msg ON unknown_senders(email, message_id);",
]

ENSURE_META = """
INSERT OR IGNORE INTO allowlist_meta (id, version, updated_at)
VALUES (1, 1, datetime('now'));
"""

def table_has_column(cur, table, col):
    cur.execute(f"PRAGMA table_info({table});")
    return any(r[1].lower() == col.lower() for r in cur.fetchall())

def table_exists(cur, table):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table,))
    return cur.fetchone() is not None

con = sqlite3.connect(DB)
con.execute("PRAGMA foreign_keys=OFF;")
cur = con.cursor()

try:
    if table_exists(cur, "unknown_senders"):
        # If missing message_id, rebuild the table
        if not table_has_column(cur, "unknown_senders", "message_id"):
            cur.executescript(DDL_NEW)
            cur.executescript(COPY_SQL)
            cur.executescript(RENAME_SQL)
    else:
        # Fresh create with the right schema
        cur.executescript(DDL_NEW)
        cur.executescript(RENAME_SQL.replace("DROP TABLE unknown_senders;", ""))  # rename only

    # Indexes + meta
    for idx in INDEXES:
        cur.execute(idx)
    cur.executescript(ENSURE_META)

    con.commit()
    print("✅ unknown_senders migrated/ensured; indexes + allowlist_meta OK.")
finally:
    con.close()
