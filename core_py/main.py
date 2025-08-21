import os
import asyncio
import json
import time
import logging
import uuid
from time import perf_counter
from typing import Optional
from sqlalchemy import text 
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

# Load environment variables from .env if present
load_dotenv()

# -----------------------------------------------------------------------------
# Config / Logging
# -----------------------------------------------------------------------------
DEV_MODE = os.getenv("ENV", "dev").lower() == "dev"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
ALLOW_ORIGINS_ENV = os.getenv("ALLOW_ORIGINS")  # comma-separated
DEFAULT_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

try:
    logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
except Exception:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("helios")

# -----------------------------------------------------------------------------
# Import feature routers
# -----------------------------------------------------------------------------
from core_py.routes.calendar_routes import router as calendar_router
from core_py.routes.tasks_routes import router as tasks_router
from core_py.routes.fss_routes import router as fss_router
from core_py.routes.toggl_routes import router as toggl_router
from core_py.routes.balances import router as balances_router
from core_py.routes import clickup_webhook
from core_py.routes.advice_routes import router as advice_router
from core_py.routes.shutdown import shutdown_router
from core_py.routes.prioritised_tasks import router as prioritised_tasks_router
from core_py.routes import voice
from core_py.routes import todoist_routes
from core_py.routes import reclaim_routes
from core_py.routes import triage_routes
from core_py.routes.contacts import router as contacts_router
from core_py.routes import contacts_admin
from core_py.routes.schedule_routes import router as schedule_router
from core_py.routes.email_tasks import router as email_tasks_router
from core_py.db.session import get_session, db_session
from core_py.routes.email_tasks_read import router as email_tasks_read_router
# -----------------------------------------------------------------------------
# FastAPI app
# -----------------------------------------------------------------------------
app = FastAPI(title="Helios Backend", version="8.0")

# GZip for larger payloads
app.add_middleware(GZipMiddleware, minimum_size=1024)

# CORS
allow_origins = (
    [o.strip() for o in ALLOW_ORIGINS_ENV.split(",")] if ALLOW_ORIGINS_ENV
    else DEFAULT_DEV_ORIGINS
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Structured logging middleware
# -----------------------------------------------------------------------------
@app.middleware("http")
async def _request_logging(request: Request, call_next):
    rid = str(uuid.uuid4())
    start = perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        try:
            response.headers["X-Request-ID"] = rid
        except Exception:
            pass
        return response
    except Exception:
        logger.exception({"rid": rid, "path": str(request.url.path)})
        raise
    finally:
        dur_ms = int((perf_counter() - start) * 1000)
        logger.info(
            {"rid": rid, "path": str(request.url.path), "status": status, "dur_ms": dur_ms}
        )

# -----------------------------------------------------------------------------
# Global exception envelope
# -----------------------------------------------------------------------------
@app.exception_handler(Exception)
async def _unhandled_ex(request: Request, exc: Exception):
    logger.exception({"path": str(request.url.path)})
    return JSONResponse(status_code=500, content={"error": "internal_error"})

# -----------------------------------------------------------------------------
# Include feature routers under /api
# -----------------------------------------------------------------------------
app.include_router(calendar_router, prefix="/api/calendar")
app.include_router(tasks_router, prefix="/api")
app.include_router(fss_router, prefix="/api")
app.include_router(toggl_router, prefix="/api/toggl")
app.include_router(balances_router, prefix="/api")
app.include_router(clickup_webhook.router)
app.include_router(advice_router, prefix="/api")
app.include_router(shutdown_router, prefix="/api")
app.include_router(prioritised_tasks_router, prefix="/api")
app.include_router(voice.router, prefix="/api/voice")
app.include_router(todoist_routes.router)
app.include_router(reclaim_routes.router)
app.include_router(triage_routes.router, prefix="/api/triage")
app.include_router(contacts_router, prefix="/api")
app.include_router(contacts_admin.router)
app.include_router(schedule_router, prefix="/api")
app.include_router(email_tasks_router)
app.include_router(email_tasks_read_router)

# -----------------------------------------------------------------------------
# Root / Exit
# -----------------------------------------------------------------------------
@app.get("/")
def root():
    return JSONResponse({"ok": True, "service": "Helios Backend v8.0"})

@app.get("/api/exit")
def exit_app():
    if not DEV_MODE:
        return JSONResponse(status_code=403, content={"error": "disabled_in_prod"})
    return JSONResponse({"ok": True})

# -----------------------------------------------------------------------------
# Health / Readiness
# -----------------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "Helios Backend v8.0"}

@app.get("/readyz")
def readyz():
    try:
        from core_py.db.session import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"ready": True}
    except Exception as e:
        return JSONResponse(status_code=503, content={"ready": False, "error": str(e)})

# -----------------------------------------------------------------------------
# Realtime: WebSocket + Metronome
# -----------------------------------------------------------------------------
_clients: set[WebSocket] = set()
_seq = 0
MAX_WS_CLIENTS = 200
_metronome_task: Optional[asyncio.Task] = None

async def _broadcast(stream: str, data: dict):
    global _seq
    _seq += 1
    msg = json.dumps({
        "stream": stream,
        "seq": _seq,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "data": data
    })
    dead = []
    for ws in list(_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for d in dead:
        _clients.discard(d)

@app.websocket("/ws")
async def ws_main(ws: WebSocket):
    await ws.accept()
    if len(_clients) >= MAX_WS_CLIENTS:
        await ws.close(code=1001)
        return
    _clients.add(ws)
    try:
        while True:
            await asyncio.sleep(3600)
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(ws)

async def _metronome():
    while True:
        await asyncio.sleep(30)
        await _broadcast("ticks", {"type": "tick"})

@app.on_event("startup")
async def _on_startup():
    global _metronome_task
    _metronome_task = asyncio.create_task(_metronome())

@app.on_event("shutdown")
async def _on_shutdown():
    global _metronome_task
    if _metronome_task and not _metronome_task.done():
        _metronome_task.cancel()
        try:
            await _metronome_task
        except asyncio.CancelledError:
            pass
