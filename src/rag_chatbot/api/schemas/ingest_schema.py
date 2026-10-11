"""Pydantic schemas for the ingest API endpoints."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from rag_chatbot.config.constants import IngestionStatus


class FileIngestionResult(BaseModel):
    """Result for a single file ingestion attempt."""

    document_id: uuid.UUID | None = Field(None, description="UUID of the created document record")
    filename: str
    status: IngestionStatus
    chunk_count: int = 0
    already_indexed: bool = False
    message: str
    error: str | None = None


class IngestResponse(BaseModel):
    """Response body for POST /ingest."""

    results: list[FileIngestionResult]
    total_files: int
    succeeded: int
    failed: int


class DocumentSummary(BaseModel):
    """Brief document info for the listing endpoint."""

    document_id: uuid.UUID
    filename: str
    file_type: str
    status: IngestionStatus
    chunk_count: int
    created_at: str


class DocumentListResponse(BaseModel):
    """Response body for GET /documents."""

    documents: list[DocumentSummary]
    total: int
