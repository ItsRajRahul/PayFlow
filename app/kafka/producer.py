import asyncio
import json
import logging
from datetime import UTC, datetime

from aiokafka import AIOKafkaProducer
from sqlalchemy import select

from app.config import Settings
from app.database import SessionFactory
from app.models import OutboxEvent, PaymentAudit

logger = logging.getLogger(__name__)


class OutboxPublisher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.producer: AIOKafkaProducer | None = None
        self.task: asyncio.Task[None] | None = None
        self.connected = False

    async def start(self) -> None:
        await self._connect()
        self.task = asyncio.create_task(self._run(), name="payflow-outbox-publisher")

    async def _connect(self) -> None:
        if self.producer is not None:
            return
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            value_serializer=lambda value: json.dumps(value).encode(),
            enable_idempotence=True,
        )
        try:
            await asyncio.wait_for(self.producer.start(), timeout=5)
        except Exception:
            logger.warning("kafka_unavailable_outbox_will_retry", exc_info=True)
            await self.producer.stop()
            self.producer = None
            return
        self.connected = True

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        if self.producer:
            await self.producer.stop()
        self.connected = False

    async def _run(self) -> None:
        while True:
            delay = self.settings.outbox_poll_interval_seconds
            try:
                if self.producer is None:
                    await self._connect()
                    if self.producer is None:
                        delay = self.settings.kafka_reconnect_interval_seconds
                else:
                    await self.publish_batch()
            except Exception:
                logger.exception("outbox_publish_failed")
                self.connected = False
                delay = self.settings.kafka_reconnect_interval_seconds
            await asyncio.sleep(delay)

    async def publish_batch(self) -> int:
        if not self.producer:
            return 0
        async with SessionFactory() as session:
            events = list(
                (
                    await session.scalars(
                        select(OutboxEvent)
                        .where(OutboxEvent.published_at.is_(None))
                        .order_by(OutboxEvent.created_at)
                        .limit(100)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            for event in events:
                await self.producer.send_and_wait(
                    self.settings.kafka_topic,
                    value=event.payload,
                    key=event.aggregate_id.encode(),
                )
                event.published_at = datetime.now(UTC)
                session.add(
                    PaymentAudit(
                        transaction_id=event.aggregate_id,
                        event="EVENT_PUBLISHED",
                        details={"event_type": event.event_type},
                    )
                )
                logger.info(
                    "kafka_event_published",
                    extra={"transaction_id": event.aggregate_id, "event_type": event.event_type},
                )
            await session.commit()
            self.connected = True
            return len(events)
