# core_py/agents/prioritiser/agent_prioritiser.py
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
import sqlite3
import json
import re
from core.llm.route_prompt import routePrompt, JSON_OUTPUT_SYSTEM_PROMPT

DB_PATH = os.path.join(os.path.dirname(__file__), "../../db/helios.db")


def fetch_triaged_tasks():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, score FROM triaged_tasks ORDER BY score DESC LIMIT 25")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "urgency": r[2]} for r in rows]


from datetime import datetime

def write_agent_ranks(task_list):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    timestamp = datetime.now().isoformat()

    for rank, task in enumerate(task_list, start=1):
        task_id = task["id"]
        reason = task.get("reason", "No reason provided")

        # Update triaged_tasks with latest rank and reason
        c.execute(
            "UPDATE triaged_tasks SET agent_rank = ?, agent_reason = ? WHERE id = ?",
            (rank, reason, task_id)
        )

        # Insert memory log into task_logs
        c.execute(
            "INSERT INTO task_logs (task_id, agent_rank, agent_reason, timestamp) VALUES (?, ?, ?, ?)",
            (task_id, rank, reason, timestamp)
        )

    conn.commit()
    conn.close()
    print("[Helios] Agent ranking and memory logs written to DB.")


def run_prioritiser():
    tasks = fetch_triaged_tasks()

    prompt = f"""You are Helios AI. Rank the following tasks by execution priority.

Each task has:
- ID (unique)
- Title
- Urgency score

Format:
<ID>: <Title> (Urgency: <urgency>)

Tasks:
{chr(10).join([f"{t['id']}: {t['title']} (Urgency: {t['urgency']})" for t in tasks])}

Return a JSON array of objects in priority order.
Each object must contain `id` and `reason`, like:
[
  {{ "id": "task_001", "reason": "Urgent HMRC deadline" }},
  {{ "id": "task_002", "reason": "Client onboarding is time-sensitive" }}
]"""

    result = routePrompt(prompt, model="llama3", system=JSON_OUTPUT_SYSTEM_PROMPT)

    # Debug output to see what LLM returns
    print("[DEBUG] Raw LLM response:")
    print(result)

    print("[Prioritisation Result]")
    print(result)

    try:
        # If result is already a list, we can directly pass it to write_agent_ranks
        if not isinstance(result, list):
            raise ValueError(f"Expected list from LLM, got: {type(result)} - {result}")

        write_agent_ranks(result)
    except Exception as e:
        print(f"[ERROR] Could not write ranks: {e}")
