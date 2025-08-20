# core_py/routes/advice_routes.py
from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List, Optional, Literal
from sqlalchemy import text
import os, time
import ollama

from core_py.db.session import get_session

load_dotenv(dotenv_path="core_py/.env")

MODEL_NAME = os.getenv("ADVICE_MODEL", "llama3:pinned-adv")
NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))

router = APIRouter(prefix="/advice", tags=["advice"])

# -----------------------------
# /latest (pivot legacy.fss_advice kinds -> wide fields)
# -----------------------------
@router.get("/latest")
def get_latest_advice():
    """
    Returns: {
      "uc": str|None, "buffer": str|None, "tee": str|None,
      "spending": str|None, "savings": str|None,
      "generated_at": ISO|None
    }
    """
    kinds = ["uc", "buffer", "tee", "spending", "savings"]
    placeholders = ",".join([f":k{i}" for i, _ in enumerate(kinds)])
    params = {f"k{i}": k for i, k in enumerate(kinds)}

    # DISTINCT ON picks the latest row per kind by created_at
    sql = f"""
    SELECT DISTINCT ON (kind) kind, message, created_at
    FROM legacy.fss_advice
    WHERE kind IN ({placeholders})
    ORDER BY kind, created_at DESC
    """
    out = {k: None for k in kinds}
    latest_ts = None

    with get_session() as s:
        rows = s.execute(text(sql), params).mappings().all()
        for r in rows:
            k = (r["kind"] or "").strip().lower()
            if k in out:
                out[k] = r["message"]
                ts = r.get("created_at")
                if ts and (latest_ts is None or ts > latest_ts):
                    latest_ts = ts

    return {
        "uc": out["uc"],
        "buffer": out["buffer"],
        "tee": out["tee"],
        "spending": out["spending"],
        "savings": out["savings"],
        "generated_at": latest_ts.isoformat() if latest_ts else None,
    }

# -----------------------------
# Chat models & schemas
# -----------------------------
class Msg(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class ChatRequest(BaseModel):
    messages: List[Msg]
    history: Optional[List[dict]] = None
    task_context: Optional[list] = None
    session_id: Optional[str] = "default"

# -----------------------------
# Postgres helpers for memory
# -----------------------------
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

def _append_messages_pg(session_id: str, turns: List[dict]):
    if not turns:
        return
    with get_session() as s:
        s.execute(text("""
            INSERT INTO helios.advice_messages(ts, role, text, session_id)
            VALUES (:ts, :role, :text, :sid)
        """), [{"ts": int(time.time()), "role": t["role"], "text": t["content"], "sid": session_id}
               for t in turns])
        s.commit()

# -----------------------------
# /chat endpoint for Advice Panel
# -----------------------------
@router.post("/chat")
def chat(req: ChatRequest):
    _ensure_tables_pg()
    session_id = req.session_id or "default"

    # Build recent context
    hist_msgs: List[Msg] = []
    if req.history:
        for h in req.history[-20:]:
            role = h.get("role") if h.get("role") in ("user", "assistant") \
                   else ("assistant" if h.get("from") == "agent" else "user")
            hist_msgs.append({"role": role, "content": h.get("content") or h.get("text", "")})

    recent_server = _load_recent_messages_pg(session_id, limit=20)
    running_summary = _get_running_summary_pg(session_id)

    # Task context summary (short)
    key_ctx = []
    tc = req.task_context or []
    if isinstance(tc, list):
        for t in tc[:20]:
            title = t.get("title") or t.get("name") or str(t)
            src = t.get("source") or ""
            key_ctx.append(f"{src} {title}")
    key_ctx_str = "\n".join(key_ctx)[:1200]

    # System prompts
    assembled: List[dict] = [{
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
    assembled.extend(hist_msgs)
    assembled.extend(recent_server)
    assembled.extend([m.model_dump() for m in req.messages])

    # Trim (rough token control)
    MAX_CHARS = 18000
    total_chars = sum(len(m["content"]) for m in assembled)
    if total_chars > MAX_CHARS:
        assembled = [m for m in assembled if m["role"] == "system"] + assembled[-20:]

    try:
        print(f"[DEBUG] Using Ollama model={MODEL_NAME} num_ctx={NUM_CTX}")
        res = ollama.chat(
            model=MODEL_NAME,
            messages=assembled,
            options={"num_ctx": NUM_CTX, "temperature": 0.2},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama chat error: {e}")

    reply = (res.get("message") or {}).get("content", "").strip() or "I didn't get a response."

    # Save new turns
    new_turns = []
    for m in req.messages:
        if m.role in ("user", "assistant"):
            new_turns.append({"role": m.role, "content": m.content})
    if reply:
        new_turns.append({"role": "assistant", "content": reply})
    _append_messages_pg(session_id, new_turns)

    # Periodic running-summary refresh
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
