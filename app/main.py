import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.payments import router as payments_router
from app.config import get_settings
from app.database import SessionFactory, create_schema
from app.errors import DomainError
from app.kafka.producer import OutboxPublisher
from app.logging import configure_logging
from app.schemas import HealthResponse

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
publisher = OutboxPublisher(settings)
static_directory = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    if settings.auto_create_schema:
        await create_schema()
    await publisher.start()
    application.state.publisher = publisher
    yield
    await publisher.stop()


app = FastAPI(
    title="PayFlow API",
    version="0.1.0",
    description="Reliable, idempotent payment processing with event-driven integrations.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=static_directory), name="static")
app.include_router(payments_router)


@app.exception_handler(DomainError)
async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code, content={"error": exc.code, "message": exc.message}
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0]
    location = ".".join(str(part) for part in first["loc"] if part not in {"body", "header"})
    message = f"{location}: {first['msg']}" if location else first["msg"]
    return JSONResponse(status_code=422, content={"error": "VALIDATION_ERROR", "message": message})


@app.exception_handler(Exception)
async def unexpected_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_request_error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_ERROR", "message": "An unexpected error occurred"},
    )


@app.get("/health", response_model=HealthResponse, tags=["operations"])
async def health() -> HealthResponse:
    database_status = "healthy"
    try:
        async with SessionFactory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        database_status = "unhealthy"
    return HealthResponse(
        api="healthy",
        database=database_status,
        kafka="healthy" if publisher.connected else "degraded",
    )


@app.get("/", include_in_schema=False, response_class=FileResponse)
async def root() -> FileResponse:
    return FileResponse(static_directory / "index.html")
