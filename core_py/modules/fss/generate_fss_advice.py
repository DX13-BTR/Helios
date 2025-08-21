from datetime import date
import os
import sys

# Ensure we can import project modules when run as a package or directly
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

import ollama
from db.database import get_db_connection

# --- Prompt templates (kept as-is) ---
TEMPLATES = {
    "uc": (
        "Given the following FSS summary, is the household's Universal Credit protected? "
        "If not, briefly explain why and what can be done.\n\n{summary}"
    ),
    "buffer": (
        "Based on this FSS summary, assess the current buffer and drawdown availability. "
        "Should reserves be increased or drawn down?\n\n{summary}"
    ),
    "tee": (
        "This FSS summary includes payment status for Tee. Is her pay covered? "
        "If not, what action is needed?\n\n{summary}"
    ),
    "spending": (
        "Review the FSS summary. Offer a quick insight on spending patterns, risks, or improvements.\n\n{summary}"
    ),
    "savings": (
        "From the FSS summary, assess whether any money should be put into savings this week.\n\n{summary}"
    ),
}

# --- Model config ---
FSS_MODEL = os.getenv("FSS_MODEL", os.getenv("ADVICE_MODEL", "llama3"))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))

def _llama_text(prompt: str) -> str:
    """
    Call Ollama Llama and return a short, plain-text answer.
    No JSON, no lists — just 2–4 concise sentences.
    """
    res = ollama.chat(
        model=FSS_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are Helios FSS. Reply with 2–4 concise sentences. "
                           "No JSON. No bullet points. Plain text only.",
            },
            {"role": "user", "content": prompt},
        ],
        options={"num_ctx": OLLAMA_NUM_CTX, "temperature": 0.2},
    )
    return (res.get("message") or {}).get("content", "").strip()

def generate_fss_advice():
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Compute Monday of this week
        today = date.today()
        this_week = today - date.resolution * today.weekday()  # Monday

        # Fetch the latest FSS summary row for this week
        cur.execute(
            """
            SELECT * FROM fss_summary
            WHERE week_start = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (this_week.isoformat(),),
        )
        row = cur.fetchone()
        if not row:
            print("❌ No FSS summary found for this week.")
            return

        # Turn row into a readable summary block
        columns = [col[0] for col in cur.description]
        summary_dict = dict(zip(columns, row))
        summary_str = "\n".join(f"{k}: {v}" for k, v in summary_dict.items())

        # Generate advice via Llama (plain text per key)
        print("🤖 Generating FSS advice via LLM...")
        advice: dict[str, str] = {}
        for key, prompt_template in TEMPLATES.items():
            prompt = prompt_template.format(summary=summary_str)
            text = _llama_text(prompt)
            advice[key] = text
            print(f"✅ {key.upper()} advice generated.")

        # Insert or update fss_advice (expects TEXT fields)
        cur.execute(
            """
            INSERT INTO fss_advice
            (week_start, uc_advice, buffer_advice, tee_advice, spending_advice, savings_advice, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(week_start) DO UPDATE SET
                uc_advice=excluded.uc_advice,
                buffer_advice=excluded.buffer_advice,
                tee_advice=excluded.tee_advice,
                spending_advice=excluded.spending_advice,
                savings_advice=excluded.savings_advice,
                created_at=excluded.created_at
            """,
            (
                this_week.isoformat(),
                advice.get("uc", ""),
                advice.get("buffer", ""),
                advice.get("tee", ""),
                advice.get("spending", ""),
                advice.get("savings", ""),
                date.today().isoformat(),
            ),
        )
        conn.commit()

    print("✅ FSS Advice written to fss_advice table.")

if __name__ == "__main__":
    generate_fss_advice()
