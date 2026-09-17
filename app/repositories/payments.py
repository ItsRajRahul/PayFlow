from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Payment


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_transaction_id(self, transaction_id: str) -> Payment | None:
        return await self.session.scalar(
            select(Payment).where(Payment.transaction_id == transaction_id)
        )

    async def get_by_idempotency_key(self, key: str) -> Payment | None:
        return await self.session.scalar(select(Payment).where(Payment.idempotency_key == key))

    async def active_accounts(self, *account_ids: int) -> set[int]:
        rows = await self.session.scalars(
            select(Account.id).where(Account.id.in_(account_ids), Account.is_active.is_(True))
        )
        return set(rows.all())

    async def recent_sender_count(self, sender_id: int, seconds: int = 60) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=seconds)
        value = await self.session.scalar(
            select(func.count(Payment.id)).where(
                Payment.sender_id == sender_id, Payment.created_at >= cutoff
            )
        )
        return int(value or 0)

    async def list(self, limit: int, offset: int) -> tuple[list[Payment], int]:
        records = list(
            (
                await self.session.scalars(
                    select(Payment).order_by(Payment.created_at.desc()).limit(limit).offset(offset)
                )
            ).all()
        )
        total = int(await self.session.scalar(select(func.count(Payment.id))) or 0)
        return records, total
