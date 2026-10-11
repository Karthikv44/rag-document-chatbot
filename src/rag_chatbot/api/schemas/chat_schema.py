"""Pydantic schemas for the chat API endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field

from rag_chatbot.config.constants import DEFAULT_RETRIEVAL_TOP_K, MAX_RETRIEVAL_TOP_K


class ChatRequest(BaseModel):
    """Request body for POST /chat."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The natural-language question to answer from indexed documents.",
    )
    top_k: int = Field(
        default=DEFAULT_RETRIEVAL_TOP_K,
        ge=1,
        le=MAX_RETRIEVAL_TOP_K,
        description="Number of chunks to retrieve. Defaults to the configured value.",
    )


class CitationDetail(BaseModel):
    """Source reference for a single file."""

    filename: str
    file_type: str
    locations: list[str]
    display: str


class ChatResponse(BaseModel):
    """Response body for POST /chat."""

    answer: str
    insufficient_evidence: bool = Field(description="True when the indexed content does not support an answer.")
    citations: list[CitationDetail]
    context_chunk_count: int = Field(description="Number of retrieved chunks used as context.")
    top_k_used: int
