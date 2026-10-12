"""Ingest router — file upload and document management endpoints.

POST /ingest      — upload one or more files, trigger ingestion pipeline
GET  /documents   — list all indexed documents
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from rag_chatbot.api.schemas.ingest_schema import (
    DocumentListResponse,
    DocumentSummary,
    FileIngestionResult,
    IngestResponse,
)
from rag_chatbot.config.constants import IngestionStatus
from rag_chatbot.db.session import get_db_session
from rag_chatbot.ingestion.chunker import DocumentChunker
from rag_chatbot.ingestion.file_validator import file_validator
from rag_chatbot.ingestion.parser_registry import parser_registry
from rag_chatbot.ingestion.pipeline import IngestionPipeline
from rag_chatbot.repositories.document_repository import DocumentRepository
from rag_chatbot.repositories.vector_repository import vector_repository
from rag_chatbot.utils.exception_handler import RAGError
from rag_chatbot.utils.logger import logger

router = APIRouter(prefix="/ingest", tags=["ingestion"])

# Single shared pipeline instance (stateless)
_pipeline = IngestionPipeline(
    file_validator=file_validator,
    parser_registry=parser_registry,
    chunker=DocumentChunker(),
    vector_repository=vector_repository,
)


@router.post("", response_model=IngestResponse, summary="Upload and ingest documents")
async def ingest_files(
    files: list[UploadFile],
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> IngestResponse:
    """Accept one or more Excel, CSV, or PowerPoint files for ingestion.

    Each file is validated, parsed, chunked, embedded, and indexed in
    PostgreSQL + pgvector. Returns a per-file result so partial failures
    are visible.
    """
    from rag_chatbot.config.config import settings  # noqa: PLC0415

    if len(files) > settings.max_files_per_request:
        from fastapi import HTTPException, status  # noqa: PLC0415

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Too many files. Maximum {settings.max_files_per_request} per request.",
        )

    results: list[FileIngestionResult] = []

    for upload in files:
        filename = upload.filename or "unknown"
        logger.info("Received upload: %r", filename)
        try:
            data = await upload.read()
            result = await _pipeline.ingest(filename=filename, data=data, session=session)
            results.append(
                FileIngestionResult(
                    document_id=result.document_id,
                    filename=result.filename,
                    status=result.status,
                    chunk_count=result.chunk_count,
                    already_indexed=result.already_indexed,
                    message=result.message,
                )
            )
        except RAGError as exc:
            logger.warning("Ingestion failed for %r: %s", filename, exc)
            results.append(
                FileIngestionResult(
                    filename=filename,
                    status=IngestionStatus.FAILED,
                    message=f"Ingestion failed: {exc}",
                    error=str(exc),
                )
            )
        except Exception as exc:
            logger.exception("Unexpected error ingesting %r: %s", filename, exc)
            results.append(
                FileIngestionResult(
                    filename=filename,
                    status=IngestionStatus.FAILED,
                    message="An unexpected error occurred during ingestion.",
                    error="Internal error",
                )
            )

    succeeded = sum(1 for r in results if r.status == IngestionStatus.COMPLETE)
    failed = len(results) - succeeded

    return IngestResponse(
        results=results,
        total_files=len(results),
        succeeded=succeeded,
        failed=failed,
    )


@router.get("/documents", response_model=DocumentListResponse, summary="List indexed documents")
async def list_documents(
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> DocumentListResponse:
    """Return a list of all documents with their ingestion status."""
    doc_repo = DocumentRepository(session)
    docs = await doc_repo.list_all()

    summaries = []
    for doc in docs:
        chunk_count = await doc_repo.get_chunk_count(doc.id)
        summaries.append(
            DocumentSummary(
                document_id=doc.id,
                filename=doc.filename,
                file_type=doc.file_type,
                status=IngestionStatus(doc.status),
                chunk_count=chunk_count,
                created_at=doc.created_at.isoformat(),
            )
        )

    return DocumentListResponse(documents=summaries, total=len(summaries))
