from datetime import datetime
import pytz

def transform_starling_to_helios(balance_data, spaces_data, account_name):
    """
    Normalize Starling API responses into a Helios-friendly shape.
    Includes BOTH main account balance and spaces/goals in totals.

    Inputs (typical):
      balance_data:
        {
          "effectiveBalance": {"minorUnits": ...},
          "clearedBalance":   {"minorUnits": ...},
          ...
        }
      spaces_data (personal):
        { "spaces": [ { "savingsGoalName": "...", "balance": {"minorUnits": ...} }, ... ] }
      spaces_data (business):
        { "savingsGoalList": [ { "name": "...", "totalSaved": {"minorUnits": ...} }, ... ] }

    Output:
      {
        "timestamp": ISO8601 London time,
        "by_account": {"efkaristo" | "personal": <main_balance_gbp>},
        "by_space": [ {"account": "...", "space": "Name", "balance": n.nn}, ... ],
        "company_balance": <total for company account (main + spaces) or 0>,
        "personal_balance": <total for personal account (main + spaces) or 0>,
        "combined_balance": <company_balance + personal_balance for this call if applicable>
      }
    """
    local_time = datetime.now(pytz.timezone("Europe/London")).isoformat()
    account_key = str(account_name or "").strip().lower()

    # Main balance: prefer effective, fall back to cleared
    def mu(d, *path):
        cur = d or {}
        for p in path:
            cur = cur.get(p, {}) if isinstance(cur, dict) else {}
        if isinstance(cur, dict):
            val = cur.get("minorUnits", 0)
        else:
            val = cur
        try:
            return int(val)
        except Exception:
            return 0

    main_minor = mu(balance_data, "effectiveBalance") or mu(balance_data, "clearedBalance")
    main_balance = float(main_minor) / 100.0

    by_account = {account_key: main_balance}
    by_space = []

    # Personal spaces
    if isinstance(spaces_data, dict) and "spaces" in spaces_data:
        for space in spaces_data["spaces"]:
            name = space.get("savingsGoalName") or space.get("name") or "Unnamed"
            bal_minor = mu(space, "balance")
            by_space.append({
                "account": account_key,
                "space": name,
                "balance": float(bal_minor) / 100.0,
            })

    # Business savings goals
    elif isinstance(spaces_data, dict) and ("savingsGoalList" in spaces_data or "savingsGoals" in spaces_data):
        goals = spaces_data.get("savingsGoalList") or spaces_data.get("savingsGoals") or []
        for goal in goals:
            name = goal.get("name") or "Unnamed"
            bal_minor = mu(goal, "totalSaved")
            by_space.append({
                "account": account_key,
                "space": name,
                "balance": float(bal_minor) / 100.0,
            })

    total_space_balance = sum(s["balance"] for s in by_space)
    total_for_account = round(main_balance + total_space_balance, 2)

    # Per-account projections for convenience
    company_balance = total_for_account if account_key == "efkaristo" else 0.0
    personal_balance = total_for_account if account_key == "personal" else 0.0

    return {
        "timestamp": local_time,
        "by_account": by_account,
        "by_space": by_space,
        "company_balance": company_balance,
        "personal_balance": personal_balance,
        # combined here reflects this invocation's account total; your caller can sum across both accounts
        "combined_balance": total_for_account,
    }
