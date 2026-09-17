import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import DomainError
from app.models import OutboxEvent, Payment, PaymentAudit, PaymentStatus, RiskLevel
from app.repositories.payments import PaymentRepository
from app.schemas import PaymentCreate
from app.services.risk import assess_risk

logger = logging.getLogger(__name__)


def request_fingerprint(request: PaymentCreate) -> str:
    canonical = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = PaymentRepository(session)

    async def create(self, request: PaymentCreate, idempotency_key: str) -> tuple[Payment, bool]:
        fingerprint = request_fingerprint(request)
        existing = await self.repository.get_by_idempotency_key(idempotency_key)
        if existing:
            self._ensure_same_request(existing, fingerprint)
            return existing, False

        if request.sender_id == request.receiver_id:
            raise DomainError("SAME_SENDER_RECEIVER", "Sender and receiver must be different", 400)

        active_accounts = await self.repository.active_accounts(
            request.sender_id, request.receiver_id
        )
        missing = {request.sender_id, request.receiver_id} - active_accounts
        if missing:
            raise DomainError("USER_NOT_FOUND", f"Active account not found: {min(missing)}", 404)

        recent_count = await self.repository.recent_sender_count(request.sender_id)
        risk = assess_risk(request.amount, recent_count)
        transaction_id = f"pay_{uuid.uuid4().hex[:16]}"
        status = PaymentStatus.REJECTED if risk.level == RiskLevel.HIGH else PaymentStatus.SUCCESS
        payment = Payment(
            transaction_id=transaction_id,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            sender_id=request.sender_id,
            receiver_id=request.receiver_id,
            amount=request.amount,
            currency=request.currency,
            status=status,
            risk_level=risk.level,
            risk_score=risk.score,
        )
        self.session.add(payment)
        self.session.add_all(
            [
                PaymentAudit(transaction_id=transaction_id, event="PAYMENT_RECEIVED"),
                PaymentAudit(transaction_id=transaction_id, event="PAYMENT_VALIDATED"),
                PaymentAudit(
                    transaction_id=transaction_id,
                    event="RISK_CHECK_COMPLETE",
                    details={
                        "score": risk.score,
                        "level": risk.level.value,
                        "reasons": risk.reasons,
                    },
                ),
                PaymentAudit(
                    transaction_id=transaction_id,
                    event=(
                        "PAYMENT_REJECTED"
                        if status == PaymentStatus.REJECTED
                        else "PAYMENT_COMPLETED"
                    ),
                ),
            ]
        )
        event_type = "PAYMENT_REJECTED" if status == PaymentStatus.REJECTED else "PAYMENT_COMPLETED"
        payload = {
            "event_type": event_type,
            "transaction_id": transaction_id,
            "sender_id": request.sender_id,
            "receiver_id": request.receiver_id,
            "amount": str(request.amount),
            "currency": request.currency,
            "status": status.value,
            "risk_level": risk.level.value,
            "reason": "HIGH_RISK" if status == PaymentStatus.REJECTED else None,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.session.add(
            OutboxEvent(aggregate_id=transaction_id, event_type=event_type, payload=payload)
        )
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.repository.get_by_idempotency_key(idempotency_key)
            if existing:
                self._ensure_same_request(existing, fingerprint)
                return existing, False
            raise
        await self.session.refresh(payment)
        logger.info(
            "payment_processed",
            extra={"transaction_id": transaction_id, "status": status.value},
        )
        return payment, True

    async def get(self, transaction_id: str) -> Payment:
        payment = await self.repository.get_by_transaction_id(transaction_id)
        if not payment:
            raise DomainError("PAYMENT_NOT_FOUND", "Payment was not found", 404)
        return payment

    async def list(self, limit: int, offset: int) -> tuple[list[Payment], int]:
        return await self.repository.list(limit, offset)

    @staticmethod
    def _ensure_same_request(payment: Payment, fingerprint: str) -> None:
        if payment.request_fingerprint != fingerprint:
            raise DomainError(
                "IDEMPOTENCY_KEY_REUSED",
                "This idempotency key was already used for a different payment request",
                409,
            )
