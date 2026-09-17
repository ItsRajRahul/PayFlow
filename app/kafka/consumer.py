import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.database import SessionFactory
from app.logging import configure_logging
from app.models import Notification

logger = logging.getLogger(__name__)


async def store_notification(event: dict[str, object]) -> None:
    if event.get("event_type") != "PAYMENT_COMPLETED":
        return
    transaction_id = str(event["transaction_id"])
    message = (
        f"INR {event['amount']} successfully sent from user {event['sender_id']} "
        f"to user {event['receiver_id']}"
    )
    async with SessionFactory() as session:
        session.add(Notification(transaction_id=transaction_id, message=message))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.info("duplicate_notification_ignored", extra={"transaction_id": transaction_id})
            return
    logger.info("notification_recorded", extra={"transaction_id": transaction_id})


async def consume() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    consumer = AIOKafkaConsumer(
        settings.kafka_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        value_deserializer=lambda raw: json.loads(raw.decode()),
        enable_auto_commit=False,
    )
    await consumer.start()
    try:
        async for message in consumer:
            await store_notification(message.value)
            await consumer.commit()
    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(consume())
