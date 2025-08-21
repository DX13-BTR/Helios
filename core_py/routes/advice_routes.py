# core_py/routes/advice_routes.py
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError, OperationalError
import os, time
import ollama

from core_py.db.session import get_session

router = APIRouter(prefix="/advice", tags=["advice"])

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _to_utc_iso(ts: Optional[Any]) -> Optional[str]:
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)) or str(ts).isdigit():
            v = int(float(ts))
            if v < 10**11:
                v *= 1000
            return datetime.fromtimestamp(v / 1000.0, tz=timezone.utc).isoformat()
        s = str(ts)
        if "T" in s or "-" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(
                timezone.utc
            ).isoformat()
    except Exception:
        pass
    return None

def _table_has_column(schema: str, table: str, col: str) -> bool:
    q = text("""
        SELECT COUNT(*) > 0
        FROM information_schema.columns
        WHERE table_schema = :sch AND table_name = :tbl AND column_name = :col
    """)
    with get_session() as s:
        return bool(s.execute(q, {"sch": schema, "tbl": table, "col": col}).scalar())

# -----------------------------------------------------------------------------
# /latest — tolerant of schema (no id/kind assumptions)
# -----------------------------------------------------------------------------
@router.get("/latest")
def get_latest_advice():
    """
    Return the most recent row from legacy.fss_advice.
    - If 'created_at' exists -> ORDER BY created_at DESC
    - Else -> just LIMIT 1 (no ordering guarantees)
    Returns {"advice": {...}} or {} if none.
    """
    has_created = _table_has_column("legacy", "fss_advice", "created_at")
    try:
        with get_session() as s:
            if has_created:
                row = s.execute(text("""
                    SELECT *
                    FROM legacy.fss_advice
                    ORDER BY created_at DESC NULLS LAST
                    LIMIT 1
                """)).mappings().fetchone()
            else:
                row = s.execute(text("""
                    SELECT * FROM legacy.fss_advice LIMIT 1
                """)).mappings().fetchone()
        if not row:
            return {}
        obj = dict(row)
        if "created_at" in obj:
            obj["created_at"] = _to_utc_iso(obj["created_at"])
        return {"advice": obj}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

@router.get("/all")
def get_all_advice(limit: int = 20):
    """
    Return last N rows from legacy.fss_advice (best-effort ordering).
    """
    has_created = _table_has_column("legacy", "fss_advice", "created_at")
    try:
        with get_session() as s:
            if has_created:
                rows = s.execute(text("""
                    SELECT * FROM legacy.fss_advice
                    ORDER BY created_at DESC NULLS LAST
                    LIMIT :lim
                """), {"lim": limit}).mappings().all()
            else:
                rows = s.execute(text("""
                    SELECT * FROM legacy.fss_advice LIMIT :lim
                """), {"lim": limit}).mappings().all()
        out = [dict(r) for r in rows]
        for r in out:
            if "created_at" in r:
                r["created_at"] = _to_utc_iso(r["created_at"])
        return {"advice": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

# -----------------------------------------------------------------------------
# Chat memory (Postgres)
# -----------------------------------------------------------------------------
DDL = text("""
CREATE SCHEMA IF NOT EXISTS helios;

CREATE TABLE IF NOT EXISTS helios.advice_messages (
  id BIGSERIAL PRIMARY KEY,
  ts BIGINT,
  role TEXT,
  text TEXT,
  session_id TEXT
);

CREATE TABLE IF NOT EXISTS helios.advice_summaries (
  id BIGSERIAL PRIMARY KEY,
  ts BIGINT,
  summary TEXT,
  session_id TEXT
);
""")

def _ensure_tables_pg():
    with get_session() as s:
        s.execute(DDL)
        s.commit()

def _get_running_summary_pg(session_id: str) -> str:
    with get_session() as s:
        row = s.execute(text("""
            SELECT summary FROM helios.advice_summaries
            WHERE session_id=:sid
            ORDER BY ts DESC LIMIT 1
        """), {"sid": session_id}).scalar()
        return row or ""

def _save_running_summary_pg(session_id: str, summary: str):
    with get_session() as s:
        s.execute(text("""
            INSERT INTO helios.advice_summaries(ts, summary, session_id)
            VALUES (:ts, :summary, :sid)
        """), {"ts": int(time.time()), "summary": summary, "sid": session_id})
        s.commit()

def _load_recent_messages_pg(session_id: str, limit: int = 20):
    with get_session() as s:
        rows = s.execute(text("""
            SELECT role, text FROM helios.advice_messages
            WHERE session_id=:sid
            ORDER BY ts DESC
            LIMIT :lim
        """), {"sid": session_id, "lim": limit}).mappings().all()
        return [{"role": r["role"], "content": r["text"]} for r in rows[::-1]]

def _append_messages_pg(session_id: str, turns: List[Dict[str, str]]):
    if not turns:
        return
    with get_session() as s:
        s.execute(text("""
            INSERT INTO helios.advice_messages(ts, role, text, session_id)
            VALUES (:ts, :role, :text, :sid)
        """), [{"ts": int(time.time()), "role": t["role"], "text": t["content"], "sid": session_id}
               for t in turns])
        s.commit()

# -----------------------------------------------------------------------------
# /chat — Ollama-based advice chat with Postgres memory (AS IS)
# -----------------------------------------------------------------------------
class Msg(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class ChatRequest(BaseModel):
    messages: List[Msg]
    history: Optional[List[dict]] = None
    task_context: Optional[list] = None
    session_id: Optional[str] = "default"

MODEL_NAME = os.getenv("ADVICE_MODEL", "llama3:pinned-adv")
NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))

@router.post("/chat")
def chat(req: ChatRequest):
    _ensure_tables_pg()
    session_id = req.session_id or "default"

    # recent convo from DB
    recent_server = _load_recent_messages_pg(session_id, limit=20)

    # optional running summary
    running_summary = _get_running_summary_pg(session_id)

    # short task context (optional)
    key_ctx = []
    tc = req.task_context or []
    if isinstance(tc, list):
        for t in tc[:20]:
            title = t.get("title") or t.get("name") or str(t)
            src = t.get("source") or ""
            key_ctx.append(f"{src} {title}")
    key_ctx_str = "\n".join(key_ctx)[:1200]

    # assemble prompt
    assembled: List[Dict[str, str]] = [{
        "role": "system",
        "content": (
            "You are Helios Advice. Be concise, concrete, cost-aware, "
            "and use Helios conventions. Prefer step-by-step actions. "
            "If information is missing, ask one targeted question."
        )
    }]
    if running_summary:
        assembled.append({"role": "system", "content": f"[Running Summary]\n{running_summary}"})
    if key_ctx_str:
        assembled.append({"role": "system", "content": f"[Task Context]\n{key_ctx_str}"})
    assembled.extend(recent_server)
    assembled.extend([m.model_dump() for m in req.messages])

    # rough token control
    MAX_CHARS = 18000
    total_chars = sum(len(m["content"]) for m in assembled)
    if total_chars > MAX_CHARS:
        assembled = [m for m in assembled if m["role"] == "system"] + assembled[-20:]

    try:
        res = ollama.chat(
            model=MODEL_NAME,
            messages=assembled,
            options={"num_ctx": NUM_CTX, "temperature": 0.2},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama chat error: {e}")

    reply = (res.get("message") or {}).get("content", "").strip() or "I didn't get a response."

    # persist turns
    new_turns: List[Dict[str, str]] = []
    for m in req.messages:
        if m.role in ("user", "assistant", "system"):
            new_turns.append({"role": m.role, "content": m.content})
    if reply:
        new_turns.append({"role": "assistant", "content": reply})
    _append_messages_pg(session_id, new_turns)

    # periodic summary (every 12 user msgs)
    with get_session() as s:
        user_count = s.execute(text("""
            SELECT COUNT(*) FROM helios.advice_messages
            WHERE session_id=:sid AND role='user'
        """), {"sid": session_id}).scalar() or 0
    if user_count % 12 == 0 and user_count > 0:
        try:
            sum_res = ollama.chat(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content":
                        "Summarize the dialogue below into 6–8 concise bullets with decisions, assumptions, and open questions."},
                    {"role": "user", "content":
                        "\n".join([f"{m['role'][:1].upper()}: {m['content']}" for m in recent_server[-40:]])}
                ],
                options={"num_ctx": 2048, "temperature": 0.1},
            )
            summary_txt = (sum_res.get("message") or {}).get("content", "").strip()
            if summary_txt:
                _save_running_summary_pg(session_id, summary_txt[:4000])
        except Exception:
            pass

    return {"reply": {"content": reply}}
