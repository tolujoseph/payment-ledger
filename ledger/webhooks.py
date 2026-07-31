"""
Signed webhook delivery with retries.

Every webhook payload is signed with HMAC-SHA256 so the receiver can verify
it genuinely came from us and wasn't tampered with in transit -- the same
pattern Stripe, GoCardless, and most payment providers use for webhooks.

Delivery retries with exponential backoff, since receiving servers are
often temporarily down or slow, and a single failed attempt shouldn't mean
the event is lost.
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass


@dataclass
class WebhookDeliveryResult:
    success: bool
    attempts: int
    last_status_code: int | None
    last_error: str | None


def sign_payload(payload: bytes, secret: str) -> str:
    """
    HMAC-SHA256 signature of the payload using a shared secret.
    The receiver recomputes this signature on their end and compares it --
    if it doesn't match, they reject the webhook as potentially forged.
    """
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Constant-time comparison to prevent timing attacks -- using `==` to
    compare signatures can leak information about how many leading
    characters matched, based on how long the comparison takes.
    """
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, signature)


def deliver_webhook(
    send_request,
    url: str,
    event_data: dict,
    secret: str,
    max_attempts: int = 3,
    base_delay_seconds: float = 1.0,
) -> WebhookDeliveryResult:
    """
    Deliver a signed webhook with exponential backoff retries.

    send_request: a function(url, headers, body) -> status_code, injected
    so this function is testable without making real HTTP calls.
    """
    payload = json.dumps(event_data).encode()
    signature = sign_payload(payload, secret)
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
    }

    last_error = None
    last_status_code = None

    for attempt in range(1, max_attempts + 1):
        try:
            status_code = send_request(url, headers, payload)
            last_status_code = status_code

            if 200 <= status_code < 300:
                return WebhookDeliveryResult(
                    success=True,
                    attempts=attempt,
                    last_status_code=status_code,
                    last_error=None,
                )
            last_error = f"Received status code {status_code}"

        except Exception as e:
            last_error = str(e)

        if attempt < max_attempts:
            delay = base_delay_seconds * (2 ** (attempt - 1))  # 1s, 2s, 4s, ...
            time.sleep(delay)

    return WebhookDeliveryResult(
        success=False,
        attempts=max_attempts,
        last_status_code=last_status_code,
        last_error=last_error,
    )