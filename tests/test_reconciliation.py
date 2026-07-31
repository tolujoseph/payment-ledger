from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

from ledger.models import Base, EntryType
from ledger.service import post_transaction
from ledger.reconciliation import reconcile, ExternalStatementLine


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_matched_transaction(db):
    post_transaction(
        db, idempotency_key="ref-1", description="Matched payment",
        entries=[
            ("customer_wallet", EntryType.CREDIT, Decimal("100")),
            ("company_cash", EntryType.DEBIT, Decimal("100")),
        ],
    )
    result = reconcile(db, [ExternalStatementLine(reference="ref-1", amount=Decimal("100"))])
    assert result.matched == ["ref-1"]
    assert result.missing_in_ledger == []
    assert result.missing_in_statement == []
    assert result.amount_mismatches == []


def test_missing_in_ledger(db):
    result = reconcile(db, [ExternalStatementLine(reference="ref-ghost", amount=Decimal("50"))])
    assert result.missing_in_ledger == ["ref-ghost"]


def test_missing_in_statement(db):
    post_transaction(
        db, idempotency_key="ref-2", description="Unreported payment",
        entries=[
            ("customer_wallet", EntryType.CREDIT, Decimal("75")),
            ("company_cash", EntryType.DEBIT, Decimal("75")),
        ],
    )
    result = reconcile(db, [])
    assert result.missing_in_statement == ["ref-2"]


def test_amount_mismatch(db):
    post_transaction(
        db, idempotency_key="ref-3", description="Partial refund scenario",
        entries=[
            ("customer_wallet", EntryType.CREDIT, Decimal("200")),
            ("company_cash", EntryType.DEBIT, Decimal("200")),
        ],
    )
    result = reconcile(db, [ExternalStatementLine(reference="ref-3", amount=Decimal("180"))])
    assert result.amount_mismatches == [("ref-3", Decimal("200"), Decimal("180"))]