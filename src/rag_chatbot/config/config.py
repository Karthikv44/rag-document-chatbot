"""Centralised configuration management.

Uses pydantic-settings for validated, typed environment variable loading.
A singleton instance `settings` is exported for use throughout the application.
"""

from functools import cached_property
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MAX_TOKENS,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TEMPERATURE,
    DEFAULT_MAX_FILE_SIZE_MB,
    DEFAULT_MAX_FILES_PER_REQUEST,
    DEFAULT_RETRIEVAL_TOP_K,
)


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file.

    All secrets are wrapped in SecretStr so they are never accidentally
    serialised or logged as plain text.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    port: int = Field(default=8000, ge=1, le=65535)

    # ------------------------------------------------------------------
    # API Security
    # ------------------------------------------------------------------
    api_key: SecretStr = Field(..., description="X-API-Key header value required on all endpoints")

    # ------------------------------------------------------------------
    # Google Gemini
    # ------------------------------------------------------------------
    google_api_key: SecretStr = Field(..., description="Google AI API key")
    gemini_llm_model: str = Field(default=DEFAULT_LLM_MODEL)
    gemini_embedding_model: str = Field(default=DEFAULT_EMBEDDING_MODEL)
    embedding_dimensions: int = Field(default=DEFAULT_EMBEDDING_DIMENSIONS, ge=1)

    # ------------------------------------------------------------------
    # PostgreSQL
    # ------------------------------------------------------------------
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = Field(default="rag_chatbot")
    postgres_user: str = Field(default="rag_user")
    postgres_password: SecretStr = Field(...)

    # Optional override for the full URL
    database_url: str | None = Field(default=None)

    # ------------------------------------------------------------------
    # Langfuse
    # ------------------------------------------------------------------
    langfuse_enabled: bool = Field(default=True)
    langfuse_public_key: str = Field(default="")
    langfuse_secret_key: SecretStr = Field(default=SecretStr(""))
    langfuse_base_url: str = Field(default="https://cloud.langfuse.com")

    # ------------------------------------------------------------------
    # File upload limits
    # ------------------------------------------------------------------
    max_file_size_mb: int = Field(default=DEFAULT_MAX_FILE_SIZE_MB, ge=1, le=500)
    max_files_per_request: int = Field(default=DEFAULT_MAX_FILES_PER_REQUEST, ge=1, le=50)

    # ------------------------------------------------------------------
    # RAG parameters
    # ------------------------------------------------------------------
    retrieval_top_k: int = Field(default=DEFAULT_RETRIEVAL_TOP_K, ge=1, le=20)
    llm_max_tokens: int = Field(default=DEFAULT_LLM_MAX_TOKENS, ge=1)
    llm_temperature: float = Field(default=DEFAULT_LLM_TEMPERATURE, ge=0.0, le=2.0)

    @field_validator("langfuse_enabled", mode="before")
    @classmethod
    def _coerce_langfuse_enabled(cls, v: object) -> bool:
        if isinstance(v, str):
            return v.lower() not in {"false", "0", "no", "off"}
        return bool(v)

    @cached_property
    def async_database_url(self) -> str:
        """Build the async SQLAlchemy connection URL from components."""
        if self.database_url:
            # Ensure asyncpg driver is used even if a sync URL is provided
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://").replace(
                "postgresql+psycopg://", "postgresql+asyncpg://"
            )
        pw = self.postgres_password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{pw}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @cached_property
    def sync_database_url(self) -> str:
        """Sync URL used by Alembic migrations."""
        if self.database_url:
            return self.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
        pw = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.postgres_user}:{pw}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @cached_property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


# Singleton — import this everywhere
settings = Settings()  # type: ignore[call-arg]
