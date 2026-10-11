# syntax=docker/dockerfile:1
# Multi-stage build using uv for fast, reproducible installs.
# Stage 1: install dependencies
# Stage 2: minimal runtime image

ARG PYTHON_VERSION=3.13
ARG UV_VERSION=0.9

FROM ghcr.io/astral-sh/uv:${UV_VERSION}-python${PYTHON_VERSION}-alpine AS uv

FROM python:${PYTHON_VERSION}-slim AS build

ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY --from=uv /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app

# Install OS deps needed by python-magic (libmagic) and psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install runtime deps (no dev group, frozen lockfile)
RUN uv sync --frozen --no-dev --no-cache

# Copy application source
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PORT=8000

EXPOSE ${PORT}

ENTRYPOINT []
CMD ["app"]
