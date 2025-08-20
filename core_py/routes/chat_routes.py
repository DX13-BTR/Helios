# core_py/routes/chat_routes.py
from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv
from sqlalchemy import text
import openai
import os
import pprint

from core_py.db.session import get_session

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

router = APIRouter(prefix="/chat", tags=["chat"])

DDL = text("""
CREATE SCHEMA IF NOT EXISTS helios;
CREATE TABLE IF NOT EXISTS helios.chat_history (
  id BIGSERIAL PRIMARY KEY,
  role TEXT,
  content TEXT,
  ts TIMESTAMPTZ DEFAULT NOW()
);
""")

def _ensure_tables():
    with get_session() as s:
        s.execute(DDL)
        s.commit()

@router.post("/completions")
def chat_handler(payload: dict):
    try:
        _ensure_tables()

        # Fetch last 10 user/assistant messages from chat history
        with get_session() as s:
            rows = s.execute(text("""
                SELECT role, content
                FROM helios.chat_history
                WHERE role IN ('user', 'assistant')
                ORDER BY id DESC
                LIMIT 10
            """)).mappings().all()
            history_messages = [dict(r) for r in reversed(rows)]

        # Extract latest user message and task context
        incoming_messages = payload.get("messages", [])
        task_context = payload.get("task_context", [])

        # 🧠 Format flat task context (from AIAdvicePanel.jsx)
        context_lines = []
        if isinstance(task_context, list) and task_context:
            context_lines.append("Here are the current tasks you should consider:")
            for t in task_context:
                content = t.get("content") or t.get("name") or "[No content]"
                due = t.get("due") or t.get("due_date") or "no due date"
                emoji = t.get("source", "•")
                context_lines.append(f"{emoji} {content} (due: {due})")
        else:
            context_lines.append("⚠️ No task context received.")

        full_task_context = "\n".join(context_lines)

        # 🧠 Build system prompt
        system_prompt = {
            "role": "system",
            "content": (
                "You are Helios Advisor. Your job is to help Mike make decisions about current tasks.\n\n"
                f"{full_task_context}\n\n"
                "Each task includes an emoji prefix representing its source:\n"
                "- 🚨 = Urgent (Todoist)\n"
                "- ✅ = Do Next\n"
                "- 📥 = Email\n"
                "- 👤 = Personal\n\n"
                "When giving advice, include the emoji and task name in your responses so Mike can easily trace it back to its panel.\n"
                "Be concise, practical, and prioritize based on due date, urgency, and panel weight."
            )
        }

        all_messages = [system_prompt] + history_messages + incoming_messages

        # 👀 Optional debug log
        print("🧾 Prompt preview:")
        pprint.pprint(all_messages)

        # Chat Completion with GPT-4 (unchanged)
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=all_messages
        )

        reply_obj = response.choices[0].message
        reply = {"role": reply_obj.role, "content": reply_obj.content}

        # Store new messages into Postgres
        with get_session() as s:
            s.execute(text("""
                INSERT INTO helios.chat_history (role, content)
                VALUES (:role, :content)
            """), [{"role": m["role"], "content": m["content"]}
                   for m in incoming_messages + [reply]])
            s.commit()

        return {"reply": reply}

    except Exception as e:
        print(f"🔥 Error in chat_handler: {e}")
        raise HTTPException(status_code=500, detail="Error processing chat request")
