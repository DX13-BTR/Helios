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
from core_py.clickup_complete_extractor import ClickUpCompleteExtractor  # NEW: Added for migration

# === env ===
load_dotenv(dotenv_path="core_py/.env")

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

class EmailTaskRequest(BaseModel):
    message_id: str
    sender: str
    subject: str
    content: str
    gmail_link: Optional[str] = None
    thread_id: Optional[str] = None
    received_ts: Optional[int] = None
    start_ts: Optional[int] = None
    due_ts: Optional[int] = None
    source_label: Optional[str] = None
    dry_run: Optional[bool] = False
    dual_write_clickup: Optional[bool] = False
    priority: Optional[str] = "normal"
    client_hint: Optional[str] = None

# ------------------------------------------------------------------------------------
# ClickUp helpers (for legacy data only)
# ------------------------------------------------------------------------------------
def _headers():
    if not CLICKUP_API_KEY:
        raise HTTPException(status_code=500, detail="Missing CLICKUP_API_KEY")
    return {"Authorization": CLICKUP_API_KEY}

def get_clickup_list_tasks(list_id: str):
    if not list_id:
        return []
    try:
        res = requests.get(f"{CLICKUP_API_URL}/list/{list_id}/task", headers=_headers(), timeout=20)
        res.raise_for_status()
        return res.json().get("tasks", [])
    except Exception as e:
        print(f"⚠️ ClickUp list {list_id} fetch failed:", e)
        return []

def get_clickup_space_tasks(space_id: str):
    if not (space_id and CLICKUP_TEAM_ID):
        return []
    try:
        params = {
            "space_ids[]": space_id,
            "archived": "false",
            "statuses[]": ["to do", "in progress"],
        }
        url = f"{CLICKUP_API_URL}/team/{CLICKUP_TEAM_ID}/task"
        res = requests.get(url, headers=_headers(), params=params, timeout=25)
        res.raise_for_status()
        return res.json().get("tasks", [])
    except Exception as e:
        print(f"⚠️ ClickUp space {space_id} fetch failed:", e)
        return []

def update_clickup_task_status(task_id: str, status: str):
    """Optional ClickUp mirror - non-blocking"""
    try:
        res = requests.put(
            f"{CLICKUP_API_URL}/task/{task_id}",
            headers=_headers(),
            json={"status": status},
            timeout=20,
        )
        res.raise_for_status()
        return True
    except Exception as e:
        print(f"⚠️ ClickUp update failed for task {task_id}:", e)
        return False

# ------------------------------------------------------------------------------------
# PostgreSQL-first task operations
# ------------------------------------------------------------------------------------
def update_helios_task_status(task_id: str, status: str):
    """Update task status in Helios PostgreSQL database"""
    try:
        with db_session() as s:
            # Ensure tables exist
            s.execute(text("""
                CREATE SCHEMA IF NOT EXISTS helios;
                CREATE TABLE IF NOT EXISTS helios.triaged_tasks (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    due_date BIGINT,
                    priority INT,
                    score INT,
                    status TEXT
                );
            """))
            
            # Update status
            result = s.execute(
                text("UPDATE helios.triaged_tasks SET status = :status WHERE id = :id"),
                {"status": status, "id": task_id}
            )
            s.commit()
            
            if result.rowcount == 0:
                # Task not found in triaged_tasks, try to create it
                s.execute(
                    text("""
                        INSERT INTO helios.triaged_tasks (id, name, status, due_date, priority, score)
                        VALUES (:id, :name, :status, NULL, 1, 0)
                        ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status
                    """),
                    {"id": task_id, "name": f"Task {task_id}", "status": status}
                )
                s.commit()
                
            return True
    except Exception as e:
        print(f"⚠️ Helios task update failed for {task_id}:", e)
        raise HTTPException(status_code=500, detail=f"Failed to update task in Helios: {e}")

def create_helios_task_from_email(email_data: EmailTaskRequest):
    """Create a new task in Helios from email data"""
    try:
        task_id = f"email_{email_data.message_id}_{int(time.time())}"
        
        # Parse priority to score
        priority_map = {"low": 1, "normal": 2, "high": 3, "urgent": 4}
        priority_num = priority_map.get(email_data.priority, 2)
        score = priority_num * 10  # Basic scoring
        
        # Use due_ts or set reasonable default
        due_date = email_data.due_ts or (int(time.time() * 1000) + 86400000)  # +1 day
        
        with db_session() as s:
            # Ensure tables exist
            s.execute(text("""
                CREATE SCHEMA IF NOT EXISTS helios;
                CREATE TABLE IF NOT EXISTS helios.triaged_tasks (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    due_date BIGINT,
                    priority INT,
                    score INT,
                    status TEXT
                );
            """))
            
            # Create task
            s.execute(
                text("""
                    INSERT INTO helios.triaged_tasks (id, name, due_date, priority, score, status)
                    VALUES (:id, :name, :due_date, :priority, :score, :status)
                    ON CONFLICT (id) DO UPDATE SET 
                        name = EXCLUDED.name,
                        due_date = EXCLUDED.due_date,
                        priority = EXCLUDED.priority,
                        score = EXCLUDED.score,
                        status = EXCLUDED.status
                """),
                {
                    "id": task_id,
                    "name": f"Email: {email_data.subject}",
                    "due_date": due_date,
                    "priority": priority_num,
                    "score": score,
                    "status": "open"
                }
            )
            s.commit()
            
        return {
            "task_id": task_id,
            "name": f"Email: {email_data.subject}",
            "status": "open",
            "source": "helios_native"
        }
        
    except Exception as e:
        print(f"⚠️ Failed to create Helios task from email:", e)
        raise HTTPException(status_code=500, detail=f"Failed to create task: {e}")

# ------------------------------------------------------------------------------------
# NEW: ClickUp Migration Endpoints
# ------------------------------------------------------------------------------------
@router.post("/migrate/extract-clickup-complete")
def extract_complete_clickup_workspace():
    """
    🔄 COMPREHENSIVE: Extract entire ClickUp workspace for migration
    
    ⚠️ WARNING: This is a LONG-RUNNING operation (30-60 minutes)
    
    This endpoint pulls EVERYTHING from ClickUp:
    - All organizational structure (spaces, folders, lists)
    - All tasks with full metadata and recurrence patterns  
    - All task relationships and dependencies
    - All users and custom field definitions
    
    Includes proper rate limiting (95 requests/minute) to avoid 429 errors.
    Progress is logged to console. Saves to JSON file for analysis.
    """
    if not CLICKUP_API_KEY or not CLICKUP_TEAM_ID:
        raise HTTPException(status_code=400, detail="ClickUp credentials missing")
    
    try:
        extractor = ClickUpCompleteExtractor(CLICKUP_API_KEY, CLICKUP_TEAM_ID)
        
        # Give user a heads up about timing
        print("⚠️ Starting comprehensive ClickUp extraction...")
        print("⏳ This will take 30-60 minutes due to ClickUp's 100/minute rate limit")
        print("📊 Progress will be logged every 50 tasks processed")
        
        # Extract everything with proper rate limiting
        extraction = extractor.extract_complete_workspace(save_to_file=True)
        
        return {
            "success": True,
            "message": "Complete ClickUp workspace extracted successfully!",
            "duration": f"{extraction['metadata']['extraction_duration_seconds']/60:.1f} minutes",
            "statistics": extraction['statistics'],
            "api_usage": extraction['statistics']['api_statistics'],
            "saved_to_file": extraction['metadata'].get('saved_to_file'),
            "next_steps": [
                "Review the generated JSON file", 
                "Analyze recurring patterns and project structure",
                "Design Helios schema based on actual data",
                "Run migration script to create Helios-native tasks"
            ],
            "performance_notes": {
                "rate_limiting": "95 requests/minute (stayed under ClickUp's 100/min limit)",
                "throttling_effectiveness": f"{extraction['statistics']['api_statistics']['rate_limit_hits']} rate limit hits out of {extraction['statistics']['api_statistics']['total_requests']} requests"
            }
        }
        
    except Exception as e:
        print(f"❌ Complete extraction failed: {e}")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")

@router.get("/migrate/analyze-clickup-structure") 
def analyze_clickup_structure():
    """
    📊 ANALYSIS: Quick ClickUp structure overview before extraction
    
    Shows what we'll be extracting without doing the full extraction.
    This is FAST and helps estimate the extraction time.
    """
    try:
        extractor = ClickUpCompleteExtractor(CLICKUP_API_KEY, CLICKUP_TEAM_ID)
        
        # Quick counts only (no task extraction)
        spaces = extractor.get_all_spaces()
        folders = extractor.get_all_folders() 
        lists = extractor.get_all_lists()
        
        # Estimate total tasks from list metadata
        total_tasks_estimate = 0
        for lst in lists[:5]:  # Sample first 5 lists
            list_info = extractor._request(f"/list/{lst['id']}")
            total_tasks_estimate += list_info.get('task_count', 0)
        
        # Rough extrapolation
        if len(lists) > 5:
            avg_tasks_per_list = total_tasks_estimate / 5
            total_tasks_estimate = int(avg_tasks_per_list * len(lists))
        
        # Sample a few tasks to check recurrence patterns
        sample_tasks = []
        recurring_sample_count = 0
        if lists:
            sample_list = lists[0]
            data = extractor._request(f"/list/{sample_list['id']}/task", {"page": 0, "archived": "false"})
            sample_tasks = data.get("tasks", [])[:10]  # More samples
            
            # Check for recurrence in samples
            for task in sample_tasks:
                recurrence_info = extractor._extract_recurrence_pattern(task)
                task['helios_recurrence'] = recurrence_info
                if recurrence_info['is_recurring']:
                    recurring_sample_count += 1
        
        # Estimate extraction time
        estimated_api_calls = len(lists) * 3 + total_tasks_estimate * 0.5  # Rough estimate
        estimated_minutes = (estimated_api_calls / 95) + 5  # 95 calls/min + buffer
        
        return {
            "workspace_overview": {
                "spaces": len(spaces),
                "folders": len(folders), 
                "lists": len(lists),
                "estimated_total_tasks": total_tasks_estimate,
                "estimated_recurring_tasks": int((recurring_sample_count / len(sample_tasks)) * total_tasks_estimate) if sample_tasks else 0
            },
            "sample_tasks": sample_tasks,
            "performance_estimates": {
                "estimated_api_calls": int(estimated_api_calls),
                "estimated_duration_minutes": f"{estimated_minutes:.0f}-{estimated_minutes*1.5:.0f}",
                "rate_limiting": "95 requests/minute (proactive throttling)",
                "recommendation": "Schedule during off-hours due to long duration"
            },
            "ready_for_extraction": True,
            "warning": f"Extraction will take ~{estimated_minutes:.0f} minutes due to rate limiting"
        }
        
    except Exception as e:
        return {"error": str(e), "ready_for_extraction": False}

# ------------------------------------------------------------------------------------
# Main endpoints (UNCHANGED - your existing functionality)
# ------------------------------------------------------------------------------------
@router.post("/tasks/{id}/update-status")
def update_task_status(id: str, request: UpdateStatusRequest):
    """
    🔧 FIXED: PostgreSQL-first task completion
    
    This is the endpoint your Complete buttons call.
    Now updates Helios PostgreSQL first, ClickUp as optional mirror.
    """
    # 1) Update in Helios PostgreSQL (PRIMARY)
    try:
        update_helios_task_status(id, request.status)
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Helios update failed: {e}")

    # 2) Optional ClickUp mirror (non-blocking)
    clickup_success = update_clickup_task_status(id, request.status)
    
    return {
        "success": True,
        "task_id": id,
        "new_status": request.status,
        "helios_updated": True,
        "clickup_updated": clickup_success
    }

@router.post("/tasks/from-email")
def create_task_from_email(email_data: EmailTaskRequest):
    """
    🔧 FIXED: Create tasks in Helios PostgreSQL from email triage
    
    Used by your email triage system.
    """
    if email_data.dry_run:
        return {
            "dry_run": True,
            "would_create": f"Email: {email_data.subject}",
            "sender": email_data.sender
        }
    
    # Create in Helios (primary)
    helios_task = create_helios_task_from_email(email_data)
    
    # Optional ClickUp dual-write (if requested and not disabled)
    clickup_task = None
    if email_data.dual_write_clickup and CLICKUP_EMAIL_LIST_ID:
        try:
            clickup_payload = {
                "name": f"Email: {email_data.subject}",
                "description": f"From: {email_data.sender}\n\n{email_data.content}",
                "priority": {"urgent": 4, "high": 3, "normal": 2, "low": 1}.get(email_data.priority, 2),
                "due_date": email_data.due_ts,
            }
            res = requests.post(
                f"{CLICKUP_API_URL}/list/{CLICKUP_EMAIL_LIST_ID}/task",
                headers=_headers(),
                json=clickup_payload,
                timeout=20
            )
            if res.ok:
                clickup_task = res.json()
        except Exception as e:
            print(f"⚠️ ClickUp dual-write failed:", e)
    
    return {
        "success": True,
        "helios_task": helios_task,
        "clickup_task": clickup_task,
        "source": "helios_native"
    }

@router.get("/triaged-tasks")
def get_combined_triaged_tasks():
    """
    🔧 MIXED: DoNext from PostgreSQL, Email/Personal from ClickUp during migration
    
    This supports your current dashboard during the transition.
    """
    try:
        # 1) DoNext from Helios PostgreSQL (primary)
        do_next = top_triaged_tasks(limit=50)  # Increased limit

        # 2) Email list from ClickUp (during migration)
        email_tasks = get_clickup_list_tasks(CLICKUP_EMAIL_LIST_ID)

        # 3) Personal space from ClickUp (during migration)
        personal_tasks = get_clickup_space_tasks(CLICKUP_PERSONAL_SPACE_ID)
        personal_tasks = sorted(
            personal_tasks,
            key=lambda t: int(t.get("due_date", 0)) or 2**63 - 1
        )

        return {
            "doNext": do_next,
            "email": email_tasks,
            "personal": personal_tasks,
            "source": "mixed_helios_clickup"
        }
    except Exception as e:
        print("⚠️ Task aggregation failed:", e)
        raise HTTPException(status_code=500, detail=f"Failed to load task panels: {e}")

@router.get("/do-next-tasks")
def get_do_next_tasks():
    """Get top Do Next tasks from Helios PostgreSQL"""
    try:
        return {"doNext": top_triaged_tasks(limit=10)}
    except Exception as e:
        print("⚠️ doNext failed:", e)
        raise HTTPException(status_code=500, detail=f"doNext route failed: {e}")

@router.post("/refresh-triaged-tasks")
def refresh_triaged_tasks():
    """
    🔧 IMPROVED: Refresh triaged tasks with better error handling
    """
    try:
        # 1) Pull fresh from ClickUp for DoNext pool (during migration)
        tasks = CLIENT.refresh_triaged_view_source()

        # 2) Score/enrich with better logic
        now = int(time.time() * 1000)
        enriched = []
        
        for t in tasks:
            score = 0
            due = int(t.get("due_date") or 0)

            # Due date scoring
            if due > 0:
                diff_days = (due - now) / 86400000
                if diff_days < -7:    # Very overdue
                    score += 5
                elif diff_days < 0:   # Overdue
                    score += 4
                elif diff_days < 1:   # Due today
                    score += 3
                elif diff_days < 3:   # Due soon
                    score += 2
                elif diff_days < 7:   # Due this week
                    score += 1

            # Priority scoring
            priority = None
            try:
                priority_obj = t.get("priority")
                if isinstance(priority_obj, dict):
                    priority = int(priority_obj.get("priority", 1))
                elif priority_obj:
                    priority = int(priority_obj)
            except Exception:
                priority = 1
            
            if priority >= 4:  # Urgent
                score += 3
            elif priority >= 3:  # High
                score += 2
            elif priority >= 2:  # Normal
                score += 1

            # Tag-based scoring
            tags = []
            for tag in t.get("tags", []):
                if isinstance(tag, dict):
                    tags.append(tag.get("name", "").lower())
                else:
                    tags.append(str(tag).lower())
            
            if "urgent" in tags or "asap" in tags:
                score += 2
            if "email" in tags:
                score += 1

            enriched.append({
                "id": t["id"],
                "name": t["name"],
                "due_date": due,
                "priority": priority,
                "score": max(score, 1),  # Minimum score of 1
                "status": t.get("status", {}).get("status") if isinstance(t.get("status"), dict) else t.get("status", "open"),
            })

        # 3) Write to Postgres
        upsert_triaged_tasks(enriched)
        
        return {
            "success": True,
            "refreshed": len(enriched),
            "source": "clickup_to_helios"
        }
    except Exception as e:
        print("⚠️ Refresh triaged tasks failed:", e)
        raise HTTPException(status_code=500, detail=f"Failed to refresh triaged tasks: {e}")

@router.get("/fixed-date-tasks")
def get_fixed_date_tasks():
    """
    🔧 IMPROVED: Fixed date tasks with better error handling
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
            # Ensure tables exist
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
                CREATE TABLE IF NOT EXISTS helios.triaged_tasks (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    due_date BIGINT,
                    priority INT,
                    score INT,
                    status TEXT
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
                  COALESCE(t.name, 'Fixed deadline task') AS name,
                  t.due_date,
                  t.priority,
                  COALESCE(t.status, 'open') AS status
                FROM helios.task_meta m
                LEFT JOIN helios.triaged_tasks t ON t.id = m.task_id
                WHERE m.task_type = 'fixed_date'
                ORDER BY m.fixed_date ASC
            """)).mappings().all()

        out = []
        for r in rows:
            d = dict(r)
            due_iso = to_iso(d.pop("due_date"))
            d["due_date_iso"] = due_iso
            d["fixed_date"] = d["fixed_date"] or due_iso
            out.append(d)

        return out
    except Exception as e:
        print("⚠️ /fixed-date-tasks failed:", repr(e))
        raise HTTPException(status_code=500, detail=f"Failed to load fixed date tasks: {e}")

# ------------------------------------------------------------------------------------
# Task metadata endpoints (unchanged)
# ------------------------------------------------------------------------------------
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
        print("⚠️ set_task_meta failed:", e)
        raise HTTPException(status_code=500, detail=f"Failed to set task meta: {e}")

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
        print("⚠️ bulk_upsert_task_meta failed:", e)
        raise HTTPException(status_code=500, detail=f"Bulk upsert failed: {e}")

@router.get("/debug/db")
def db_debug():
    """🔧 ENHANCED: Database connectivity and status check"""
    try:
        with db_session() as s:
            ok = s.execute(text("SELECT 1")).scalar()
            
            # Check existing schema first
            schema_info = s.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema = 'helios' AND table_name = 'triaged_tasks'
                ORDER BY ordinal_position
            """)).mappings().all()
            
            # Ensure tables exist with correct schema
            s.execute(text("""
                CREATE SCHEMA IF NOT EXISTS helios;
                CREATE TABLE IF NOT EXISTS helios.triaged_tasks (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    due_date BIGINT,
                    priority INT,
                    score INT,
                    status TEXT
                );
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
            
            triaged_count = s.execute(text("SELECT COUNT(*) FROM helios.triaged_tasks")).scalar()
            meta_count = s.execute(text("SELECT COUNT(*) FROM helios.task_meta")).scalar()
            
            # Sample data
            recent_tasks = s.execute(text("""
                SELECT id, name, status FROM helios.triaged_tasks 
                ORDER BY score DESC 
                LIMIT 5
            """)).mappings().all()
            
        return {
            "engine": "postgresql",
            "status": "connected",
            "ok": ok == 1,
            "tables": {
                "triaged_tasks": triaged_count,
                "task_meta": meta_count
            },
            "schema": [dict(r) for r in schema_info],
            "recent_tasks": [dict(r) for r in recent_tasks],
            "migration_status": "helios_native_ready"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database debug failed: {e}")

@router.post("/debug/fix-schema")
def fix_schema():
    """🔧 AUTO-FIX: Handle VIEW vs TABLE issue and create proper table"""
    try:
        with db_session() as s:
            fixes_applied = []
            
            # Step 1: First check if triaged_tasks exists and what type it is
            relation_check = s.execute(text("""
                SELECT 
                    CASE 
                        WHEN EXISTS (
                            SELECT 1 FROM information_schema.views 
                            WHERE table_schema = 'helios' AND table_name = 'triaged_tasks'
                        ) THEN 'VIEW'
                        WHEN EXISTS (
                            SELECT 1 FROM information_schema.tables 
                            WHERE table_schema = 'helios' AND table_name = 'triaged_tasks'
                            AND table_type = 'BASE TABLE'
                        ) THEN 'TABLE'
                        ELSE 'NONE'
                    END as relation_type
            """)).fetchone()
            
            relation_type = relation_check[0] if relation_check else 'NONE'
            fixes_applied.append(f"Detected triaged_tasks as: {relation_type}")
            
            if relation_type == 'VIEW':
                # Handle VIEW: Drop and recreate as table
                fixes_applied.append("Converting VIEW to TABLE...")
                
                # Get current data from the view
                try:
                    current_data = s.execute(text("SELECT * FROM helios.triaged_tasks LIMIT 5")).fetchall()
                    fixes_applied.append(f"Found {len(current_data)} sample records in view")
                except Exception as e:
                    fixes_applied.append(f"Could not read from view: {str(e)}")
                
                # Drop the view
                s.execute(text("DROP VIEW IF EXISTS helios.triaged_tasks CASCADE"))
                fixes_applied.append("Dropped VIEW helios.triaged_tasks")
                
                # Create new table with proper schema
                s.execute(text("""
                    CREATE TABLE helios.triaged_tasks (
                        id SERIAL PRIMARY KEY,
                        title VARCHAR(500),
                        description TEXT,
                        status VARCHAR(50) DEFAULT 'pending',
                        priority VARCHAR(20) DEFAULT 'medium',
                        due_date BIGINT,  -- Already as BIGINT (timestamp)
                        created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW()) * 1000,
                        updated_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW()) * 1000,
                        tags TEXT[],
                        assignee VARCHAR(255),
                        source VARCHAR(100),
                        metadata JSONB DEFAULT '{}'::jsonb
                    )
                """))
                fixes_applied.append("Created new TABLE helios.triaged_tasks with proper schema")
                
            elif relation_type == 'TABLE':
                # Handle existing table: Check and fix schema
                fixes_applied.append("Working with existing TABLE...")
                
                # Check current due_date column type
                col_check = s.execute(text("""
                    SELECT data_type, is_nullable
                    FROM information_schema.columns 
                    WHERE table_schema = 'helios' 
                    AND table_name = 'triaged_tasks' 
                    AND column_name = 'due_date'
                """)).fetchone()
                
                if col_check:
                    current_type = col_check[0]
                    fixes_applied.append(f"Current due_date type: {current_type}")
                    
                    if current_type != 'bigint':
                        # Convert due_date to BIGINT
                        s.execute(text("""
                            ALTER TABLE helios.triaged_tasks 
                            ALTER COLUMN due_date TYPE BIGINT 
                            USING CASE 
                                WHEN due_date IS NULL THEN NULL
                                ELSE EXTRACT(EPOCH FROM due_date) * 1000
                            END
                        """))
                        fixes_applied.append("Converted due_date to BIGINT (timestamp)")
                    else:
                        fixes_applied.append("due_date already BIGINT - no change needed")
                else:
                    # Add due_date column if missing
                    s.execute(text("""
                        ALTER TABLE helios.triaged_tasks 
                        ADD COLUMN IF NOT EXISTS due_date BIGINT
                    """))
                    fixes_applied.append("Added missing due_date column as BIGINT")
                    
            else:
                # Create table from scratch
                fixes_applied.append("Creating new TABLE from scratch...")
                s.execute(text("""
                    CREATE TABLE helios.triaged_tasks (
                        id SERIAL PRIMARY KEY,
                        title VARCHAR(500),
                        description TEXT,
                        status VARCHAR(50) DEFAULT 'pending',
                        priority VARCHAR(20) DEFAULT 'medium',
                        due_date BIGINT,
                        created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW()) * 1000,
                        updated_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW()) * 1000,
                        tags TEXT[],
                        assignee VARCHAR(255),
                        source VARCHAR(100),
                        metadata JSONB DEFAULT '{}'::jsonb
                    )
                """))
                fixes_applied.append("Created new TABLE helios.triaged_tasks")
            
            # Verify final schema
            final_check = s.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_schema = 'helios' 
                AND table_name = 'triaged_tasks'
                ORDER BY ordinal_position
            """)).fetchall()
            
            schema_info = [f"{col[0]}: {col[1]}" for col in final_check]
            
            s.commit()
            
            return {
                "status": "success",
                "message": "Schema fixed successfully! ✅",
                "fixes_applied": fixes_applied,
                "final_schema": schema_info
            }
            
    except Exception as e:
        return {
            "status": "error", 
            "detail": f"Schema fix failed: {str(e)}",
            "fixes_attempted": fixes_applied if 'fixes_applied' in locals() else []
        }