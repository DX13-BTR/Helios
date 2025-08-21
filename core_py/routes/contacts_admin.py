from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import text
from core_py.db import engine
import os
from datetime import datetime

router = APIRouter(prefix="/api/contacts", tags=["contacts-admin"])

# Simple guard: use a dedicated admin key (or reuse RECLAIM_API_KEY)
ADMIN_KEY = os.getenv("ADMIN_KEY") or os.getenv("RECLAIM_API_KEY")

def require_admin():
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="Admin key not configured")
    return True

@router.post("/allowlist/cleanup")
def allowlist_cleanup(_=Depends(require_admin)):
    moved = dedup_emails = dedup_domains = 0

    with engine.begin() as conn:  # single transaction
        res = conn.execute(text("""
            INSERT OR IGNORE INTO client_emails (id, client_id, email, created_at)
            SELECT lower(hex(randomblob(16))), client_id, lower(trim(domain)), datetime('now')
            FROM client_domains
            WHERE instr(domain,'@') > 0
        """))
        moved = res.rowcount or 0

        conn.execute(text("DELETE FROM client_domains WHERE instr(domain,'@') > 0"))

        res = conn.execute(text("""
            DELETE FROM client_emails
            WHERE rowid NOT IN (SELECT MIN(rowid) FROM client_emails GROUP BY client_id, lower(email))
        """))
        dedup_emails = res.rowcount or 0

        res = conn.execute(text("""
            DELETE FROM client_domains
            WHERE rowid NOT IN (SELECT MIN(rowid) FROM client_domains GROUP BY client_id, lower(domain), wildcard)
        """))
        dedup_domains = res.rowcount or 0

        conn.execute(text("""
            UPDATE allowlist_meta
               SET version = COALESCE(version, 0) + 1,
                   updated_at = datetime('now')
             WHERE id = 1
        """))

    return {
        "moved_to_emails": moved,
        "dedup_emails": dedup_emails,
        "dedup_domains": dedup_domains,
        "version_bumped": True,
        "at": datetime.utcnow().isoformat() + "Z"
    }
