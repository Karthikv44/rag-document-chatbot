"""Centralised structured logging configuration.

Provides a module-level `logger` instance configured from application settings.
Uses Python's standard `logging` module with a structured JSON-friendly formatter
for production and a readable format for development.
"""

import logging
import sys
from typing import Any


class _StructuredFormatter(logging.Formatter):
    """Formatter that produces readable structured log lines.

    Format: LEVEL     [module] message  {extra_fields}
    """

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras: dict[str, Any] = {
            k: v
            for k, v in record.__dict__.items()
            if k
            not in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
                "taskName",
            }
        }
        if extras:
            extras_str = "  " + "  ".join(f"{k}={v!r}" for k, v in extras.items())
            return base + extras_str
        return base


def _build_logger() -> logging.Logger:
    """Create and configure the application logger."""
    # Avoid circular imports by importing settings lazily
    try:
        from rag_chatbot.config.config import settings

        level_name = settings.log_level
    except Exception:
        level_name = "INFO"

    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    formatter = _StructuredFormatter(
        fmt="%(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)

    log = logging.getLogger("rag_chatbot")
    log.setLevel(level)
    if not log.handlers:
        log.addHandler(handler)
    log.propagate = False
    return log


logger: logging.Logger = _build_logger()
