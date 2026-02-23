"""
Shared RabbitMQ client for all ADMADC services.

Phase 2 additions:
- Dead-Letter Exchange (admadc.dlx) + per-queue DLQs
- Message-level retry with exponential backoff via x-retry-count header
- Proper NACK on handler failure (no silent ACK of errored messages)
- Persistent IdempotencyStore interface for cross-restart deduplication
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Awaitable

import aio_pika
from aio_pika import ExchangeType, Message
from aio_pika.abc import (
    AbstractConnection,
    AbstractChannel,
    AbstractExchange,
    AbstractIncomingMessage,
)

from shared.contracts.events import BaseEvent

logger = logging.getLogger(__name__)

EXCHANGE_NAME = "admadc.events"
DLX_EXCHANGE_NAME = "admadc.dlx"

CONNECT_MAX_RETRIES = 10
CONNECT_INITIAL_BACKOFF = 1.0

DEFAULT_MSG_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY_BASE = 1.0


class IdempotencyStore:
    """
    Pluggable deduplication store.

    Default implementation is in-memory (lost on container restart).
    Pass redis_url to use Redis for cross-restart persistence.
    """

    def __init__(self, redis_url: str | None = None, ttl: int = 86400) -> None:
        self._memory: set[str] = set()
        self._redis = None
        self._ttl = ttl

        if redis_url:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(redis_url, decode_responses=True)
            except ImportError:
                logger.warning("redis package not available; falling back to in-memory idempotency")

    async def is_seen(self, key: str) -> bool:
        if self._redis:
            return bool(await self._redis.exists(f"idem:msg:{key}"))
        return key in self._memory

    async def mark_seen(self, key: str) -> None:
        if self._redis:
            await self._redis.set(f"idem:msg:{key}", "1", ex=self._ttl)
        else:
            self._memory.add(key)


class EventBus:
    """
    Thin abstraction over aio-pika for publishing and consuming BaseEvents.

    Design principles (Phase 2):
    - DLX declared alongside the main exchange on connect()
    - Each subscribed queue gets a paired DLQ (dlq.<queue_name>) on admadc.dlx
    - Failed messages are NACK'd (requeue=False) and manually re-published
      on the main exchange with an incremented x-retry-count header
    - After max_retries exhausted, message is routed to the DLQ for manual review
    - Re-publishing manually (vs RabbitMQ native DLX requeue) gives us explicit
      backoff control and avoids infinite requeue loops
    """

    def __init__(self, rabbitmq_url: str) -> None:
        self._url = rabbitmq_url
        self._connection: AbstractConnection | None = None
        self._channel: AbstractChannel | None = None
        self._exchange: AbstractExchange | None = None
        self._dlx_exchange: AbstractExchange | None = None

    async def connect(self) -> None:
        backoff = CONNECT_INITIAL_BACKOFF
        for attempt in range(1, CONNECT_MAX_RETRIES + 1):
            try:
                self._connection = await aio_pika.connect_robust(self._url)
                self._channel = await self._connection.channel()
                await self._channel.set_qos(prefetch_count=1)

                self._exchange = await self._channel.declare_exchange(
                    EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
                )
                self._dlx_exchange = await self._channel.declare_exchange(
                    DLX_EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
                )
                logger.info("Connected to RabbitMQ (attempt %d)", attempt)
                return
            except Exception:
                if attempt == CONNECT_MAX_RETRIES:
                    logger.error(
                        "Failed to connect to RabbitMQ after %d attempts",
                        CONNECT_MAX_RETRIES,
                    )
                    raise
                logger.warning(
                    "RabbitMQ connection attempt %d failed, retrying in %.1fs",
                    attempt,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    async def close(self) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("RabbitMQ connection closed")

    async def publish(self, event: BaseEvent) -> None:
        if not self._exchange:
            raise RuntimeError("EventBus not connected. Call connect() first.")

        body = event.model_dump_json().encode()
        message = Message(
            body=body,
            content_type="application/json",
            message_id=event.event_id,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            headers={
                "idempotency_key": event.idempotency_key,
                "x-retry-count": 0,
            },
        )
        routing_key = event.event_type.value
        await self._exchange.publish(message, routing_key=routing_key)
        logger.debug("Published %s [%s]", routing_key, event.event_id[:8])

    async def subscribe(
        self,
        queue_name: str,
        routing_keys: list[str],
        handler: Callable[[BaseEvent], Awaitable[None]],
        idempotency_store: IdempotencyStore | None = None,
        max_retries: int = DEFAULT_MSG_MAX_RETRIES,
        retry_delay_base: float = DEFAULT_RETRY_DELAY_BASE,
    ) -> None:
        """
        Declare a durable queue + paired DLQ, bind them, and start consuming.

        Args:
            queue_name: Unique name for this consumer's queue.
            routing_keys: Event types to receive (topic patterns allowed).
            handler: Async callback invoked with each deserialized BaseEvent.
            idempotency_store: Deduplication backend (in-memory default).
            max_retries: Max delivery attempts before message goes to DLQ.
            retry_delay_base: Base for exponential backoff (actual = base * 2^n).
        """
        if not self._channel or not self._exchange or not self._dlx_exchange:
            raise RuntimeError("EventBus not connected. Call connect() first.")

        if idempotency_store is None:
            idempotency_store = IdempotencyStore()

        dlq_name = f"dlq.{queue_name}"
        dlq = await self._channel.declare_queue(dlq_name, durable=True)
        for rk in routing_keys:
            await dlq.bind(self._dlx_exchange, routing_key=rk)

        queue = await self._channel.declare_queue(queue_name, durable=True)
        for rk in routing_keys:
            await queue.bind(self._exchange, routing_key=rk)
            logger.info("Queue %s bound to routing key %s", queue_name, rk)

        main_exchange = self._exchange
        dlx_exchange = self._dlx_exchange

        async def _republish_for_retry(
            original: AbstractIncomingMessage, retry_count: int
        ) -> None:
            headers = dict(original.headers or {})
            headers["x-retry-count"] = retry_count
            retry_msg = Message(
                body=original.body,
                content_type=original.content_type or "application/json",
                message_id=original.message_id,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                headers=headers,
            )
            await main_exchange.publish(retry_msg, routing_key=original.routing_key or "")

        async def _route_to_dlq(original: AbstractIncomingMessage) -> None:
            headers = dict(original.headers or {})
            headers["x-final-failure"] = "true"
            dlq_msg = Message(
                body=original.body,
                content_type=original.content_type or "application/json",
                message_id=original.message_id,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                headers=headers,
            )
            await dlx_exchange.publish(dlq_msg, routing_key=original.routing_key or "unknown")

        async def _on_message(message: AbstractIncomingMessage) -> None:
            retry_count = int((message.headers or {}).get("x-retry-count", 0))
            try:
                async with message.process(requeue=False, ignore_processed=True):
                    data = json.loads(message.body.decode())
                    event = BaseEvent.model_validate(data)
                    # Use retry-scoped key so republished retries are not skipped as duplicates
                    effective_key = (
                        event.idempotency_key
                        if retry_count == 0
                        else f"{event.idempotency_key}:retry:{retry_count}"
                    )
                    if await idempotency_store.is_seen(effective_key):
                        logger.info(
                            "Skipping duplicate event %s [idem=%s]",
                            event.event_id[:8],
                            effective_key[:20],
                        )
                        return

                    await idempotency_store.mark_seen(effective_key)
                    await handler(event)

            except Exception:
                logger.exception(
                    "Error processing message %s (attempt %d/%d)",
                    message.message_id,
                    retry_count + 1,
                    max_retries,
                )
                if retry_count < max_retries - 1:
                    delay = min(retry_delay_base * (2 ** retry_count), 32.0)
                    logger.info(
                        "Retrying message %s in %.1fs (attempt %d)",
                        message.message_id,
                        delay,
                        retry_count + 1,
                    )
                    await asyncio.sleep(delay)
                    await _republish_for_retry(message, retry_count + 1)
                else:
                    logger.error(
                        "Message %s exhausted %d retries -> DLQ %s",
                        message.message_id,
                        max_retries,
                        dlq_name,
                    )
                    await _route_to_dlq(message)

        await queue.consume(_on_message)
        logger.info(
            "Consuming from queue %s (max_retries=%d, dlq=%s)",
            queue_name,
            max_retries,
            dlq_name,
        )
