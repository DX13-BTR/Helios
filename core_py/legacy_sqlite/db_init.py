import sqlite3
import os
from dotenv import load_dotenv
load_dotenv(dotenv_path="core_py/.env")

DB_PATH = os.getenv("HELIOS_DB_PATH", "C:/Helios/core_py/db/helios.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,              -- 'user' or 'assistant'
            message TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
