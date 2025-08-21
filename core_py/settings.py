# core_py/settings.py
from pydantic import BaseSettings, Field, AnyUrl
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    ENV: str = "dev"
    DB_URL: str = "postgresql+psycopg2://helios:helios@localhost:5432/helios"
    RECLAIM_API_KEY: Optional[str] = None
    TIMEZONE: str = "Europe/London"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache
def get_settings() -> Settings:
    return Settings()
