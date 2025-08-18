from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv
import openai
import sqlite3
import os
import pprint

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

DB_PATH = os.getenv("DB_PATH")
print(f"DB_PATH is: {DB_PATH}")

router = APIRouter()

@router.post("/chat")
def chat_handler(payload: dict):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Fetch last 10 user/assistant messages from chat history
        cursor.execute("""
            SELECT role, content FROM chat_history
            WHERE role IN ('user', 'assistant')
            ORDER BY id DESC LIMIT 10
        """)
        history_rows = cursor.fetchall()
        history_messages = [dict(row) for row in reversed(history_rows)]

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

        # Chat Completion with GPT-4
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=all_messages
        )

        reply_obj = response.choices[0].message
        reply = {"role": reply_obj.role, "content": reply_obj.content}

        # Store new messages into database
        insert_query = "INSERT INTO chat_history (role, content) VALUES (?, ?)"
        for msg in incoming_messages + [reply]:
            cursor.execute(insert_query, (msg["role"], msg["content"]))

        conn.commit()
        conn.close()

        return {"reply": reply}

    except Exception as e:
        print(f"🔥 Error in chat_handler: {e}")
        raise HTTPException(status_code=500, detail="Error processing chat request")
