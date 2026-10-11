"""FastAPI application factory and entry point.

Responsibilities:
- Create and configure the FastAPI app
- Register API routers
- API key authentication middleware
- Startup / shutdown lifecycle (DB table creation, engine disposal)
- Health and readiness endpoints
- Structured error handlers

Run with:
    uv run app
or directly:
    uv run uvicorn rag_chatbot.main:app --reload
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from rag_chatbot.api.routers.chat_router import router as chat_router
from rag_chatbot.api.routers.ingest_router import router as ingest_router
from rag_chatbot.config.config import settings
from rag_chatbot.config.constants import API_PREFIX, HEALTH_ENDPOINT, READINESS_ENDPOINT
from rag_chatbot.db.session import create_tables, dispose_engine
from rag_chatbot.utils.logger import logger

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan: startup and shutdown hooks."""
    logger.info("Starting RAG Chatbot API (env=%s)", settings.app_env)
    try:
        await create_tables()
        logger.info("Database ready")
    except Exception as exc:
        logger.error("Database initialisation failed: %s", exc)
        # Don't block startup — DB may not be needed for health checks
    yield
    logger.info("Shutting down RAG Chatbot API")
    await dispose_engine()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(
        title="Acme Retail RAG Chatbot",
        description=("Multi-format RAG document chatbot. Upload Excel, CSV, and PowerPoint files, then ask questions."),
        version="0.1.0",
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=f"{API_PREFIX}/redoc",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )

    # CORS — restrict in production via environment
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app_env == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API key authentication middleware
    @app.middleware("http")
    async def api_key_middleware(request: Request, call_next: Any) -> Any:  # type: ignore[no-untyped-def]
        # Skip auth for health/readiness probes and OpenAPI docs
        skip_paths = {
            HEALTH_ENDPOINT,
            READINESS_ENDPOINT,
            f"{API_PREFIX}/docs",
            f"{API_PREFIX}/redoc",
            f"{API_PREFIX}/openapi.json",
        }
        if request.url.path in skip_paths:
            return await call_next(request)

        provided_key = request.headers.get("X-API-Key", "")
        if provided_key != settings.api_key.get_secret_value():
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Invalid or missing API key.", "header": "X-API-Key"},
            )
        return await call_next(request)

    # Request timing middleware
    @app.middleware("http")
    async def timing_middleware(request: Request, call_next: Any) -> Any:  # type: ignore[no-untyped-def]
        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
        return response

    # Routers
    app.include_router(ingest_router, prefix=API_PREFIX)
    app.include_router(chat_router, prefix=API_PREFIX)

    # Health / readiness
    @app.get(HEALTH_ENDPOINT, tags=["ops"], summary="Liveness probe")
    async def health() -> dict:
        return {"status": "healthy", "service": "rag-chatbot"}

    @app.get(READINESS_ENDPOINT, tags=["ops"], summary="Readiness probe")
    async def readiness() -> dict:
        # A lightweight check that the DB engine is reachable
        from sqlalchemy import text  # noqa: PLC0415

        from rag_chatbot.db.session import engine  # noqa: PLC0415

        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False

        ready = db_ok
        return {
            "status": "ready" if ready else "not ready",
            "checks": {"database": "ok" if db_ok else "unavailable"},
        }

    # Global exception handler — ensures stack traces never leak to clients
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "An unexpected error occurred. Please try again later."},
        )

    return app


app = create_app()


def main() -> None:
    """Entry point for `uv run app`."""
    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        "rag_chatbot.main:app",
        host="0.0.0.0",  # noqa: S104
        port=settings.port,
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
