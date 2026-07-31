"""
Outbox worker: polls for unpublished events and 'publishes' them.
In a real system this would push to Kafka, SQS, or call webhooks --
here it just prints, to keep the demo runnable without external infra.
"""

from sqlalchemy.orm import Session
from ledger.models import OutboxEvent


def publish_pending_events(db: Session) -> int:
    """
    Find all unpublished events, 'publish' them, and mark as published.
    Returns the number of events published.
    """
    pending = db.query(OutboxEvent).filter_by(published=0).all()

    for event in pending:
        # Real implementation: push to a queue, call a webhook, etc.
        print(f"Publishing event: {event.event_type} — {event.payload}")
        event.published = 1

    db.commit()
    return len(pending)