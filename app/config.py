from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "PayFlow"
    app_env: str = "development"
    api_key: str = Field(min_length=12)
    database_url: str = "postgresql+asyncpg://payflow:payflow@localhost:5432/payflow"
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_topic: str = "payment-events"
    kafka_consumer_group: str = "payflow-notifications"
    auto_create_schema: bool = False
    log_level: str = "INFO"
    outbox_poll_interval_seconds: float = 1.0
    kafka_reconnect_interval_seconds: float = 10.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
