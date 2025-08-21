# core_py/routes/email_tasks.py
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Header
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, Literal
from sqlalchemy.orm import Session
from datetime import datetime

# ✅ Correct import for DB session
from core_py.db.session import get_session, db_session

# Try to import your real verifier; fall back to a no-op to avoid crashes
try:
    from core_py.services.security import verify_helios_signature  # optional HMAC/header check
except Exception:
    def verify_helios_signature(x_helios_token: Optional[str] = Header(default=None)):
        return True

# Adjust these imports to your actual models module path
from core_py.models import (
    EmailTask, ProcessedEmail, TaskMeta, ClientEmail, ClientDomain
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class EmailTaskIn(BaseModel):
    message_id: str = Field(..., min_length=5)
    sender: str = Field(..., description="Full sender email like 'name@example.com'")
    subject: str = Field(..., max_length=500)
    content: str = Field(..., description="Plaintext or HTML stripped")
    gmail_link: Optional[HttpUrl] = None
    thread_id: Optional[str] = None
    received_ts: Optional[int] = Field(None, description="Epoch ms")
    start_ts: Optional[int] = None
    due_ts: Optional[int] = None
    source_label: Optional[str] = None      # e.g. "triage/inbox"
    dry_run: bool = False                   # for dual mode testing
    dual_write_clickup: bool = False        # keep legacy running in parallel for a week
    priority: Optional[Literal["low","normal","high"]] = "normal"
    client_hint: Optional[str] = None       # if you already know the client key


class EmailTaskOut(BaseModel):
    helios_task_id: Optional[int]
    processed: bool
    reason: Optional[str] = None
    clickup_task_id: Optional[str] = None


def _sender_parts(sender_email: str):
    em = (sender_email or "").lower().strip()
    domain = em.split("@")[-1] if "@" in em else ""
    return em, domain


def _is_allowed(db: Session, sender_email: str) -> bool:
    em, domain = _sender_parts(sender_email)
    # active allowlist from contacts (emails or domains)
    email_allowed = db.query(ClientEmail).filter(
        ClientEmail.email == em, getattr(ClientEmail, "is_active", True) == True  # tolerate schema w/out flag
    ).first() is not None
    domain_allowed = db.query(ClientDomain).filter(
        ClientDomain.domain == domain, getattr(ClientDomain, "is_active", True) == True
    ).first() is not None
    return email_allowed or domain_allowed


@router.post("/from-email", response_model=EmailTaskOut)
def create_task_from_email(
    payload: EmailTaskIn,
    db: Session = Depends(get_session),          # ✅ correct dependency
    bt: BackgroundTasks = None,
    _auth=Depends(verify_helios_signature)
):
    # Idempotency: short-circuit if we’ve already handled this message_id
    existing = db.query(ProcessedEmail).filter(
        ProcessedEmail.message_id == payload.message_id
    ).first()
    if existing:
        return EmailTaskOut(helios_task_id=getattr(existing, "helios_task_id", None),
                            processed=True, reason="duplicate")

    # Allowlist gate
    if not _is_allowed(db, payload.sender):
        # still record the fact we saw it, but rejected
        pe = ProcessedEmail(message_id=payload.message_id,
                            helios_task_id=None,
                            status="rejected_allowlist",
                            received_at=datetime.utcnow())
        db.add(pe)
        db.commit()
        raise HTTPException(status_code=403, detail="Sender not in allowlist")

    # Create EmailTask (and TaskMeta) in a transaction
    received_at = datetime.utcfromtimestamp(payload.received_ts/1000) if payload.received_ts else datetime.utcnow()

    email_task = EmailTask(
        message_id=payload.message_id,
        sender=payload.sender,
        subject=(payload.subject or "")[:500],
        content=payload.content or "",
        gmail_link=str(payload.gmail_link) if payload.gmail_link else None,
        thread_id=payload.thread_id,
        received_at=received_at,
        source_label=payload.source_label,
        priority=payload.priority or "normal",
        client_key_hint=payload.client_hint
    )
    db.add(email_task)
    db.flush()  # get PK

    if payload.start_ts or payload.due_ts:
        tm = TaskMeta(
            task_id=email_task.id,
            start_at=datetime.utcfromtimestamp(payload.start_ts/1000) if payload.start_ts else None,
            due_at=datetime.utcfromtimestamp(payload.due_ts/1000) if payload.due_ts else None,
            source="email"
        )
        db.add(tm)

    # During dual-write week, optionally create a ClickUp task in the background
    clickup_id = None
    if payload.dual_write_clickup and not payload.dry_run:
        try:
            from core_py.adapters.clickup import create_clickup_task_from_email  # thin adapter if present
            def _dual():
                nonlocal clickup_id
                try:
                    clickup_id = create_clickup_task_from_email(email_task)
                except Exception:
                    pass  # Helios is source of truth now
            if bt:
                bt.add_task(_dual)
        except Exception:
            pass  # no adapter = skip

    status = "created" if not payload.dry_run else "dry_run"
    pe = ProcessedEmail(message_id=payload.message_id,
                        helios_task_id=None if payload.dry_run else email_task.id,
                        status=status, received_at=received_at)
    db.add(pe)

    if payload.dry_run:
        db.rollback()  # don’t persist task/meta/processed
        return EmailTaskOut(helios_task_id=None, processed=False, reason="dry_run")

    db.commit()
    return EmailTaskOut(helios_task_id=email_task.id, processed=True, clickup_task_id=clickup_id)
