from datetime import datetime, timedelta
import sqlite3
import os

DB_PATH = os.getenv("SQLITE_DB_PATH", "core_py/db/helios.db")


def get_overdue_tasks():
    now = datetime.now().timestamp() * 1000  # milliseconds
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, due_date, section FROM triaged_tasks
            WHERE due_date IS NOT NULL AND due_date < ? AND space_name = 'Personal'
            ORDER BY due_date ASC
        """, (now,))
        rows = cursor.fetchall()
    return [
    {"id": row[0], "name": row[1], "due_date": int(row[2]), "section": row[3]}
    for row in rows
]


def get_upcoming_tasks(window_minutes=30):
    now = datetime.now()
    end = now + timedelta(minutes=window_minutes)
    now_ms = now.timestamp() * 1000
    end_ms = end.timestamp() * 1000

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, due_date, section FROM triaged_tasks
            WHERE due_date BETWEEN ? AND ? AND space_name = 'Personal'
            ORDER BY due_date ASC
        """, (now_ms, end_ms))
        rows = cursor.fetchall()

    return [
    {"id": row[0], "name": row[1], "due_date": int(row[2]), "section": row[3]}
    for row in rows
]
