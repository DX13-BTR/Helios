# core_py/db/session.py
# SQLAlchemy engine + session factory + FastAPI dependency + context manager.

import os
from typing import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Prefer env var; fallback to your local Postgres
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://helios:helios@localhost:5432/helios",
)

# Engine: pre_ping avoids stale connections across sleep/wake etc.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,  # SQLAlchemy 2.x style
)

# Session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    future=True,
)

# ----- FastAPI dependency -----
def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a DB session and always closes it.
    Use: Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----- Script/helper accessor -----
def get_session() -> Session:
    """
    Get a plain Session instance (caller manages commit/rollback/close).
    """
    return SessionLocal()

# ----- Back-compat context manager expected by tasks_routes.py -----
@contextmanager
def db_session() -> Iterator[Session]:
    """
    Context manager that opens a session, commits on success,
    rolls back on exception, then closes.
    Usage:
        with db_session() as db:
            ...
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
