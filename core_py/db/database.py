# core_py/db/database.py

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in the environment.")

# SQLAlchemy Base
Base = declarative_base()

# Engine factory
def get_engine():
    return create_engine(DATABASE_URL)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())

def get_session():
    """
    Dependency-style session generator.
    Yields a session and ensures proper cleanup.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----------------------------
# Auto-create tables on import
# ----------------------------
from core_py.models import Base as ModelsBase

engine = get_engine()
ModelsBase.metadata.create_all(bind=engine)
