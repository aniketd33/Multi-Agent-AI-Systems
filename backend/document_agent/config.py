"""
Configuration for the Document Agent module.

All settings are read from environment variables with sensible defaults, so the
module works out of the box but can be customized without editing code.

Why environment variables (and not a .env file)?
    They keep configuration out of source code (so secrets and machine-specific
    paths are not committed to git) and let different environments
    (dev / test / prod) use different settings. Per the project decision we do
    NOT use python-dotenv; callers set environment variables directly.

This file defines configuration ONLY. It does not import third-party libraries
(sentence-transformers, chromadb), so it can be imported even before those
dependencies are installed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


# --- Defaults ---------------------------------------------------------------

# Sentence Transformers model used for BOTH document chunks and search queries.
#   "all-MiniLM-L6-v2": 384-dimensional, ~80MB, fast on CPU, good general-purpose
#   semantic retrieval. Selected as the initial model; retrieval quality may be
#   re-evaluated later (e.g. upgrade to all-mpnet-base-v2).
DEFAULT_EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# Configured EXPECTED vector dimension for the default model. This is an
# ADDITIONAL consistency check, NOT the only validation. The authoritative
# dimension is the one the loaded Sentence Transformers model reports at
# runtime — embedder.py obtains it directly from the model instance (e.g. via
# model.get_sentence_embedding_dimension()) and validates each generated
# embedding against THAT actual dimension. Separately, embedder.py compares
# the model's actual dimension against this configured value; if they disagree,
# the configured model name and the expected size are likely out of sync, which
# is caught early — before any embeddings are generated.
DEFAULT_EMBEDDING_DIMENSION = 384

# ChromaDB persistent collection name. A single collection holds all documents;
# per-document isolation is achieved via metadata filtering, not via separate
# collections. This makes document-level filtering straightforward.
DEFAULT_CHROMA_COLLECTION_NAME = "financial_documents"

# Default chunking parameters (character-based with overlap).
#   CHUNK_SIZE   ~ characters per chunk (roughly 150-250 words).
#   CHUNK_OVERLAP ~ characters repeated between consecutive chunks, so context
#     that straddles a chunk boundary is not lost.
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200

# Supported input file extensions (lowercase, without the leading dot).
SUPPORTED_FILE_TYPES = ("pdf", "docx", "txt")


def _module_dir() -> Path:
    """Return the directory that contains this file (the package root)."""
    return Path(__file__).resolve().parent


def _default_persist_directory() -> Path:
    """Default on-disk ChromaDB location: <package>/data/vector_db.

    Kept inside the module so all Document Agent artifacts stay isolated and a
    nested .gitignore can exclude them. The path is computed (not hardcoded)
    so it works regardless of where the repository is cloned.
    """
    return _module_dir() / "data" / "vector_db"


def _as_int(value: str, default: int) -> int:
    """Convert a string env var to int, falling back to `default` on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class DocumentAgentConfig:
    """Immutable configuration container for the Document Agent.

    Instances are built from environment variables via `DocumentAgentConfig.from_env()`.
    The dataclass is frozen so a config object cannot be accidentally mutated
    mid-run.
    """

    embedding_model_name: str
    embedding_dimension: int
    chroma_collection_name: str
    chroma_persist_directory: Path
    chunk_size: int
    chunk_overlap: int
    supported_file_types: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "DocumentAgentConfig":
        """Build a config from environment variables, using defaults if unset.

        Recognized environment variables:
            DA_EMBEDDING_MODEL      embedding model name
            DA_EMBEDDING_DIMENSION  configured expected embedding vector length
                                   (int); used as an ADDITIONAL consistency
                                   check against the model's actual dimension
            DA_CHROMA_COLLECTION    ChromaDB collection name
            DA_CHROMA_PERSIST_DIR   ChromaDB on-disk storage path
            DA_CHUNK_SIZE           chunk size in characters (int)
            DA_CHUNK_OVERLAP        chunk overlap in characters (int)
        """
        return cls(
            embedding_model_name=os.environ.get(
                "DA_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL_NAME
            ),
            embedding_dimension=_as_int(
                os.environ.get("DA_EMBEDDING_DIMENSION"), DEFAULT_EMBEDDING_DIMENSION
            ),
            chroma_collection_name=os.environ.get(
                "DA_CHROMA_COLLECTION", DEFAULT_CHROMA_COLLECTION_NAME
            ),
            chroma_persist_directory=Path(
                os.environ.get(
                    "DA_CHROMA_PERSIST_DIR", str(_default_persist_directory())
                )
            ),
            chunk_size=_as_int(
                os.environ.get("DA_CHUNK_SIZE"), DEFAULT_CHUNK_SIZE
            ),
            chunk_overlap=_as_int(
                os.environ.get("DA_CHUNK_OVERLAP"), DEFAULT_CHUNK_OVERLAP
            ),
            supported_file_types=SUPPORTED_FILE_TYPES,
        )


# A module-level default config built from the current environment.
#
# This is a convenience for quick inspection (and for tests that do not need to
# override settings). Modules that need a guaranteed-fresh snapshot should call
# `DocumentAgentConfig.from_env()` themselves rather than rely on this object,
# because it captures environment values at import time.
default_config = DocumentAgentConfig.from_env()
