"""Chat router — question-answering endpoint.

POST /chat — accepts a question, returns a grounded answer with citations.
"""

from __future__ import annotations

from fastapi import APIRouter

from rag_chatbot.api.schemas.chat_schema import ChatRequest, ChatResponse, CitationDetail
from rag_chatbot.providers.llm_provider import llm_provider
from rag_chatbot.rag.citation_builder import CitationBuilder
from rag_chatbot.rag.generator import AnswerGenerator
from rag_chatbot.rag.pipeline import RAGPipeline
from rag_chatbot.rag.retriever import VectorRetriever
from rag_chatbot.repositories.vector_repository import vector_repository

router = APIRouter(prefix="/chat", tags=["chat"])

# Compose the RAG pipeline from its dependencies
_rag_pipeline = RAGPipeline(
    retriever=VectorRetriever(vector_repository=vector_repository),
    generator=AnswerGenerator(llm_provider=llm_provider),
    citation_builder=CitationBuilder(),
)


@router.post("", response_model=ChatResponse, summary="Ask a question against indexed documents")
async def ask(request: ChatRequest) -> ChatResponse:
    """Answer a natural-language question using the indexed document corpus.

    The response includes:
    - A concise grounded answer (or an explicit "insufficient evidence" message)
    - Source citations with file name and location metadata
    - Metadata about retrieval depth used
    """
    result = await _rag_pipeline.answer(
        question=request.question,
        top_k=request.top_k,
    )

    return ChatResponse(
        answer=result.answer,
        insufficient_evidence=result.insufficient_evidence,
        citations=[CitationDetail(**c) for c in result.citations],
        context_chunk_count=result.context_chunk_count,
        top_k_used=result.top_k_used,
    )
