"""Claves de deduplicación del consumidor RabbitMQ."""

from __future__ import annotations

from shared.contracts.events import BaseEvent, EventType
from shared.utils.rabbitmq import consumer_idempotency_key


def _evt(key: str) -> BaseEvent:
    return BaseEvent(
        event_type=EventType.QA_PASSED,
        producer="t",
        payload={"x": 1},
        idempotency_key=key,
    )


def test_key_primary() -> None:
    e = _evt("abc")
    assert consumer_idempotency_key(e, 0) == "abc"
    assert consumer_idempotency_key(e, -1) == "abc"


def test_key_retry() -> None:
    e = _evt("abc")
    assert consumer_idempotency_key(e, 1) == "abc:retry:1"
    assert consumer_idempotency_key(e, 2) == "abc:retry:2"
