"""Application settings loaded from environment / .env via Pydantic Settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/colearn"

    # Auth
    jwt_secret: str = "dev-only-insecure-secret-change-me-0123456789"

    # LLM
    anthropic_api_key: str = ""
    llm_model: str = ""
    llm_temperature: float = 0.0

    # Evaluation
    self_consistency_runs: int = 2
    confidence_review_threshold: float = 0.75
    auto_approve_enabled: bool = False

    # Analytics thresholds
    mastery_ema_alpha: float = 0.4
    weak_topic_threshold: float = 0.5
    watch_threshold: float = 0.6

    # Monitoring scheduler
    monitoring_scheduler_enabled: bool = True
    monitoring_interval_hours: int = 6

    # Storage
    storage_dir: str = "./storage"

    # Tracing
    langsmith_tracing: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
