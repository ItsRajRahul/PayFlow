import hmac
from typing import Annotated

from fastapi import Depends, Header

from app.config import Settings, get_settings
from app.errors import DomainError


async def verify_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    if x_api_key is None or not hmac.compare_digest(x_api_key, settings.api_key):
        raise DomainError("UNAUTHORIZED", "A valid X-API-Key header is required", 401)
