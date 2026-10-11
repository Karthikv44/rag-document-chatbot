"""Vector retriever.

Wraps the VectorRepository similarity search and converts raw LangChain
Documents into a typed RetrievedChunk list that carries all the metadata
the citation builder needs.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.documents import Document as LCDocument

from rag_chatbot.config.config import settings
from rag_chatbot.observability.langfuse_client import trace_operation
from rag_chatbot.repositories.vector_repository import VectorRepository
from rag_chatbot.utils.exception_handler import handle_service_exceptions
from rag_chatbot.utils.logger import logger


@dataclass
class RetrievedChunk:
    """A single retrieved chunk with its content and source metadata."""

    chunk_id: str
    content: str
    source_filename: str
    file_type: str
    document_id: str

    # Format-specific location fields (None when not applicable)
    sheet_name: str | None = None
    row_range_start: int | None = None
    row_range_end: int | None = None
    slide_number: int | None = None
    slide_title: str | None = None

    def location_label(self) -> str:
        """Human-readable source location string for citations."""
        if self.file_type in {"xlsx", "xls"}:
            parts = [self.source_filename]
            if self.sheet_name:
                parts.append(self.sheet_name)
            if self.row_range_start and self.row_range_end:
                parts.append(f"rows {self.row_range_start}–{self.row_range_end}")
            return " → ".join(parts)
        if self.file_type == "csv":
            parts = [self.source_filename]
            if self.row_range_start and self.row_range_end:
                parts.append(f"rows {self.row_range_start}–{self.row_range_end}")
            return " → ".join(parts)
        if self.file_type in {"pptx", "ppt"}:
            parts = [self.source_filename]
            if self.slide_number:
                slide_label = f"Slide {self.slide_number}"
                if self.slide_title:
                    slide_label += f" ({self.slide_title})"
                parts.append(slide_label)
            return " → ".join(parts)
        return self.source_filename


class VectorRetriever:
    """Performs similarity search and returns typed RetrievedChunk objects."""

    def __init__(self, vector_repository: VectorRepository) -> None:
        self._vector_repo = vector_repository

    @handle_service_exceptions("retrieve")
    async def retrieve(
        self,
        question: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Retrieve the most relevant chunks for a question.

        Args:
            question: The user's natural-language question.
            top_k: Number of results to return (defaults to settings).

        Returns:
            List of RetrievedChunk ordered by relevance (most relevant first).
        """
        k = top_k or settings.retrieval_top_k

        async with trace_operation("retrieve", {"question_len": len(question), "k": k}) as span:
            import asyncio  # noqa: PLC0415

            # PGVector similarity_search is sync — run in thread pool
            lc_docs: list[LCDocument] = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._vector_repo.similarity_search(question, k=k),
            )

            chunks = [self._to_retrieved_chunk(doc) for doc in lc_docs]
            span["retrieved_count"] = len(chunks)

        logger.info("Retrieved %d chunks for question (k=%d)", len(chunks), k)
        return chunks

    @staticmethod
    def _to_retrieved_chunk(doc: LCDocument) -> RetrievedChunk:
        """Map a LangChain Document to a RetrievedChunk."""
        meta = doc.metadata
        return RetrievedChunk(
            chunk_id=meta.get("chunk_id", ""),
            content=doc.page_content,
            source_filename=meta.get("source_filename", "unknown"),
            file_type=meta.get("file_type", ""),
            document_id=meta.get("document_id", ""),
            sheet_name=meta.get("sheet_name"),
            row_range_start=meta.get("row_range_start"),
            row_range_end=meta.get("row_range_end"),
            slide_number=meta.get("slide_number"),
            slide_title=meta.get("slide_title"),
        )
