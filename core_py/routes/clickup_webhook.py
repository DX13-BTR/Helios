# core_py/routes/clickup_webhook.py

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import text

from core_py.db.database import get_engine  # uses your DB engine factory

router = APIRouter()

# --- Ensure the target table exists (safe, idempotent) ---
# If you already manage schema elsewhere, you can remove this block.
_ddl = """
CREATE TABLE IF NOT EXISTS triaged_tasks (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  priority INT NULL,
  due_date TIMESTAMPTZ NULL,
  score NUMERIC NULL,
  status TEXT NULL,
  is_urgent BOOLEAN DEFAULT FALSE,
  section TEXT NULL,
  reason TEXT NULL
);
"""
_engine = get_engine()
with _engine.begin() as _conn:
    _conn.execute(text(_ddl))


def _coerce_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def _coerce_datetime(v: Any) -> Optional[datetime]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    # ClickUp webhooks sometimes send millis or ISO strings
    try:
        # int milliseconds since epoch
        if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
            ms = int(v)
            # ClickUp often sends ms; if it's seconds, datetime will still parse reasonably
            if ms > 10_000_000_000:  # heuristic: treat as milliseconds
                return datetime.utcfromtimestamp(ms / 1000.0)
            return datetime.utcfromtimestamp(ms)
    except Exception:
        pass
    try:
        # ISO8601 string
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def _extract_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Be liberal in what we accept. ClickUp payloads vary by event.
    We try both top-level and nested 'task' objects.
    """
    task_obj = payload.get("task") or payload

    return {
        "id": str(task_obj.get("id") or payload.get("id") or ""),
        "name": task_obj.get("name") or payload.get("name") or "Unnamed",
        "priority": task_obj.get("priority") if isinstance(task_obj.get("priority"), (int, float)) else None,
        "due_date": _coerce_datetime(task_obj.get("due_date") or payload.get("due_date")),
        "score": task_obj.get("score"),
        "status": (task_obj.get("status") or payload.get("status") or "").strip() or None,
        "is_urgent": _coerce_bool(task_obj.get("is_urgent") or payload.get("is_urgent")),
        "section": task_obj.get("section") or payload.get("section") or None,
        "reason": task_obj.get("reason") or payload.get("reason") or None,
    }


@router.post("/webhook")
async def clickup_webhook(request: Request):
    """
    Receives ClickUp webhook payloads and upserts into triaged_tasks.
    """
    payload = await request.json()
    task = _extract_task(payload)

    if not task["id"]:
        raise HTTPException(status_code=400, detail="Missing task id")

    # Upsert into Postgres
    upsert_sql = text("""
        INSERT INTO triaged_tasks
            (id, name, priority, due_date, score, status, is_urgent, section, reason)
        VALUES
            (:id, :name, :priority, :due_date, :score, :status, :is_urgent, :section, :reason)
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            priority = EXCLUDED.priority,
            due_date = EXCLUDED.due_date,
            score = EXCLUDED.score,
            status = EXCLUDED.status,
            is_urgent = EXCLUDED.is_urgent,
            section = EXCLUDED.section,
            reason = EXCLUDED.reason
    """)

    # Use a single transaction
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(upsert_sql, {
            "id": task["id"],
            "name": task["name"],
            "priority": task["priority"],
            "due_date": task["due_date"],
            "score": task["score"],
            "status": task["status"],
            "is_urgent": task["is_urgent"],
            "section": task["section"],
            "reason": task["reason"],
        })

    return {"ok": True, "id": task["id"]}
