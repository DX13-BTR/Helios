from fastapi import APIRouter, HTTPException, Body
import os
import sqlite3
import time
import ollama
from dotenv import load_dotenv
from typing import List, Optional, Literal
from pydantic import BaseModel
from ..db.database import get_db_connection

# Load .env for DB path, model name, and context size
load_dotenv(dotenv_path="core_py/.env")
if not os.getenv("DB_PATH"):
    raise ValueError("❌ DB_PATH not set. Check your .env file.")

MODEL_NAME = os.getenv("ADVICE_MODEL", "llama3:pinned-adv")
NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))

router = APIRouter()

# -----------------------------
# Existing /latest endpoint
# -----------------------------
@router.get("/latest")
def get_latest_advice():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT uc_advice, buffer_advice, tee_advice, spending_advice, savings_advice, created_at
        FROM fss_advice
        ORDER BY created_at DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {}

    return {
        "uc": row["uc_advice"],
        "buffer": row["buffer_advice"],
        "tee": row["tee_advice"],
        "spending": row["spending_advice"],
        "savings": row["savings_advice"],
        # NEW: expose the timestamp so the UI can show freshness
        "generated_at": row["created_at"],
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
# SQLite helpers for memory
# -----------------------------
def _ensure_tables(conn: sqlite3.Connection):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS advice_messages (
        id INTEGER PRIMARY KEY,
        ts INTEGER,
        role TEXT,
        text TEXT,
        session_id TEXT
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS advice_summaries (
        id INTEGER PRIMARY KEY,
        ts INTEGER,
        summary TEXT,
        session_id TEXT
    )
    """)
    conn.commit()

def _get_running_summary(conn, session_id: str) -> str:
    cur = conn.execute(
        "SELECT summary FROM advice_summaries WHERE session_id=? ORDER BY ts DESC LIMIT 1",
        (session_id,)
    )
    row = cur.fetchone()
    return row[0] if row else ""

def _save_running_summary(conn, session_id: str, summary: str):
    conn.execute(
        "INSERT INTO advice_summaries(ts, summary, session_id) VALUES(?,?,?)",
        (int(time.time()), summary, session_id),
    )
    conn.commit()

def _load_recent_messages(conn, session_id: str, limit: int = 20):
    cur = conn.execute(
        "SELECT role, text FROM advice_messages WHERE session_id=? ORDER BY ts DESC LIMIT ?",
        (session_id, limit)
    )
    rows = cur.fetchall()
    return [{"role": r[0], "content": r[1]} for r in rows[::-1]]

def _append_messages(conn, session_id: str, turns: List[dict]):
    conn.executemany(
        "INSERT INTO advice_messages(ts, role, text, session_id) VALUES(?,?,?,?)",
        [(int(time.time()), t["role"], t["content"], session_id) for t in turns]
    )
    conn.commit()

# -----------------------------
# /chat endpoint for Advice Panel
# -----------------------------
@router.post("/chat")
def chat(req: ChatRequest):
    conn = get_db_connection()
    _ensure_tables(conn)
    session_id = req.session_id or "default"

    # Build recent context
    hist_msgs: List[Msg] = []
    if req.history:
        for h in req.history[-20:]:
            role = h.get("role") if h.get("role") in ("user", "assistant") \
                   else ("assistant" if h.get("from") == "agent" else "user")
            hist_msgs.append({"role": role, "content": h.get("content") or h.get("text", "")})

    recent_server = _load_recent_messages(conn, session_id, limit=20)
    running_summary = _get_running_summary(conn, session_id)

    # Task context summary
    key_ctx = []
    tc = req.task_context or []
    if isinstance(tc, list):
        for t in tc[:20]:  # cap to first 20 tasks
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

    # Simple size limit (chars, rough token proxy)
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

    reply = (res.get("message") or {}).get("content", "").strip()
    if not reply:
        reply = "I didn't get a response."

    # Save new turns
    new_turns = []
    for m in req.messages:
        if m.role in ("user", "assistant"):
            new_turns.append({"role": m.role, "content": m.content})
    if reply:
        new_turns.append({"role": "assistant", "content": reply})
    if new_turns:
        _append_messages(conn, session_id, new_turns)

    # Periodically refresh running summary
    cur = conn.execute(
        "SELECT COUNT(*) FROM advice_messages WHERE session_id=? AND role='user'",
        (session_id,)
    )
    user_count = cur.fetchone()[0]
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
                _save_running_summary(conn, session_id, summary_txt[:4000])
        except Exception:
            pass

    return {"reply": {"content": reply}}
