# core_py/db/session.py
from sqlalchemy.orm import Session
from core_py.db.database import get_engine, get_session as _get_session

# Expose engine for code that imports it
engine = get_engine()

def get_session() -> Session:
    # Return a Session object in a contextmanager-friendly way
    # Old code: `with get_session() as s: ...`
    return _get_session()
