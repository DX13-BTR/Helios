# core_py/db/schema_upgrade.py
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "helios.db")

def create_task_logs_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS task_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            score INTEGER,
            agent_rank INTEGER,
            agent_reason TEXT
        )
    ''')

    conn.commit()
    conn.close()
    print("[Helios] task_logs table ready.")

if __name__ == "__main__":
    create_task_logs_table()
