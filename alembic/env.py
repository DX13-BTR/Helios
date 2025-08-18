# alembic/env.py
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# --- Alembic Config ---
config = context.config

# Logging config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Import your models so autogenerate can "see" them ---
# Base comes from your active DB package (core_py/db/__init__.py)
from core_py.db import Base
import core_py.models  # noqa: F401  (side-effect: registers tables on Base.metadata)

target_metadata = Base.metadata

# Only manage these 4 tables with Alembic (everything else stays under raw SQL)
MANAGED_TABLES = {"clients", "client_emails", "client_domains", "allowlist_meta"}

def include_object(object, name, type_, reflected, compare_to):
    # Limit Alembic’s scope to the allowlist/contacts tables
    if type_ == "table":
        return name in MANAGED_TABLES
    if type_ == "index":
        parent = getattr(object, "table", None)
        parent_name = getattr(parent, "name", None)
        return parent_name in MANAGED_TABLES
    return True

# --- Resolve DB URL ---
def _resolve_db_url() -> str:
    # Prefer env (e.g., set in .env) else fallback to alembic.ini's sqlalchemy.url
    env_url = os.getenv("DB_URL")
    if env_url and env_url.strip():
        return env_url
    return config.get_main_option("sqlalchemy.url")

def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")

# --- Offline migration runner ---
def run_migrations_offline() -> None:
    url = _resolve_db_url()
    config.set_main_option("sqlalchemy.url", url)

    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_is_sqlite(url),  # important for SQLite schema changes
    )

    with context.begin_transaction():
        context.run_migrations()

# --- Online migration runner ---
def run_migrations_online() -> None:
    url = _resolve_db_url()
    config.set_main_option("sqlalchemy.url", url)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            render_as_batch=_is_sqlite(url),  # important for SQLite schema changes
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
