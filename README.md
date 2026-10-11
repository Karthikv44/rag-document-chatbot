# Acme Retail — Multi-Format RAG Document Chatbot

A production-oriented Retrieval-Augmented Generation (RAG) chatbot that ingests
Excel, CSV, and PowerPoint files and answers natural-language questions with
grounded, source-cited responses.

---

## Architecture overview

```
┌──────────────┐    HTTP     ┌─────────────────────────────────────────────┐
│  Streamlit   │ ──────────► │  FastAPI Backend                            │
│  UI          │             │  /api/v1/ingest   /api/v1/chat              │
└──────────────┘             └───────────┬─────────────────────────────────┘
                                         │
               ┌─────────────────────────┼──────────────────────────┐
               │                         │                          │
    ┌──────────▼──────────┐   ┌──────────▼──────────┐   ┌──────────▼──────────┐
    │  Ingestion Pipeline │   │   RAG Pipeline       │   │  PostgreSQL          │
    │  - FileValidator    │   │  - VectorRetriever   │   │  + pgvector          │
    │  - Parsers          │   │  - AnswerGenerator   │   │  (documents, chunks, │
    │    Excel/CSV/PPTX   │   │  - CitationBuilder   │   │   embeddings)        │
    │  - Chunker          │   └──────────────────────┘   └──────────────────────┘
    │  - EmbeddingProvider│             │
    └─────────────────────┘             │
               │                        ▼
               │           ┌────────────────────────┐
               └──────────►│  Google Gemini API      │
                           │  (embeddings + LLM)     │
                           └────────────────────────┘
                                        │
                           ┌────────────▼────────────┐
                           │  Langfuse               │
                           │  (tracing, observability)│
                           └─────────────────────────┘
```

---

## Technology stack

| Component | Package |
|---|---|
| Backend | FastAPI + Uvicorn |
| RAG framework | LangChain (langchain-core, langchain-google-genai) |
| Vector store | langchain-postgres (PGVector) |
| LLM | Google Gemini (`gemini-2.0-flash` default, configurable) |
| Embeddings | Google Gemini (`models/gemini-embedding-001`, 768 dims) |
| Database | PostgreSQL 16 + pgvector |
| ORM | SQLAlchemy async + asyncpg |
| Migrations | Alembic |
| Parsers | openpyxl, xlrd, python-pptx |
| Observability | Langfuse |
| UI | Streamlit |
| Package manager | uv |
| Code quality | Ruff + pre-commit |

---

## Prerequisites

- [uv](https://docs.astral.sh/uv/) ≥ 0.9
- Python 3.13
- PostgreSQL 16 with the [pgvector](https://github.com/pgvector/pgvector) extension **OR** Docker + Docker Compose
- A [Google AI Studio](https://aistudio.google.com/) API key (free tier is sufficient for development)
- *(Optional)* A [Langfuse](https://langfuse.com/) account for tracing

---

## Quick start (Docker Compose — recommended)

```bash
# 1. Clone and enter the project
cd rag-usecase

# 2. Copy and configure the environment file
cp .env.example .env
# Edit .env — set GOOGLE_API_KEY, API_KEY, and POSTGRES_PASSWORD at minimum

# 3. Start all services (PostgreSQL, API, Streamlit UI)
docker compose up --build

# 4. Open the UI
#    Streamlit:  http://localhost:8501
#    API docs:   http://localhost:8000/api/v1/docs
```

---

## Local development setup

### 1. Install uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Create the virtual environment and install dependencies

```bash
uv sync
```

This creates `.venv/` and installs all runtime + dev dependencies from `uv.lock`.

### 3. Set up environment variables

```bash
cp .env.example .env
# Fill in required values — see comments in .env.example
```

**Minimum required values in `.env`:**
```
GOOGLE_API_KEY=<your-google-ai-api-key>
API_KEY=<any-random-string-you-choose>
POSTGRES_PASSWORD=<your-postgres-password>
```

### 4. Start PostgreSQL with pgvector

Using Docker (easiest):
```bash
docker run -d \
  --name rag-postgres \
  -e POSTGRES_DB=rag_chatbot \
  -e POSTGRES_USER=rag_user \
  -e POSTGRES_PASSWORD=changeme \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

Or use an existing PostgreSQL instance with the `vector` extension installed:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 5. Run database migrations

```bash
uv run alembic upgrade head
```

*(On first startup, the API also auto-creates tables for convenience in development.)*

### 6. Start the API backend

```bash
uv run app
# or
uv run uvicorn rag_chatbot.main:app --reload
```

API available at: `http://localhost:8000`
Interactive docs: `http://localhost:8000/api/v1/docs`

### 7. Start the Streamlit UI (separate terminal)

```bash
uv run streamlit run ui/app.py
```

UI available at: `http://localhost:8501`

---

## API reference

All endpoints require the `X-API-Key` header.

### Upload and index files

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "X-API-Key: your-api-key" \
  -F "files=@sales_q1.xlsx" \
  -F "files=@customer_sales.csv" \
  -F "files=@q1_business_review.pptx"
```

### Ask a question

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"question": "What was the South region revenue in Q1?", "top_k": 5}'
```

### List indexed documents

```bash
curl http://localhost:8000/api/v1/ingest/documents \
  -H "X-API-Key: your-api-key"
```

### Health and readiness

```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz
```

---

## Configuration reference

All settings are loaded from environment variables (`.env` file in local dev).
See `.env.example` for the complete list with descriptions.

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_API_KEY` | ✅ | — | Google AI Studio API key |
| `API_KEY` | ✅ | — | `X-API-Key` header value |
| `POSTGRES_PASSWORD` | ✅ | — | PostgreSQL password |
| `GEMINI_LLM_MODEL` | | `gemini-2.0-flash` | LLM model identifier |
| `GEMINI_EMBEDDING_MODEL` | | `models/gemini-embedding-001` | Embedding model |
| `RETRIEVAL_TOP_K` | | `5` | Chunks retrieved per question |
| `LANGFUSE_ENABLED` | | `true` | Enable/disable Langfuse tracing |
| `LANGFUSE_PUBLIC_KEY` | | — | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | | — | Langfuse secret key |
| `MAX_FILE_SIZE_MB` | | `50` | Per-file upload size limit |

---

## Code quality

### Ruff linting and formatting

```bash
# Lint (with auto-fix)
uv run ruff check --fix .

# Format
uv run ruff format .
```

### Pre-commit hooks

```bash
# Install hooks
uv run pre-commit install

# Run all hooks manually
uv run pre-commit run --all-files
```

---

## Project structure

```
rag-usecase/
├── src/rag_chatbot/
│   ├── main.py                    # FastAPI app factory + entry point
│   ├── api/
│   │   ├── routers/
│   │   │   ├── ingest_router.py   # POST /ingest, GET /documents
│   │   │   └── chat_router.py     # POST /chat
│   │   └── schemas/               # Pydantic request/response models
│   ├── config/
│   │   ├── config.py              # Settings (pydantic-settings)
│   │   └── constants.py           # Enums, defaults, operation names
│   ├── ingestion/
│   │   ├── pipeline.py            # IngestionPipeline orchestrator
│   │   ├── parsers/               # Excel, CSV, PPTX parsers
│   │   ├── parser_registry.py     # Parser factory / registry
│   │   ├── chunker.py             # Format-aware document chunker
│   │   └── file_validator.py      # Extension, size, MIME validation
│   ├── rag/
│   │   ├── pipeline.py            # RAGPipeline orchestrator
│   │   ├── retriever.py           # VectorRetriever
│   │   ├── generator.py           # AnswerGenerator (LCEL chain)
│   │   └── citation_builder.py    # CitationBuilder
│   ├── providers/
│   │   ├── embedding_provider.py  # GoogleGenerativeAIEmbeddings adapter
│   │   └── llm_provider.py        # ChatGoogleGenerativeAI adapter
│   ├── repositories/
│   │   ├── document_repository.py # Documents + chunks DB operations
│   │   └── vector_repository.py   # PGVector operations
│   ├── db/
│   │   ├── session.py             # Async SQLAlchemy engine + session
│   │   └── models.py              # Document, Chunk ORM models
│   ├── observability/
│   │   └── langfuse_client.py     # Langfuse callback + trace_operation
│   └── utils/
│       ├── exception_handler.py   # RAGError hierarchy + decorators
│       ├── logger.py              # Structured logger
│       └── temp_file.py           # Secure temp file context manager
├── ui/
│   └── app.py                     # Streamlit chatbot UI
├── alembic/                       # Database migration scripts
├── Dockerfile
├── docker-compose.yaml
├── pyproject.toml
├── .pre-commit-config.yaml
├── .env.example
└── README.md
```

---

## Supported file formats

| Format | Extensions | Notes |
|---|---|---|
| Excel | `.xlsx`, `.xls` | Sheet names, headers, rows, cached formula values |
| CSV | `.csv` | Headers, records, encoding auto-detection |
| PowerPoint | `.pptx` | Slide titles, text, tables, speaker notes |
| PowerPoint (legacy) | `.ppt` | ❌ Not supported — convert to `.pptx` first |

---

## Observability with Langfuse

When `LANGFUSE_ENABLED=true` and keys are configured, the following operations
are automatically traced:

- `ingest_file` → includes parse, chunk, embed, index sub-spans
- `rag_pipeline` → includes retrieve and generate sub-spans
- LangChain LLM calls → captured automatically via `CallbackHandler`

Set `LANGFUSE_ENABLED=false` to run without Langfuse (e.g. purely local dev).

---

## Known limitations and deployment notes

1. **Authentication**: The current `X-API-Key` header is a single shared key (Option B).
   For multi-user production deployments, replace with OAuth2/JWT and add a `user_id`
   foreign key to the `documents` table.

2. **Legacy `.ppt` files**: python-pptx does not support the legacy binary format.
   Convert to `.pptx` using Microsoft PowerPoint or LibreOffice before uploading.

3. **PGVector sync driver**: `langchain-postgres` uses a synchronous psycopg3 connection
   for vector store operations. These are wrapped in `asyncio.get_event_loop().run_in_executor`
   to avoid blocking the async event loop.

4. **Production hardening**: Before production deployment:
   - Set `APP_ENV=production` (disables CORS wildcard, disables SQL echo)
   - Run Alembic migrations rather than relying on `create_tables()` at startup
   - Configure a secrets manager for `GOOGLE_API_KEY` and `POSTGRES_PASSWORD`
   - Set resource limits on Docker containers
   - Configure TLS termination in front of the API

5. **Gemini model names**: Model identifiers change over time. The configured default
   (`gemini-2.0-flash`) was verified against LangChain documentation in October 2026.
   Check [ai.google.dev](https://ai.google.dev/gemini-api/docs/models) if you encounter
   `404 model not found` errors and update `GEMINI_LLM_MODEL` accordingly.
