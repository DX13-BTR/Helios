import sqlite3
import os
from datetime import datetime
from typing import Dict

import requests
from fastapi import APIRouter
from dotenv import load_dotenv

from ..db.database import get_db_connection

# Load .env for Starling tokens and UIDs
load_dotenv(dotenv_path="core_py/.env")

router = APIRouter(prefix="/fss", tags=["FSS Summary"])

# === Starling live totals helpers ===================================================

STARLING_BASE = "https://api.starlingbank.com/api/v2"

def _hdr(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

def _get_env(name: str) -> str:
    v = os.getenv(name)
    return v.strip() if isinstance(v, str) else ""

def _spaces_url(acct_type: str, uid: str) -> str:
    """
    Personal: /account/{uid}/spaces
    Business: /account/{uid}/savings-goals
    """
    if acct_type.lower() == "personal":
        return f"{STARLING_BASE}/account/{uid}/spaces"
    return f"{STARLING_BASE}/account/{uid}/savings-goals"

def _parse_minor_units(d: dict, *path) -> int:
    """
    Safely pull a nested .minorUnits; returns 0 if missing.
    """
    cur = d or {}
    for p in path:
        cur = cur.get(p, {}) if isinstance(cur, dict) else {}
    val = cur if isinstance(cur, (int, float)) else cur.get("minorUnits", 0) if isinstance(cur, dict) else 0
    if isinstance(val, (int, float)):
        return int(val)
    return 0

def _live_totals() -> Dict[str, float]:
    """
    Fetch live balances for company (Efkaristo) and personal accounts.
    Sums main account balance + all spaces/goals for each account.
    Returns GBP totals as floats.
    """
    accounts = [
        {
            "name": "Efkaristo",
            "type": "business",
            "token": _get_env("EFK_STARLING_TOKEN"),
            "uid": _get_env("EFK_ACCOUNT_UID"),
        },
        {
            "name": "Personal",
            "type": "personal",
            "token": _get_env("PERS_STARLING_TOKEN"),
            "uid": _get_env("PERS_ACCOUNT_UID"),
        },
    ]

    out = {"company_total": 0.0, "personal_total": 0.0, "combined_total": 0.0}

    for acc in accounts:
        token, uid, acct_type = acc["token"], acc["uid"], acc["type"]
        if not token or not uid:
            continue

        # 1) Main account balance (prefer effectiveBalance, then clearedBalance)
        r = requests.get(f"{STARLING_BASE}/accounts/{uid}/balance", headers=_hdr(token), timeout=6)
        r.raise_for_status()
        bj = r.json() or {}
        main_mu = (
            _parse_minor_units(bj.get("effectiveBalance", {}))  # preferred
            or _parse_minor_units(bj.get("clearedBalance", {}))
            or 0
        )
        main = main_mu / 100.0

        # 2) Spaces / Goals
        spaces_url = _spaces_url(acct_type, uid)
        s = requests.get(spaces_url, headers=_hdr(token), timeout=6)
        s.raise_for_status()
        sj = s.json() or {}

        # API returns differ for personal vs business
        items = sj.get("spaces") or sj.get("savingsGoals") or sj.get("savingsGoalList") or []
        spaces_total = 0.0
        for it in items:
            # personal: space.balance.minorUnits
            # business: savingsGoal.totalSaved.minorUnits
            mu = (
                _parse_minor_units(it.get("balance", {}))
                or _parse_minor_units(it.get("totalSaved", {}))
                or 0
            )
            spaces_total += mu / 100.0

        total_acc = round(main + spaces_total, 2)
        if acc["name"].lower() == "efkaristo":
            out["company_total"] = total_acc
        else:
            out["personal_total"] = total_acc

    out["combined_total"] = round(out["company_total"] + out["personal_total"], 2)
    return out

# === Routes ========================================================================

@router.get("/snapshot")
def fss_snapshot():
    """
    Minimal daily FSS signal with live Starling override for total_balance.
    - Risk comes from fss_summary.buffer_pct (DB).
    - total_balance is overridden with live Starling (main + spaces) when available.
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            total_balance,
            buffer_pct,
            uc_safe,
            tee_covered,
            drawdown_available,
            suggested_pay,
            suggested_savings,
            created_at,
            week_start
        FROM fss_summary
        ORDER BY week_start DESC, created_at DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        # Even if DB is empty, try to return something useful via live totals.
        payload = {"available": False}
        try:
            live = _live_totals()
            payload.update(
                {
                    "available": True,
                    "total_balance": live["combined_total"],
                    "buffer_pct": 0.0,
                    "uc_safe": False,
                    "tee_covered": False,
                    "drawdown_available": 0.0,
                    "suggested_pay": 0.0,
                    "suggested_savings": 0.0,
                    "generated_at": datetime.now().isoformat(),
                    "risk_level": "med",  # neutral default without DB context
                    "source": "starling_live",
                }
            )
        except Exception:
            pass
        return payload

    d = dict(row)

    def f(key, default=0.0):
        v = d.get(key)
        try:
            return float(v) if v is not None else default
        except Exception:
            return default

    payload = {
        "available": True,
        "total_balance": f("total_balance"),  # will be live-overridden below if possible
        "buffer_pct": f("buffer_pct"),
        "uc_safe": bool(d.get("uc_safe", 0)),
        "tee_covered": bool(d.get("tee_covered", 0)),
        "drawdown_available": f("drawdown_available"),
        "suggested_pay": f("suggested_pay"),
        "suggested_savings": f("suggested_savings"),
        "generated_at": d.get("created_at") or d.get("week_start"),
    }
    bp = payload["buffer_pct"]
    payload["risk_level"] = "high" if bp < 10 else ("med" if bp < 25 else "low")

    # Override total_balance with live Starling combined (main + spaces)
    try:
        live = _live_totals()
        payload["total_balance"] = live["combined_total"]
        payload["live_company_total"] = live["company_total"]
        payload["live_personal_total"] = live["personal_total"]
        payload["source"] = "starling_live"
    except Exception:
        # Keep DB total if Starling call fails
        payload["source"] = "fss_summary"

    return payload


@router.get("/live-balance")
def fss_live_balance():
    """
    Optional: raw live totals endpoint for FSS page cards or debugging.
    """
    try:
        t = _live_totals()
        return {"timestamp": datetime.now().isoformat(), **t}
    except Exception as e:
        return {"error": str(e)}
        

@router.get("/summary/latest")
def get_latest_fss_summary():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM fss_summary
        ORDER BY week_start DESC, created_at DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return {"error": "No summary found"}

    summary = dict(row)
    # Convert int flags to bool
    summary["uc_safe"] = bool(summary.get("uc_safe", 0))
    summary["tee_covered"] = bool(summary.get("tee_covered", 0))

    # Format numeric fields
    for key in [
        "uc_entitlement",
        "uc_reduction",
        "household_income",
        "net_income",
        "net_expenses",
        "tee_paid",
        "total_balance",
        "buffer_pct",
        "drawdown_available",
        "suggested_pay",
        "suggested_savings",
    ]:
        if key in summary and summary[key] is not None:
            summary[key] = float(summary[key])

    return summary
