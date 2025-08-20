import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Default to Cloud SQL connection string if DB_URL not set
DB_URL = os.getenv(
    "DB_URL",
    "postgresql+psycopg2://helios:${DB_PASSWORD}@/helios?host=/cloudsql/helios-467214:europe-west2:helios-pg",
)

# echo=False keeps logs clean; pool_pre_ping avoids broken connections
engine = create_engine(DB_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def get_session():
    """Return a new SQLAlchemy session bound to our Postgres database."""
    return SessionLocal()
