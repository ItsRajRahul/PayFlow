from dataclasses import dataclass
from decimal import Decimal

from app.models import RiskLevel


@dataclass(frozen=True)
class RiskAssessment:
    score: int
    level: RiskLevel
    reasons: tuple[str, ...]


def assess_risk(amount: Decimal, recent_transaction_count: int) -> RiskAssessment:
    score = 0
    reasons: list[str] = []
    if amount > Decimal("50000.00"):
        score += 50
        reasons.append("AMOUNT_ABOVE_50000")
    if recent_transaction_count >= 5:
        score += 50
        reasons.append("RAPID_TRANSACTION_VELOCITY")
    level = RiskLevel.HIGH if score >= 50 else RiskLevel.LOW
    return RiskAssessment(score=score, level=level, reasons=tuple(reasons))
