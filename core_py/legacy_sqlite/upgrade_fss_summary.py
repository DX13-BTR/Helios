import sqlite3
from core_py.db.database import get_db_connection

COLUMNS = [
    ("uc_entitlement", "REAL"),
    ("uc_reduction", "REAL"),
    ("household_income", "REAL"),
    ("net_income", "REAL"),
    ("net_expenses", "REAL"),
    ("tee_paid", "REAL"),
    ("total_balance", "REAL"),
    ("drawdown_available", "REAL"),
    ("suggested_pay", "REAL"),
    ("suggested_savings", "REAL"),
]

conn = get_db_connection()
cur = conn.cursor()

for col, col_type in COLUMNS:
    try:
        cur.execute(f"ALTER TABLE fss_summary ADD COLUMN {col} {col_type}")
        print(f"✅ Added column: {col}")
    except sqlite3.OperationalError:
        print(f"ℹ️ Column already exists: {col}")

conn.commit()
conn.close()
print("✅ fss_summary table ready for HeliosDashboard v2")
