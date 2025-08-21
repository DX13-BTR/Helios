# core_py/routes/contacts_admin.py
import os
from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.orm import Session
from sqlalchemy import text
from core_py.db.session import engine, get_session

router = APIRouter(prefix="/contacts-admin", tags=["contacts-admin"])

# --- Security ---
def require_admin(x_admin_key: str | None = Header(default=None)):
    admin_key = os.getenv("ADMIN_KEY")
    if not admin_key:
        raise HTTPException(status_code=500, detail="Admin key not configured")
    if x_admin_key != admin_key:
        raise HTTPException(status_code=401, detail="unauthorized")
    return True

# --- Routes ---
@router.post("/allowlist/rebuild")
def rebuild_allowlist(
    db: Session = Depends(get_session),
    _: bool = Depends(require_admin)
):
    """
    Rebuild allowlist from clients, emails, and domains in Postgres.
    """
    # Wipe current allowlist
    db.execute(text("TRUNCATE allowlist_emails, allowlist_domains RESTART IDENTITY CASCADE"))

    # Insert emails
    db.execute(text("""
        INSERT INTO allowlist_emails (email)
        SELECT DISTINCT LOWER(email)
        FROM client_emails
    """))

    # Insert domains
    db.execute(text("""
        INSERT INTO allowlist_domains (domain)
        SELECT DISTINCT LOWER(domain)
        FROM client_domains
    """))

    db.commit()
    return {"ok": True, "message": "Allowlist fully rebuilt"}

@router.get("/allowlist/cleanup")
def allowlist_cleanup(
    db: Session = Depends(get_session),
    _: bool = Depends(require_admin)
):
    """
    Cleanup orphaned emails/domains (where associated client no longer exists).
    """
    # Clean orphaned emails
    db.execute(text("""
        DELETE FROM allowlist_emails
        WHERE email NOT IN (
            SELECT LOWER(email) FROM client_emails
        )
    """))

    # Clean orphaned domains
    db.execute(text("""
        DELETE FROM allowlist_domains
        WHERE domain NOT IN (
            SELECT LOWER(domain) FROM client_domains
        )
    """))

    db.commit()
    return {"ok": True, "message": "Orphaned allowlist entries cleaned up"}

@router.post("/clients/{client_id}/add-email")
def add_client_email(
    client_id: str,
    email: str,
    db: Session = Depends(get_session),
    _: bool = Depends(require_admin)
):
    """
    Add a new email to an existing client, Postgres-safe with ON CONFLICT DO NOTHING.
    """
    db.execute(text("""
        INSERT INTO client_emails (id, client_id, email)
        VALUES (:id, :client_id, LOWER(:email))
        ON CONFLICT (id) DO NOTHING
    """), {"id": f"{client_id}:{email}", "client_id": client_id, "email": email})
    db.commit()
    return {"ok": True, "client_id": client_id, "email": email}

@router.post("/clients/{client_id}/add-domain")
def add_client_domain(
    client_id: str,
    domain: str,
    wildcard: bool = False,
    db: Session = Depends(get_session),
    _: bool = Depends(require_admin)
):
    """
    Add a new domain to an existing client, Postgres-safe with ON CONFLICT DO NOTHING.
    """
    db.execute(text("""
        INSERT INTO client_domains (id, client_id, domain, wildcard)
        VALUES (:id, :client_id, LOWER(:domain), :wildcard)
        ON CONFLICT (id) DO NOTHING
    """), {"id": f"{client_id}:{domain}:{int(wildcard)}", "client_id": client_id, "domain": domain, "wildcard": wildcard})
    db.commit()
    return {"ok": True, "client_id": client_id, "domain": domain, "wildcard": wildcard}
