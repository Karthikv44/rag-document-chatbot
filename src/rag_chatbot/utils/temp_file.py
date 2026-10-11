"""Secure temporary file management.

Provides a context manager that writes upload bytes to a named temp file,
yields the path, and guarantees cleanup on exit — even on exception.
"""

import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path


@asynccontextmanager
async def temp_upload_file(
    data: bytes,
    suffix: str = "",
    prefix: str = "rag_upload_",
) -> AsyncGenerator[Path]:
    """Write `data` to a secure temporary file and yield its Path.

    The file is deleted on context exit regardless of success or failure.

    Args:
        data: Raw file bytes to write.
        suffix: File suffix, e.g. ".xlsx".
        prefix: Filename prefix for easy identification in logs.

    Yields:
        pathlib.Path to the temporary file.
    """
    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix,
        prefix=prefix,
        mode="wb",
    )
    try:
        tmp.write(data)
        tmp.flush()
        tmp.close()
        yield Path(tmp.name)
    finally:
        path = Path(tmp.name)
        if path.exists():
            path.unlink(missing_ok=True)
