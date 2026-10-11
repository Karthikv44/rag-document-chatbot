"""Langfuse observability client.

Provides:
- `get_langfuse_callback` — returns a LangChain CallbackHandler for tracing
  LangChain/LCEL chains. Returns None when Langfuse is disabled.
- `langfuse_context` — re-exports Langfuse's context manager for manual
  span instrumentation outside of LangChain chains.
- `trace_operation` — async context manager that wraps arbitrary code in a
  Langfuse span with latency, success/failure, and optional metadata.

Configuration is driven entirely by settings.langfuse_* fields. If
LANGFUSE_ENABLED=false or required keys are missing, all calls become no-ops
so the application works without Langfuse configured locally.

IMPORTANT: Never log full document content to Langfuse. Only log safe metadata
(filenames, chunk counts, latency, status) to avoid transmitting sensitive data.
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from rag_chatbot.config.config import settings
from rag_chatbot.utils.logger import logger


def _langfuse_available() -> bool:
    """Return True if Langfuse is enabled and properly configured."""
    if not settings.langfuse_enabled:
        return False
    if not settings.langfuse_public_key or not settings.langfuse_secret_key.get_secret_value():
        logger.warning(
            "LANGFUSE_ENABLED=true but LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are not set. "
            "Langfuse tracing is disabled."
        )
        return False
    return True


def get_langfuse_callback() -> Any | None:
    """Return a configured Langfuse CallbackHandler for LangChain chains.

    Returns None when Langfuse is unavailable so callers can safely pass
    `callbacks=[c for c in [get_langfuse_callback()] if c]`.
    """
    if not _langfuse_available():
        return None
    try:
        import os

        from langfuse.langchain import CallbackHandler  # type: ignore[import-untyped]

        # Set env vars that the CallbackHandler reads automatically
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key.get_secret_value())
        os.environ.setdefault("LANGFUSE_BASE_URL", settings.langfuse_base_url)

        return CallbackHandler()
    except ImportError:
        logger.warning("langfuse package not installed; tracing disabled.")
        return None
    except Exception as exc:
        logger.warning("Failed to initialise Langfuse callback: %s", exc)
        return None


@asynccontextmanager
async def trace_operation(
    name: str,
    metadata: dict[str, Any] | None = None,
) -> AsyncGenerator[dict[str, Any]]:
    """Async context manager for manual Langfuse span instrumentation.

    Yields a dict that the caller can populate with output metadata.
    Records latency and success/failure status.

    Usage:
        async with trace_operation("embed_chunks", {"doc_id": str(doc_id)}) as span_meta:
            result = await do_work()
            span_meta["chunk_count"] = len(result)

    When Langfuse is unavailable this is a lightweight no-op (only measures latency
    via time.monotonic for local logging).
    """
    span_meta: dict[str, Any] = {}
    start = time.monotonic()
    available = _langfuse_available()

    lf_span = None
    if available:
        try:
            from langfuse import get_client  # type: ignore[import-untyped]

            lf = get_client()
            lf_span = lf.start_span(name=name, input=metadata or {})
        except Exception as exc:
            logger.debug("Could not start Langfuse span %s: %s", name, exc)
            lf_span = None

    try:
        yield span_meta
        elapsed = time.monotonic() - start
        logger.debug("Operation %s succeeded in %.3fs", name, elapsed)
        if lf_span:
            try:
                lf_span.end(output=span_meta)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Failed to end Langfuse span: %s", exc)
    except Exception as exc:
        elapsed = time.monotonic() - start
        logger.debug("Operation %s failed in %.3fs: %s", name, elapsed, exc)
        if lf_span:
            try:
                lf_span.end(output={"error": str(exc)}, level="ERROR")
            except Exception as inner:  # noqa: BLE001
                logger.debug("Failed to end Langfuse error span: %s", inner)
        raise
