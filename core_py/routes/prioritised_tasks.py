# core_py/api/prioritised_tasks.py
from fastapi import APIRouter
import sqlite3
import os

router = APIRouter()

DB_PATH = os.path.join(os.path.dirname(__file__), "../db/helios.db")

@router.get("/prioritised-tasks")
def get_prioritised_tasks():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, name, score, agent_rank, agent_reason
        FROM triaged_tasks
        WHERE agent_rank IS NOT NULL
        ORDER BY agent_rank ASC
        LIMIT 25
    """)
    rows = c.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "title": r[1],
            "score": r[2],
            "agent_rank": r[3],
            "agent_reason": r[4]
        }
        for r in rows
    ]
