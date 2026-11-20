"""
Document Agent — Document Processing + AI Pipeline
==================================================

Part of the Multi-Agent Financial Research System.

This package is responsible for:
    1. Extracting text from PDF, DOCX and TXT financial documents.
    2. Cleaning and preprocessing text while preserving financial information.
    3. Chunking text into meaningful segments.
    4. Generating vector embeddings with Sentence Transformers.
    5. Storing chunks, embeddings and metadata in ChromaDB.
    6. Retrieving relevant chunks via similarity search.

Public API:
    - process_document(file_path, document_id, metadata=None, config=None) -> ProcessingResult
    - search_documents(query, top_k=5, document_id=None, config=None) -> list[SearchResult]

These names are imported LAZILY (PEP 562 module-level __getattr__). That means
`import document_agent` is cheap and does NOT require the third-party
dependencies to be installed; they are only loaded when you actually access
process_document / search_documents (or call them). Submodules such as
`document_agent.cleaner` or `document_agent.chunker` can also be imported
directly and independently for unit testing.

Phase 2 status: CORE PIPELINE IMPLEMENTED.

Author: Durga (Document Agent module)
Branch: Durga/document-agent
"""

from __future__ import annotations

import importlib
import logging
from logging import NullHandler

__version__ = "0.2.0"

# Library best practice: attach a NullHandler so the package never emits
# "No handlers could be found for logger ..." warnings. The application that
# uses this package is responsible for configuring real handlers.
logging.getLogger(__name__).addHandler(NullHandler())

# Maps public names to the submodule that defines them. Importing happens only
# when the name is accessed, keeping `import document_agent` dependency-light.
_LAZY_EXPORTS = {
    "process_document": "document_agent.pipeline",
    "search_documents": "document_agent.pipeline",
    "Chunk": "document_agent.models",
    "ChunkMetadata": "document_agent.models",
    "PageText": "document_agent.models",
    "ProcessingResult": "document_agent.models",
    "SearchResult": "document_agent.models",
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name):
    """Lazily import public names on first access (PEP 562)."""
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_name)
    if not hasattr(module, name):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(module, name)
    # Cache on this module so later accesses skip the import.
    globals()[name] = value
    return value
