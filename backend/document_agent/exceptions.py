"""
Custom exception types for the Document Agent.

Why custom exceptions?
    They let callers distinguish between different failure modes (a missing file
    vs. an unsupported format vs. an embedding failure) and handle each one
    appropriately, instead of catching a generic Exception and guessing. All
    Document Agent errors inherit from DocumentAgentError, so a caller can catch
    the whole family with one `except DocumentAgentError` when that is enough.

This file contains exception DEFINITIONS only — no processing logic lives here.
"""

from __future__ import annotations


class DocumentAgentError(Exception):
    """Base class for all Document Agent errors."""


class UnsupportedFormatError(DocumentAgentError):
    """The input file extension is not one of the supported types (pdf/docx/txt)."""


class MissingFileError(DocumentAgentError):
    """The input file path does not exist or is not a readable file.

    (Named to avoid clashing with Python's built-in FileNotFoundError.)
    """


class EmptyDocumentError(DocumentAgentError):
    """No text could be extracted from the document (it is effectively empty)."""


class ExtractionError(DocumentAgentError):
    """Text extraction failed for a reason other than a missing or empty file."""


class InvalidMetadataError(DocumentAgentError):
    """Provided metadata is of the wrong type or contains invalid values."""


class EmbeddingError(DocumentAgentError):
    """Embedding generation failed."""


class EmbeddingDimensionError(EmbeddingError):
    """An embedding's length does not match the expected dimension.

    Validation has two layers (implemented in embedder.py, Phase 6):

      1. PRIMARY (authoritative): the actual embedding dimension is obtained at
         runtime from the loaded Sentence Transformers model itself (e.g. via
         model.get_sentence_embedding_dimension()). Every generated embedding
         vector is checked against THIS actual dimension.

      2. ADDITIONAL (consistency check): the model's actual dimension is compared
         against the configured ``embedding_dimension`` (DA_EMBEDDING_DIMENSION).
         A disagreement signals that the configured model name and the expected
         size are out of sync.

    Raised when EITHER check fails. The configured dimension is an extra
    consistency check, NOT the only validation.
    """


class VectorStoreError(DocumentAgentError):
    """ChromaDB connection, indexing or retrieval failed."""
