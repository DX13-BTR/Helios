import os
import sqlite3
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# === CONFIG ===
DB_PATH = os.path.join(os.path.dirname(__file__), "db", "helios.db")
CHAT_DUMPS_FOLDER = os.path.join(os.path.dirname(__file__), "archive", "chat_dumps")

# === INITIALIZE DB ===
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY,
    source TEXT,
    thread_id TEXT,
    timestamp DATETIME,
    sender TEXT,
    message TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    agent_name TEXT,
    payload TEXT,
    status TEXT,
    created_at DATETIME,
    updated_at DATETIME
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY,
    metric_name TEXT,
    metric_value REAL,
    timestamp DATETIME
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY,
    agent_name TEXT,
    task_id INTEGER,
    event TEXT,
    timestamp DATETIME
)
""")

conn.commit()
conn.close()

# === INGEST CHAT DUMPS ===
def ingest_chat_dumps():
    if not os.path.exists(CHAT_DUMPS_FOLDER):
        return 0

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    ingested = 0

    for file in os.listdir(CHAT_DUMPS_FOLDER):
        if file.endswith(".json"):
            path = os.path.join(CHAT_DUMPS_FOLDER, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Expected: list of {"thread_id":..., "timestamp":..., "sender":..., "message":...}
                for item in data:
                    c.execute("""
                        INSERT INTO chats (source, thread_id, timestamp, sender, message)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        file,
                        item.get("thread_id"),
                        item.get("timestamp", datetime.utcnow().isoformat()),
                        item.get("sender", "unknown"),
                        item.get("message", "")
                    ))
                    ingested += 1
            except Exception as e:
                print(f"Error ingesting {file}: {e}")

    conn.commit()
    conn.close()
    return ingested


# === FASTAPI APP ===
app = FastAPI(title="Helios Orchestrator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Memory Endpoints ---
@app.get("/get-chats")
def get_chats(limit: int = 50):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, source, thread_id, timestamp, sender, message FROM chats ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(zip(["id","source","thread_id","timestamp","sender","message"], row)) for row in rows]

@app.get("/search-chats")
def search_chats(query: str, limit: int = 50):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, source, thread_id, timestamp, sender, message
        FROM chats
        WHERE message LIKE ?
        ORDER BY id DESC LIMIT ?
    """, (f"%{query}%", limit))
    rows = c.fetchall()
    conn.close()
    return [dict(zip(["id","source","thread_id","timestamp","sender","message"], row)) for row in rows]

# --- Task Queue Endpoints ---
@app.post("/add-task")
def add_task(agent_name: str, payload: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute("INSERT INTO tasks (agent_name, payload, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
              (agent_name, payload, "pending", now, now))
    conn.commit()
    task_id = c.lastrowid
    conn.close()
    return {"task_id": task_id, "status": "pending"}

@app.get("/get-tasks")
def get_tasks(status: str = "pending"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, agent_name, payload, status, created_at, updated_at FROM tasks WHERE status=?", (status,))
    rows = c.fetchall()
    conn.close()
    return [dict(zip(["id","agent_name","payload","status","created_at","updated_at"], row)) for row in rows]

# --- Logging Endpoint ---
@app.post("/log-event")
def log_event(agent_name: str, task_id: int, event: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute("INSERT INTO logs (agent_name, task_id, event, timestamp) VALUES (?, ?, ?, ?)",
              (agent_name, task_id, event, now))
    conn.commit()
    conn.close()
    return {"logged": True}

if __name__ == "__main__":
    count = ingest_chat_dumps()
    print(f"[Helios Kernel] DB ready at {DB_PATH} | {count} chats ingested")
    uvicorn.run(app, host="0.0.0.0", port=5000)
