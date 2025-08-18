import sqlite3
import os
from datetime import datetime, date, timedelta
from core_py.db.database import get_db_connection

# --- UC / FSS Settings ---
MIF_MIKE = 1642.72
MIF_TEE = 1055.42
UC_STANDARD = 1647.65   # £628.10 + £680.55 + £339.00
UC_WORK_ALLOWANCE = 411
UC_TAPER = 0.55
TEE_TARGET = 650.00
BUFFER_TARGET = 500.00  # can make dynamic later

def calculate_fss_summary():
    conn = get_db_connection()
    cur = conn.cursor()

    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end = week_start + timedelta(days=6)
    this_month = today.strftime("%Y-%m")

    # --- 1️⃣ Load Transactions ---
    cur.execute("SELECT date, amount, direction, counterparty, source, status FROM transactions_efkaristo")
    efk_tx = cur.fetchall()

    cur.execute("SELECT date, amount, direction, counterparty, source, status FROM transactions_personal")
    per_tx = cur.fetchall()

    # --- 2️⃣ Calculate net income & expenses for Mike ---
    net_mike = 0.0
    net_expenses = 0.0

    for d, amt, direction, counterparty, source, status in efk_tx:
        if not d or this_month not in d:
            continue

        if direction == "IN":
            if source not in ("ON_US_PAY_ME", "INTERNAL_TRANSFER"):
                net_mike += amt
        else:
            # Expense
            if counterparty not in ("Tee", "Savings", "Directors Loan"):
                net_mike -= amt
                net_expenses += amt

    # --- 3️⃣ Tee Payments ---
    tee_paid = sum(
        amt for d, amt, direction, counterparty, *_ in per_tx
        if d and this_month in d and direction == "IN" and counterparty == "Tee"
    )

    # --- 4️⃣ UC & Household Income ---
    # Apply MIFs
    uc_income_mike = max(net_mike, MIF_MIKE)
    uc_income_tee = max(0.0, MIF_TEE)  # assuming no Tee self‑employment in personal table
    household_income = uc_income_mike + uc_income_tee

    uc_reduction = max(0, household_income - UC_WORK_ALLOWANCE) * UC_TAPER
    uc_entitlement = max(0, UC_STANDARD - uc_reduction)
    uc_safe = uc_entitlement > 0

    # --- 5️⃣ Balances & Buffer ---
    cur.execute("SELECT SUM(balance) FROM balances")
    total_balance = cur.fetchone()[0] or 0.0
    buffer_pct = (total_balance / BUFFER_TARGET) * 100
    drawdown_available = max(0, total_balance - BUFFER_TARGET)

    # --- 6️⃣ Suggested Pay (headroom vs UC taper) ---
    uc_income_limit = (UC_STANDARD / UC_TAPER) + UC_WORK_ALLOWANCE
    headroom = uc_income_limit - household_income
    suggested_pay = max(0, min(drawdown_available, headroom))

    # --- 7️⃣ Suggested Savings ---
    suggested_savings = 0.0
    if buffer_pct >= 130 and drawdown_available > 0:
        suggested_savings = round(drawdown_available * 0.5, 2)

    # --- 8️⃣ Build Summary Dict (all fields accountant‑grade) ---
    summary = {
        "week_start": week_start,
        "week_end": week_end,
        "uc_safe": uc_safe,
        "uc_entitlement": round(uc_entitlement, 2),
        "uc_reduction": round(uc_reduction, 2),
        "household_income": round(household_income, 2),
        "net_income": round(net_mike, 2),
        "net_expenses": round(net_expenses, 2),
        "tee_paid": round(tee_paid, 2),
        "tee_covered": tee_paid >= TEE_TARGET,
        "total_balance": round(total_balance, 2),
        "buffer_pct": round(buffer_pct, 2),
        "drawdown_available": round(drawdown_available, 2),
        "suggested_pay": round(suggested_pay, 2),
        "suggested_savings": round(suggested_savings, 2),
    }

    # --- 9️⃣ Insert into fss_summary (verbose version) ---
    cur.execute("""
        INSERT INTO fss_summary
        (week_start, week_end, uc_safe, uc_entitlement, uc_reduction,
         household_income, net_income, net_expenses, tee_paid, tee_covered,
         total_balance, buffer_pct, drawdown_available,
         suggested_pay, suggested_savings, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        week_start.isoformat(),
        week_end.isoformat(),
        int(uc_safe),
        summary["uc_entitlement"],
        summary["uc_reduction"],
        summary["household_income"],
        summary["net_income"],
        summary["net_expenses"],
        summary["tee_paid"],
        int(summary["tee_covered"]),
        summary["total_balance"],
        summary["buffer_pct"],
        summary["drawdown_available"],
        summary["suggested_pay"],
        summary["suggested_savings"],
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()
    return summary


if __name__ == "__main__":
    print("Using DB:", os.getenv("HELIOS_DB_PATH"))
    summary = calculate_fss_summary()
    print("✅ Full FSS Summary Calculated:")
    for k, v in summary.items():
        print(f"{k}: {v}")
