import sqlite3
from core_py.db.database import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

columns_to_add = [
    ("week_start", "TEXT"),
    ("week_end", "TEXT"),
    ("uc_advice", "TEXT"),
    ("buffer_advice", "TEXT"),
    ("tee_advice", "TEXT"),
    ("spending_advice", "TEXT"),
    ("savings_advice", "TEXT"),
    ("created_at", "TEXT")
]

for column, dtype in columns_to_add:
    try:
        cur.execute(f"ALTER TABLE fss_advice ADD COLUMN {column} {dtype}")
        print(f"✅ Added column: {column}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print(f"ℹ️ Column already exists: {column}")
        else:
            raise

conn.commit()
conn.close()
print("✅ fss_advice table upgraded successfully.")
