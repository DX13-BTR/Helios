# core_py/routes/fss_routes.py
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from core_py.db.session import get_session

router = APIRouter(prefix="/fss", tags=["fss"])

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def _to_utc_iso(ts: Optional[Any]) -> Optional[str]:
    if ts is None:
        return None
    # Accept raw epoch (s or ms) or ISO strings; normalize to ISO UTC
    try:
        if isinstance(ts, (int, float)) or str(ts).isdigit():
            v = int(float(ts))
            if v < 10**11:  # seconds → ms
                v *= 1000
            return datetime.fromtimestamp(v / 1000.0, tz=timezone.utc).isoformat()
        s = str(ts)
        if "T" in s or "-" in s:
            # already ISO-ish
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    return None


def _safe_query_list(sql: str, params: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    try:
        with get_session() as s:
            rows = s.execute(text(sql), params or {}).mappings().all()
            return [dict(r) for r in rows]
    except Exception as e:
        # If table doesn’t exist yet or any other issue, return empty
        print(f"⚠️ _safe_query_list failed: {e}")
        return []


def _safe_query_one(sql: str, params: Dict[str, Any] | None = None) -> Optional[Dict[str, Any]]:
    try:
        with get_session() as s:
            row = s.execute(text(sql), params or {}).mappings().fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"⚠️ _safe_query_one failed: {e}")
        return None


# --------------------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------------------

@router.get("/snapshot")
def get_snapshot():
    """
    Returns a compact snapshot for the FSS (Financial Snapshot & Strategy) view.
    Pulls latest summary + advice, and a quick totals breakdown from balances.
    Tables are expected in the `legacy` schema (per your import).
    """
    # Latest summary
    summary = _safe_query_one(
        """
        SELECT
          id,
          period_start,
          period_end,
          total_cash,
          projected_cash_30d,
          projected_cash_60d,
          runway_days,
          created_at
        FROM legacy.fss_summary
        ORDER BY created_at DESC
        LIMIT 1
        """
    ) or {}

    # Latest advice message (if present)
    advice = _safe_query_one(
        """
        SELECT
          id,
          summary_id,
          kind,
          message,
          created_at
        FROM legacy.fss_advice
        ORDER BY created_at DESC
        LIMIT 1
        """
    ) or {}

    # Quick live total from balances (distinct-on by account)
    balances = _safe_query_list(
        """
        SELECT DISTINCT ON (account_id)
          account_id,
          COALESCE(account_name, account_id) AS account_name,
          balance,
          as_of
        FROM legacy.balances
        ORDER BY account_id, as_of DESC
        """
    )

    total_live = sum([float(b.get("balance") or 0) for b in balances]) if balances else 0.0

    # Normalize some timestamps
    for k in ("period_start", "period_end", "created_at"):
        if k in summary:
            summary[k] = _to_utc_iso(summary[k])
    if "created_at" in advice:
        advice["created_at"] = _to_utc_iso(advice["created_at"])
    for b in balances:
        b["as_of"] = _to_utc_iso(b.get("as_of"))

    return {
        "summary": summary,
        "advice": advice,
        "balances": balances,
        "totals": {
            "live_cash": total_live,
            "accounts": len(balances),
        },
    }


@router.get("/live-balance")
def get_live_balance():
    """
    Returns latest balance per account (DISTINCT ON pattern) and a grand total.
    """
    rows = _safe_query_list(
        """
        SELECT DISTINCT ON (account_id)
          account_id,
          COALESCE(account_name, account_id) AS account_name,
          currency,
          balance,
          as_of
        FROM legacy.balances
        ORDER BY account_id, as_of DESC
        """
    )
    for r in rows:
        r["as_of"] = _to_utc_iso(r.get("as_of"))
    total = sum([float(r.get("balance") or 0) for r in rows]) if rows else 0.0
    return {"accounts": rows, "total": total}


@router.get("/summary/latest")
def get_latest_summary():
    """
    Returns the latest row from fss_summary plus any advice rows tied to it.
    """
    summary = _safe_query_one(
        """
        SELECT
          id,
          period_start,
          period_end,
          total_cash,
          projected_cash_30d,
          projected_cash_60d,
          runway_days,
          created_at
        FROM legacy.fss_summary
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    if not summary:
        return {"summary": None, "advice": []}

    # Normalize timestamps
    for k in ("period_start", "period_end", "created_at"):
        summary[k] = _to_utc_iso(summary.get(k))

    advice = _safe_query_list(
        """
        SELECT
          id,
          kind,
          message,
          created_at
        FROM legacy.fss_advice
        WHERE summary_id = :sid
        ORDER BY created_at DESC
        """,
        {"sid": summary["id"]},
    )
    for a in advice:
        a["created_at"] = _to_utc_iso(a.get("created_at"))

    return {"summary": summary, "advice": advice}
