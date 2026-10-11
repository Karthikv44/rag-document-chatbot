"""RAG pipeline orchestrator.

Coordinates the full question → answer workflow:
  1. Retrieve relevant chunks
  2. Generate grounded answer
  3. Build source citations

The pipeline is the single entry point for the chat router, keeping
orchestration logic out of the route handler.
"""

from __future__ import annotations

from dataclasses import dataclass

from rag_chatbot.config.config import settings
from rag_chatbot.observability.langfuse_client import trace_operation
from rag_chatbot.utils.exception_handler import handle_service_exceptions
from rag_chatbot.utils.logger import logger

from .citation_builder import Citation, CitationBuilder
from .generator import AnswerGenerator, GeneratedAnswer
from .retriever import VectorRetriever


@dataclass
class RAGResponse:
    """Complete response from the RAG pipeline."""

    answer: str
    citations: list[dict]
    insufficient_evidence: bool
    context_chunk_count: int
    top_k_used: int


class RAGPipeline:
    """End-to-end question-answering pipeline."""

    def __init__(
        self,
        retriever: VectorRetriever,
        generator: AnswerGenerator,
        citation_builder: CitationBuilder,
    ) -> None:
        self._retriever = retriever
        self._generator = generator
        self._citation_builder = citation_builder

    @handle_service_exceptions("rag_pipeline")
    async def answer(self, question: str, top_k: int | None = None) -> RAGResponse:
        """Run the full RAG pipeline for a user question.

        Args:
            question: The natural-language question from the user.
            top_k: Override the default retrieval depth (optional).

        Returns:
            RAGResponse with answer text, citations, and metadata.
        """
        k = top_k or settings.retrieval_top_k
        question = question.strip()

        if not question:
            from rag_chatbot.utils.exception_handler import RAGError  # noqa: PLC0415

            raise RAGError("Question must not be empty.")

        async with trace_operation("rag_pipeline", {"question_len": len(question), "top_k": k}) as span:
            # Step 1: Retrieve
            logger.info("RAG pipeline: retrieving (k=%d) for question len=%d", k, len(question))
            chunks = await self._retriever.retrieve(question, top_k=k)

            # Step 2: Generate
            generated: GeneratedAnswer = await self._generator.generate(question, chunks)

            # Step 3: Citations (only when evidence was found)
            citations_raw: list[Citation] = []
            if not generated.insufficient_evidence and chunks:
                citations_raw = self._citation_builder.build(chunks)

            citations = self._citation_builder.format_for_response(citations_raw)

            span["chunk_count"] = len(chunks)
            span["insufficient_evidence"] = generated.insufficient_evidence
            span["citation_count"] = len(citations)

        logger.info(
            "RAG pipeline complete: insufficient=%s citations=%d",
            generated.insufficient_evidence,
            len(citations),
        )

        return RAGResponse(
            answer=generated.answer,
            citations=citations,
            insufficient_evidence=generated.insufficient_evidence,
            context_chunk_count=generated.context_chunk_count,
            top_k_used=k,
        )
