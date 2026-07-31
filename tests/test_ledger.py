import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ledger.models import Base, EntryType
from ledger.service import (
    post_transaction, get_balance,
    UnbalancedTransactionError, DuplicateTransactionError,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_balanced_transaction_posts_successfully(db):
    post_transaction(
        db, idempotency_key="tx-1", description="Test payment",
        entries=[
            ("customer_wallet", EntryType.CREDIT, 100),
            ("company_cash", EntryType.DEBIT, 100),
        ],
    )
    assert get_balance(db, "customer_wallet") == 100
    assert get_balance(db, "company_cash") == -100


def test_unbalanced_transaction_is_rejected(db):
    with pytest.raises(UnbalancedTransactionError):
        post_transaction(
            db, idempotency_key="tx-2", description="Bad payment",
            entries=[
                ("customer_wallet", EntryType.CREDIT, 100),
                ("company_cash", EntryType.DEBIT, 90),
            ],
        )


def test_duplicate_idempotency_key_is_rejected(db):
    post_transaction(
        db, idempotency_key="tx-3", description="First attempt",
        entries=[
            ("customer_wallet", EntryType.CREDIT, 50),
            ("company_cash", EntryType.DEBIT, 50),
        ],
    )
    with pytest.raises(DuplicateTransactionError):
        post_transaction(
            db, idempotency_key="tx-3", description="Retried attempt",
            entries=[
                ("customer_wallet", EntryType.CREDIT, 50),
                ("company_cash", EntryType.DEBIT, 50),
            ],
        )