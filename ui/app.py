"""Streamlit chatbot UI.

Communicates with the FastAPI backend via httpx. All business logic
(parsing, embedding, retrieval, generation) remains in the backend.
This file is intentionally thin — it only handles UI state and HTTP calls.

Run with:
    uv run streamlit run ui/app.py
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import streamlit as st
from dotenv import load_dotenv

# Load .env file from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE_URL = os.getenv("RAG_API_URL", "http://localhost:8000/api/v1")
API_KEY = os.getenv("API_KEY", "")
REQUEST_TIMEOUT = 120  # seconds — embedding + generation can be slow

HEADERS = {"X-API-Key": API_KEY}

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Acme Retail Document Chatbot",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Acme Retail Document Chatbot")
st.caption("Ask questions across Excel, CSV, and PowerPoint files.")

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []  # list of {"role": str, "content": str, "citations": list}

if "indexed_docs" not in st.session_state:
    st.session_state.indexed_docs = []

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _api_headers() -> dict[str, str]:
    key = API_KEY or st.session_state.get("api_key_input", "")
    return {"X-API-Key": key}


def upload_files(files: list) -> dict:
    """POST /ingest with the provided UploadFile objects."""
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        file_tuples = [("files", (f.name, f.getvalue(), f.type or "application/octet-stream")) for f in files]
        response = client.post(f"{API_BASE_URL}/ingest", files=file_tuples, headers=_api_headers())
        response.raise_for_status()
        return response.json()


def fetch_documents() -> list[dict]:
    """GET /ingest/documents."""
    try:
        with httpx.Client(timeout=15) as client:
            response = client.get(f"{API_BASE_URL}/ingest/documents", headers=_api_headers())
            response.raise_for_status()
            return response.json().get("documents", [])
    except Exception:
        return []


def ask_question(question: str, top_k: int) -> dict:
    """POST /chat."""
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        response = client.post(
            f"{API_BASE_URL}/chat",
            json={"question": question, "top_k": top_k},
            headers=_api_headers(),
        )
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Sidebar — Upload and document list
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("⚙️ Configuration")

    if not API_KEY:
        api_key_input = st.text_input("API Key", type="password", key="api_key_input")
        st.caption("Set the API_KEY environment variable to avoid entering it each time.")
    else:
        st.success("API key loaded from environment.")

    st.divider()

    st.header("📁 Upload Documents")
    uploaded_files = st.file_uploader(
        "Upload Excel, CSV, or PowerPoint files",
        type=["xlsx", "xls", "csv", "pptx"],
        accept_multiple_files=True,
        help="Maximum 50 MB per file. Legacy .ppt format is not supported — convert to .pptx first.",
    )

    if st.button("📥 Index Files", disabled=not uploaded_files, use_container_width=True):
        if uploaded_files:
            with st.spinner("Uploading and indexing files…"):
                try:
                    result = upload_files(uploaded_files)
                    for r in result.get("results", []):
                        if r["status"] == "complete":
                            if r.get("already_indexed"):
                                st.info(f"⏭️ {r['filename']} — already indexed, skipped.")
                            else:
                                st.success(f"✅ {r['filename']} — {r['chunk_count']} chunks indexed.")
                        else:
                            st.error(f"❌ {r['filename']} — {r.get('message', 'Failed')}")
                except httpx.HTTPStatusError as exc:
                    st.error(f"API error {exc.response.status_code}: {exc.response.text[:300]}")
                except httpx.RequestError as exc:
                    st.error(f"Cannot reach API at {API_BASE_URL}: {exc}")
                except Exception as exc:
                    st.error(f"Unexpected error: {exc}")

    st.divider()

    st.header("📄 Indexed Documents")
    if st.button("🔄 Refresh list", use_container_width=True):
        st.session_state.indexed_docs = fetch_documents()

    if not st.session_state.indexed_docs:
        st.session_state.indexed_docs = fetch_documents()

    if st.session_state.indexed_docs:
        for doc in st.session_state.indexed_docs:
            status_icon = "✅" if doc["status"] == "complete" else "❌" if doc["status"] == "failed" else "⏳"
            st.caption(f"{status_icon} **{doc['filename']}** ({doc['file_type'].upper()}, {doc['chunk_count']} chunks)")
    else:
        st.caption("No documents indexed yet.")

    st.divider()

    st.header("🔧 Retrieval Settings")
    top_k = st.slider(
        "Top-K results",
        min_value=1,
        max_value=20,
        value=5,
        help="Number of document chunks retrieved per question.",
    )

# ---------------------------------------------------------------------------
# Main — Chat history and input
# ---------------------------------------------------------------------------

# Render existing chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("citations"):
            with st.expander("📚 Sources"):
                for cite in message["citations"]:
                    st.markdown(f"**{cite['filename']}**")
                    if cite.get("locations"):
                        for loc in cite["locations"]:
                            st.markdown(f"  - {loc}")

# Chat input
if prompt := st.chat_input("Ask a question about your documents…"):
    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate answer
    with st.chat_message("assistant"):
        with st.spinner("Searching and generating answer…"):
            try:
                response = ask_question(prompt, top_k=top_k)

                answer = response.get("answer", "No answer returned.")
                citations = response.get("citations", [])
                insufficient = response.get("insufficient_evidence", False)

                if insufficient:
                    st.warning(answer)
                else:
                    st.markdown(answer)

                if citations and not insufficient:
                    with st.expander("📚 Sources"):
                        for cite in citations:
                            st.markdown(f"**{cite['filename']}**")
                            if cite.get("locations"):
                                for loc in cite["locations"]:
                                    st.markdown(f"  - {loc}")

                # Store in session
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": answer,
                        "citations": citations if not insufficient else [],
                    }
                )

            except httpx.HTTPStatusError as exc:
                error_msg = f"API error {exc.response.status_code}"
                try:
                    detail = exc.response.json().get("detail", {})
                    if isinstance(detail, dict):
                        error_msg += f": {detail.get('error', exc.response.text[:200])}"
                    else:
                        error_msg += f": {detail}"
                except Exception:
                    error_msg += f": {exc.response.text[:200]}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": f"⚠️ {error_msg}"})

            except httpx.RequestError as exc:
                error_msg = f"Cannot reach the API at {API_BASE_URL}. Is the backend running?\n\nError: {exc}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": f"⚠️ {error_msg}"})

            except Exception as exc:
                error_msg = f"Unexpected error: {exc}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": f"⚠️ {error_msg}"})
