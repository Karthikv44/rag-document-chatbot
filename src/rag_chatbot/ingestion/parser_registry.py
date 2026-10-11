"""Parser registry — maps file extensions to their concrete parser instances.

Acts as a factory: the rest of the application calls `get_parser(ext)` and
receives the correct BaseParser without needing to know which class handles
which format. Adding a new format requires only registering it here.
"""

from __future__ import annotations

from rag_chatbot.utils.exception_handler import UnsupportedFormatError
from rag_chatbot.utils.logger import logger

from .parsers.base_parser import BaseParser
from .parsers.csv_parser import CsvParser
from .parsers.excel_parser import ExcelParser
from .parsers.pptx_parser import PptxParser


class ParserRegistry:
    """Registry that maps file extensions to parser instances."""

    def __init__(self) -> None:
        self._parsers: dict[str, BaseParser] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        for parser in [ExcelParser(), CsvParser(), PptxParser()]:
            for ext in parser.supported_extensions:
                self._parsers[ext.lower()] = parser
                logger.debug("Registered parser %s for .%s", type(parser).__name__, ext)

    def register(self, parser: BaseParser) -> None:
        """Register a parser, overriding any existing parser for its extensions."""
        for ext in parser.supported_extensions:
            self._parsers[ext.lower()] = parser

    def get_parser(self, extension: str) -> BaseParser:
        """Return the parser for `extension` (without leading dot).

        Raises:
            UnsupportedFormatError: If no parser handles this extension.
        """
        ext = extension.lower().lstrip(".")
        parser = self._parsers.get(ext)
        if parser is None:
            raise UnsupportedFormatError(
                f"No parser registered for file extension '.{ext}'. Supported: {sorted(self._parsers.keys())}",
                details={"extension": ext},
            )
        return parser

    @property
    def supported_extensions(self) -> list[str]:
        return sorted(self._parsers.keys())


# Module-level singleton
parser_registry = ParserRegistry()
