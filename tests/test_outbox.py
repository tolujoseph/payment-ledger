from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

from ledger.models import Base, EntryType, OutboxEvent
from ledger.service import post_transaction
from ledger.outbox_worker import publish_pending_events


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_posting_transaction_creates_outbox_event(db):
    post_transaction(
        db, idempotency_key="tx-outbox-1", description="Test",
        entries=[
            ("customer_wallet", EntryType.CREDIT, Decimal("50")),
            ("company_cash", EntryType.DEBIT, Decimal("50")),
        ],
    )
    events = db.query(OutboxEvent).all()
    assert len(events) == 1
    assert events[0].published == 0


def test_publish_pending_events_marks_them_published(db):
    post_transaction(
        db, idempotency_key="tx-outbox-2", description="Test",
        entries=[
            ("customer_wallet", EntryType.CREDIT, Decimal("30")),
            ("company_cash", EntryType.DEBIT, Decimal("30")),
        ],
    )
    published_count = publish_pending_events(db)
    assert published_count == 1

    events = db.query(OutboxEvent).all()
    assert events[0].published == 1