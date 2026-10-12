"""Shared constants used across all modules.

Centralises enums, defaults, endpoint paths, and tool/operation names
so they are never duplicated across the codebase.
"""

from enum import StrEnum

# =============================================================================
# SUPPORTED FILE TYPES
# =============================================================================


class FileType(StrEnum):
    """Supported document file extensions."""

    XLSX = "xlsx"
    XLS = "xls"
    CSV = "csv"
    PPT = "ppt"
    PPTX = "pptx"


EXCEL_EXTENSIONS: frozenset[str] = frozenset({FileType.XLSX, FileType.XLS})
CSV_EXTENSIONS: frozenset[str] = frozenset({FileType.CSV})
PPTX_EXTENSIONS: frozenset[str] = frozenset({FileType.PPT, FileType.PPTX})
ALL_SUPPORTED_EXTENSIONS: frozenset[str] = EXCEL_EXTENSIONS | CSV_EXTENSIONS | PPTX_EXTENSIONS

MIME_TYPE_MAP: dict[str, str] = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": FileType.XLSX,
    "application/vnd.ms-excel": FileType.XLS,
    "text/csv": FileType.CSV,
    "application/csv": FileType.CSV,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": FileType.PPTX,
    "application/vnd.ms-powerpoint": FileType.PPT,
}


# =============================================================================
# DOCUMENT / INGESTION STATUS
# =============================================================================


class IngestionStatus(StrEnum):
    """Lifecycle states for a document ingestion job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


# =============================================================================
# CHUNKING DEFAULTS
# =============================================================================

# Maximum characters per text chunk for non-tabular content
DEFAULT_CHUNK_SIZE: int = 600
DEFAULT_CHUNK_OVERLAP: int = 60

# Maximum rows per table chunk (preserves header context per chunk)
DEFAULT_TABLE_CHUNK_ROWS: int = 30

# =============================================================================
# RETRIEVAL DEFAULTS
# =============================================================================

DEFAULT_RETRIEVAL_TOP_K: int = 5
MAX_RETRIEVAL_TOP_K: int = 20

# =============================================================================
# EMBEDDING
# =============================================================================

DEFAULT_EMBEDDING_MODEL: str = "models/gemini-embedding-001"
DEFAULT_EMBEDDING_DIMENSIONS: int = 768

# =============================================================================
# LLM
# =============================================================================

DEFAULT_LLM_MODEL: str = "gemini-2.0-flash"
DEFAULT_LLM_TEMPERATURE: float = 0.1
DEFAULT_LLM_MAX_TOKENS: int = 2048

# =============================================================================
# FILE UPLOAD LIMITS
# =============================================================================

DEFAULT_MAX_FILE_SIZE_MB: int = 50
DEFAULT_MAX_FILES_PER_REQUEST: int = 10

# =============================================================================
# OPERATION NAMES (for decorator logging and Langfuse spans)
# =============================================================================

OP_INGEST_FILE = "ingest_file"
OP_PARSE_DOCUMENT = "parse_document"
OP_CHUNK_DOCUMENT = "chunk_document"
OP_EMBED_CHUNKS = "embed_chunks"
OP_INDEX_CHUNKS = "index_chunks"
OP_RETRIEVE = "retrieve"
OP_GENERATE = "generate"
OP_BUILD_CITATIONS = "build_citations"
OP_RAG_PIPELINE = "rag_pipeline"

# =============================================================================
# API
# =============================================================================

API_PREFIX = "/api/v1"
HEALTH_ENDPOINT = "/healthz"
READINESS_ENDPOINT = "/readyz"

# =============================================================================
# VECTOR STORE
# =============================================================================

VECTOR_COLLECTION_NAME: str = "rag_chunks"

# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

INSUFFICIENT_EVIDENCE_PHRASE: str = (
    "The indexed documents do not contain sufficient information to answer this question."
)

SYSTEM_PROMPT_TEMPLATE: str = """You are a helpful assistant for Acme Retail. \
Answer the user's question using ONLY the information provided in the context below. \
Do not fabricate facts, numbers, file names, sheet names, or slide references that are not present in the context.

If the context does not contain enough information to answer, respond with exactly:
"{insufficient_phrase}"

Context:
{{context}}
"""
