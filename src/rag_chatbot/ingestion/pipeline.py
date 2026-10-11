"""Ingestion pipeline orchestrator.

Coordinates the full file → chunks → embeddings → DB workflow:

1. Validate file
2. Compute content hash (idempotency)
3. Check if document already indexed (skip if unchanged)
4. Create Document record (PENDING)
5. Parse file → ParsedChunks
6. Chunk → LangChain Documents with stable IDs
7. Persist Chunk records to PostgreSQL
8. Add LangChain Documents to PGVector (embeds + stores)
9. Mark Document COMPLETE
10. On any failure → mark Document FAILED, re-raise

All DB work runs inside a shared transaction that is committed only on success.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from rag_chatbot.config.constants import IngestionStatus
from rag_chatbot.db.models import Chunk
from rag_chatbot.observability.langfuse_client import trace_operation
from rag_chatbot.repositories.document_repository import DocumentRepository
from rag_chatbot.repositories.vector_repository import VectorRepository
from rag_chatbot.utils.exception_handler import PersistenceError, handle_service_exceptions
from rag_chatbot.utils.logger import logger
from rag_chatbot.utils.temp_file import temp_upload_file

from .chunker import DocumentChunker
from .file_validator import FileValidator
from .parser_registry import ParserRegistry


@dataclass
class IngestionResult:
    """Summary returned to the API layer after ingestion completes."""

    document_id: uuid.UUID
    filename: str
    status: IngestionStatus
    chunk_count: int
    already_indexed: bool
    message: str


class IngestionPipeline:
    """Orchestrates end-to-end document ingestion."""

    def __init__(
        self,
        file_validator: FileValidator,
        parser_registry: ParserRegistry,
        chunker: DocumentChunker,
        vector_repository: VectorRepository,
    ) -> None:
        self._validator = file_validator
        self._registry = parser_registry
        self._chunker = chunker
        self._vector_repo = vector_repository

    @handle_service_exceptions("ingest_file")
    async def ingest(
        self,
        filename: str,
        data: bytes,
        session: AsyncSession,
    ) -> IngestionResult:
        """Ingest a single uploaded file end-to-end.

        Args:
            filename: Original uploaded filename.
            data: Raw file bytes.
            session: Async DB session (managed by caller/dependency).

        Returns:
            IngestionResult describing what was done.
        """
        doc_repo = DocumentRepository(session)

        async with trace_operation("ingest_file", {"filename": filename, "size": len(data)}) as span:
            # --- Step 1: Validate ---
            ext = self._validator.validate(filename, data)
            content_hash = hashlib.sha256(data).hexdigest()

            # --- Step 2: Idempotency check ---
            existing = await doc_repo.get_by_hash(content_hash)
            if existing and existing.status == IngestionStatus.COMPLETE:
                logger.info(
                    "File %r already indexed (doc_id=%s); skipping re-ingestion.",
                    filename,
                    existing.id,
                )
                span["already_indexed"] = True
                return IngestionResult(
                    document_id=existing.id,
                    filename=filename,
                    status=IngestionStatus.COMPLETE,
                    chunk_count=len(existing.chunks) if existing.chunks else 0,
                    already_indexed=True,
                    message="Document already indexed. No changes detected.",
                )

            # --- Step 3: Create document record ---
            doc = await doc_repo.create(
                filename=filename,
                file_type=ext,
                content_hash=content_hash,
                file_size_bytes=len(data),
            )
            await doc_repo.update_status(doc.id, IngestionStatus.PROCESSING)

            try:
                # --- Step 4: Parse ---
                async with trace_operation("parse_document", {"filename": filename, "ext": ext}):
                    parser = self._registry.get_parser(ext)
                    async with temp_upload_file(data, suffix=f".{ext}") as tmp_path:
                        parsed_chunks = parser.parse(tmp_path, filename)
                logger.info("Parsed %d chunks from %r", len(parsed_chunks), filename)

                # --- Step 5: Chunk ---
                async with trace_operation("chunk_document", {"filename": filename}) as chunk_span:
                    chunked = self._chunker.chunk(parsed_chunks, doc.id)
                    chunk_span["chunk_count"] = len(chunked)
                logger.info("Produced %d final chunks from %r", len(chunked), filename)

                # --- Step 6: Persist Chunk records ---
                async with trace_operation("index_chunks_db", {"chunk_count": len(chunked)}):
                    chunk_records = [
                        Chunk(
                            id=uuid.UUID(chunk_id),
                            document_id=doc.id,
                            chunk_index=lc_doc.metadata["chunk_index"],
                            chunk_hash=content_hash_val,
                            content=lc_doc.page_content,
                            sheet_name=lc_doc.metadata.get("sheet_name"),
                            row_range_start=lc_doc.metadata.get("row_range_start"),
                            row_range_end=lc_doc.metadata.get("row_range_end"),
                            slide_number=lc_doc.metadata.get("slide_number"),
                            slide_title=lc_doc.metadata.get("slide_title"),
                        )
                        for lc_doc, chunk_id, content_hash_val in chunked
                    ]
                    await doc_repo.create_chunks(chunk_records)

                # --- Step 7: Embed + store in pgvector ---
                async with trace_operation("embed_and_index", {"chunk_count": len(chunked)}):
                    lc_docs = [lc_doc for lc_doc, _, _ in chunked]
                    ids = [chunk_id for _, chunk_id, _ in chunked]
                    # PGVector.add_documents is sync — run in thread pool
                    import asyncio  # noqa: PLC0415

                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self._vector_repo.add_documents(lc_docs, ids),
                    )

                # --- Step 8: Mark complete ---
                await doc_repo.update_status(doc.id, IngestionStatus.COMPLETE)
                span["chunk_count"] = len(chunked)
                span["status"] = "complete"

                return IngestionResult(
                    document_id=doc.id,
                    filename=filename,
                    status=IngestionStatus.COMPLETE,
                    chunk_count=len(chunked),
                    already_indexed=False,
                    message=f"Successfully ingested {len(chunked)} chunks.",
                )

            except Exception as exc:
                # Mark failed — do not swallow the exception
                try:
                    await doc_repo.update_status(
                        doc.id,
                        IngestionStatus.FAILED,
                        error_message=str(exc)[:1000],
                    )
                except PersistenceError:
                    logger.exception("Failed to update document status to FAILED for id=%s", doc.id)
                raise
