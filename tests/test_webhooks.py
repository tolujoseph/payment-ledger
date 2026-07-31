from ledger.webhooks import sign_payload, verify_signature, deliver_webhook


def test_signature_verifies_correctly():
    payload = b'{"event": "payment.posted"}'
    secret = "test-secret"
    signature = sign_payload(payload, secret)
    assert verify_signature(payload, signature, secret) is True


def test_signature_fails_with_wrong_secret():
    payload = b'{"event": "payment.posted"}'
    signature = sign_payload(payload, "correct-secret")
    assert verify_signature(payload, signature, "wrong-secret") is False


def test_delivery_succeeds_on_first_attempt():
    def fake_send(url, headers, body):
        return 200

    result = deliver_webhook(
        fake_send, "https://example.com/webhook",
        {"event": "payment.posted"}, secret="test-secret",
    )
    assert result.success is True
    assert result.attempts == 1


def test_delivery_retries_and_eventually_succeeds():
    call_count = {"count": 0}

    def flaky_send(url, headers, body):
        call_count["count"] += 1
        if call_count["count"] < 3:
            return 500
        return 200

    result = deliver_webhook(
        flaky_send, "https://example.com/webhook",
        {"event": "payment.posted"}, secret="test-secret",
        base_delay_seconds=0.01,  # keep the test fast
    )
    assert result.success is True
    assert result.attempts == 3


def test_delivery_fails_after_max_attempts():
    def always_failing_send(url, headers, body):
        return 500

    result = deliver_webhook(
        always_failing_send, "https://example.com/webhook",
        {"event": "payment.posted"}, secret="test-secret",
        max_attempts=2, base_delay_seconds=0.01,
    )
    assert result.success is False
    assert result.attempts == 2