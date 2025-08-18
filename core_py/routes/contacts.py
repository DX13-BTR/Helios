# core_py/routes/contacts.py
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict
from datetime import datetime
import json
from pydantic import BaseModel

from core_py.db.sqlite_conn import q_all, q_one, q_exec, tx
from core_py.utils.contacts_norm import uuid4, normalize_email, normalize_domain

router = APIRouter(prefix="", tags=["contacts"])

# --------- Schemas (lightweight) ----------
from pydantic import BaseModel, Field


class DomainIn(BaseModel):
    domain: str
    wildcard: bool = False


class ClientCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    emails: List[str] = Field(default_factory=list)
    domains: List[DomainIn] = Field(default_factory=list)


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    emails: Optional[List[str]] = None
    domains: Optional[List[DomainIn]] = None
    active: Optional[bool] = None


# --------- Helpers ----------
def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def hydrate_client(cid: str):
    r = q_one("SELECT * FROM clients WHERE id=?", (cid,))
    if not r:
        raise HTTPException(404, "Client not found")
    r["tags"] = json.loads(r.get("tags_json") or "[]")
    r["active"] = bool(r["active"])
    r["emails"] = [
        e["email"]
        for e in q_all(
            "SELECT email FROM client_emails WHERE client_id=? ORDER BY email", (cid,)
        )
    ]
    r["domains"] = [
        {"domain": d["domain"], "wildcard": bool(d["wildcard"])}
        for d in q_all(
            "SELECT domain, wildcard FROM client_domains WHERE client_id=? ORDER BY domain",
            (cid,),
        )
    ]
    return r


# --------- Routes ----------
@router.get("/contacts/lookup-by-attendees")
def contacts_lookup_by_attendees(emails: List[str] = Query(default=[])) -> Dict:
    """
    Given a list of attendee emails, return probable client matches.
    Match order: direct email > exact domain > wildcard domain.
    """
    emails = [normalize_email(e) for e in emails if e]
    candidates = {}

    for e in emails:
        if not e or "@" not in e:
            continue

        # 1) direct email
        row = q_one("""
          SELECT c.id AS client_id
          FROM client_emails ce
          JOIN clients c ON c.id=ce.client_id
          WHERE lower(ce.email)=?
        """, (e,))
        if row:
            cid = row["client_id"]
            candidates.setdefault(cid, {"score": 100, "reason": "email"})
            continue

        # 2) exact domain
        dom = normalize_domain(e.split("@", 1)[1])
        row = q_one("""
          SELECT c.id AS client_id
          FROM client_domains cd
          JOIN clients c ON c.id=cd.client_id
          WHERE lower(cd.domain)=? AND cd.wildcard=0
        """, (dom,))
        if row:
            cid = row["client_id"]
            cur = candidates.get(cid, {"score": 0})
            candidates[cid] = {"score": max(cur["score"], 80), "reason": "domain"}

        # 3) wildcard domain
        row = q_one("""
          SELECT c.id AS client_id
          FROM client_domains cd
          JOIN clients c ON c.id=cd.client_id
          WHERE cd.wildcard=1
            AND (? LIKE '%.' || lower(cd.domain) OR ? = lower(cd.domain))
        """, (dom, dom))
        if row:
            cid = row["client_id"]
            cur = candidates.get(cid, {"score": 0})
            candidates[cid] = {"score": max(cur["score"], 60), "reason": "wildcard"}

    # hydrate results (reuse existing logic)
    results = []
    for cid, meta in candidates.items():
        try:
            c = hydrate_client(cid)
            c["_match"] = meta
            results.append(c)
        except Exception:
            pass

    # sort by score desc
    results.sort(key=lambda x: x.get("_match", {}).get("score", 0), reverse=True)
    return {"matches": results, "count": len(results)}

@router.get("/clients")
def list_clients(q: str = "", active: Optional[bool] = None):
    params, where = [], []
    if q:
        where.append("name LIKE ?")
        params.append(f"%{q}%")
    if active is not None:
        where.append("active = ?")
        params.append(1 if active else 0)
    sql = "SELECT * FROM clients"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY name COLLATE NOCASE"
    rows = q_all(sql, params)
    out = []
    for r in rows:
        r["tags"] = json.loads(r.get("tags_json") or "[]")
        r["active"] = bool(r["active"])
        r["emails"] = [
            e["email"]
            for e in q_all(
                "SELECT email FROM client_emails WHERE client_id=? ORDER BY email",
                (r["id"],),
            )
        ]
        r["domains"] = [
            {"domain": d["domain"], "wildcard": bool(d["wildcard"])}
            for d in q_all(
                "SELECT domain, wildcard FROM client_domains WHERE client_id=? ORDER BY domain",
                (r["id"],),
            )
        ]
        out.append(r)
    return out


@router.post("/clients")
def create_client(body: ClientCreate):
    now, cid = now_iso(), uuid4()
    with tx():
        # unique name
        if q_one("SELECT 1 FROM clients WHERE name=?", (body.name.strip(),)):
            raise HTTPException(409, "Client name already exists")
        q_exec(
            """INSERT INTO clients (id,name,phone,notes,tags_json,active,created_at,updated_at)
                  VALUES (?,?,?,?,?,?,?,?)""",
            (
                cid,
                body.name.strip(),
                body.phone,
                body.notes,
                json.dumps(body.tags),
                1,
                now,
                now,
            ),
        )
        for e in body.emails:
            em = normalize_email(e)
            if em:
                q_exec(
                    "INSERT OR IGNORE INTO client_emails (id,client_id,email,created_at) VALUES (?,?,?,?)",
                    (uuid4(), cid, em, now),
                )
        for d in body.domains:
            q_exec(
                """INSERT OR IGNORE INTO client_domains (id,client_id,domain,wildcard,created_at)
                      VALUES (?,?,?,?,?)""",
                (uuid4(), cid, normalize_domain(d.domain), 1 if d.wildcard else 0, now),
            )
    return hydrate_client(cid)


@router.get("/clients/{cid}")
def get_client(cid: str):
    return hydrate_client(cid)


@router.patch("/clients/{cid}")
def update_client(cid: str, body: ClientUpdate):
    now = now_iso()
    with tx():
        cur = q_one("SELECT * FROM clients WHERE id=?", (cid,))
        if not cur:
            raise HTTPException(404, "Client not found")
        name = body.name.strip() if body.name is not None else cur["name"]
        phone = cur["phone"] if body.phone is None else body.phone
        notes = cur["notes"] if body.notes is None else body.notes
        tags = cur["tags_json"] if body.tags is None else json.dumps(body.tags)
        active = cur["active"] if body.active is None else (1 if body.active else 0)
        q_exec(
            """UPDATE clients SET name=?, phone=?, notes=?, tags_json=?, active=?, updated_at=? WHERE id=?""",
            (name, phone, notes, tags, active, now, cid),
        )
        if body.emails is not None:
            q_exec("DELETE FROM client_emails WHERE client_id=?", (cid,))
            for e in body.emails:
                em = normalize_email(e)
                if em:
                    q_exec(
                        "INSERT OR IGNORE INTO client_emails (id,client_id,email,created_at) VALUES (?,?,?,?)",
                        (uuid4(), cid, em, now),
                    )
        if body.domains is not None:
            q_exec("DELETE FROM client_domains WHERE client_id=?", (cid,))
            for d in body.domains or []:
                q_exec(
                    """INSERT OR IGNORE INTO client_domains (id,client_id,domain,wildcard,created_at)
                          VALUES (?,?,?,?,?)""",
                    (
                        uuid4(),
                        cid,
                        normalize_domain(d.domain),
                        1 if d.wildcard else 0,
                        now,
                    ),
                )
    return hydrate_client(cid)


@router.delete("/clients/{cid}")
def soft_delete_client(cid: str):
    with tx():
        if (
            q_exec(
                "UPDATE clients SET active=0, updated_at=? WHERE id=?", (now_iso(), cid)
            ).rowcount
            == 0
        ):
            raise HTTPException(404, "Client not found")
    return {"ok": True}


# ------- Allowlist for triage (ETag-style payload) -------
@router.get("/allowlist")
def get_allowlist(ifNoneMatch: Optional[str] = None):
    meta = q_one("SELECT version, updated_at FROM allowlist_meta WHERE id=1")
    etag = f'W/"{meta["version"]}"'
    if ifNoneMatch and ifNoneMatch == etag:
        return {"not_modified": True, "etag": etag}
    emails = [
        r["email"] for r in q_all("SELECT email FROM client_emails ORDER BY email")
    ]
    domains = [
        {"domain": r["domain"], "wildcard": bool(r["wildcard"])}
        for r in q_all("SELECT domain, wildcard FROM client_domains ORDER BY domain")
    ]
    return {
        "emails": emails,
        "domains": domains,
        "etag": etag,
        "version": meta["version"],
        "generated_at": meta["updated_at"],
    }


class UnknownCreate(BaseModel):
    email: str
    message_id: str
    subject: str = ""


@router.get("/unknown-senders")
def list_unknown_senders(limit: int = 200, resolved: bool | None = None):
    where, params = [], []
    if resolved is not None:
        where.append("resolved=?")
        params.append(1 if resolved else 0)
    sql = """SELECT id,email,domain,message_id,last_message_id,subject,
                    first_seen,last_seen,hits,status,client_id,resolved
             FROM unknown_senders"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY last_seen DESC LIMIT ?"
    params.append(limit)
    return q_all(sql, tuple(params))


@router.post("/unknown-senders")
def create_unknown_sender(body: UnknownCreate):
    e = (body.email or "").strip().lower()
    mid = (body.message_id or "").strip()
    if not e or not mid:
        raise HTTPException(400, "email and message_id are required")
    now = now_iso()

    # Insert or bump
    with tx():
        row = q_one("SELECT id,hits FROM unknown_senders WHERE email=? AND message_id=?", (e, mid))
        if row:
            q_exec("UPDATE unknown_senders SET hits=?, last_seen=? WHERE id=?",
                   (row["hits"] + 1, now, row["id"]))
            uid = row["id"]
        else:
            uid = uuid4()
            q_exec("""INSERT INTO unknown_senders
                      (id,email,domain,message_id,last_message_id,subject,first_seen,last_seen,hits,status,client_id,resolved)
                      VALUES (?,?,?,?,?,?,?,?,?,'pending',NULL,0)""",
                   (uid, e, "", mid, mid, body.subject or "", now, now, 1))

    # Try to auto-match to a client
    m = q_one("""SELECT c.id AS client_id
                 FROM client_emails ce
                 JOIN clients c ON c.id=ce.client_id
                 WHERE lower(ce.email)=?""", (e,))
    client_id = m["client_id"] if m else None

    if not client_id and "@" in e:
        dom = e.split("@", 1)[1].lower()
        m = q_one("""SELECT c.id AS client_id
                     FROM client_domains cd
                     JOIN clients c ON c.id=cd.client_id
                     WHERE lower(cd.domain)=?""", (dom,))
        if m:
            client_id = m["client_id"]
        else:
            m = q_one("""SELECT c.id AS client_id
                         FROM client_domains cd
                         JOIN clients c ON c.id=cd.client_id
                         WHERE cd.wildcard=1
                           AND (? LIKE '%.' || lower(cd.domain) OR ? = lower(cd.domain))""",
                      (dom, dom))
            if m:
                client_id = m["client_id"]

    if client_id:
        with tx():
            q_exec("UPDATE unknown_senders SET client_id=?, status='matched' WHERE id=?",
                   (client_id, uid))

    return {"ok": True, "id": uid, "matched_client_id": client_id}



class UnknownResolve(BaseModel):
    action: str  # "approve_email" | "approve_domain" | "ignore"
    client_id: str | None = None
    wildcard: bool = False


@router.post("/unknown-senders/{uid}/resolve")
def resolve_unknown(uid: str, body: UnknownResolve):
    unk = q_one("SELECT * FROM unknown_senders WHERE id=?", (uid,))
    if not unk:
        raise HTTPException(404, "Unknown sender not found")

    email = (unk["email"] or "").lower().strip()

    if body.action == "ignore":
        with tx():
            q_exec(
                "UPDATE unknown_senders SET resolved=1, status='ignored' WHERE id=?",
                (uid,),
            )
        return {"ok": True}

    if not body.client_id:
        raise HTTPException(400, "client_id is required for approve actions")

    now = now_iso()
    if body.action == "approve_email":
        q_exec(
            """INSERT OR IGNORE INTO client_emails (id, client_id, email, created_at)
                  VALUES (?,?,?,?)""",
            (uuid4(), body.client_id, email, now),
        )
    elif body.action == "approve_domain":
        domain = email.split("@")[-1]
        q_exec(
            """INSERT OR IGNORE INTO client_domains (id, client_id, domain, wildcard, created_at)
                  VALUES (?,?,?,?,?)""",
            (uuid4(), body.client_id, domain, 1 if body.wildcard else 0, now),
        )
    else:
        raise HTTPException(400, "invalid action")

    with tx():
        q_exec(
            "UPDATE unknown_senders SET resolved=1, status='resolved', client_id=? WHERE id=?",
            (body.client_id, uid),
        )
        q_exec(
            "UPDATE allowlist_meta SET version=version+1, updated_at=datetime('now') WHERE id=1"
        )

    return {"ok": True}
