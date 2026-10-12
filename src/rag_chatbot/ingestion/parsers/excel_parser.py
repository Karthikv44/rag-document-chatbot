"""Excel parser (.xlsx and .xls).

Extracts sheet names, headers, and row data from Excel workbooks.
Each sheet is chunked into groups of rows (preserving the header on every
chunk) so that tabular context is never lost across chunk boundaries.

- .xlsx files: parsed with openpyxl (data_only=True to get cached values)
- .xls files:  parsed with xlrd
"""

from __future__ import annotations

from pathlib import Path

from rag_chatbot.config.constants import DEFAULT_TABLE_CHUNK_ROWS, EXCEL_EXTENSIONS
from rag_chatbot.utils.exception_handler import DocumentParseError, InvalidDocumentContentError
from rag_chatbot.utils.logger import logger

from .base_parser import BaseParser, ParsedChunk


class ExcelParser(BaseParser):
    """Parses Excel workbooks into row-chunked ParsedChunk objects."""

    @property
    def supported_extensions(self) -> frozenset[str]:
        return EXCEL_EXTENSIONS

    def parse(self, file_path: Path, filename: str) -> list[ParsedChunk]:  # noqa: C901
        ext = file_path.suffix.lstrip(".").lower()
        logger.info("Parsing Excel file: %s (ext=%s)", filename, ext)

        try:
            if ext == "xlsx":
                return self._parse_xlsx(file_path, filename)
            elif ext == "xls":
                return self._parse_xls(file_path, filename)
            else:
                raise DocumentParseError(f"ExcelParser does not support extension: .{ext}")
        except (DocumentParseError, InvalidDocumentContentError):
            raise
        except Exception as exc:
            raise DocumentParseError(
                f"Failed to parse Excel file {filename!r}: {exc}",
                details={"filename": filename, "ext": ext},
            ) from exc

    # ------------------------------------------------------------------
    # xlsx parsing (openpyxl)
    # ------------------------------------------------------------------

    def _parse_xlsx(self, file_path: Path, filename: str) -> list[ParsedChunk]:
        import openpyxl  # noqa: PLC0415

        try:
            wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
        except Exception as exc:
            raise DocumentParseError(f"Cannot open .xlsx file {filename!r}: {exc}") from exc

        chunks: list[ParsedChunk] = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            sheet_chunks = self._rows_to_chunks(rows, sheet_name, filename, "xlsx")
            chunks.extend(sheet_chunks)

        wb.close()
        self._validate_chunks(chunks, filename)
        return chunks

    # ------------------------------------------------------------------
    # xls parsing (xlrd)
    # ------------------------------------------------------------------

    def _parse_xls(self, file_path: Path, filename: str) -> list[ParsedChunk]:
        try:
            import xlrd  # noqa: PLC0415
        except ImportError as exc:
            raise DocumentParseError("xlrd is required for .xls files. It is listed in dependencies.") from exc

        try:
            wb = xlrd.open_workbook(str(file_path))
        except Exception as exc:
            raise DocumentParseError(f"Cannot open .xls file {filename!r}: {exc}") from exc

        chunks: list[ParsedChunk] = []
        for sheet_name in wb.sheet_names():
            ws = wb.sheet_by_name(sheet_name)
            rows = [tuple(ws.cell_value(r, c) for c in range(ws.ncols)) for r in range(ws.nrows)]
            sheet_chunks = self._rows_to_chunks(rows, sheet_name, filename, "xls")
            chunks.extend(sheet_chunks)

        self._validate_chunks(chunks, filename)
        return chunks

    # ------------------------------------------------------------------
    # Shared chunking logic
    # ------------------------------------------------------------------

    def _rows_to_chunks(
        self,
        rows: list[tuple],
        sheet_name: str,
        filename: str,
        file_type: str,
    ) -> list[ParsedChunk]:
        """Convert raw rows into ParsedChunks, preserving header context."""
        if not rows:
            return []

        # First non-empty row is treated as the header
        header_row = rows[0]
        headers = [str(c) if c is not None else "" for c in header_row]
        data_rows = rows[1:]

        if not data_rows:
            # Sheet has only a header — still produce one chunk
            content = "Sheet: {}\nHeaders: {}".format(sheet_name, " | ".join(headers))
            return [
                ParsedChunk(
                    content=content,
                    source_filename=filename,
                    file_type=file_type,
                    sheet_name=sheet_name,
                    row_range_start=1,
                    row_range_end=1,
                )
            ]

        chunks: list[ParsedChunk] = []
        chunk_size = DEFAULT_TABLE_CHUNK_ROWS

        for i in range(0, len(data_rows), chunk_size):
            batch = data_rows[i : i + chunk_size]
            # 1-indexed row numbers (row 1 = header, data starts at row 2)
            row_start = i + 2
            row_end = i + len(batch) + 1

            lines = [
                f"Sheet: {sheet_name}",
                f"Rows: {row_start}-{row_end}",
                f"Columns: {' | '.join(headers)}",
                "",
            ]
            for row in batch:
                cells = [str(c) if c is not None else "" for c in row]
                lines.append(" | ".join(cells))

            chunks.append(
                ParsedChunk(
                    content="\n".join(lines),
                    source_filename=filename,
                    file_type=file_type,
                    sheet_name=sheet_name,
                    row_range_start=row_start,
                    row_range_end=row_end,
                )
            )

        return chunks

    @staticmethod
    def _validate_chunks(chunks: list[ParsedChunk], filename: str) -> None:
        if not chunks:
            raise InvalidDocumentContentError(
                f"Excel file {filename!r} produced no extractable content. "
                "The workbook may be empty or contain only hidden sheets."
            )
        total_content = sum(len(c.content.strip()) for c in chunks)
        if total_content == 0:
            raise InvalidDocumentContentError(f"Excel file {filename!r} contains no readable cell values.")
