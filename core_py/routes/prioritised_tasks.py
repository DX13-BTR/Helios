# core_py/routes/prioritised_tasks.py
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from core_py.db.session import get_session

router = APIRouter()

@router.get("/prioritised-tasks")
def get_prioritised_tasks():
    """
    Reads top prioritised tasks from Postgres.

    NOTE:
    - We query helios.triaged_tasks. In your migration you also created a
      compatibility view that maps helios.triaged_tasks -> legacy.triaged_tasks,
      so this works regardless of where the data physically lives.
    - Output shape matches the old endpoint: id, title (from name), score, agent_rank, agent_reason.
    """
    sql = text("""
        SELECT id, name, score, agent_rank, agent_reason
        FROM helios.triaged_tasks
        WHERE agent_rank IS NOT NULL
        ORDER BY agent_rank ASC
        LIMIT 25
    """)

    try:
        with get_session() as s:
            rows = s.execute(sql).mappings().all()

        return [
            {
                "id": r["id"],
                "title": r["name"],
                "score": r.get("score"),
                "agent_rank": r.get("agent_rank"),
                "agent_reason": r.get("agent_reason"),
            }
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed_to_load_prioritised: {e}")
