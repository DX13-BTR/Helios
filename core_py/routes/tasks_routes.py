# core_py/routes/tasks_routes.py
from datetime import datetime, timezone
from typing import List, Optional

import os
import time
import requests
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from core_py.db.session import get_session, db_session
from core_py.db.triaged_tasks_pg import upsert_triaged_tasks, top_triaged_tasks
from core_py.db.task_meta_pg import upsert_task_meta, get_task_meta
from core_py.integrations.clickup_client import ClickUpClient

# === env ===
load_dotenv(dotenv_path="core_py/.env")  # harmless on Cloud Run

CLICKUP_API_KEY = os.getenv("CLICKUP_API_KEY")
CLICKUP_API_URL = "https://api.clickup.com/api/v2"
CLICKUP_EMAIL_LIST_ID = os.getenv("CLICKUP_EMAIL_LIST_ID")
CLICKUP_PERSONAL_SPACE_ID = os.getenv("CLICKUP_PERSONAL_SPACE_ID")
CLICKUP_TEAM_ID = os.getenv("CLICKUP_TEAM_ID")

router = APIRouter()
CLIENT = ClickUpClient()

# ------------------------------------------------------------------------------------
# Models
# ------------------------------------------------------------------------------------
class UpdateStatusRequest(BaseModel):
    status: str

class TaskMetaUpdate(BaseModel):
    task_type: Optional[str] = Field(None, description="'fixed_date' or 'flexible'")
    deadline_type: Optional[str] = Field(None, description="vat_return|payroll|ct600|cs01|sa100|sa800|cis_return")
    fixed_date: Optional[str] = Field(None, description="ISO 8601, e.g. 2025-10-07T00:00:00")
    calendar_blocked: Optional[bool] = None
    recurrence_pattern: Optional[str] = Field(None, description="monthly|quarterly|annual|one_time")
    client_code: Optional[str] = None

class TaskMetaIn(BaseModel):
    task_id: str
    task_type: Optional[str] = "fixed_date"
    deadline_type: Optional[str] = None
    fixed_date: Optional[str] = None
    calendar_blocked: Optional[bool | int] = 0
    recurrence_pattern: Optional[str] = None
    client_code: Optional[str] = None

# ------------------------------------------------------------------------------------
# ClickUp helpers
# ------------------------------------------------------------------------------------
def _headers():
    if not CLICKUP_API_KEY:
        raise HTTPException(status_code=500, detail="Missing CLICKUP_API_KEY")
    return {"Authorization": CLICKUP_API_KEY}

def get_clickup_list_tasks(list_id: str):
    if not list_id:
        return []
    res = requests.get(f"{CLICKUP_API_URL}/list/{list_id}/task", headers=_headers(), timeout=20)
    res.raise_for_status()
    return res.json().get("tasks", [])

def get_clickup_space_tasks(space_id: str):
    if not (space_id and CLICKUP_TEAM_ID):
        return []
    params = {
        "space_ids[]": space_id,
        "archived": "false",
        "statuses[]": ["to do", "in progress"],
    }
    url = f"{CLICKUP_API_URL}/team/{CLICKUP_TEAM_ID}/task"
    res = requests.get(url, headers=_headers(), params=params, timeout=25)
    res.raise_for_status()
    return res.json().get("tasks", [])

# If you prefer to use your abstraction:
def refresh_triaged_view_source():
    return CLIENT.refresh_triaged_view_source()

# ------------------------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------------------------
@router.post("/tasks/{id}/update-status")
def update_task_status(id: str, request: UpdateStatusRequest):
    # 1) Update in ClickUp (source of truth)
    try:
        res = requests.put(
            f"{CLICKUP_API_URL}/task/{id}",
            headers=_headers(),
            json={"status": request.status},
            timeout=20,
        )
        res.raise_for_status()
    except Exception as e:
        print("❌ ClickUp update failed:", e)
        raise HTTPException(status_code=502, detail="ClickUp update failed")

    # 2) Best-effort mirror in Postgres
    try:
        with db_session() as s:
            s.execute(text("UPDATE helios.triaged_tasks SET status = :st WHERE id = :id"),
                      {"st": request.status, "id": id})
            s.commit()
    except Exception as e:
        print("⚠️ Postgres mirror update failed:", e)

    return {"success": True, "task_id": id, "new_status": request.status}


@router.get("/triaged-tasks")
def get_combined_triaged_tasks():
    """
    doNext panel from helios.triaged_tasks (Postgres).
    Email panel via CLICKUP_EMAIL_LIST_ID.
    Personal panel via CLICKUP_PERSONAL_SPACE_ID.
    """
    try:
        # 1) DoNext
        do_next = top_triaged_tasks(limit=2000)

        # 2) Email list
        try:
            email_tasks = get_clickup_list_tasks(CLICKUP_EMAIL_LIST_ID)
        except Exception as e:
            print("⚠️ Email fetch failed:", e)
            email_tasks = []

        # 3) Personal space
        try:
            personal_tasks = get_clickup_space_tasks(CLICKUP_PERSONAL_SPACE_ID)
            personal_tasks = sorted(
                personal_tasks,
                key=lambda t: int(t.get("due_date", 0)) or 2**63 - 1
            )
        except Exception as e:
            print("⚠️ Personal fetch failed:", e)
            personal_tasks = []

        return {"doNext": do_next, "email": email_tasks, "personal": personal_tasks}
    except Exception as e:
        print("❌ Task aggregation failed:", e)
        raise HTTPException(status_code=500, detail="Failed to load task panels")


@router.get("/do-next-tasks")
def get_do_next_tasks():
    try:
        return {"doNext": top_triaged_tasks(limit=3)}
    except Exception as e:
        print("❌ doNext failed:", e)
        raise HTTPException(status_code=500, detail="doNext route failed")


@router.post("/refresh-triaged-tasks")
def refresh_triaged_tasks():
    try:
        # 1) Pull fresh from ClickUp for DoNext pool
        tasks = refresh_triaged_view_source()

        # 2) Score/enrich (simple/fast)
        now = int(time.time() * 1000)
        enriched = []
        for t in tasks:
            score = 0
            due = int(t.get("due_date") or 0)

            if due > 0:
                diff_days = (due - now) / 86400000
                if diff_days < 0:
                    score += 3
                elif diff_days < 1:
                    score += 2
                elif diff_days < 3:
                    score += 1

            pr = None
            try:
                pr = int(t.get("priority", {}).get("priority")) if t.get("priority") else None
            except Exception:
                pr = None
            if pr in (3, 4):
                score += 2

            enriched.append({
                "id": t["id"],
                "name": t["name"],
                "due_date": due,
                "priority": pr,
                "score": score,
                "status": t.get("status", {}).get("status"),
            })

        # 3) Write to Postgres (truncate + upsert)
        upsert_triaged_tasks(enriched)
        return {"refreshed": len(enriched)}
    except Exception as e:
        print("❌ Refresh triaged tasks failed:", e)
        raise HTTPException(status_code=500, detail="Failed to refresh triaged tasks")


@router.get("/fixed-date-tasks")
def get_fixed_date_tasks():
    """
    Source = helios.task_meta (fixed_date items),
    LEFT JOIN helios.triaged_tasks for name/priority/status/due_date.
    """
    def to_iso(raw):
        if raw is None:
            return None
        s = str(raw).strip()
        if not s:
            return None
        if "-" in s or "T" in s:
            return s
        try:
            val = int(float(s))
            if val <= 0:
                return None
            if val < 10**11:
                val *= 1000
            return datetime.fromtimestamp(val / 1000.0, tz=timezone.utc).isoformat()
        except Exception:
            return None

    try:
        with db_session() as s:
            s.execute(text("""
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
            """))

            rows = s.execute(text("""
                SELECT
                  m.task_id AS id,
                  m.deadline_type,
                  m.fixed_date,
                  m.client_code,
                  m.recurrence_pattern,
                  m.calendar_blocked,
                  t.name,
                  t.due_date,
                  t.priority,
                  t.status
                FROM helios.task_meta m
                LEFT JOIN helios.triaged_tasks t ON t.id = m.task_id
                WHERE m.task_type = 'fixed_date'
            """)).mappings().all()

        out = []
        for r in rows:
            d = dict(r)
            due_iso = to_iso(d.pop("due_date"))
            d["due_date_iso"] = due_iso
            d["fixed_date"] = d["fixed_date"] or due_iso
            out.append(d)

        def key(x):
            try:
                dt = datetime.fromisoformat(str(x["fixed_date"]).replace("Z", "+00:00"))
                return (0 if dt < datetime.now(timezone.utc) else 1, dt)
            except Exception:
                return (2, datetime.max)

        out.sort(key=key)
        return out
    except Exception as e:
        print("❌ /fixed-date-tasks failed:", repr(e))
        raise HTTPException(status_code=500, detail="failed_to_load_fixed_date_tasks")


@router.post("/task-meta/{task_id}/set")
def set_task_meta(task_id: str, payload: TaskMetaUpdate):
    try:
        if payload.fixed_date:
            try:
                _ = datetime.fromisoformat(payload.fixed_date)
            except Exception:
                raise HTTPException(status_code=400, detail="fixed_date must be ISO 8601 (e.g. 2025-10-07T00:00:00)")

        upsert_task_meta({
            "task_id": task_id,
            "task_type": (payload.task_type or "flexible").strip(),
            "deadline_type": payload.deadline_type,
            "fixed_date": payload.fixed_date,
            "calendar_blocked": 1 if (payload.calendar_blocked is True) else 0,
            "recurrence_pattern": payload.recurrence_pattern,
            "client_code": payload.client_code,
        })
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        print("❌ set_task_meta failed:", e)
        raise HTTPException(status_code=500, detail="failed_to_set_task_meta")


@router.post("/task-meta/bulk-upsert")
def bulk_upsert_task_meta(items: List[TaskMetaIn]):
    if not items:
        return {"upserted": 0}
    try:
        count = 0
        for it in items:
            cb = it.calendar_blocked
            if isinstance(cb, bool):
                cb_val = 1 if cb else 0
            else:
                cb_val = 1 if int(cb or 0) != 0 else 0

            upsert_task_meta({
                "task_id": it.task_id.strip(),
                "task_type": (it.task_type or "fixed_date").strip(),
                "deadline_type": (it.deadline_type or None),
                "fixed_date": (it.fixed_date or None),
                "calendar_blocked": cb_val,
                "recurrence_pattern": (it.recurrence_pattern or None),
                "client_code": (it.client_code or None),
            })
            count += 1
        return {"upserted": count}
    except Exception as e:
        print("❌ bulk_upsert_task_meta failed:", e)
        raise HTTPException(status_code=500, detail="bulk_upsert_failed")


@router.get("/debug/db")
def db_debug():
    """Confirm Postgres connectivity and basic counts."""
    try:
        with db_session() as s:
            ok = s.execute(text("SELECT 1")).scalar()
            triaged_count = s.execute(text("SELECT COUNT(*) FROM helios.triaged_tasks")).scalar()
            meta_count = s.execute(text("SELECT COUNT(*) FROM helios.task_meta")).scalar()
        return {"engine": "postgres", "ok": ok == 1, "triaged_tasks": triaged_count, "task_meta": meta_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"db_debug_failed: {e}")
