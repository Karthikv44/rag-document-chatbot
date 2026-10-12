"""CSV parser.

Extracts headers and record rows from CSV files. Handles common encoding
variations (UTF-8, UTF-8-BOM, Latin-1) through detection fallback.
Rows are chunked into groups to keep each chunk's token count manageable.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from rag_chatbot.config.constants import CSV_EXTENSIONS, DEFAULT_TABLE_CHUNK_ROWS
from rag_chatbot.utils.exception_handler import DocumentParseError, InvalidDocumentContentError
from rag_chatbot.utils.logger import logger

from .base_parser import BaseParser, ParsedChunk

# Encodings tried in order when UTF-8 fails
_FALLBACK_ENCODINGS = ("utf-8-sig", "latin-1", "cp1252")


class CsvParser(BaseParser):
    """Parses CSV files into row-chunked ParsedChunk objects."""

    @property
    def supported_extensions(self) -> frozenset[str]:
        return CSV_EXTENSIONS

    def parse(self, file_path: Path, filename: str) -> list[ParsedChunk]:
        logger.info("Parsing CSV file: %s", filename)
        try:
            raw_bytes = file_path.read_bytes()
            text = self._decode(raw_bytes, filename)
            return self._parse_text(text, filename)
        except (DocumentParseError, InvalidDocumentContentError):
            raise
        except Exception as exc:
            raise DocumentParseError(
                f"Failed to parse CSV file {filename!r}: {exc}",
                details={"filename": filename},
            ) from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _decode(raw: bytes, filename: str) -> str:
        """Try UTF-8 first, then fall back through common encodings."""
        for enc in ("utf-8", *_FALLBACK_ENCODINGS):
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        raise DocumentParseError(f"Cannot decode CSV file {filename!r} with any known encoding.")

    def _parse_text(self, text: str, filename: str) -> list[ParsedChunk]:
        reader = csv.reader(io.StringIO(text))
        all_rows = list(reader)

        if not all_rows:
            raise InvalidDocumentContentError(f"CSV file {filename!r} is empty.")

        header_row = all_rows[0]
        headers = [h.strip() for h in header_row]
        data_rows = all_rows[1:]

        if not any(h for h in headers):
            raise InvalidDocumentContentError(f"CSV file {filename!r} has no column headers.")

        chunks: list[ParsedChunk] = []
        chunk_size = DEFAULT_TABLE_CHUNK_ROWS

        if not data_rows:
            # Header-only CSV
            content = f"Columns: {' | '.join(headers)}"
            return [
                ParsedChunk(
                    content=content,
                    source_filename=filename,
                    file_type="csv",
                    row_range_start=1,
                    row_range_end=1,
                )
            ]

        for i in range(0, len(data_rows), chunk_size):
            batch = data_rows[i : i + chunk_size]
            # 1-indexed (header = row 1, first data row = row 2)
            row_start = i + 2
            row_end = i + len(batch) + 1

            lines = [f"Rows: {row_start}-{row_end}", f"Columns: {' | '.join(headers)}", ""]
            for row in batch:
                # Pad short rows to match header length
                cells = list(row) + [""] * (len(headers) - len(row))
                lines.append(" | ".join(str(c).strip() for c in cells))

            chunks.append(
                ParsedChunk(
                    content="\n".join(lines),
                    source_filename=filename,
                    file_type="csv",
                    row_range_start=row_start,
                    row_range_end=row_end,
                )
            )

        if not chunks:
            raise InvalidDocumentContentError(f"CSV file {filename!r} produced no content chunks.")

        logger.debug("CSV %r: %d chunks from %d data rows", filename, len(chunks), len(data_rows))
        return chunks
