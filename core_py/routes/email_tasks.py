# core_py/routes/email_tasks.py
# Full replacement: email → task ingestion (Postgres only)

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core_py.db.session import get_db
from core_py.models import EmailTask, ProcessedEmail, TaskMeta

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ---------------------------
# Pydantic schemas
# ---------------------------

class EmailTaskIn(BaseModel):
    message_id: str = Field(..., description="Stable ID from mail provider (used as EmailTask.id)")
    sender: str = Field(..., description="From email address")
    subject: Optional[str] = None
    content: Optional[str] = None

    gmail_link: Optional[str] = None
    thread_id: Optional[str] = None

    # epoch milliseconds; all optional
    received_ts: Optional[int] = None
    start_ts: Optional[int] = None
    due_ts: Optional[int] = None

    source_label: Optional[str] = None
    priority: Optional[str] = None
    client_hint: Optional[str] = None

    # control flags
    dry_run: bool = False
    dual_write_clickup: bool = False  # ignored (migration off ClickUp)


class EmailTaskOut(BaseModel):
    # EmailTask.id is VARCHAR, not int
    helios_task_id: Optional[str] = None
    processed: bool = True
    reason: Optional[str] = None
    clickup_task_id: Optional[str] = None  # reserved; always None in this migration


# ---------------------------
# Helpers
# ---------------------------

def _ms_to_dt(ms: Optional[int]) -> Optional[datetime]:
    if ms is None:
        return None
    try:
        return datetime.utcfromtimestamp(int(ms) / 1000)
    # Protect against strings or bad numbers
    except Exception:
        return None


def _email_domain(addr: str) -> Optional[str]:
    if not addr or "@" not in addr:
        return None
    return addr.rsplit("@", 1)[-1].lower()


def _is_sender_allowlisted(db: Session, sender: str) -> bool:
    """
    Allow if exact address is present in client_emails.email OR domain is present in client_domains.domain.
    These tables exist per your schema; we keep the query minimal and defensive.
    """
    try:
        email_l = sender.lower()
        domain_l = _email_domain(sender)

        row = db.execute(text("SELECT 1 FROM client_emails WHERE lower(email)=:e LIMIT 1"),
                         {"e": email_l}).first()
        if row:
            return True

        if domain_l:
            row = db.execute(text("SELECT 1 FROM client_domains WHERE lower(domain)=:d LIMIT 1"),
                             {"d": domain_l}).first()
            if row:
                return True
    except SQLAlchemyError:
        # If allowlist tables are temporarily unavailable, fail closed (reject)
        return False

    return False


def _resolve_client_id(db: Session, sender: str, client_hint: Optional[str]) -> Optional[str]:
    """
    Try to resolve a client_id from allowlist tables; fallback to None.
    We do NOT force client_id to client_hint (hint is stored in client_key_hint column).
    """
    try:
        email_l = sender.lower()
        domain_l = _email_domain(sender)

        row = db.execute(text("SELECT client_id FROM client_emails WHERE lower(email)=:e LIMIT 1"),
                         {"e": email_l}).first()
        if row and row[0]:
            return str(row[0])

        if domain_l:
            row = db.execute(text("SELECT client_id FROM client_domains WHERE lower(domain)=:d LIMIT 1"),
                             {"d": domain_l}).first()
            if row and row[0]:
                return str(row[0])
    except SQLAlchemyError:
        pass

    return None


# ---------------------------
# Route
# ---------------------------

@router.post("/from-email", response_model=EmailTaskOut)
def create_task_from_email(payload: EmailTaskIn, db: Session = Depends(get_db)) -> EmailTaskOut:
    """
    Ingest an email as a task:
      - Enforces dedupe by ProcessedEmail.message_id (unique)
      - Validates allowlist (email/domain); if blocked → logs 'rejected_allowlist'
      - Writes EmailTask (+ TaskMeta if provided) and ProcessedEmail
    """
    # Idempotency: if we've already processed this message_id, short-circuit.
    existing = db.query(ProcessedEmail).filter(ProcessedEmail.message_id == payload.message_id).first()
    if existing:
        return EmailTaskOut(helios_task_id=existing.helios_task_id, processed=True, reason="duplicate")

    # If dry-run, don't write anything
    if payload.dry_run:
        return EmailTaskOut(helios_task_id=None, processed=True, reason="dry_run")

    # Timestamps
    now = datetime.utcnow()
    received_at = _ms_to_dt(payload.received_ts) or now
    start_at = _ms_to_dt(payload.start_ts)
    due_at = _ms_to_dt(payload.due_ts)

    # Allowlist check
    if not _is_sender_allowlisted(db, payload.sender):
        try:
            db.add(ProcessedEmail(
                message_id=payload.message_id,
                helios_task_id=None,
                status="rejected_allowlist",
                received_at=received_at,
                processed_at=now,  # explicit even though DB has default
            ))
            db.commit()
        except Exception:
            db.rollback()
        # Return 200 with reason (keeps upstream pipelines simple)
        return EmailTaskOut(helios_task_id=None, processed=True, reason="rejected_allowlist")

    # Create the task + meta + processed rows in one transaction
    try:
        # Resolve client_id if present in allowlist tables (optional)
        client_id = _resolve_client_id(db, payload.sender, payload.client_hint)

        # Build the EmailTask (map message_id -> id; content -> body_text; set created_at)
        email_task = EmailTask(
            id=payload.message_id,
            client_id=client_id,
            sender=payload.sender,
            subject=(payload.subject or "")[:500],
            snippet=(payload.content or "")[:500],
            body_html=None,
            body_text=payload.content or "",
            created_at=received_at,            # table has NOT NULL; DB default also present
            gmail_link=payload.gmail_link,
            thread_id=payload.thread_id,
            received_at=received_at,
            source_label=payload.source_label,
            priority=payload.priority or "normal",
            client_key_hint=payload.client_hint,
        )
        db.add(email_task)

        # Optional scheduling metadata
        if start_at or due_at:
            db.add(TaskMeta(
                task_id=email_task.id,
                start_at=start_at,
                due_at=due_at,
                source="email",
            ))

        # Log the processing (dedupe ledger)
        db.add(ProcessedEmail(
            message_id=payload.message_id,
            helios_task_id=email_task.id,
            status="created",
            received_at=received_at,
            processed_at=now,  # explicit even with DB default
        ))

        db.commit()
        return EmailTaskOut(helios_task_id=email_task.id, processed=True, reason="created")

    except SQLAlchemyError as e:
        db.rollback()
        # If this fails due to a unique race, convert to duplicate
        if "ix_processed_emails_message_id" in str(e) or "processed_emails_message_id_key" in str(e):
            return EmailTaskOut(helios_task_id=None, processed=True, reason="duplicate")
        raise HTTPException(status_code=500, detail="internal_error")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="internal_error")
