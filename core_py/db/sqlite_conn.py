# core_py/db/sqlite_conn.py
import os, sqlite3, threading, contextlib

# Point to your actual DB file
DEFAULT_DB_PATH = os.getenv("DB_PATH", r"C:\Helios\core_py\db\helios.db")

_local = threading.local()

def get_conn(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        _local.conn = conn
    return conn

@contextlib.contextmanager
def tx():
    c = get_conn()
    try:
        yield c
        c.commit()
    except:
        c.rollback()
        raise

def q_all(sql: str, params=()):
    return [dict(r) for r in get_conn().execute(sql, params).fetchall()]

def q_one(sql: str, params=()):
    r = get_conn().execute(sql, params).fetchone()
    return dict(r) if r else None

def q_exec(sql: str, params=()):
    return get_conn().execute(sql, params)
