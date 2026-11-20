"""
End-to-end Document Agent pipeline: process_document and search_documents.

These are the two functions the rest of the system (and, later, Aniket's
FastAPI upload endpoint) calls. They keep all HTTP/file-upload concerns OUT of
this module — they take plain paths and ids and return plain data structures.

    process_document(file_path, document_id, metadata=None, config=None)
        -> ProcessingResult

    search_documents(query, top_k=5, document_id=None, config=None)
        -> list[SearchResult]

Integration note for the future upload API (do NOT implement the endpoint here):
    1. The endpoint saves the uploaded file to disk (that is the upload API's job).
    2. It generates a unique document_id.
    3. It calls process_document(saved_path, document_id, metadata).
    4. It maps the ProcessingResult fields onto its HTTP response.

This module never imports FastAPI or any HTTP library.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

from .chunker import chunk_pages
from .cleaner import clean_text
from .config import DocumentAgentConfig, default_config
from .embedder import Embedder
from .exceptions import DocumentAgentError
from .extractors import extract_text, identify_format
from .models import ChunkMetadata, PageText, ProcessingResult, SearchResult
from .vector_store import VectorStore

logger = logging.getLogger("document_agent")

# Caches keyed so that the same model is loaded once and each persist directory
# gets its own VectorStore. Tests pass a unique temp dir per test, so they never
# collide with each other or with the default production store.
_embedders: Dict[str, Embedder] = {}
_vector_stores: Dict[str, VectorStore] = {}

# User-facing metadata keys we know how to attach to chunks. Unknown keys are
# ignored (with a warning) so the chunk metadata schema stays predictable.
_ALLOWED_USER_METADATA_KEYS = ("company_name", "document_type", "source")


def _get_embedder(config: DocumentAgentConfig) -> Embedder:
    key = config.embedding_model_name
    embedder = _embedders.get(key)
    if embedder is None:
        embedder = Embedder(config)
        _embedders[key] = embedder
    return embedder


def _get_vector_store(config: DocumentAgentConfig) -> VectorStore:
    key = str(config.chroma_persist_directory)
    store = _vector_stores.get(key)
    if store is None:
        store = VectorStore(config, _get_embedder(config))
        _vector_stores[key] = store
    return store


def _validate_user_metadata(metadata) -> Dict[str, str]:
    """Return a clean dict of allowed metadata keys with non-None string values.

    Unknown keys are ignored (with a warning). None values are dropped. Non-str
    scalar values are coerced to str so ChromaDB metadata stays simple.
    """
    if metadata is None:
        return {}
    if not isinstance(metadata, dict):
        raise DocumentAgentError("metadata must be a dict or None")
    cleaned: Dict[str, str] = {}
    for key, value in metadata.items():
        if not isinstance(key, str):
            raise DocumentAgentError("metadata keys must be strings")
        if key not in _ALLOWED_USER_METADATA_KEYS:
            logger.warning(
                "Ignoring unknown metadata key %r (allowed: %s)",
                key, ", ".join(_ALLOWED_USER_METADATA_KEYS),
            )
            continue
        if value is None:
            continue
        if not isinstance(value, (str, int, float, bool)):
            raise DocumentAgentError(
                f"metadata value for '{key}' must be str/int/float/bool, "
                f"got {type(value).__name__}"
            )
        cleaned[key] = value if isinstance(value, str) else str(value)
    return cleaned


def process_document(
    file_path,
    document_id,
    metadata=None,
    config: Optional[DocumentAgentConfig] = None,
) -> ProcessingResult:
    """Process one document end to end: extract -> clean -> chunk -> embed -> index.

    Returns a ProcessingResult. On any DocumentAgentError (or unexpected error)
    it returns a FAILURE result with the error message rather than raising, so
    callers like an HTTP endpoint can simply inspect `result.success`.

    Args:
        file_path: Path to a PDF, DOCX or TXT file.
        document_id: Unique id for this document (used to filter later).
        metadata: Optional dict with any of company_name, document_type, source.
        config: Optional DocumentAgentConfig. Defaults to the env-based config.
    """
    cfg = config if config is not None else default_config
    doc_id = document_id if isinstance(document_id, str) else ""

    try:
        # --- Validate inputs ---
        if not document_id or not isinstance(document_id, str):
            raise DocumentAgentError("document_id must be a non-empty string")
        user_meta = _validate_user_metadata(metadata)

        path = Path(file_path)

        # --- Identify format (raises UnsupportedFormatError on bad extension) ---
        file_type = identify_format(path)

        # --- Extract (raises MissingFileError / EmptyDocumentError / ExtractionError) ---
        pages = extract_text(path)

        # --- Clean (per page, preserving page_number) ---
        cleaned_pages = [
            PageText(text=clean_text(p.text), page_number=p.page_number)
            for p in pages
        ]

        # --- Build base metadata shared by every chunk ---
        base = ChunkMetadata(
            document_id=document_id,
            original_filename=path.name,
            file_type=file_type,
            chunk_id="",          # filled per chunk
            chunk_index=0,         # filled per chunk
            company_name=user_meta.get("company_name"),
            document_type=user_meta.get("document_type"),
            source=user_meta.get("source"),
        )

        # --- Chunk ---
        chunks = chunk_pages(cleaned_pages, cfg.chunk_size, cfg.chunk_overlap, base)
        if not chunks:
            raise DocumentAgentError(f"No chunks produced from document: {path.name}")

        # --- Embed + index ---
        store = _get_vector_store(cfg)
        indexed = store.index_chunks(chunks, document_id)

        # pages_extracted is meaningful for PDF/TXT; None for DOCX (no pages).
        pages_extracted = None if file_type == "docx" else len(pages)
        message = (
            f"Processed '{path.name}' [{file_type}]: "
            f"{pages_extracted if pages_extracted is not None else 'N/A'} page(s), "
            f"{len(chunks)} chunk(s), {indexed} indexed."
        )
        logger.info(message)
        return ProcessingResult(
            success=True,
            document_id=document_id,
            pages_extracted=pages_extracted,
            chunks_generated=len(chunks),
            chunks_indexed=indexed,
            message=message,
            error=None,
        )
    except DocumentAgentError as e:
        logger.error("process_document failed for document_id=%s: %s", doc_id, e)
        return ProcessingResult(
            success=False,
            document_id=doc_id,
            message="Processing failed.",
            error=str(e),
        )
    except Exception as e:  # safety net for truly unexpected errors
        logger.exception(
            "Unexpected error in process_document (document_id=%s)", doc_id
        )
        return ProcessingResult(
            success=False,
            document_id=doc_id,
            message="Processing failed due to an unexpected error.",
            error=f"{type(e).__name__}: {e}",
        )


def search_documents(
    query: str,
    top_k: int = 5,
    document_id: Optional[str] = None,
    config: Optional[DocumentAgentConfig] = None,
) -> List[SearchResult]:
    """Search indexed documents for a natural-language query.

    The query is embedded with the SAME model used for indexing, then ChromaDB
    returns the closest chunks. If document_id is given, results are restricted
    to that document. No matches -> empty list.

    Raises DocumentAgentError on embedding/search failures (callers may catch).
    """
    cfg = config if config is not None else default_config
    if not isinstance(query, str) or not query.strip():
        raise DocumentAgentError("query must be a non-empty string")
    store = _get_vector_store(cfg)
    return store.search(query=query, top_k=top_k, document_id=document_id)
