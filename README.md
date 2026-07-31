# Payment Ledger

A backend payment processing system built around a proper double-entry
ledger — the core abstraction behind real payment infrastructure
(Stripe, GoCardless, Wise, Ramp all use this pattern).

## Why this exists

Most simple "payments" demos just update a balance field on an account.
Real payment systems don't do that, because a single balance field can't
tell you *what happened* or prove it's still correct — it can silently
drift, get corrupted by a race condition, or be impossible to audit
after the fact. This project builds the actual pattern real fintechs use
instead: every change is an immutable, balanced ledger entry, and a
balance is always *derived*, never stored directly.

## Architecture
POST /payments
↓
Validate request
↓
post_transaction()
├─ Check debits == credits (reject if not)
├─ Check idempotency_key not already used (reject if it is)
├─ Write LedgerEntry rows (never update a balance directly)
└─ Write OutboxEvent row ─┐ (same DB transaction —
↓ │ both succeed or both fail)
db.commit() ←─────────────┘
↓
outbox_worker (separate process)
↓
publish_pending_events() → webhooks.deliver_webhook()
(signed, retried with backoff)

reconciliation.reconcile() — separately compares the ledger
against a mock external bank statement feed, on demand

## The five pieces

1. **Double-entry ledger** (`ledger/models.py`, `ledger/service.py`) —
   every transaction creates balanced debit/credit entries. Balances are
   always derived by summing entries, never stored or updated directly.
2. **Idempotent payments API** (`api/main.py`) — a `POST /payments`
   endpoint using an `Idempotency-Key` header, matching how Stripe and
   GoCardless structure this. Retrying the same request is always safe.
3. **Outbox pattern** (`ledger/outbox_worker.py`) — the ledger write and
   the "event to publish" are written in the *same* database transaction,
   so a crash between "update the ledger" and "notify other systems" can
   never lose an event.
4. **Reconciliation** (`ledger/reconciliation.py`) — compares the ledger
   against a mock external statement feed, distinguishing three separate
   failure modes: missing in ledger, missing in statement, and amount
   mismatches — each needs a different operational response.
5. **Signed webhooks with retries** (`ledger/webhooks.py`) — HMAC-SHA256
   signed payloads (verified with constant-time comparison to prevent
   timing attacks), delivered with exponential backoff retries.

## Key design decisions

- **Amounts are always positive; direction is expressed via `entry_type`**,
  not sign — avoids a whole class of sign-flip bugs.
- **Idempotency is enforced at the database level** (a unique constraint),
  not just checked in application code, so it holds even under race
  conditions between near-simultaneous identical requests.
- **`send_request` is injected into `deliver_webhook`** rather than
  hardcoded, so webhook delivery is fully testable without real network
  calls.
- **Balances are always derived, never cached** — the honest tradeoff is
  that this is slower at scale; a production system would periodically
  snapshot balances and reconcile them against the derived value, rather
  than deriving from scratch on every read.

## Tests

14 tests across ledger correctness, outbox atomicity, reconciliation
matching logic, and webhook signing/delivery/retries:

```bash
pytest tests/ -v
```

Current result: **14/14 passing**.

## Running it

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install sqlalchemy fastapi "uvicorn[standard]" pytest
uvicorn api.main:app --reload
```

Then, in another terminal:

```bash
curl -X POST http://localhost:8000/payments \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: payment-001" \
  -d '{"from_account": "company_cash", "to_account": "customer_wallet", "amount": 100.00, "description": "Test payment"}'
```

Send the same command again to see idempotent retry behavior — the
second call returns `"status": "already_processed"` instead of creating
a duplicate transaction.

## What I'd build next

- Postgres instead of SQLite, with `SELECT FOR UPDATE` or `SERIALIZABLE`
  isolation to handle real concurrent writes correctly
- A scheduled job runner (e.g. APScheduler or a cron-triggered Lambda)
  for the outbox worker and reconciliation, instead of manual invocation
- Balance snapshotting for performance at scale, reconciled periodically
  against the fully-derived value
- Real HTTP delivery in the webhook worker (currently injected for
  testability, would use `httpx` or `requests` in production)
  