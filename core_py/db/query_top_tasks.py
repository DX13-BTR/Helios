import sqlite3

DB_PATH = "C:/core_py/db/helios.db"

def query_top_tasks():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("→ Top 10 tasks by score:")
    for row in cur.execute("""
        SELECT id, name, score, section, due_date
        FROM triaged_tasks
        ORDER BY score DESC
        LIMIT 10
    """):
        print(row)

    conn.close()

if __name__ == "__main__":
    query_top_tasks()
