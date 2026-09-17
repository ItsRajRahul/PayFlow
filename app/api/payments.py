from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import PaymentCreate, PaymentList, PaymentResponse
from app.security import verify_api_key
from app.services.payments import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"], dependencies=[Depends(verify_api_key)])
SessionDependency = Annotated[AsyncSession, Depends(get_db)]


@router.post(
    "",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Idempotent replay"}, 409: {"description": "Key conflict"}},
)
async def create_payment(
    request: PaymentCreate,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=255),
    ],
    session: SessionDependency,
) -> PaymentResponse:
    payment, created = await PaymentService(session).create(request, idempotency_key)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return PaymentResponse.model_validate(payment)


@router.get("/{transaction_id}", response_model=PaymentResponse)
async def get_payment(transaction_id: str, session: SessionDependency) -> PaymentResponse:
    payment = await PaymentService(session).get(transaction_id)
    return PaymentResponse.model_validate(payment)


@router.get("", response_model=PaymentList)
async def list_payments(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaymentList:
    payments, total = await PaymentService(session).list(limit, offset)
    return PaymentList(
        items=[PaymentResponse.model_validate(payment) for payment in payments],
        total=total,
        limit=limit,
        offset=offset,
    )
