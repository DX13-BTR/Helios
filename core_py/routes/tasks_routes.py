import sqlite3
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import os
import requests
import time
from dotenv import load_dotenv
from core_py.integrations.clickup_client import ClickUpClient
CLIENT = ClickUpClient()
def refresh_triaged_view_source():
    return CLIENT.refresh_triaged_view_source()
def fetch_tasks_grouped():
    return CLIENT.fetch_tasks_grouped()

# === Load environment variables ===
load_dotenv(dotenv_path="core_py/.env")

DB_PATH = os.getenv("HELIOS_DB_PATH", r"C:\Helios\core_py\db\helios.db")
CLICKUP_API_KEY = os.getenv("CLICKUP_API_KEY")
CLICKUP_API_URL = "https://api.clickup.com/api/v2"
CLICKUP_EMAIL_LIST_ID = os.getenv("CLICKUP_EMAIL_LIST_ID")
CLICKUP_PERSONAL_SPACE_ID = os.getenv("CLICKUP_PERSONAL_SPACE_ID")

router = APIRouter()

# === Payload model for task status updates ===
class UpdateStatusRequest(BaseModel):
    status: str

# === Payload model for task_meta updates (single row) ===
class TaskMetaUpdate(BaseModel):
    task_type: str | None = Field(None, description="'fixed_date' or 'flexible'")
    deadline_type: str | None = Field(None, description="vat_return|payroll|ct600|cs01|sa100|sa800|cis_return")
    fixed_date: str | None = Field(None, description="ISO 8601, e.g. 2025-10-07T00:00:00")
    calendar_blocked: bool | None = None
    recurrence_pattern: str | None = Field(None, description="monthly|quarterly|annual|one_time")
    client_code: str | None = None

# === Payload model for task_meta bulk upsert (array items) ===
class TaskMetaIn(BaseModel):
    task_id: str
    task_type: Optional[str] = "fixed_date"
    deadline_type: Optional[str] = None
    fixed_date: Optional[str] = None            # ISO 8601 (stored as TEXT)
    calendar_blocked: Optional[bool | int] = 0  # accepts 0/1 or bool
    recurrence_pattern: Optional[str] = None
    client_code: Optional[str] = None

# === Utility: Fetch tasks from a ClickUp list ===
def get_clickup_list_tasks(list_id: str):
    headers = {"Authorization": CLICKUP_API_KEY}
    res = requests.get(f"{CLICKUP_API_URL}/list/{list_id}/task", headers=headers)
    res.raise_for_status()
    return res.json().get("tasks", [])

# === Utility: Fetch tasks from a ClickUp space ===
def get_clickup_space_tasks(space_id: str):
    headers = {"Authorization": CLICKUP_API_KEY}

    params = {
        "space_ids[]": space_id,
        "archived": "false",
        "statuses[]": ["to do", "in progress"]
    }

    url = f"{CLICKUP_API_URL}/team/{os.getenv('CLICKUP_TEAM_ID')}/task"
    res = requests.get(url, headers=headers, params=params)
    res.raise_for_status()
    return res.json().get("tasks", [])

# === Internal utility: SQLite connection with Row factory ===
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

# -------------------------------------------------------------------------------------------------
# Existing endpoints
# -------------------------------------------------------------------------------------------------

@router.post("/tasks/{id}/update-status")
def update_task_status(id: str, request: UpdateStatusRequest):
    # 1) Update in ClickUp (authoritative)
    try:
        cu_update_status(id, request.status)
    except Exception as e:
        print("❌ ClickUp update failed:", e)
        raise HTTPException(status_code=502, detail="ClickUp update failed")

    # 2) Best-effort mirror in your local SQLite (keep your existing DB logic)
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE triaged_tasks SET status = ? WHERE id = ?",
            (request.status, id)
        )
        if cur.rowcount:
            conn.commit()
        conn.close()
    except Exception as e:
        print("⚠️ SQLite update failed:", e)

    return {"success": True, "task_id": id, "new_status": request.status}


# === GET: Combined task view for Helios Dashboard ===
@router.get("/triaged-tasks")
def get_combined_triaged_tasks():
    try:
        # 1) DoNext — unchanged (from your local SQLite)
        conn = _conn()
        conn.row_factory = sqlite3.Row  # if not already set globally
        cur = conn.cursor()
        cur.execute("SELECT * FROM triaged_tasks ORDER BY score DESC, due_date ASC")
        do_next = [dict(row) for row in cur.fetchall()]
        conn.close()

        # 2) Email — via ClickUp list (safe wrapper)
        try:
            email = get_email_tasks()
        except Exception as e:
            print("⚠️ Email fetch failed:", e)
            email = []

        # 3) Personal — via ClickUp space (safe wrapper)
        try:
            personal = get_personal_space_tasks()
            # Optional: keep predictable ordering in UI
            personal = sorted(
                personal,
                key=lambda t: int(t.get("due_date", 0)) or 2**63 - 1
            )
        except Exception as e:
            print("⚠️ Personal fetch failed:", e)
            personal = []

        return {"doNext": do_next, "email": email, "personal": personal}

    except Exception as e:
        print("❌ Task aggregation failed:", e)
        raise HTTPException(status_code=500, detail="Failed to load task panels")


# === Optional legacy support ===
@router.get("/do-next-tasks")
def get_do_next_tasks():
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM triaged_tasks ORDER BY score DESC, due_date ASC LIMIT 3")
        rows = cur.fetchall()
        conn.close()
        return {"doNext": [dict(row) for row in rows]}
    except Exception as e:
        print("❌ Failed to load doNext tasks:", e)
        raise HTTPException(status_code=500, detail="Legacy doNext route failed")

@router.post("/refresh-triaged-tasks")
def refresh_triaged_tasks():
    try:
        # 1) Pull fresh tasks from ClickUp for the DoNext pool
        #    (excludes Email list & Personal space by default)
        tasks = refresh_triaged_view_source()

        # 2) Score/enrich (keep your own scoring rules if you prefer)
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

            # High/Urgent in ClickUp is usually priority priority=3/4
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

        # 3) Store in SQLite (exactly as before)
        conn = _conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM triaged_tasks")
        for task in enriched:
            cur.execute("""
                INSERT INTO triaged_tasks (id, name, due_date, priority, score, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (task["id"], task["name"], task["due_date"], task["priority"], task["score"], task["status"]))
        conn.commit()
        conn.close()

        return {"refreshed": len(enriched)}

    except Exception as e:
        print("❌ Refresh triaged tasks failed:", e)
        raise HTTPException(status_code=500, detail="Failed to refresh triaged tasks")


# -------------------------------------------------------------------------------------------------
# New endpoints: fixed/flexible metadata (task_meta)
# -------------------------------------------------------------------------------------------------

@router.get("/fixed-date-tasks")
def get_fixed_date_tasks():
    """
    Source of truth = task_meta (fixed_date items), with triaged_tasks joined
    only for name/priority/status/due_date if present.
    This shows ALL compliance items even if triaged_tasks is a small slice.
    """
    from datetime import datetime, timezone

    def to_iso(raw):
        if raw is None: return None
        s = str(raw).strip()
        if not s: return None
        if "-" in s or "T" in s: return s
        try:
            val = int(float(s))
            if val <= 0: return None
            if val < 10**11: val *= 1000
            return datetime.fromtimestamp(val/1000.0, tz=timezone.utc).isoformat()
        except Exception:
            return None

    try:
        conn = _conn()
        cur = conn.cursor()
        # ensure table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS task_meta (
              task_id TEXT PRIMARY KEY,
              task_type TEXT DEFAULT 'flexible',
              deadline_type TEXT,
              fixed_date TEXT,
              calendar_blocked INTEGER DEFAULT 0,
              recurrence_pattern TEXT,
              client_code TEXT
            )
        """)

        rows = cur.execute("""
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
            FROM task_meta m
            LEFT JOIN triaged_tasks t ON t.id = m.task_id
            WHERE m.task_type = 'fixed_date'
        """).fetchall()
        conn.close()

        out = []
        for r in rows:
            d = dict(r)
            due_iso = to_iso(d.pop("due_date"))
            # final fixed_date = explicit metadata date, else fallback to ClickUp due
            d["due_date_iso"] = due_iso
            d["fixed_date"] = d["fixed_date"] or due_iso
            out.append(d)

        # sort: overdue first, then soonest; undated last
        def key(x):
            try:
                dt = datetime.fromisoformat(str(x["fixed_date"]).replace("Z","+00:00"))
                return (0 if dt < datetime.now(timezone.utc) else 1, dt)
            except Exception:
                return (2, datetime.max)
        out.sort(key=key)
        return out

    except Exception as e:
        print("❌ /fixed-date-tasks(meta) failed:", repr(e))
        raise HTTPException(status_code=500, detail="failed_to_load_fixed_date_tasks")


@router.post("/task-meta/{task_id}/set")
def set_task_meta(task_id: str, payload: TaskMetaUpdate):
    """
    Upsert metadata for a single task id.
    Payload can include: task_type, deadline_type, fixed_date (ISO),
    calendar_blocked, recurrence_pattern, client_code.
    """
    try:
        # Validate ISO date if provided
        fixed_date_iso = payload.fixed_date
        if fixed_date_iso:
            try:
                _ = datetime.fromisoformat(fixed_date_iso)
            except Exception:
                raise HTTPException(status_code=400, detail="fixed_date must be ISO 8601 (e.g. 2025-10-07T00:00:00)")

        conn = _conn()
        cur = conn.cursor()

        # Ensure table exists (safety)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS task_meta (
                task_id TEXT PRIMARY KEY,
                task_type TEXT DEFAULT 'flexible',
                deadline_type TEXT,
                fixed_date TEXT,
                calendar_blocked INTEGER DEFAULT 0,
                recurrence_pattern TEXT,
                client_code TEXT
            )
        """)

        # Normalize values
        task_type = payload.task_type or "flexible"
        deadline_type = payload.deadline_type
        calendar_blocked = 1 if (payload.calendar_blocked is True) else 0
        recurrence_pattern = payload.recurrence_pattern
        client_code = payload.client_code

        # UPSERT
        cur.execute("""
            INSERT INTO task_meta (task_id, task_type, deadline_type, fixed_date, calendar_blocked, recurrence_pattern, client_code)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
              task_type=excluded.task_type,
              deadline_type=excluded.deadline_type,
              fixed_date=excluded.fixed_date,
              calendar_blocked=excluded.calendar_blocked,
              recurrence_pattern=excluded.recurrence_pattern,
              client_code=excluded.client_code
        """, (task_id, task_type, deadline_type, fixed_date_iso, calendar_blocked, recurrence_pattern, client_code))
        conn.commit()
        conn.close()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        print("❌ set_task_meta failed:", e)
        raise HTTPException(status_code=500, detail="failed_to_set_task_meta")

@router.post("/task-meta/bulk-upsert")
def bulk_upsert_task_meta(items: List[TaskMetaIn]):
    """
    Upsert multiple task_meta rows in one call.
    Final path is /api/task-meta/bulk-upsert (router mounted with prefix /api).
    """
    if not items:
        return {"upserted": 0}
    try:
        conn = _conn()
        cur = conn.cursor()

        # Ensure table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS task_meta (
                task_id TEXT PRIMARY KEY,
                task_type TEXT DEFAULT 'flexible',
                deadline_type TEXT,
                fixed_date TEXT,
                calendar_blocked INTEGER DEFAULT 0,
                recurrence_pattern TEXT,
                client_code TEXT
            )
        """)

        sql = """
            INSERT INTO task_meta
                (task_id, task_type, deadline_type, fixed_date, calendar_blocked, recurrence_pattern, client_code)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                task_type=excluded.task_type,
                deadline_type=excluded.deadline_type,
                fixed_date=excluded.fixed_date,
                calendar_blocked=excluded.calendar_blocked,
                recurrence_pattern=excluded.recurrence_pattern,
                client_code=excluded.client_code
        """

        payload = []
        for it in items:
            cb = it.calendar_blocked
            # normalize to 0/1
            if isinstance(cb, bool):
                cb = 1 if cb else 0
            else:
                cb = 1 if int(cb or 0) != 0 else 0

            payload.append((
                it.task_id.strip(),
                (it.task_type or "fixed_date").strip(),
                (it.deadline_type or None),
                (it.fixed_date or None),
                cb,
                (it.recurrence_pattern or None),
                (it.client_code or None),
            ))

        cur.executemany(sql, payload)
        conn.commit()
        conn.close()
        return {"upserted": len(payload)}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print("❌ bulk_upsert_task_meta failed:", e)
        raise HTTPException(status_code=500, detail="bulk_upsert_failed")

@router.get("/debug/db-path")
def db_path():
    """
    Returns the attached SQLite database path(s) to help diagnose mismatched DB files.
    """
    try:
        conn = _conn()
        cur = conn.cursor()
        res = cur.execute("PRAGMA database_list").fetchall()
        conn.close()
        # row = (seq, name, file)
        return [{"name": r[1], "file": r[2]} for r in res]
    except Exception as e:
        print("❌ /debug/db-path failed:", e)
        raise HTTPException(status_code=500, detail="failed_to_get_db_path")
