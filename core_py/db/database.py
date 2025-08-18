import sqlite3
import os
from dotenv import load_dotenv
load_dotenv(dotenv_path="core_py/.env")

DB_PATH = os.getenv("HELIOS_DB_PATH", "C:/Helios/core_py/db/helios.db")

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def insert_or_replace_task(task):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO triaged_tasks 
        (id, name, priority, due_date, score, status, is_urgent, section, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        task["id"],
        task["name"],
        task.get("priority"),
        task.get("due_date"),
        task.get("score"),
        task["status"],
        int(task.get("is_urgent", False)),
        task.get("section", "general"),
        task.get("reason"),
    ))
    conn.commit()
    conn.close()