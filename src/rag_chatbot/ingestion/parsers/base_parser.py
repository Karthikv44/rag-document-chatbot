"""Base parser interface.

All format-specific parsers implement BaseParser so they are substitutable
(LSP) and can be selected by the parser registry (OCP).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedChunk:
    """A single extracted content unit from a document.

    All metadata fields are optional because they are format-specific.
    Fields not applicable to the format remain None.
    """

    content: str
    """The text content of this chunk."""

    source_filename: str
    """Original uploaded filename."""

    file_type: str
    """File extension without dot (e.g. 'xlsx', 'csv', 'pptx')."""

    # Excel / CSV specific
    sheet_name: str | None = None
    row_range_start: int | None = None
    row_range_end: int | None = None

    # PowerPoint specific
    slide_number: int | None = None
    slide_title: str | None = None

    # Additional free-form metadata
    extra: dict = field(default_factory=dict)

    def to_metadata(self) -> dict:
        """Return a flat metadata dict suitable for LangChain Document metadata."""
        meta: dict = {
            "source_filename": self.source_filename,
            "file_type": self.file_type,
        }
        if self.sheet_name is not None:
            meta["sheet_name"] = self.sheet_name
        if self.row_range_start is not None:
            meta["row_range_start"] = self.row_range_start
        if self.row_range_end is not None:
            meta["row_range_end"] = self.row_range_end
        if self.slide_number is not None:
            meta["slide_number"] = self.slide_number
        if self.slide_title is not None:
            meta["slide_title"] = self.slide_title
        meta.update(self.extra)
        return meta


class BaseParser(ABC):
    """Abstract base for format-specific document parsers.

    Concrete implementations must be stateless — they receive a file path
    and filename, and return a list of ParsedChunk objects.
    """

    @abstractmethod
    def parse(self, file_path: Path, filename: str) -> list[ParsedChunk]:
        """Extract content chunks from the file at `file_path`.

        Args:
            file_path: Path to a local (temp) copy of the file.
            filename: Original uploaded filename for metadata attribution.

        Returns:
            List of ParsedChunk objects. Must not be empty for a valid file.

        Raises:
            DocumentParseError: If the file cannot be parsed.
            InvalidDocumentContentError: If parsed content is structurally empty.
        """

    @property
    @abstractmethod
    def supported_extensions(self) -> frozenset[str]:
        """Set of lowercase file extensions this parser handles (without dot)."""
