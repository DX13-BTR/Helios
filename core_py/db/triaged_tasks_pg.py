from sqlalchemy import text
from typing import Iterable, Mapping
from core_py.db.session import get_session, db_session

DDL = """
CREATE SCHEMA IF NOT EXISTS helios;
CREATE TABLE IF NOT EXISTS helios.triaged_tasks (
  id TEXT PRIMARY KEY,
  name TEXT,
  due_date BIGINT,
  priority INT,
  score INT,
  status TEXT
);
"""

def upsert_triaged_tasks(rows: Iterable[Mapping]):
    """rows: iterable of dicts with keys id,name,due_date,priority,score,status"""
    with db_session() as s:
        s.execute(text(DDL))
        # Clear and reinsert (keeps logic identical to your current flow)
        s.execute(text("DELETE FROM helios.triaged_tasks"))
        for r in rows:
            s.execute(text("""
                INSERT INTO helios.triaged_tasks (id, name, due_date, priority, score, status)
                VALUES (:id, :name, :due_date, :priority, :score, :status)
                ON CONFLICT (id) DO UPDATE SET
                  name=EXCLUDED.name,
                  due_date=EXCLUDED.due_date,
                  priority=EXCLUDED.priority,
                  score=EXCLUDED.score,
                  status=EXCLUDED.status
            """), r)
        s.commit()

def top_triaged_tasks(limit: int = 3):
    with db_session() as s:
        rows = s.execute(text("""
            SELECT id, name, due_date, priority, score, status
            FROM helios.triaged_tasks
            ORDER BY score DESC, due_date ASC
            LIMIT :lim
        """), {"lim": limit}).mappings().all()
        return [dict(r) for r in rows]
