"""Document repository.

Encapsulates all PostgreSQL operations for the `documents` and `chunks` tables.
All methods are async and accept an injected AsyncSession so they compose
cleanly with FastAPI's dependency injection and transactional boundaries.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rag_chatbot.config.constants import IngestionStatus
from rag_chatbot.db.models import Chunk, Document
from rag_chatbot.utils.exception_handler import PersistenceError
from rag_chatbot.utils.logger import logger


class DocumentRepository:
    """CRUD operations for Documents and Chunks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Document operations
    # ------------------------------------------------------------------

    async def get_by_hash(self, content_hash: str) -> Document | None:
        """Return the document matching `content_hash`, or None."""
        try:
            result = await self._session.execute(select(Document).where(Document.content_hash == content_hash))
            return result.scalar_one_or_none()
        except Exception as exc:
            raise PersistenceError(f"Failed to query document by hash: {exc}") from exc

    async def get_by_id(self, doc_id: uuid.UUID) -> Document | None:
        """Return the document with `doc_id`, or None."""
        try:
            result = await self._session.execute(select(Document).where(Document.id == doc_id))
            return result.scalar_one_or_none()
        except Exception as exc:
            raise PersistenceError(f"Failed to query document by id: {exc}") from exc

    async def create(
        self,
        filename: str,
        file_type: str,
        content_hash: str,
        file_size_bytes: int,
    ) -> Document:
        """Insert a new document record with PENDING status."""
        try:
            doc = Document(
                filename=filename,
                file_type=file_type,
                content_hash=content_hash,
                file_size_bytes=file_size_bytes,
                status=IngestionStatus.PENDING,
            )
            self._session.add(doc)
            await self._session.flush()  # get the generated ID without committing
            logger.info("Created document record id=%s filename=%r", doc.id, filename)
            return doc
        except Exception as exc:
            raise PersistenceError(f"Failed to create document record: {exc}") from exc

    async def update_status(
        self,
        doc_id: uuid.UUID,
        status: IngestionStatus,
        error_message: str | None = None,
    ) -> None:
        """Update the ingestion status (and optionally an error message)."""
        try:
            values: dict = {
                "status": status,
                "updated_at": datetime.now(UTC),
            }
            if error_message is not None:
                values["error_message"] = error_message
            await self._session.execute(update(Document).where(Document.id == doc_id).values(**values))
            logger.info("Document id=%s status → %s", doc_id, status)
        except Exception as exc:
            raise PersistenceError(f"Failed to update document status: {exc}") from exc

    async def list_all(self) -> list[Document]:
        """Return all documents ordered by creation time descending."""
        try:
            result = await self._session.execute(select(Document).order_by(Document.created_at.desc()))
            return list(result.scalars().all())
        except Exception as exc:
            raise PersistenceError(f"Failed to list documents: {exc}") from exc

    async def get_chunk_count(self, doc_id: uuid.UUID) -> int:
        """Count the number of chunks for a specific document."""
        try:
            from sqlalchemy import func  # noqa: PLC0415

            result = await self._session.execute(select(func.count(Chunk.id)).where(Chunk.document_id == doc_id))
            return result.scalar_one()
        except Exception as exc:
            raise PersistenceError(f"Failed to count chunks: {exc}") from exc

    # ------------------------------------------------------------------
    # Chunk operations
    # ------------------------------------------------------------------

    async def create_chunks(self, chunks: list[Chunk]) -> None:
        """Bulk-insert a list of Chunk objects."""
        try:
            self._session.add_all(chunks)
            await self._session.flush()
            logger.debug("Inserted %d chunks", len(chunks))
        except Exception as exc:
            raise PersistenceError(f"Failed to insert chunks: {exc}") from exc

    async def get_chunks_by_ids(self, chunk_ids: list[uuid.UUID]) -> list[Chunk]:
        """Fetch chunks by a list of UUIDs (used for citation lookup)."""
        if not chunk_ids:
            return []
        try:
            result = await self._session.execute(select(Chunk).where(Chunk.id.in_(chunk_ids)))
            return list(result.scalars().all())
        except Exception as exc:
            raise PersistenceError(f"Failed to fetch chunks by ids: {exc}") from exc

    async def delete_chunks_for_document(self, doc_id: uuid.UUID) -> None:
        """Remove all chunks belonging to a document (used on re-ingestion)."""
        try:
            from sqlalchemy import delete  # noqa: PLC0415

            await self._session.execute(delete(Chunk).where(Chunk.document_id == doc_id))
            logger.info("Deleted chunks for document id=%s", doc_id)
        except Exception as exc:
            raise PersistenceError(f"Failed to delete chunks for document: {exc}") from exc
