"""Centralised exception handling for the RAG chatbot.

Adapts the reference project's two-layer decorator pattern to FastAPI:

Layer 1 — handle_provider_exceptions
    Applied to provider/client methods that call external services (Gemini, DB).
    Maps transport-level errors to domain RAGError subclasses.
    Does NOT catch everything silently — unexpected exceptions re-raise.

Layer 2 — handle_service_exceptions(operation_name)
    Applied to service and pipeline methods.
    Catches domain exceptions and converts them to FastAPI HTTPException with
    structured JSON bodies. Logs every exception with operation context.

Custom exceptions follow a single hierarchy rooted at RAGError so callers
can catch broadly or narrowly depending on their needs.
"""

import functools
import uuid
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import HTTPException, status

from .logger import logger

# =============================================================================
# Domain Exception Hierarchy
# =============================================================================


class RAGError(Exception):
    """Base domain exception for all RAG chatbot errors.

    Args:
        message: Human-readable description.
        details: Optional dict with structured context for logging.
    """

    http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class UnsupportedFormatError(RAGError):
    """File format is not supported or cannot be determined."""

    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT


class DocumentParseError(RAGError):
    """File content could not be parsed (corrupt, empty, or invalid structure)."""

    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT


class InvalidDocumentContentError(RAGError):
    """Parsed content is structurally invalid (e.g. no columns, empty sheets)."""

    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT


class FileSizeExceededError(RAGError):
    """Uploaded file exceeds the configured size limit."""

    http_status = status.HTTP_413_CONTENT_TOO_LARGE


class EmbeddingProviderError(RAGError):
    """Gemini embedding API call failed."""

    http_status = status.HTTP_502_BAD_GATEWAY


class VectorStoreError(RAGError):
    """pgvector read or write operation failed."""

    http_status = status.HTTP_502_BAD_GATEWAY


class RetrievalError(RAGError):
    """Similarity search or metadata filtering failed."""

    http_status = status.HTTP_502_BAD_GATEWAY


class LLMGenerationError(RAGError):
    """Gemini LLM generation call failed."""

    http_status = status.HTTP_502_BAD_GATEWAY


class PersistenceError(RAGError):
    """PostgreSQL read or write operation failed."""

    http_status = status.HTTP_500_INTERNAL_SERVER_ERROR


class ConfigurationError(RAGError):
    """Application is misconfigured (e.g. missing required env var)."""

    http_status = status.HTTP_500_INTERNAL_SERVER_ERROR


# =============================================================================
# Layer 1 — Provider / HTTP client decorator
# =============================================================================


def handle_provider_exceptions(func: Callable) -> Callable:
    """Wrap external provider calls to translate transport errors into RAGError.

    Applied to methods in providers/ and repositories/ that call Gemini or
    the database. Unexpected exceptions that are not httpx errors re-raise
    unchanged so they bubble up to Layer 2.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except httpx.HTTPStatusError as exc:
            logger.exception("HTTP status error in %s: %s", func.__qualname__, exc)
            raise EmbeddingProviderError(
                f"Provider HTTP error: {exc.response.status_code}",
                details={"url": str(exc.request.url), "status": exc.response.status_code},
            ) from exc
        except httpx.TimeoutException as exc:
            logger.exception("Request timeout in %s: %s", func.__qualname__, exc)
            raise EmbeddingProviderError(
                f"Provider request timed out: {exc}",
            ) from exc
        except httpx.RequestError as exc:
            logger.exception("Request error in %s: %s", func.__qualname__, exc)
            raise EmbeddingProviderError(f"Provider request error: {exc}") from exc
        # All other exceptions propagate unchanged

    return wrapper


# =============================================================================
# Layer 2 — Service / pipeline decorator
# =============================================================================


def handle_service_exceptions(operation_name: str) -> Callable:
    """Decorator factory for service and pipeline methods.

    Converts RAGError subclasses into FastAPI HTTPException with structured
    JSON error bodies. Assigns a correlation ID to every error for log tracing.

    Args:
        operation_name: Short label for the operation, used in logs and response body.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            correlation_id = str(uuid.uuid4())
            try:
                return await func(*args, **kwargs)

            except RAGError as exc:
                logger.exception(
                    "%s failed: %s",
                    operation_name,
                    str(exc),
                    extra={"correlation_id": correlation_id, "details": exc.details},
                )
                raise HTTPException(
                    status_code=exc.http_status,
                    detail={
                        "error": str(exc),
                        "operation": operation_name,
                        "correlation_id": correlation_id,
                    },
                ) from exc

            except ValueError as exc:
                logger.exception(
                    "%s validation error: %s",
                    operation_name,
                    str(exc),
                    extra={"correlation_id": correlation_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "error": f"Validation error: {exc}",
                        "operation": operation_name,
                        "correlation_id": correlation_id,
                    },
                ) from exc

            except HTTPException:
                # Already a well-formed HTTP exception — let it pass through
                raise

            except Exception as exc:
                logger.exception(
                    "%s unexpected error: %s",
                    operation_name,
                    str(exc),
                    extra={"correlation_id": correlation_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "error": "An unexpected internal error occurred.",
                        "operation": operation_name,
                        "correlation_id": correlation_id,
                    },
                ) from exc

        return wrapper

    return decorator
