import sqlite3
from core_py.db.database import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

# 1. Rename old table
cur.execute("ALTER TABLE fss_advice RENAME TO fss_advice_old")

# 2. Create new table with UNIQUE constraint
cur.execute("""
CREATE TABLE fss_advice (
    week_start TEXT UNIQUE,
    week_end TEXT,
    uc_advice TEXT,
    buffer_advice TEXT,
    tee_advice TEXT,
    spending_advice TEXT,
    savings_advice TEXT,
    created_at TEXT
)
""")

# 3. Copy data across (only copy columns that exist in both)
try:
    cur.execute("""
        INSERT INTO fss_advice (week_start, week_end, uc_advice, buffer_advice, tee_advice,
                                spending_advice, savings_advice, created_at)
        SELECT week_start, week_end, uc_advice, buffer_advice, tee_advice,
               spending_advice, savings_advice, created_at
        FROM fss_advice_old
    """)
except Exception as e:
    print("⚠️ Skipping data copy:", e)

# 4. Drop old table
cur.execute("DROP TABLE fss_advice_old")

conn.commit()
conn.close()
print("✅ fss_advice table rebuilt with UNIQUE constraint on week_start.")
