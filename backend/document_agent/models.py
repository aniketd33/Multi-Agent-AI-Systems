"""
Data structures (dataclasses) used across the Document Agent pipeline.

These are plain data containers with docstrings. They carry information between
stages (extraction -> cleaning -> chunking -> embedding -> storage -> retrieval)
without containing processing logic. Defining them in one place means every
stage speaks the same "language" and metadata stays attached to its chunk.

Design note (project requirement): before a record is written to ChromaDB,
metadata fields whose value is None are removed, so ChromaDB stores only
fields that actually have a value (no fabricated "null" placeholders). This is
handled at storage time via `ChunkMetadata.to_storage_dict()`. It does NOT alter
the in-memory metadata, which keeps None for traceability.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class PageText:
    """Text extracted from a single page of a document.

    Attributes:
        text: The extracted text for this page.
        page_number: 1-based page number when known (PDF). None when page
            information is unavailable (e.g. DOCX has no page concept). A TXT
            file is treated as a single page with page_number = 1 by the
            extractor, not None.
    """

    text: str
    page_number: Optional[int] = None


@dataclass
class ChunkMetadata:
    """Metadata attached to every chunk, preserved through the whole pipeline.

    Only `document_id`, `original_filename`, `file_type`, `chunk_id` and
    `chunk_index` are always present (they are derived from the input). The
    remaining fields are set ONLY when the information genuinely exists;
    otherwise they stay None. None values are NEVER fabricated.
    """

    document_id: str
    original_filename: str
    file_type: str
    chunk_id: str
    chunk_index: int
    company_name: Optional[str] = None
    document_type: Optional[str] = None
    page_number: Optional[int] = None
    section: Optional[str] = None
    source: Optional[str] = None

    def to_storage_dict(self) -> dict:
        """Return a metadata dict for ChromaDB, with None values dropped.

        ChromaDB metadata filters behave more predictably when absent fields are
        omitted rather than stored as None. This keeps None for traceability in
        the in-memory object while storing only present fields in ChromaDB.

        This is a pure data operation (it does not touch ChromaDB). The actual
        write happens later in vector_store.py.
        """
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Chunk:
    """A chunk of cleaned document text plus the metadata that identifies it.

    Attributes:
        text: The cleaned chunk text (will be embedded and stored).
        metadata: Provenance metadata that travels with this chunk.
    """

    text: str
    metadata: ChunkMetadata


@dataclass
class ProcessingResult:
    """Structured result returned by process_document().

    Attributes:
        success: True if processing completed and chunks were indexed.
        document_id: The document id that was processed.
        pages_extracted: Number of pages extracted (None if not applicable).
        chunks_generated: Number of chunks produced by the chunker.
        chunks_indexed: Number of chunks actually written to ChromaDB.
        message: Short human-readable summary of the outcome.
        error: None on success; a description of what failed on failure.
    """

    success: bool
    document_id: str
    pages_extracted: Optional[int] = None
    chunks_generated: int = 0
    chunks_indexed: int = 0
    message: str = ""
    error: Optional[str] = None


@dataclass
class SearchResult:
    """One retrieved chunk from a similarity search.

    Attributes:
        text: The matched chunk text.
        metadata: The metadata associated with the matched chunk.
        score: Similarity score/distance returned by ChromaDB. Lower distance
            usually means more relevant; the exact semantics depend on
            ChromaDB's configured distance metric.
    """

    text: str
    metadata: dict
    score: Optional[float] = None
