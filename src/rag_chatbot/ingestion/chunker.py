"""Document chunker.

Converts ParsedChunk objects (from parsers) into LangChain Document objects
ready for embedding and vector storage.

For tabular content (Excel, CSV), ParsedChunks already carry row-range
boundaries from the parser, so they are not re-split — only wrapped.

For slide content (PPTX), each slide is one chunk by default, but long
slides are split on paragraph boundaries to avoid embedding oversized text.

A stable chunk ID (UUID v5 derived from document_id + content) is computed
for deduplication: if the same content appears in a re-uploaded file, the
existing embedding can be reused.
"""

from __future__ import annotations

import hashlib
import uuid

from langchain_core.documents import Document as LCDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag_chatbot.config.constants import (
    CSV_EXTENSIONS,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    EXCEL_EXTENSIONS,
)
from rag_chatbot.utils.logger import logger

from .parsers.base_parser import ParsedChunk

# UUID namespace for deterministic chunk IDs
_CHUNK_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # UUID v5 namespace:URL


def _stable_chunk_id(document_id: uuid.UUID, content: str) -> str:
    """Produce a deterministic UUID string from document_id + content hash."""
    seed = f"{document_id}:{hashlib.sha256(content.encode()).hexdigest()}"
    return str(uuid.uuid5(_CHUNK_NS, seed))


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


class DocumentChunker:
    """Converts ParsedChunks into LangChain Documents with stable IDs."""

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> None:
        self._text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", " ", ""],
        )

    def chunk(
        self,
        parsed_chunks: list[ParsedChunk],
        document_id: uuid.UUID,
    ) -> list[tuple[LCDocument, str, str]]:
        """Convert ParsedChunk objects to (LCDocument, chunk_id, content_hash) tuples.

        Tabular chunks (Excel / CSV) are never re-split — they already have
        appropriate row boundaries. Slide and prose content may be split further
        if it exceeds the configured chunk size.

        Args:
            parsed_chunks: Output from a format parser.
            document_id: UUID of the owning Document record.

        Returns:
            List of (LangChain Document, stable chunk ID string, SHA-256 hash)
            ordered by appearance in the source document.
        """
        result: list[tuple[LCDocument, str, str]] = []
        global_index = 0

        for parsed in parsed_chunks:
            is_tabular = parsed.file_type in (EXCEL_EXTENSIONS | CSV_EXTENSIONS)

            if is_tabular:
                # Tabular content: use as-is — do not split across row boundaries
                sub_chunks = [parsed.content]
            elif len(parsed.content) > DEFAULT_CHUNK_SIZE:
                # Long slide / prose: split on paragraph/sentence boundaries
                sub_chunks = self._text_splitter.split_text(parsed.content)
            else:
                sub_chunks = [parsed.content]

            for sub in sub_chunks:
                if not sub.strip():
                    continue

                chunk_id = _stable_chunk_id(document_id, sub)
                content_hash = _content_hash(sub)
                metadata = parsed.to_metadata()
                metadata.update(
                    {
                        "document_id": str(document_id),
                        "chunk_index": global_index,
                        "chunk_id": chunk_id,
                    }
                )

                lc_doc = LCDocument(page_content=sub, metadata=metadata)
                result.append((lc_doc, chunk_id, content_hash))
                global_index += 1

        logger.debug(
            "Chunked document_id=%s: %d parsed → %d final chunks",
            document_id,
            len(parsed_chunks),
            len(result),
        )
        return result
