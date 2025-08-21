# core_py/modules/fss/fss_summary.py

from datetime import datetime
from sqlalchemy import func
from core_py.db.database import get_session
from core_py.models import TransactionEfkaristo, TransactionPersonal, Balance, FssSummary

def calculate_fss_summary():
    """
    Calculate weekly FSS summary from transactions and balances,
    and insert a row into fss_summary (Postgres).
    """

    with get_session() as session:
        # Fetch transactions
        efkaristo_tx = session.query(
            TransactionEfkaristo.date,
            TransactionEfkaristo.amount,
            TransactionEfkaristo.direction,
            TransactionEfkaristo.counterparty,
            TransactionEfkaristo.source,
            TransactionEfkaristo.status
        ).all()

        personal_tx = session.query(
            TransactionPersonal.date,
            TransactionPersonal.amount,
            TransactionPersonal.direction,
            TransactionPersonal.counterparty,
            TransactionPersonal.source,
            TransactionPersonal.status
        ).all()

        # Compute total balances
        total_balance = session.query(func.sum(Balance.balance)).scalar() or 0

        # Prepare summary fields
        total_transactions = len(efkaristo_tx) + len(personal_tx)
        total_incoming = sum(
            t.amount for t in efkaristo_tx + personal_tx if t.direction == "IN"
        )
        total_outgoing = sum(
            t.amount for t in efkaristo_tx + personal_tx if t.direction == "OUT"
        )

        # Insert into fss_summary
        summary_row = FssSummary(
            week_ending=datetime.utcnow().date(),
            total_transactions=total_transactions,
            total_incoming=total_incoming,
            total_outgoing=total_outgoing,
            net_flow=total_incoming - total_outgoing,
            closing_balance=total_balance,
            created_at=datetime.utcnow(),
        )

        session.add(summary_row)
        session.commit()

        return summary_row
