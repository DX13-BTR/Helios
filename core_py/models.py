# core_py/models.py
from sqlalchemy import Column, String, Boolean, DateTime, Integer, ForeignKey, UniqueConstraint, Float
from sqlalchemy.orm import relationship
from core_py.db import Base

class Client(Base):
    __tablename__ = "clients"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)

class ClientEmail(Base):
    __tablename__ = "client_emails"
    id = Column(String, primary_key=True)
    client_id = Column(String, ForeignKey("clients.id"), nullable=False, index=True)
    email = Column(String, nullable=False, index=True)
    created_at = Column(DateTime)
    client = relationship("Client", backref="emails")
    __table_args__ = (
        UniqueConstraint("client_id", "email", name="uq_client_email"),
    )

class ClientDomain(Base):
    __tablename__ = "client_domains"
    id = Column(String, primary_key=True)
    client_id = Column(String, ForeignKey("clients.id"), nullable=False, index=True)
    domain = Column(String, nullable=False, index=True)
    wildcard = Column(Boolean, default=False)
    client = relationship("Client", backref="domains")
    __table_args__ = (
        UniqueConstraint("client_id", "domain", "wildcard", name="uq_client_domain_wild"),
    )

class AllowlistMeta(Base):
    __tablename__ = "allowlist_meta"
    id = Column(Integer, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime, nullable=True)

class TaskMeta(Base):
    __tablename__ = "task_meta"

    # ClickUp / external task id as the stable key
    task_id = Column(String, primary_key=True)

    # 'fixed_date' or 'flexible' (default)
    task_type = Column(String(20), default="flexible")

    # One of: 'vat_return', 'payroll', 'ct600', 'cs01', 'sa100', 'sa800', 'cis_return'
    deadline_type = Column(String(50))

    # Actual deadline date (UTC)
    fixed_date = Column(DateTime)

    # Whether you’ve time-blocked this into calendar
    calendar_blocked = Column(Boolean, default=False)

    # 'monthly', 'quarterly', 'annual', 'one_time'
    recurrence_pattern = Column(String(50))

    # Optional client code tag
    client_code = Column(String(20))

class TransactionEfkaristo(Base):
    __tablename__ = "transaction_efkaristo"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False)
    amount = Column(Float, nullable=False)
    direction = Column(String(10), nullable=False)  # "IN" or "OUT"
    counterparty = Column(String, nullable=True)
    source = Column(String, nullable=True)
    status = Column(String(20), nullable=True)


class TransactionPersonal(Base):
    __tablename__ = "transaction_personal"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False)
    amount = Column(Float, nullable=False)
    direction = Column(String(10), nullable=False)  # "IN" or "OUT"
    counterparty = Column(String, nullable=True)
    source = Column(String, nullable=True)
    status = Column(String(20), nullable=True)


class Balance(Base):
    __tablename__ = "balance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_name = Column(String, nullable=False)
    balance = Column(Float, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class FssSummary(Base):
    __tablename__ = "fss_summary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    week_ending = Column(DateTime, nullable=False)
    total_transactions = Column(Integer, nullable=False)
    total_incoming = Column(Float, nullable=False)
    total_outgoing = Column(Float, nullable=False)
    net_flow = Column(Float, nullable=False)
    closing_balance = Column(Float, nullable=False)
    created_at = Column(DateTime, nullable=False)
