import sqlite3
import os
from core_py.db.database import get_db_connection

DB_PATH = os.getenv("HELIOS_DB_PATH")

if not DB_PATH or not os.path.exists(DB_PATH):
    print(f"❌ DB not found at {DB_PATH}")
    exit()

conn = get_db_connection()
cur = conn.cursor()

print(f"🔍 Inspecting DB: {DB_PATH}\n")

# --- 1. List all tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [t[0] for t in cur.fetchall()]
print("📋 Tables found:")
for t in tables:
    print(f"  - {t}")

print("\n--- Table Details ---")
for t in tables:
    print(f"\n🔹 Table: {t}")
    cur.execute(f"PRAGMA table_info({t})")
    cols = cur.fetchall()
    for col in cols:
        # col = (cid, name, type, notnull, dflt_value, pk)
        print(f"  {col[1]} ({col[2]}){' [PK]' if col[5] else ''}")

    # Show 5 sample rows
    cur.execute(f"SELECT * FROM {t} LIMIT 5;")
    rows = cur.fetchall()
    if rows:
        print("  Sample rows:")
        for row in rows:
            print(f"   {row}")
    else:
        print("  (empty)")

conn.close()
print("\n✅ DB inspection complete.")
