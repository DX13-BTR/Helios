from fastapi import APIRouter
from db import get_db_connection

router = APIRouter()

@router.get("/advice/latest")
def get_latest_advice():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT uc_advice, buffer_advice, tee_advice, spending_advice, savings_advice
        FROM fss_advice
        ORDER BY week_start DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    conn.close()

    if row:
        return {
            "uc": row["uc_advice"],
            "buffer": row["buffer_advice"],
            "tee": row["tee_advice"],
            "spending": row["spending_advice"],
            "savings": row["savings_advice"]
        }
    else:
        return {
            "uc": "No UC advice available.",
            "buffer": "No buffer advice available.",
            "tee": "No Tee advice available.",
            "spending": "No spending advice available.",
            "savings": "No savings advice available."
        }
