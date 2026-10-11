"""Gemini Embedding Provider.

Wraps langchain-google-genai's GoogleGenerativeAIEmbeddings so the rest of
the application depends on this thin adapter rather than the LangChain class
directly. Supports lazy initialisation and caching.
"""

from functools import cached_property

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from rag_chatbot.config.config import settings
from rag_chatbot.utils.logger import logger


class EmbeddingProvider:
    """Adapter around GoogleGenerativeAIEmbeddings.

    Provides a single `embeddings` property for use in the vector store and
    anywhere else an Embeddings-compatible object is required.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._model = model or settings.gemini_embedding_model
        self._api_key = api_key or settings.google_api_key.get_secret_value()

    @cached_property
    def embeddings(self) -> GoogleGenerativeAIEmbeddings:
        """Lazily construct and cache the LangChain embeddings object."""
        logger.info("Initialising Gemini embeddings model: %s", self._model)
        return GoogleGenerativeAIEmbeddings(
            model=self._model,
            google_api_key=self._api_key,  # type: ignore[arg-type]
        )


# Module-level singleton
embedding_provider = EmbeddingProvider()
