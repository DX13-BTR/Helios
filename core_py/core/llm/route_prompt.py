import re
import json
import os
import sys
sys.path.append('C:/Helios/core_py')
from openai import OpenAI
from dotenv import load_dotenv
from services.context import build_helios_context

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 🔒 Forces structured output
JSON_OUTPUT_SYSTEM_PROMPT = """
You are a Helios agent.

Your job is to prioritise tasks across three input lists and return structured JSON only.

Respond in the following format:
{
  "top_tasks": [
    { "id": "123", "name": "Task title", "reason": "Short justification", "source": "do_next" | "urgent_emails" | "personal" },
    ...
  ],
  "notes": "Optional strategy or reasoning"
}

Do not include any greeting, explanation, or formatting outside this JSON object.
"""

def fix_json_output(raw_text):
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Cannot locate JSON braces")
    
    cleaned = raw_text[start:end+1]
    cleaned = cleaned.replace("“", "\"").replace("”", "\"").replace("‘", "'").replace("’", "'")
    return cleaned

def llama3_completion(prompt, system=None):
    import requests

    payload = {
        "model": "llama3",
        "messages": [
            {"role": "system", "content": system or "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "temperature": 0.4
    }

    try:
        res = requests.post("http://localhost:11434/api/chat", json=payload)
        res.raise_for_status()
        response_data = res.json()

        content = response_data["message"]["content"].strip()
        print("🔍 LLaMA3 response:", repr(content))

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            print("⚠️ JSON parse failed, attempting fix...")
            cleaned = fix_json_output(content)
            return json.loads(cleaned)

    except Exception as e:
        print("❌ LLaMA3 request failed:", e)
        return f"[LLM ERROR] {str(e)}"

def routePrompt(prompt, model="gpt-4", system=None):
    context = build_helios_context()

    do_next_tasks = context["tasks"].get("do_next", [])
    urgent_email_tasks = context["tasks"].get("urgent_emails", [])
    personal_tasks = context["tasks"].get("personal", [])

    task_summary = f"""
You have access to the following triaged task lists:

📌 Do Next (top 25 agent-ranked):
{json.dumps(do_next_tasks[:5], indent=2)}

📨 Urgent Emails (tagged 'email'):
{json.dumps(urgent_email_tasks[:5], indent=2)}

👤 Personal Tasks (due today or overdue):
{json.dumps(personal_tasks[:5], indent=2)}
"""

    user_prompt = f"""{prompt}

Your task is to choose the 5 highest-priority items from these lists.
Rank them based on urgency, value, and context.

Include justification in the `"reason"` field. Also return a `"source"` field for each one (do_next, urgent_emails, personal).
"""

    context_str = f"""Date: {context['date']} ({context['time_of_day']}, {context['time']})
Fatigue level: {context['fatigue']}
Urgent tasks today: {context['urgent_tasks']}

Personal:
- Name: {context['personal'].get('name', 'Mike')}
- Health: {context['personal'].get('health', 'T2 diabetes, IBS')}
- Routines: {context['personal'].get('routines', 'School run at 3PM, prefers calm mornings')}
- Preferences: {context['personal'].get('preferences', 'Subtle theming, clean systems')}

Family:
""" + "\n".join([
        f"  - {member['name']} ({member['relationship']}): {member['details']}"
        for member in context.get('family', [])
    ]) + f"""

Efkaristo:
- Role: {context['company'].get('role', 'Director')}
- Tee payday: {context['company'].get('tee_pay_day', '15th')}
- Payroll rule: {context['company'].get('payroll_logic', 'Run varies')}

System state:
- Mode: {context['system'].get('mode', 'focus')}
- Theme: {context['system'].get('theme', 'default')}
- AI tone: {context['system'].get('tone', 'human')}
"""

    # Use LLaMA 3 if requested
    if model == "llama3":
        return llama3_completion(
            user_prompt,
            system=JSON_OUTPUT_SYSTEM_PROMPT + "\n\n" + context_str + "\n" + task_summary
        )

    # Default to OpenAI
    messages = [
        {"role": "system", "content": JSON_OUTPUT_SYSTEM_PROMPT + "\n\n" + context_str + "\n" + task_summary},
        {"role": "user", "content": user_prompt}
    ]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.4,
        )

        raw_content = response.choices[0].message.content.strip()
        print("🔍 Raw LLM response:", repr(raw_content))

        if not raw_content.startswith("{") and not raw_content.startswith("["):
            raise ValueError("Response did not return JSON")

        parsed = json.loads(raw_content)
        return parsed

    except Exception as e:
        print("❌ Failed to parse JSON:", e)
        return f"[LLM ERROR] {str(e)}"
