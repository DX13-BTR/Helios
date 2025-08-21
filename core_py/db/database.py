# core_py/db/database.py
"""
Central DB plumbing for Helios.

- Primary API (preferred):
    - get_engine() -> Engine
    - get_session() -> context manager yielding sqlalchemy.orm.Session
    - get_connection() -> context manager yielding sqlalchemy.engine.Connection

- Temporary compatibility API (for legacy code using sqlite3-style patterns):
    - get_db_connection_compat() -> context manager yielding an object with:
        .cursor().execute(...), .cursor().fetchone(), .cursor().fetchall(), .commit(), .rollback(), .close()

Environment:
    DATABASE_URL (recommended): e.g. postgresql+psycopg://user:pass@host:5432/helios
    DB_ECHO (optional): "1" to enable SQL echo for debugging

Notes:
    - Fallback to SQLite is provided ONLY for local/dev if DATABASE_URL is unset.
    - Remove the *_compat shim once all call sites use get_session()/get_connection().
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Optional, Sequence, Union, List

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, Connection, Result
from sqlalchemy.orm import sessionmaker, Session

# ---------------------------
# Configuration & Engine
# ---------------------------

_ENGINE: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def _get_database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return url

    # Dev fallback (kept to avoid breaking local setups without envs set)
    # You can remove this fallback once Postgres is mandatory.
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "helios.db"))
    return f"sqlite:///{db_path}"


def get_engine() -> Engine:
    """Return a process-wide Engine singleton."""
    global _ENGINE, _SessionLocal
    if _ENGINE is None:
        url = _get_database_url()
        echo = os.getenv("DB_ECHO", "0") == "1"

        # pool_pre_ping helps recover from stale connections
        # future=True enables 2.x style SQLAlchemy behaviors
        _ENGINE = create_engine(url, pool_pre_ping=True, future=True, echo=echo)

        # Configure session factory
        _SessionLocal = sessionmaker(
            bind=_ENGINE,
            autoflush=False,
            autocommit=False,
            future=True,
            expire_on_commit=False,
        )
    return _ENGINE


@contextmanager
def get_session() -> Iterable[Session]:
    """Yield a SQLAlchemy ORM Session with proper commit/rollback semantics."""
    global _SessionLocal
    if _SessionLocal is None:
        get_engine()  # initializes both engine and sessionmaker
    assert _SessionLocal is not None

    session: Session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_connection() -> Iterable[Connection]:
    """Yield a SQLAlchemy Connection; caller manages explicit transactions if desired."""
    engine = get_engine()
    with engine.connect() as conn:
        yield conn


# ---------------------------
# Optional: simple schema helper
# ---------------------------

def ensure_schema(schema_name: str = "helios") -> None:
    """
    Create schema if it doesn't exist. Safe in Postgres; no-ops on SQLite.
    """
    engine = get_engine()
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}";'))
            
from sqlalchemy import text

def insert_or_replace_task(task: dict) -> None:
    """
    Insert or update a task in triaged_tasks.
    Compatible with the old sqlite3 insert_or_replace_task, but works in Postgres.
    """
    sql = text("""
        INSERT INTO helios.triaged_tasks
        (id, name, priority, due_date, score, status, is_urgent, section, reason)
        VALUES (:id, :name, :priority, :due_date, :score, :status, :is_urgent, :section, :reason)
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            priority = EXCLUDED.priority,
            due_date = EXCLUDED.due_date,
            score = EXCLUDED.score,
            status = EXCLUDED.status,
            is_urgent = EXCLUDED.is_urgent,
            section = EXCLUDED.section,
            reason = EXCLUDED.reason
    """)
    from core_py.db.database import get_session  # safe to import here

    with get_session() as s:
        s.execute(sql, {
            "id": task["id"],
            "name": task["name"],
            "priority": task.get("priority"),
            "due_date": task.get("due_date"),
            "score": task.get("score"),
            "status": task["status"],
            "is_urgent": int(task.get("is_urgent", False)),
            "section": task.get("section", "general"),
            "reason": task.get("reason"),
        })
        s.commit()



# ---------------------------
# TEMPORARY COMPATIBILITY LAYER
# ---------------------------
# For legacy modules that still expect sqlite3-like behavior:
#   conn = get_db_connection_compat()
#   cur = conn.cursor()
#   cur.execute("SQL ...", params)
#   rows = cur.fetchall()
#   conn.commit()
#
# This adapter maps to SQLAlchemy under the hood. It supports:
#   - execute(sql, params) where params can be dict or list[dict]/list[tuple] (executemany)
#   - fetchone()/fetchall() on the last executed statement
#   - commit/rollback/close
#
# Remove this once all callers are migrated to get_session()/get_connection().

class _CompatCursor:
    def __init__(self, sa_connection: Connection):
        self._conn: Connection = sa_connection
        self._last_result: Optional[Result] = None

    def execute(
        self,
        sql: str,
        params: Optional[Union[Dict[str, Any], Sequence[Any], List[Dict[str, Any]], List[Sequence[Any]]]] = None,
    ):
        """
        Execute a statement.
        - If params is a list[dict] or list[tuple], we pass it directly (executemany semantics).
        - If params is a dict/tuple or None, we pass a single execution.
        """
        stmt = text(sql)

        if isinstance(params, list) and params and isinstance(params[0], (dict, tuple, list)):
            # executemany-style
            self._last_result = self._conn.execute(stmt, params)  # type: ignore[arg-type]
        else:
            # single-execution
            if params is None:
                self._last_result = self._conn.execute(stmt)
            else:
                self._last_result = self._conn.execute(stmt, params)  # type: ignore[arg-type]
        return self._last_result

    def fetchone(self):
        if not self._last_result:
            return None
        return self._last_result.fetchone()

    def fetchall(self):
        if not self._last_result:
            return []
        return self._last_result.fetchall()

    # For sqlite3 API parity (no-op here; SQLAlchemy manages resources via the connection)
    def close(self) -> None:
        self._last_result = None


class _CompatConnection:
    def __init__(self, sa_connection: Connection):
        self._conn: Connection = sa_connection
        self._cursor = _CompatCursor(sa_connection)
        self._trans = self._conn.begin()

    # sqlite3-like
    def cursor(self) -> _CompatCursor:
        return self._cursor

    def commit(self) -> None:
        if self._trans.is_active:
            self._trans.commit()
        # open a new transaction for subsequent operations, mirroring sqlite connection reuse
        self._trans = self._conn.begin()

    def rollback(self) -> None:
        if self._trans.is_active:
            self._trans.rollback()
        self._trans = self._conn.begin()

    def close(self) -> None:
        try:
            if self._trans.is_active:
                # if user forgot to commit/rollback, roll back to be safe
                self._trans.rollback()
        finally:
            self._conn.close()


@contextmanager
def get_db_connection_compat() -> Iterable[_CompatConnection]:
    """
    Context manager yielding a sqlite3-like connection wrapper.

    Example:
        with get_db_connection_compat() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            print(cur.fetchall())
            conn.commit()
    """
    with get_connection() as sa_conn:
        compat = _CompatConnection(sa_conn)
        try:
            yield compat
        finally:
            compat.close()
