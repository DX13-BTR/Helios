import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import sqlite3
import importlib
from datetime import datetime


def test_personal_tasks_due_date_filter(tmp_path, monkeypatch):
    db_file = tmp_path / "helios.db"
    monkeypatch.setenv("DB_PATH", str(db_file))

    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE triaged_tasks (
            id INTEGER PRIMARY KEY,
            name TEXT,
            reason TEXT,
            space_name TEXT,
            status TEXT,
            due_date INTEGER,
            priority TEXT,
            agent_rank INTEGER
        );
        CREATE TABLE personal_context (key TEXT, value TEXT);
        CREATE TABLE family_context (name TEXT, relationship TEXT, details TEXT);
        CREATE TABLE company_context (key TEXT, value TEXT);
        CREATE TABLE system_state (key TEXT, value TEXT);
        """
    )
    now_ms = int(datetime.now().timestamp() * 1000)
    cur.execute(
        "INSERT INTO triaged_tasks (id, name, reason, space_name, status, due_date) VALUES (?, ?, ?, ?, ?, ?)",
        (1, "due", "reason", "Personal", "Open", now_ms - 1000),
    )
    cur.execute(
        "INSERT INTO triaged_tasks (id, name, reason, space_name, status, due_date) VALUES (?, ?, ?, ?, ?, ?)",
        (2, "future", "reason", "Personal", "Open", now_ms + 86400000),
    )
    conn.commit()
    conn.close()

    from core_py.services import context
    importlib.reload(context)
    ctx = context.build_helios_context()
    names = [t["name"] for t in ctx["tasks"]["personal"]]
    assert names == ["due"]
