from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import PaymentStatus, RiskLevel


class PaymentCreate(BaseModel):
    sender_id: int = Field(gt=0)
    receiver_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: Literal["INR"] = "INR"


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: str
    sender_id: int
    receiver_id: int
    amount: Decimal
    currency: str
    status: PaymentStatus
    risk_level: RiskLevel
    risk_score: int
    created_at: datetime
    updated_at: datetime


class PaymentList(BaseModel):
    items: list[PaymentResponse]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    api: Literal["healthy"]
    database: Literal["healthy", "unhealthy"]
    kafka: Literal["healthy", "degraded"]


class ErrorResponse(BaseModel):
    error: str
    message: str
