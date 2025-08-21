# Compare SQLite (DB) vs SQLAlchemy models using the *real* Base from core_py.db
import os
from sqlalchemy import create_engine, inspect

DB_PATH = os.environ.get("DB_PATH", "core_py/db/helios.db")  # adjust if needed

# 1) Import the REAL Base (lives in core_py/db/__init__.py)
from core_py.db import Base  # this exposes Base used by the app
# 2) Import models so classes register on Base.metadata
import core_py.models  # noqa: F401  (side-effect: table registration)

if not os.path.exists(DB_PATH):
    raise SystemExit(f"DB file not found: {DB_PATH}")

from core_py.settings import settings
engine = create_engine(settings.DB_URL)
insp = inspect(engine)

db_tables = set(insp.get_table_names())
model_tables = set(Base.metadata.tables.keys())

print("=== TABLE PRESENCE CHECK ===")
print("DB → Models (missing in models):", sorted(db_tables - model_tables) or "OK")
print("Models → DB (missing in db):    ", sorted(model_tables - db_tables) or "OK")

# Optional: show per-table column diffs (lightweight)
for t in sorted(db_tables & model_tables):
    db_cols = {c["name"] for c in insp.get_columns(t)}
    model_cols = {c.name for c in Base.metadata.tables[t].columns}
    extra_db = sorted(db_cols - model_cols)
    extra_model = sorted(model_cols - db_cols)
    if extra_db or extra_model:
        print(f"--- {t} ---")
        if extra_db:
            print("  Columns only in DB:    ", extra_db)
        if extra_model:
            print("  Columns only in models:", extra_model)
