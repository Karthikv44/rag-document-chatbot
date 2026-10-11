"""Async SQLAlchemy engine and session factory.

Provides:
- `engine`         — async engine singleton
- `AsyncSessionLocal` — async session factory
- `get_db_session` — FastAPI dependency that yields a session and handles commit/rollback
- `create_tables`  — creates all ORM tables on startup (dev convenience)
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from rag_chatbot.config.config import settings
from rag_chatbot.utils.logger import logger

# Single engine instance for the application lifetime
engine = create_async_engine(
    settings.async_database_url,
    echo=settings.app_env == "development",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency: yields an async DB session with automatic cleanup.

    Commits on successful exit, rolls back on exception.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables() -> None:
    """Create all ORM-defined tables if they do not already exist.

    Called during application startup in development. In production,
    use Alembic migrations instead.
    """
    from rag_chatbot.db.models import Base  # noqa: PLC0415

    async with engine.begin() as conn:
        # Ensure pgvector extension exists
        await conn.execute(__import__("sqlalchemy", fromlist=["text"]).text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified/created")


async def dispose_engine() -> None:
    """Close all pooled connections on application shutdown."""
    await engine.dispose()
    logger.info("Database engine disposed")
