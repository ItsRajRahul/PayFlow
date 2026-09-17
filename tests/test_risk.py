from decimal import Decimal

from app.models import RiskLevel
from app.services.risk import assess_risk


def test_low_risk_payment():
    result = assess_risk(Decimal("49999.99"), recent_transaction_count=4)
    assert result.level == RiskLevel.LOW
    assert result.score == 0


def test_amount_rule():
    result = assess_risk(Decimal("50000.01"), recent_transaction_count=0)
    assert result.level == RiskLevel.HIGH
    assert result.reasons == ("AMOUNT_ABOVE_50000",)


def test_velocity_rule_applies_to_sixth_payment():
    result = assess_risk(Decimal("100.00"), recent_transaction_count=5)
    assert result.level == RiskLevel.HIGH
    assert "RAPID_TRANSACTION_VELOCITY" in result.reasons
