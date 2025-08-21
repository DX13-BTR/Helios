from contextlib import contextmanager
from sqlalchemy.orm import Session
from core_py.db.database import get_engine, get_session as _get_session

# Expose the SQLAlchemy engine globally
engine = get_engine()

def get_session() -> Session:
    """
    FastAPI dependency version — use with Depends(get_session) inside routes.
    """
    db = _get_session()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def db_session() -> Session:
    """
    Proper context manager for scripts, services, or anywhere outside FastAPI.
    Usage:
        with db_session() as db:
            db.query(...)
    """
    db = _get_session()
    try:
        yield db
    finally:
        db.close()
