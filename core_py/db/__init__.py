# core_py/db/__init__.py
import os
from sqlalchemy.orm import declarative_base

# Single ORM base used everywhere
Base = declarative_base()

# No DB URL here. Let core_py/db/database.py read .env (DATABASE_URL).
# Anything that previously imported DB_URL from here should stop doing that.
