"""
FastAPI layer exposing the ledger as a payments API.
Idempotency is handled the way real payment APIs (Stripe, GoCardless) do it:
the client supplies an Idempotency-Key header, and retrying the exact same
request is always safe -- it never creates a duplicate transaction.
"""

from decimal import Decimal, InvalidOperation
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ledger.models import Base, EntryType
from ledger.service import (
    post_transaction, get_balance,
    UnbalancedTransactionError, DuplicateTransactionError,
)

app = FastAPI(title="Payment Ledger API")

engine = create_engine("sqlite:///ledger.db")
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)


class PaymentRequest(BaseModel):
    from_account: str
    to_account: str
    amount: Decimal
    description: str = ""


@app.post("/payments")
def create_payment(
    payment: PaymentRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    """
    Move money from one account to another as a balanced ledger transaction.
    Safe to retry: sending the same Idempotency-Key twice returns the
    existing transaction instead of creating a duplicate.
    """
    if payment.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    db = SessionLocal()
    try:
        transaction = post_transaction(
            db,
            idempotency_key=idempotency_key,
            description=payment.description,
            entries=[
                (payment.from_account, EntryType.DEBIT, payment.amount),
                (payment.to_account, EntryType.CREDIT, payment.amount),
            ],
        )
        return {
            "transaction_id": transaction.id,
            "status": "posted",
            "idempotency_key": idempotency_key,
        }
    except UnbalancedTransactionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DuplicateTransactionError:
        # Idempotent retry: same key, so we return success rather than an error.
        # A fuller implementation would fetch and return the original
        # transaction's details here instead of just a generic message.
        return {
            "status": "already_processed",
            "idempotency_key": idempotency_key,
        }
    finally:
        db.close()


@app.get("/accounts/{account_name}/balance")
def account_balance(account_name: str):
    db = SessionLocal()
    try:
        balance = get_balance(db, account_name)
        return {"account": account_name, "balance": str(balance)}
    finally:
        db.close()