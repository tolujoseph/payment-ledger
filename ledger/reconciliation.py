"""
Reconciliation job: compares the internal ledger against a mock external
bank statement feed and flags mismatches. This is the real-world check
that catches things like a payment your system thinks succeeded but the
bank never actually processed, or a bank-side charge your ledger never
recorded.
"""

from dataclasses import dataclass
from decimal import Decimal
from sqlalchemy.orm import Session

from ledger.models import Transaction


@dataclass
class ExternalStatementLine:
    """One line from a mock external bank statement feed."""
    reference: str  # matches Transaction.idempotency_key in a real integration
    amount: Decimal


@dataclass
class ReconciliationResult:
    matched: list[str]
    missing_in_ledger: list[str]      # bank saw it, our ledger doesn't have it
    missing_in_statement: list[str]   # our ledger has it, bank feed doesn't
    amount_mismatches: list[tuple[str, Decimal, Decimal]]  # (ref, ledger_amt, bank_amt)


def reconcile(db: Session, statement_lines: list[ExternalStatementLine]) -> ReconciliationResult:
    """
    Compare ledger transactions against an external statement feed by
    matching on idempotency_key (standing in for a bank reference number).
    """
    ledger_transactions = {
        t.idempotency_key: t for t in db.query(Transaction).all()
    }
    statement_by_ref = {line.reference: line for line in statement_lines}

    matched = []
    missing_in_ledger = []
    missing_in_statement = []
    amount_mismatches = []

    for ref, statement_line in statement_by_ref.items():
        if ref not in ledger_transactions:
            missing_in_ledger.append(ref)
            continue

        transaction = ledger_transactions[ref]
        ledger_amount = sum(e.amount for e in transaction.entries) / 2  # debits==credits, so /2 gives the actual amount

        if ledger_amount != statement_line.amount:
            amount_mismatches.append((ref, ledger_amount, statement_line.amount))
        else:
            matched.append(ref)

    for ref in ledger_transactions:
        if ref not in statement_by_ref:
            missing_in_statement.append(ref)

    return ReconciliationResult(
        matched=matched,
        missing_in_ledger=missing_in_ledger,
        missing_in_statement=missing_in_statement,
        amount_mismatches=amount_mismatches,
    )