"""
Text chunking with configurable size and overlap.

Strategy (kept simple and predictable, good for a first version):
  - We chunk WITHIN each page so that every chunk keeps the page's page_number
    (important for financial documents, where "page 47" is a real citation).
  - Each page's text is split into character windows of `chunk_size` with
    `chunk_overlap` characters of overlap between consecutive windows. Overlap
    means a sentence cut at a chunk boundary is partly repeated in the next
    chunk, so context is not lost.
  - chunk_index increases across the whole document (it does NOT reset per
    page), so every chunk_id is unique and ordered.

A more advanced splitter could break on sentence boundaries; this character
splitter is simpler to understand and the overlap mitigates mid-word cuts.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import List

from .exceptions import DocumentAgentError
from .models import Chunk, ChunkMetadata, PageText

logger = logging.getLogger(__name__)


def chunk_pages(
    pages: List[PageText],
    chunk_size: int,
    chunk_overlap: int,
    base_metadata: ChunkMetadata,
) -> List[Chunk]:
    """Split page-segmented text into overlapping Chunk objects.

    Args:
        pages: The cleaned text, one PageText per page.
        chunk_size: Maximum characters per chunk. Must be > 0.
        chunk_overlap: Characters of overlap between consecutive chunks.
            Must be >= 0 and < chunk_size.
        base_metadata: A ChunkMetadata whose document-level fields
            (document_id, original_filename, file_type, company_name,
            document_type, source) are already set. The chunker fills in
            chunk_id, chunk_index and page_number per chunk.

    Returns:
        A list of Chunk objects, each carrying its own metadata.
    """
    if chunk_size <= 0:
        raise DocumentAgentError("chunk_size must be a positive integer")
    if chunk_overlap < 0:
        raise DocumentAgentError("chunk_overlap must be a non-negative integer")
    if chunk_overlap >= chunk_size:
        raise DocumentAgentError("chunk_overlap must be smaller than chunk_size")

    document_id = base_metadata.document_id
    chunks: List[Chunk] = []
    chunk_index = 0

    for page in pages:
        text = page.text or ""
        if not text.strip():
            continue
        for piece in _split_text(text, chunk_size, chunk_overlap):
            if not piece.strip():
                continue
            metadata = replace(
                base_metadata,
                chunk_index=chunk_index,
                chunk_id=f"{document_id}__chunk_{chunk_index}",
                page_number=page.page_number,
            )
            chunks.append(Chunk(text=piece.strip(), metadata=metadata))
            chunk_index += 1

    return chunks


def _split_text(text: str, size: int, overlap: int) -> List[str]:
    """Slide a window of `size` chars over `text` with `overlap` chars of overlap.

    Returns the list of window contents. The window advances by (size - overlap)
    each step, which is guaranteed > 0 because the caller validates overlap < size.
    """
    step = size - overlap
    pieces: List[str] = []
    start = 0
    total = len(text)
    while start < total:
        end = min(start + size, total)
        pieces.append(text[start:end])
        if end >= total:
            break
        start += step
    return pieces
