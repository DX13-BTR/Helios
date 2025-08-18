from datetime import datetime
import sqlite3
from pathlib import Path
import os

DB_PATH = str(Path(os.getenv("DB_PATH")))

def build_helios_context():
    now = datetime.now()

    context = {
        "datetime": now.isoformat(),
        "date": now.strftime("%A, %d %B %Y"),
        "time": now.strftime("%H:%M"),
        "time_of_day": _get_time_of_day(now),
        "fatigue": "unknown",
        "urgent_tasks": 0,
        "tone": _get_tone(now.hour),
        "personal": {},
        "family": [],
        "company": {},
        "system": {},
        "tasks": {
            "urgent_emails": [],
            "do_next": [],
            "personal": []
        }
    }

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 🧠 Fatigue level from urgent task count
        cursor.execute("""
            SELECT COUNT(*) FROM triaged_tasks
            WHERE priority = 'Urgent' AND status NOT IN ('Done', 'Cancelled')
        """)
        urgent_count = cursor.fetchone()[0]
        context["urgent_tasks"] = urgent_count
        context["fatigue"] = _calculate_fatigue(now.hour, urgent_count)

        # 👤 Personal context
        cursor.execute("SELECT key, value FROM personal_context")
        context["personal"] = {key: value for key, value in cursor.fetchall()}

        # 👨‍👩‍👦 Family context
        cursor.execute("SELECT name, relationship, details FROM family_context")
        context["family"] = [
            {"name": name, "relationship": relationship, "details": details}
            for name, relationship, details in cursor.fetchall()
        ]

        # 🏢 Company context
        cursor.execute("SELECT key, value FROM company_context")
        context["company"] = {key: value for key, value in cursor.fetchall()}

        # ⚙️ System state
        cursor.execute("SELECT key, value FROM system_state")
        context["system"] = {key: value for key, value in cursor.fetchall()}

        # 📬 Email-tagged tasks (what you're calling "urgent_emails")
        cursor.execute("""
            SELECT id, name, reason FROM triaged_tasks
            WHERE reason LIKE '%email%' AND status NOT IN ('Done', 'Cancelled')
        """)
        context["tasks"]["urgent_emails"] = [
            {"id": task_id, "name": name, "reason": reason}
            for task_id, name, reason in cursor.fetchall()
        ]

        # 🗂️ Do Next tasks (top 25 by agent_rank)
        cursor.execute("""
            SELECT id, name, reason FROM triaged_tasks
            WHERE agent_rank IS NOT NULL AND status NOT IN ('Done', 'Cancelled')
            ORDER BY agent_rank DESC LIMIT 25
        """)
        context["tasks"]["do_next"] = [
            {"id": task_id, "name": name, "reason": reason}
            for task_id, name, reason in cursor.fetchall()
        ]

        # 👤 Personal tasks (due today or earlier)
        cursor.execute("""
            SELECT id, name, reason FROM triaged_tasks
            WHERE space_name = 'Personal'
              AND status NOT IN ('Done', 'Cancelled')
              AND due_date <= ?
        """, (int(now.timestamp() * 1000),))
        context["tasks"]["personal"] = [
            {"id": task_id, "name": name, "reason": reason}
            for task_id, name, reason in cursor.fetchall()
        ]

    except sqlite3.Error as e:
        print(f"[build_helios_context] DB error: {e}")
    finally:
        conn.close()

    return context


def _get_time_of_day(now):
    hour = now.hour
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    else:
        return "late night"

def _get_tone(hour):
    if hour < 9:
        return "gentle"
    elif 9 <= hour <= 16:
        return "neutral"
    else:
        return "gentle"

def _calculate_fatigue(hour, urgent_count):
    if hour >= 20 or hour <= 5:
        return "high" if urgent_count > 2 else "moderate"
    elif urgent_count >= 4:
        return "moderate"
    else:
        return "low"
