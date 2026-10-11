"""Vector repository.

Wraps langchain-postgres PGVector for storing and searching chunk embeddings.
Keeps the vector-store concern isolated from the rest of the application.
"""

from __future__ import annotations

import uuid
from typing import Any

from langchain_core.documents import Document as LCDocument
from langchain_postgres import PGVector

from rag_chatbot.config.config import settings
from rag_chatbot.config.constants import VECTOR_COLLECTION_NAME
from rag_chatbot.providers.embedding_provider import embedding_provider
from rag_chatbot.utils.exception_handler import VectorStoreError
from rag_chatbot.utils.logger import logger


class VectorRepository:
    """Manages pgvector storage and similarity search for chunk embeddings.

    Uses a sync PostgreSQL connection string for PGVector initialisation
    (langchain-postgres requires psycopg3 sync connection for setup)
    and async-compatible search calls.
    """

    def __init__(self) -> None:
        self._store: PGVector | None = None

    def _get_store(self) -> PGVector:
        """Lazily initialise the PGVector store."""
        if self._store is None:
            logger.info("Initialising PGVector store (collection=%s)", VECTOR_COLLECTION_NAME)
            try:
                self._store = PGVector(
                    embeddings=embedding_provider.embeddings,
                    collection_name=VECTOR_COLLECTION_NAME,
                    connection=settings.sync_database_url,
                    use_jsonb=True,
                )
            except Exception as exc:
                raise VectorStoreError(f"Failed to initialise vector store: {exc}") from exc
        return self._store

    def add_documents(self, documents: list[LCDocument], ids: list[str]) -> None:
        """Embed and store a list of LangChain Documents.

        Args:
            documents: LangChain Document objects with page_content and metadata.
            ids: Stable string IDs (UUID strings from Chunk.id) for deduplication.
        """
        try:
            store = self._get_store()
            store.add_documents(documents, ids=ids)
            logger.info("Added %d documents to vector store", len(documents))
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError(f"Failed to add documents to vector store: {exc}") from exc

    def delete_by_ids(self, ids: list[str]) -> None:
        """Remove vectors by their string IDs."""
        if not ids:
            return
        try:
            store = self._get_store()
            store.delete(ids=ids)
            logger.info("Deleted %d vectors from vector store", len(ids))
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError(f"Failed to delete from vector store: {exc}") from exc  # noqa: S608

    def similarity_search(
        self,
        query: str,
        k: int | None = None,
        filter: dict[str, Any] | None = None,  # noqa: A002
    ) -> list[LCDocument]:
        """Perform a cosine similarity search.

        Args:
            query: The question text (will be embedded on the fly).
            k: Number of results; defaults to settings.retrieval_top_k.
            filter: Optional metadata filter dict passed to PGVector.

        Returns:
            List of LangChain Documents ordered by relevance.
        """
        top_k = k or settings.retrieval_top_k
        try:
            store = self._get_store()
            results = store.similarity_search(query, k=top_k, filter=filter)
            logger.debug("Similarity search returned %d chunks for query (k=%d)", len(results), top_k)
            return results
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError(f"Similarity search failed: {exc}") from exc

    def as_retriever(self, k: int | None = None) -> Any:
        """Return a LangChain Retriever for use in LCEL chains."""
        top_k = k or settings.retrieval_top_k
        store = self._get_store()
        return store.as_retriever(search_kwargs={"k": top_k})

    def delete_by_document_id(self, document_id: uuid.UUID) -> None:
        """Remove all vectors whose metadata.document_id matches."""
        try:
            store = self._get_store()
            # PGVector supports metadata filtering on delete via filter dict
            store.delete(filter={"document_id": str(document_id)})
            logger.info("Deleted vectors for document_id=%s", document_id)
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError(f"Failed to delete vectors for document_id={document_id}: {exc}") from exc


# Module-level singleton
vector_repository = VectorRepository()
