# core_py/routes/email_tasks_read.py
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from core_py.db.session import get_db
from core_py.models import EmailTask, TaskMeta

router = APIRouter(prefix="/api", tags=["tasks"])

class EmailTaskRow(BaseModel):
    id: str; sender: str; subject: str
    snippet: Optional[str] = None
    gmail_link: Optional[str] = None
    thread_id: Optional[str] = None
    received_at: Optional[datetime] = None
    created_at: datetime
    source_label: Optional[str] = None
    priority: Optional[str] = None
    client_key_hint: Optional[str] = None
    start_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    source: Optional[str] = None
    class Config: from_attributes = True

@router.get("/email-tasks/latest", response_model=List[EmailTaskRow])
def list_email_tasks(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sender: Optional[str] = None,
    source_label: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = (
        db.query(
            EmailTask.id, EmailTask.sender, EmailTask.subject, EmailTask.snippet,
            EmailTask.gmail_link, EmailTask.thread_id, EmailTask.received_at,
            EmailTask.created_at, EmailTask.source_label, EmailTask.priority,
            EmailTask.client_key_hint, TaskMeta.start_at, TaskMeta.due_at, TaskMeta.source
        ).outerjoin(TaskMeta, TaskMeta.task_id == EmailTask.id)
    )
    if sender: q = q.filter(EmailTask.sender == sender)
    if source_label: q = q.filter(EmailTask.source_label == source_label)
    q = q.order_by(func.coalesce(EmailTask.received_at, EmailTask.created_at).desc())
    rows = q.offset(offset).limit(limit).all()
    return [EmailTaskRow(**dict(r._mapping)) for r in rows]
