"""File upload validator.

Validates uploaded files before parsing begins:
- Extension must be in the allowed set
- File size must not exceed the configured limit
- Basic magic-byte check where possible (non-blocking if python-magic unavailable)
- File content must not be empty
"""

from __future__ import annotations

from rag_chatbot.config.config import settings
from rag_chatbot.config.constants import ALL_SUPPORTED_EXTENSIONS
from rag_chatbot.utils.exception_handler import FileSizeExceededError, UnsupportedFormatError
from rag_chatbot.utils.logger import logger


class FileValidator:
    """Validates uploaded file bytes and metadata before parsing."""

    def validate(
        self,
        filename: str,
        data: bytes,
        *,
        check_magic: bool = True,
    ) -> str:
        """Validate the file and return its normalised extension.

        Args:
            filename: Original uploaded filename (used to extract extension).
            data: Raw file bytes.
            check_magic: Whether to attempt magic-byte MIME validation.

        Returns:
            Lowercase extension string without dot (e.g. "xlsx").

        Raises:
            UnsupportedFormatError: Extension not supported or empty file.
            FileSizeExceededError:  File exceeds MAX_FILE_SIZE_MB.
        """
        # --- Empty file ---
        if not data:
            raise UnsupportedFormatError(
                f"Uploaded file {filename!r} is empty.",
                details={"filename": filename},
            )

        # --- File size ---
        size = len(data)
        if size > settings.max_file_size_bytes:
            raise FileSizeExceededError(
                f"File {filename!r} is {size / (1024 * 1024):.1f} MB, "
                f"which exceeds the {settings.max_file_size_mb} MB limit.",
                details={"filename": filename, "size_bytes": size},
            )

        # --- Extension ---
        if "." not in filename:
            raise UnsupportedFormatError(
                f"File {filename!r} has no extension.",
                details={"filename": filename},
            )
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext not in ALL_SUPPORTED_EXTENSIONS:
            raise UnsupportedFormatError(
                f"File extension '.{ext}' is not supported. Supported formats: {sorted(ALL_SUPPORTED_EXTENSIONS)}",
                details={"filename": filename, "extension": ext},
            )

        # --- Optional magic-byte check ---
        if check_magic:
            self._check_magic(data, filename, ext)

        logger.debug("File %r validated: ext=%s size=%d bytes", filename, ext, size)
        return ext

    @staticmethod
    def _check_magic(data: bytes, filename: str, declared_ext: str) -> None:
        """Best-effort MIME check. Logs a warning on mismatch but does not block."""
        try:
            import magic  # noqa: PLC0415

            mime = magic.from_buffer(data[:2048], mime=True)
            logger.debug("Magic MIME for %r: %s", filename, mime)

            # Map known problematic mismatches
            suspicious = False
            if declared_ext in {"xlsx", "pptx"} and not (
                "zip" in mime or "officedocument" in mime or "octet-stream" in mime
            ):
                suspicious = True
            if declared_ext == "csv" and "text" not in mime and "csv" not in mime:
                suspicious = True

            if suspicious:
                logger.warning(
                    "MIME mismatch for %r: declared ext=%s but magic reports %s. Proceeding with caution.",
                    filename,
                    declared_ext,
                    mime,
                )
        except ImportError:
            # python-magic not available (e.g. missing libmagic on Windows) — skip silently
            logger.debug("python-magic not available; skipping magic-byte check for %r", filename)
        except Exception as exc:
            logger.debug("Magic check failed for %r: %s", filename, exc)


# Module-level singleton
file_validator = FileValidator()
