"""Answer generator.

Builds the grounded answer using:
  - Retrieved chunks as the sole context source
  - A structured system prompt that forbids hallucination
  - ChatGoogleGenerativeAI via LangChain LCEL
  - Langfuse CallbackHandler for automatic LLM span tracing

The generator explicitly detects the "insufficient evidence" condition so
the API layer can flag it correctly without string-matching the LLM output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate

from rag_chatbot.config.constants import INSUFFICIENT_EVIDENCE_PHRASE
from rag_chatbot.observability.langfuse_client import get_langfuse_callback, trace_operation
from rag_chatbot.providers.llm_provider import LLMProvider
from rag_chatbot.utils.exception_handler import LLMGenerationError, handle_service_exceptions
from rag_chatbot.utils.logger import logger

from .retriever import RetrievedChunk

_SYSTEM_TEMPLATE = (
    "You are a helpful assistant for Acme Retail. "
    "Answer the user's question using ONLY the information provided in the context below. "
    "Do not fabricate facts, numbers, file names, sheet names, row numbers, or slide references "
    "that are not explicitly present in the context.\n\n"
    "If the context does not contain sufficient information to answer, respond with exactly:\n"
    f'"{INSUFFICIENT_EVIDENCE_PHRASE}"\n\n'
    "Context:\n{context}"
)

_HUMAN_TEMPLATE = "{question}"


@dataclass
class GeneratedAnswer:
    """The structured result of one RAG generation call."""

    answer: str
    insufficient_evidence: bool
    context_chunk_count: int


class AnswerGenerator:
    """Generates grounded answers from retrieved context using Gemini."""

    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm_provider = llm_provider
        self._output_parser = StrOutputParser()

    def _build_chain(self) -> Any:  # noqa: ANN401
        """Build the LCEL chain. Called lazily so the LLM is not instantiated at import."""
        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(_SYSTEM_TEMPLATE),
                HumanMessagePromptTemplate.from_template(_HUMAN_TEMPLATE),
            ]
        )
        return prompt | self._llm_provider.llm | self._output_parser

    @handle_service_exceptions("generate")
    async def generate(
        self,
        question: str,
        retrieved_chunks: list[RetrievedChunk],
    ) -> GeneratedAnswer:
        """Generate an answer grounded in the retrieved chunks.

        Args:
            question: The user's original question.
            retrieved_chunks: Chunks returned by the retriever.

        Returns:
            GeneratedAnswer with the text, insufficient-evidence flag, and chunk count.
        """
        if not retrieved_chunks:
            logger.info("No chunks retrieved; returning insufficient-evidence response.")
            return GeneratedAnswer(
                answer=INSUFFICIENT_EVIDENCE_PHRASE,
                insufficient_evidence=True,
                context_chunk_count=0,
            )

        # Build context string — treat retrieved content as untrusted user data.
        # Wrap each chunk with a clear delimiter so it cannot inject system-level
        # instructions that override the prompt above.
        context_parts = []
        for i, chunk in enumerate(retrieved_chunks, 1):
            loc = chunk.location_label()
            context_parts.append(f"[Source {i}: {loc}]\n{chunk.content}\n[End Source {i}]")
        context = "\n\n".join(context_parts)

        async with trace_operation(
            "generate",
            {"question_len": len(question), "chunk_count": len(retrieved_chunks)},
        ) as span:
            try:
                chain = self._build_chain()

                # Attach Langfuse callback if available
                callbacks = [cb for cb in [get_langfuse_callback()] if cb is not None]
                config = {"callbacks": callbacks} if callbacks else {}

                answer: str = await chain.ainvoke(
                    {"context": context, "question": question},
                    config=config,
                )
                answer = answer.strip()
                span["answer_len"] = len(answer)

            except Exception as exc:
                raise LLMGenerationError(
                    f"LLM generation failed: {exc}",
                    details={"question_len": len(question)},
                ) from exc

        insufficient = INSUFFICIENT_EVIDENCE_PHRASE.lower() in answer.lower()

        logger.info(
            "Generated answer (len=%d, insufficient=%s, chunks=%d)",
            len(answer),
            insufficient,
            len(retrieved_chunks),
        )

        return GeneratedAnswer(
            answer=answer,
            insufficient_evidence=insufficient,
            context_chunk_count=len(retrieved_chunks),
        )
