import os
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# -------------------------------------------------------------------------
# Build DB_URL from env (supports either DB_URL or discrete vars)
# -------------------------------------------------------------------------
DB_URL = os.getenv("DB_URL")
if not DB_URL:
    user = os.getenv("DB_USER", "helios")
    pwd  = os.getenv("PGPASSWORD", "")
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "5433")
    db   = os.getenv("DB_NAME", "helios")
    DB_URL = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"

# -------------------------------------------------------------------------
# Engine + Session
# -------------------------------------------------------------------------
engine = create_engine(DB_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

@contextmanager
def get_session():
    """Usage: with get_session() as s: s.execute(...); s.commit()"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
