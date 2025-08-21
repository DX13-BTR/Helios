# core_py/db/session.py
from contextlib import contextmanager
from typing import Generator
from sqlalchemy.orm import Session, sessionmaker

# Use your existing engine factory
from core_py.db.database import get_engine

# Single engine for the app
engine = get_engine()

# Canonical session factory
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# ---- FastAPI dependency (use in route signatures) ---------------------------
def get_session() -> Generator[Session, None, None]:
    """
    FastAPI dependency:
        def endpoint(db: Session = Depends(get_session)): ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---- Plain function for non-route code --------------------------------------
def get_session_sync() -> Session:
    """
    Synchronous session getter for services/helpers/background jobs:
        db = get_session_sync()
        try:
            ...
        finally:
            db.close()
    """
    return SessionLocal()

# ---- Context manager for non-route code -------------------------------------
@contextmanager
def db_session() -> Generator[Session, None, None]:
    """
    Use in services/helpers/cron:
        with db_session() as db:
            ...
    Commits on success, rolls back on exception.
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
