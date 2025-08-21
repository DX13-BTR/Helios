from sqlalchemy import text
from typing import Optional, Mapping
from core_py.db.session import get_session, db_session

DDL = """
CREATE SCHEMA IF NOT EXISTS helios;
CREATE TABLE IF NOT EXISTS helios.task_meta (
  task_id TEXT PRIMARY KEY,
  task_type TEXT DEFAULT 'flexible',
  deadline_type TEXT,
  fixed_date TEXT,
  calendar_blocked INTEGER DEFAULT 0,
  recurrence_pattern TEXT,
  client_code TEXT
);
"""

def upsert_task_meta(meta: Mapping):
    """meta keys: task_id, task_type, deadline_type, fixed_date, calendar_blocked, recurrence_pattern, client_code"""
    with db_session() as s:
        s.execute(text(DDL))
        s.execute(text("""
            INSERT INTO helios.task_meta
              (task_id, task_type, deadline_type, fixed_date, calendar_blocked, recurrence_pattern, client_code)
            VALUES (:task_id, :task_type, :deadline_type, :fixed_date, :calendar_blocked, :recurrence_pattern, :client_code)
            ON CONFLICT (task_id) DO UPDATE SET
              task_type=EXCLUDED.task_type,
              deadline_type=EXCLUDED.deadline_type,
              fixed_date=EXCLUDED.fixed_date,
              calendar_blocked=EXCLUDED.calendar_blocked,
              recurrence_pattern=EXCLUDED.recurrence_pattern,
              client_code=EXCLUDED.client_code
        """), meta)
        s.commit()

def get_task_meta(task_id: str) -> Optional[dict]:
    with db_session() as s:
        row = s.execute(text("""
            SELECT task_id, task_type, deadline_type, fixed_date, calendar_blocked, recurrence_pattern, client_code
            FROM helios.task_meta WHERE task_id = :task_id
        """), {"task_id": task_id}).mappings().fetchone()
        return dict(row) if row else None
