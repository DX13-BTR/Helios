# core_py/routes/contacts.py
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_py.db.database import get_engine
from core_py.models import Client, ClientEmail, ClientDomain

router = APIRouter(tags=["contacts"])

# Create a plain Session bound to the shared engine (no helpers)
_engine = get_engine()

def db_session() -> Session:
    return Session(bind=_engine)


# ---------- Schemas ----------
class ClientIn(BaseModel):
    id: str
    name: str

class ClientOut(BaseModel):
    id: str
    name: str

class EmailIn(BaseModel):
    email: EmailStr
    created_at: Optional[datetime] = None

class EmailOut(BaseModel):
    id: str
    client_id: str
    email: EmailStr
    created_at: Optional[datetime] = None

class DomainIn(BaseModel):
    domain: str
    wildcard: bool = False

class DomainOut(BaseModel):
    id: str
    client_id: str
    domain: str
    wildcard: bool

# NEW: allowlist response (for the email triage client)
class AllowlistResponse(BaseModel):
    emails: List[str]
    domains: List[str]


# ---------- Routes ----------
@router.get("/clients", response_model=List[ClientOut])
def list_clients():
    with db_session() as s:
        rows = s.execute(select(Client)).scalars().all()
        return [ClientOut(id=c.id, name=c.name) for c in rows]


@router.post("/clients", response_model=ClientOut)
def upsert_client(payload: ClientIn):
    with db_session() as s:
        c = s.get(Client, payload.id)
        if c is None:
            c = Client(id=payload.id, name=payload.name)
            s.add(c)
        else:
            c.name = payload.name
        s.commit()
        return ClientOut(id=c.id, name=c.name)


@router.get("/clients/{client_id}", response_model=ClientOut)
def get_client(client_id: str):
    with db_session() as s:
        c = s.get(Client, client_id)
        if not c:
            raise HTTPException(status_code=404, detail="Client not found")
        return ClientOut(id=c.id, name=c.name)


@router.get("/clients/{client_id}/emails", response_model=List[EmailOut])
def list_client_emails(client_id: str):
    with db_session() as s:
        if not s.get(Client, client_id):
            raise HTTPException(status_code=404, detail="Client not found")
        rows = (
            s.execute(select(ClientEmail).where(ClientEmail.client_id == client_id))
            .scalars()
            .all()
        )
        return [
            EmailOut(id=e.id, client_id=e.client_id, email=e.email, created_at=e.created_at)
            for e in rows
        ]


@router.post("/clients/{client_id}/emails", response_model=EmailOut)
def add_client_email(client_id: str, payload: EmailIn):
    with db_session() as s:
        c = s.get(Client, client_id)
        if not c:
            raise HTTPException(status_code=404, detail="Client not found")
        e = ClientEmail(
            id=f"{client_id}:{payload.email}",
            client_id=client_id,
            email=str(payload.email),
            created_at=payload.created_at,
        )
        s.merge(e)  # respects uq_client_email
        s.commit()
        e = s.get(ClientEmail, e.id)
        return EmailOut(id=e.id, client_id=e.client_id, email=e.email, created_at=e.created_at)


@router.get("/clients/{client_id}/domains", response_model=List[DomainOut])
def list_client_domains(client_id: str):
    with db_session() as s:
        if not s.get(Client, client_id):
            raise HTTPException(status_code=404, detail="Client not found")
        rows = (
            s.execute(select(ClientDomain).where(ClientDomain.client_id == client_id))
            .scalars()
            .all()
        )
        return [
            DomainOut(id=d.id, client_id=d.client_id, domain=d.domain, wildcard=d.wildcard)
            for d in rows
        ]


@router.post("/clients/{client_id}/domains", response_model=DomainOut)
def add_client_domain(client_id: str, payload: DomainIn):
    with db_session() as s:
        c = s.get(Client, client_id)
        if not c:
            raise HTTPException(status_code=404, detail="Client not found")
        d = ClientDomain(
            id=f"{client_id}:{payload.domain}:{int(payload.wildcard)}",
            client_id=client_id,
            domain=payload.domain,
            wildcard=payload.wildcard,
        )
        s.merge(d)  # respects uq_client_domain_wild
        s.commit()
        d = s.get(ClientDomain, d.id)
        return DomainOut(id=d.id, client_id=d.client_id, domain=d.domain, wildcard=d.wildcard)


# NEW: single allowlist endpoint for the triage client
@router.get("/allowlist", response_model=AllowlistResponse)
def get_allowlist():
    with db_session() as s:
        email_rows = s.execute(select(ClientEmail.email)).scalars().all()
        domain_rows = s.execute(select(ClientDomain.domain)).scalars().all()

    # normalize, de-duplicate, sort for stable client caching
    emails = sorted({(e or "").strip().lower() for e in email_rows if e})
    domains = sorted({(d or "").strip().lower() for d in domain_rows if d})
    return AllowlistResponse(emails=emails, domains=domains)
