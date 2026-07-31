"""
Double-entry ledger models. Every financial event creates two balanced
entries (a debit and a credit) rather than a single balance update.
This is the core abstraction behind real payment systems: it makes every
change auditable and mathematically self-checking (debits always equal
credits across the system).
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import declarative_base, relationship
import enum

Base = declarative_base()


class EntryType(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    entries = relationship("LedgerEntry", back_populates="account")


class Transaction(Base):
    """
    A Transaction groups the balanced set of entries for one financial
    event (e.g. one payment). It should always have entries that sum to
    zero across debits and credits.
    """
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    idempotency_key = Column(String, unique=True, nullable=False)
    description = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    entries = relationship("LedgerEntry", back_populates="transaction")


class LedgerEntry(Base):
    """
    A single debit or credit against one account, belonging to one
    transaction. Never update a balance directly — only ever insert entries.
    """
    __tablename__ = "ledger_entries"

    id = Column(Integer, primary_key=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    entry_type = Column(SAEnum(EntryType), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)

    transaction = relationship("Transaction", back_populates="entries")
    account = relationship("Account", back_populates="entries")