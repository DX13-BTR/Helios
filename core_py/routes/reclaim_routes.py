# core_py/routes/reclaim_routes.py
from __future__ import annotations

import os
import time
import base64
import hashlib
import secrets
import logging
import asyncio
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, constr
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# ---- Helios DB helpers (existing ite util) ----
from sqlalchemy import text
from core_py.db.session import get_session

def _ensure_tables_pg():
    with get_session() as s:
        s.execute(text("""
            CREATE SCHEMA IF NOT EXISTS helios;
            CREATE TABLE IF NOT EXISTS helios.oauth_tokens(
                provider TEXT PRIMARY KEY,
                access_token TEXT,
                refresh_token TEXT,
                token_type TEXT,
                expires_at BIGINT
            );
            CREATE TABLE IF NOT EXISTS helios.oauth_state(
                state TEXT PRIMARY KEY,
                code_verifier TEXT,
                created_at BIGINT
            );
        """))
        s.commit()

router = APIRouter()
log = logging.getLogger("reclaim")

# =========================
# Config / Environment
# =========================
# Mode: oauth | apikey | auto (auto prefers OAuth if token present, else API key)
RECLAIM_AUTH_MODE = os.getenv("RECLAIM_AUTH_MODE", "auto").lower()

# API key path (kept for fallback / simple reads)
RECLAIM_API_KEY = os.getenv("RECLAIM_API_KEY", "").strip()

# OAuth client settings (must be provided for oauth mode)
RECLAIM_CLIENT_ID = os.getenv("RECLAIM_CLIENT_ID", "").strip()
RECLAIM_CLIENT_SECRET = os.getenv("RECLAIM_CLIENT_SECRET", "").strip()  # if Reclaim requires secret; else leave blank
RECLAIM_REDIRECT_URI = os.getenv("RECLAIM_REDIRECT_URI", "").strip()
RECLAIM_AUTH_URL = os.getenv("RECLAIM_AUTH_URL", "").strip()   # e.g. https://app.reclaim.ai/oauth/authorize
RECLAIM_TOKEN_URL = os.getenv("RECLAIM_TOKEN_URL", "").strip() # e.g. https://api.app.reclaim.ai/oauth/token
# space-delimited scopes per Reclaim docs, e.g.: "tasks:read tasks:write"
RECLAIM_SCOPES = os.getenv("RECLAIM_SCOPES", "tasks:read tasks:write").strip()

# network controls
RECLAIM_TIMEOUT_SEC = float(os.getenv("RECLAIM_TIMEOUT_SEC", "12"))
RECLAIM_MAX_CONCURRENCY = int(os.getenv("RECLAIM_MAX_CONCURRENCY", "4"))
RECLAIM_MAX_RETRIES = int(os.getenv("RECLAIM_MAX_RETRIES", "3"))

# Hard kill-switch for writes (safe default off)
RECLAIM_ENABLE_WRITES = os.getenv("RECLAIM_ENABLE_WRITES", "false").lower() == "true"

# Correct Reclaim REST base
BASE_URL = "https://api.app.reclaim.ai/api/v1"

_sem = asyncio.Semaphore(RECLAIM_MAX_CONCURRENCY)

# =========================
# SQLite token storage
# =========================
def _ensure_tables():
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            provider TEXT PRIMARY KEY,
            access_token TEXT,
            refresh_token TEXT,
            token_type TEXT,
            expires_at INTEGER
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS oauth_state (
            state TEXT PRIMARY KEY,
            code_verifier TEXT,
            created_at INTEGER
        )
        """)


def _save_tokens(access_token: str, refresh_token: str, token_type: str | None, expires_at: int | None):
    _ensure_tables_pg()
    with get_session() as s:
        s.execute(text("""
            INSERT INTO helios.oauth_tokens(provider, access_token, refresh_token, token_type, expires_at)
            VALUES ('reclaim', :at, :rt, :tt, :exp)
            ON CONFLICT (provider) DO UPDATE SET
              access_token=EXCLUDED.access_token,
              refresh_token=EXCLUDED.refresh_token,
              token_type=EXCLUDED.token_type,
              expires_at=EXCLUDED.expires_at
        """), {"at": access_token, "rt": refresh_token, "tt": (token_type or "Bearer"), "exp": expires_at})
        s.commit()

def _load_tokens():
    _ensure_tables_pg()
    with get_session() as s:
        row = s.execute(text("""
            SELECT access_token, refresh_token, token_type, COALESCE(expires_at, 0)
            FROM helios.oauth_tokens
            WHERE provider='reclaim'
        """)).fetchone()
        if not row:
            return None
        return row[0], row[1], (row[2] or "Bearer"), int(row[3] or 0)

def _save_state(state: str, code_verifier: str) -> None:
    _ensure_tables_pg()
    with get_session() as s:
        s.execute(text("""
            INSERT INTO helios.oauth_state(state, code_verifier, created_at)
            VALUES(:st, :cv, EXTRACT(EPOCH FROM NOW())::bigint)
            ON CONFLICT (state) DO UPDATE SET
              code_verifier=EXCLUDED.code_verifier,
              created_at=EXCLUDED.created_at
        """), {"st": state, "cv": code_verifier})
        s.commit()

def _pop_state(state: str) -> str | None:
    _ensure_tables_pg()
    with get_session() as s:
        row = s.execute(text("SELECT code_verifier FROM helios.oauth_state WHERE state=:st"),
                        {"st": state}).fetchone()
        if not row:
            return None
        s.execute(text("DELETE FROM helios.oauth_state WHERE state=:st"), {"st": state})
        s.commit()
        return row[0]


# =========================
# PKCE helpers
# =========================
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def _gen_pkce() -> Tuple[str, str]:
    code_verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(code_verifier.encode()).digest())
    return code_verifier, challenge

# =========================
# OAuth token management
# =========================
def _oauth_config_ready() -> bool:
    return all([RECLAIM_CLIENT_ID, RECLAIM_REDIRECT_URI, RECLAIM_AUTH_URL, RECLAIM_TOKEN_URL])

async def _refresh_if_needed() -> Optional[str]:
    """Return a fresh access token if present; refresh when expiring/expired. None if no tokens."""
    tokens = _load_tokens()
    if not tokens:
        return None
    access_token, refresh_token, token_type, expires_at = tokens
    now = int(time.time())
    # refresh 60s before expiry if we have refresh_token
    if expires_at and refresh_token and now >= (expires_at - 60):
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": RECLAIM_CLIENT_ID,
        }
        if RECLAIM_CLIENT_SECRET:
            data["client_secret"] = RECLAIM_CLIENT_SECRET
        async with httpx.AsyncClient(timeout=httpx.Timeout(RECLAIM_TIMEOUT_SEC)) as client:
            resp = await client.post(RECLAIM_TOKEN_URL, data=data)
        if resp.status_code != 200:
            log.error("reclaim_refresh_failed: %s %s", resp.status_code, resp.text[:400])
            return access_token  # best-effort
        tok = resp.json()
        access_token = tok.get("access_token")
        refresh_token = tok.get("refresh_token", refresh_token)
        token_type = tok.get("token_type", "Bearer")
        expires_in = tok.get("expires_in")
        new_exp = now + int(expires_in) if expires_in else None
        _save_tokens(access_token, refresh_token, token_type, new_exp)
        return access_token
    return access_token

def _auth_headers_oauth(access_token: str, token_type: str = "Bearer") -> Dict[str, str]:
    t = token_type or "Bearer"
    return {
        "Authorization": f"{t} {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

def _auth_headers_apikey(scheme: str = "bearer") -> Dict[str, str]:
    if not RECLAIM_API_KEY:
        raise HTTPException(status_code=401, detail="RECLAIM_API_KEY not configured (apikey mode)")
    if scheme == "api-key":
        return {"X-API-Key": RECLAIM_API_KEY, "Accept": "application/json", "Content-Type": "application/json"}
    return {"Authorization": f"Bearer {RECLAIM_API_KEY}", "Accept": "application/json", "Content-Type": "application/json"}

def _prefer_oauth() -> bool:
    if RECLAIM_AUTH_MODE == "oauth":
        return True
    if RECLAIM_AUTH_MODE == "apikey":
        return False
    # auto: prefer OAuth if tokens exist and config is ready
    return _load_tokens() is not None and _oauth_config_ready()

def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(RECLAIM_TIMEOUT_SEC))

@retry(
    reraise=True,
    stop=stop_after_attempt(RECLAIM_MAX_RETRIES),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPError)),
)
async def _request_with_retry(method: str, url: str, *, json: Optional[Dict[str, Any]] = None) -> httpx.Response:
    """
    One place for concurrency, timing, and auth fallback:
    - If OAuth preferred: use access_token (refresh if needed).
    - If 401 from OAuth: try refresh then retry once.
    - If API key mode/auto fallback: try bearer, then X-API-Key on 401/403.
    """
    async with _sem:
        t0 = time.perf_counter()
        try:
            async with _client() as client:
                # OAuth path
                if _prefer_oauth():
                    token_tuple = _load_tokens()
                    if not token_tuple:
                        raise HTTPException(status_code=401, detail="No OAuth tokens found. Visit /api/reclaim/oauth/start")
                    access_token, _, token_type, _ = token_tuple
                    headers = _auth_headers_oauth(access_token, token_type)
                    resp = await client.request(method, url, headers=headers, json=json)
                    if resp.status_code == 401:
                        # refresh and retry once
                        new_access = await _refresh_if_needed()
                        if new_access:
                            headers = _auth_headers_oauth(new_access, token_type)
                            resp = await client.request(method, url, headers=headers, json=json)
                    return resp

                # API key path (explicit or auto fallback)
                # First try Bearer
                headers = _auth_headers_apikey("bearer")
                resp = await client.request(method, url, headers=headers, json=json)
                if resp.status_code in (401, 403):
                    # try X-API-Key
                    headers = _auth_headers_apikey("api-key")
                    resp = await client.request(method, url, headers=headers, json=json)
                return resp
        finally:
            log.info("reclaim_http", extra={"method": method, "url": url, "ms": int((time.perf_counter() - t0) * 1000)})

async def _get(url: str) -> httpx.Response:
    return await _request_with_retry("GET", url)

async def _post(url: str, json: Dict[str, Any]) -> httpx.Response:
    return await _request_with_retry("POST", url, json=json)

async def _delete(url: str) -> httpx.Response:
    return await _request_with_retry("DELETE", url)

# =========================
# Pydantic payloads
# =========================
class IncomingTask(BaseModel):
    content: Optional[constr(strip_whitespace=True, min_length=1)] = None
    name: Optional[constr(strip_whitespace=True, min_length=1)] = None
    duration: Optional[int] = Field(default=30, ge=5, le=8 * 60)
    due: Optional[str] = None
    due_date: Optional[str] = None
    source: Optional[str] = "unknown"
    agent: Optional[str] = None

class SyncTasksBody(BaseModel):
    tasks: List[IncomingTask] = Field(default_factory=list)

# =========================
# Business routes
# =========================
@router.post("/api/reclaim/sync_tasks")
async def sync_tasks(body: SyncTasksBody):
    if not body.tasks:
        return {"status": "ok", "created_count": 0, "created": [], "note": "no tasks in payload"}

    if not RECLAIM_ENABLE_WRITES:
        planned = []
        for t in body.tasks:
            title = t.content or t.name or "[No title]"
            planned.append({
                "title": title,
                "duration": t.duration or 30,
                "dueDate": t.due or t.due_date,
                "notes": f"From Helios Panel: {t.source or 'unknown'}",
                "isRecurrence": False,
                "timeZone": "Europe/London",
            })
        return {"status": "ok", "dry_run": True, "created_count": 0, "planned": planned}

    created: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for t in body.tasks:
        title = t.content or t.name or "[No title]"
        payload = {
            "title": title,
            "duration": t.duration or 30,
            "dueDate": t.due or t.due_date,
            "notes": f"From Helios Panel: {t.source or 'unknown'}",
            "isRecurrence": False,
            "timeZone": "Europe/London",
        }
        try:
            resp = await _post(f"{BASE_URL}/tasks", json=payload)
            if resp.status_code in (200, 201):
                try:
                    created.append(resp.json())
                except Exception:
                    created.append({"raw": resp.text})
            else:
                errors.append({
                    "title": title,
                    "status": resp.status_code,
                    "details": (resp.text[:500] if resp.text else ""),
                })
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            errors.append({"title": title, "error": "NETWORK", "details": str(e)})

    if errors:
        return {
            "status": "partial",
            "created_count": len(created),
            "errors_count": len(errors),
            "errors": errors,
            "created": created,
        }
    return {"status": "ok", "created_count": len(created), "created": created}

@router.post("/api/reclaim/clear_tasks")
async def clear_all_reclaim_tasks(
    dry_run: bool = Query(False, description="If true, only report what would be deleted")
):
    try:
        res = await _get(f"{BASE_URL}/tasks")
    except (httpx.TimeoutException, httpx.HTTPError) as e:
        raise HTTPException(status_code=504, detail={"status": "error", "code": "EXTERNAL_API_TIMEOUT", "details": str(e)})

    if res.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "error",
                "code": "UPSTREAM_FAILED",
                "upstream_status": res.status_code,
                "details": res.text[:500] if res.text else "",
            },
        )

    tasks_json: Any = {}
    try:
        tasks_json = res.json()
    except Exception:
        tasks_json = {}

    tasks = tasks_json.get("tasks", []) if isinstance(tasks_json, dict) else []
    targets = [t for t in tasks if str(t.get("notes", "")).startswith("From Helios Panel")]

    if dry_run or not RECLAIM_ENABLE_WRITES:
        return {
            "status": "ok",
            "dry_run": True,
            "would_delete_count": len(targets),
            "task_ids": [t.get("id") for t in targets if t.get("id")],
        }

    deleted_ids: List[str] = []
    errors: List[Dict[str, Any]] = []

    for t in targets:
        tid = t.get("id")
        if not tid:
            continue
        try:
            del_res = await _delete(f"{BASE_URL}/tasks/{tid}")
            if del_res.status_code in (200, 204):
                deleted_ids.append(tid)
            else:
                errors.append({
                    "id": tid,
                    "status": del_res.status_code,
                    "details": del_res.text[:500] if del_res.text else "",
                })
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            errors.append({"id": tid, "error": "NETWORK", "details": str(e)})

    return {
        "status": "ok" if not errors else "partial",
        "deleted_count": len(deleted_ids),
        "deleted_task_ids": deleted_ids,
        "errors_count": len(errors),
        "errors": errors,
    }

# =========================
# Debug / Diagnostics
# =========================
@router.get("/api/reclaim/_debug_auth_full")
async def reclaim_debug_auth_full():
    """
    Calls /tasks with both header schemes (or the preferred mode) and returns upstream status+sample.
    """
    candidates = []
    if RECLAIM_AUTH_MODE in ("bearer", "api-key"):  # legacy values (not used now, but harmless)
        candidates = ["bearer" if RECLAIM_AUTH_MODE == "bearer" else "api-key"]
    elif RECLAIM_AUTH_MODE == "apikey":
        candidates = ["bearer", "api-key"]
    elif _prefer_oauth():
        # if oauth, try only oauth by doing a GET with oauth headers
        results = []
        try:
            token_tuple = _load_tokens()
            if not token_tuple:
                return {"base_url": BASE_URL, "auth_mode": "oauth", "results": [{"scheme": "oauth", "error": "no tokens"}]}
            access_token, _, token_type, _ = token_tuple
            async with _client() as client:
                r = await client.get(f"{BASE_URL}/tasks", headers=_auth_headers_oauth(access_token, token_type))
            results.append({
                "scheme": "oauth",
                "status": r.status_code,
                "headers": dict(r.headers),
                "body_sample": (r.text[:400] if r.text else None),
            })
            return {"base_url": BASE_URL, "auth_mode": "oauth", "results": results}
        except Exception as e:
            return {"base_url": BASE_URL, "auth_mode": "oauth", "results": [{"scheme": "oauth", "error": str(e)}]}
    else:
        candidates = ["bearer", "api-key"]

    # API-key candidates (or legacy bearer/api-key)
    results = []
    for s in candidates:
        try:
            headers = _auth_headers_apikey("api-key" if s == "api-key" else "bearer")
            async with _client() as client:
                r = await client.get(f"{BASE_URL}/tasks", headers=headers)
            results.append({
                "scheme": s,
                "status": r.status_code,
                "headers": dict(r.headers),
                "body_sample": (r.text[:400] if r.text else None),
            })
        except Exception as e:
            results.append({"scheme": s, "error": str(e)})

    return {
        "base_url": BASE_URL,
        "auth_mode": RECLAIM_AUTH_MODE,
        "writes_enabled": RECLAIM_ENABLE_WRITES,
        "results": results,
    }

# =========================
# OAuth flow (PKCE): start & callback
# =========================
@router.get("/api/reclaim/oauth/start")
async def reclaim_oauth_start():
    if not _oauth_config_ready():
        raise HTTPException(status_code=400, detail="OAuth not configured. Set RECLAIM_CLIENT_ID, RECLAIM_REDIRECT_URI, RECLAIM_AUTH_URL, RECLAIM_TOKEN_URL.")
    state = _b64url(secrets.token_bytes(16))
    code_verifier, code_challenge = _gen_pkce()
    _save_state(state, code_verifier)

    params = {
        "response_type": "code",
        "client_id": RECLAIM_CLIENT_ID,
        "redirect_uri": RECLAIM_REDIRECT_URI,
        "scope": RECLAIM_SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    url = f"{RECLAIM_AUTH_URL}?{urllib.parse.urlencode(params)}"
    # Return the URL so the frontend can redirect
    return {"authorize_url": url}

@router.get("/api/reclaim/oauth/callback")
async def reclaim_oauth_callback(request: Request):
    if not _oauth_config_ready():
        raise HTTPException(status_code=400, detail="OAuth not configured.")
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(str(request.url)).query)
    code = (qs.get("code") or [None])[0]
    state = (qs.get("state") or [None])[0]
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code/state")

    code_verifier = _pop_state(state)
    if not code_verifier:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": RECLAIM_REDIRECT_URI,
        "client_id": RECLAIM_CLIENT_ID,
        "code_verifier": code_verifier,
    }
    if RECLAIM_CLIENT_SECRET:
        data["client_secret"] = RECLAIM_CLIENT_SECRET

    async with httpx.AsyncClient(timeout=httpx.Timeout(RECLAIM_TIMEOUT_SEC)) as client:
        resp = await client.post(RECLAIM_TOKEN_URL, data=data)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail={"status": "error", "code": "TOKEN_EXCHANGE_FAILED", "details": resp.text[:500]})

    tok = resp.json()
    now = int(time.time())
    access_token = tok.get("access_token")
    refresh_token = tok.get("refresh_token")
    token_type = tok.get("token_type", "Bearer")
    expires_in = tok.get("expires_in")
    expires_at = now + int(expires_in) if expires_in else None

    if not access_token:
        raise HTTPException(status_code=502, detail="Token exchange returned no access_token")

    _save_tokens(access_token, refresh_token, token_type, expires_at)
    return {"status": "ok", "auth": "oauth", "has_refresh": bool(refresh_token), "expires_at": expires_at}
