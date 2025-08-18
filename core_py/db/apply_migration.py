import sqlite3, sys, pathlib
db = pathlib.Path("helios.db")
sql = pathlib.Path("001_add_contact_list.sqlite.sql")
assert db.exists(), f"DB not found: {db}"
assert sql.exists(), f"SQL not found: {sql}"
conn = sqlite3.connect(str(db))
try:
    conn.execute("PRAGMA foreign_keys = ON;")
    with open(sql, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    print("✅ Migration applied")
except Exception as e:
    conn.rollback()
    print("❌ Migration failed:", e)
    sys.exit(1)
finally:
    conn.close()
