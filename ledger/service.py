"""
Functions for posting balanced transactions to the ledger.
This is where the double-entry rule is actually enforced: a transaction
is only ever created with a matching set of debit and credit entries
that sum to zero. There is no function anywhere that lets you update
an account balance directly — balances are always derived from entries.
"""

import json
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ledger.models import Account, Transaction, LedgerEntry, EntryType, OutboxEvent


class UnbalancedTransactionError(Exception):
    """Raised when the sum of debits does not equal the sum of credits."""
    pass


class DuplicateTransactionError(Exception):
    """Raised when an idempotency key has already been used."""
    pass


def post_transaction(
    db: Session,
    idempotency_key: str,
    description: str,
    entries: list[tuple[str, EntryType, Decimal]],
) -> Transaction:
    """
    Post a balanced transaction to the ledger.

    entries: list of (account_name, entry_type, amount) tuples.
    Every amount must be positive; direction is expressed via entry_type,
    not sign, which avoids a whole class of sign-flip bugs.

    Raises UnbalancedTransactionError if debits != credits.
    Raises DuplicateTransactionError if idempotency_key was already used
    (this is what makes retried API calls safe -- a client can safely
    retry a payment request without risking a double-charge).
    """
    total_debits = sum(amt for _, t, amt in entries if t == EntryType.DEBIT)
    total_credits = sum(amt for _, t, amt in entries if t == EntryType.CREDIT)

    if total_debits != total_credits:
        raise UnbalancedTransactionError(
            f"Debits ({total_debits}) != Credits ({total_credits})"
        )

    transaction = Transaction(idempotency_key=idempotency_key, description=description)
    db.add(transaction)

    try:
        db.flush()  # assigns transaction.id without committing yet
    except IntegrityError:
        db.rollback()
        raise DuplicateTransactionError(
            f"Transaction with idempotency_key '{idempotency_key}' already exists"
        )

    for account_name, entry_type, amount in entries:
        account = db.query(Account).filter_by(name=account_name).first()
        if account is None:
            account = Account(name=account_name)
            db.add(account)
            db.flush()

        db.add(LedgerEntry(
            transaction_id=transaction.id,
            account_id=account.id,
            entry_type=entry_type,
            amount=amount,
        ))

    db.add(OutboxEvent(
        transaction_id=transaction.id,
        event_type="payment.posted",
        payload=json.dumps({
            "transaction_id": transaction.id,
            "idempotency_key": idempotency_key,
            "description": description,
        }),
    ))

    db.commit()
    return transaction


def get_balance(db: Session, account_name: str) -> Decimal:
    """
    Derive an account's balance by summing its entries -- never stored
    directly. Credits increase balance, debits decrease it (standard
    accounting convention for a liability/customer-owed account).
    """
    account = db.query(Account).filter_by(name=account_name).first()
    if account is None:
        return Decimal("0")

    total = Decimal("0")
    for entry in account.entries:
        if entry.entry_type == EntryType.CREDIT:
            total += entry.amount
        else:
            total -= entry.amount
    return total