"""Tests for text chunking.

These match the ACTUAL on-disk chunker interface: it validates chunk_size > 0,
chunk_overlap >= 0, and chunk_overlap < chunk_size (all raising
DocumentAgentError). The on-disk chunker does NOT validate that the values are
integers (that earlier edit did not persist), so no integer-type tests are
included here.
"""

import pytest

from document_agent.chunker import chunk_pages
from document_agent.exceptions import DocumentAgentError
from document_agent.models import ChunkMetadata, PageText


def _base(document_id="doc1"):
    return ChunkMetadata(
        document_id=document_id,
        original_filename="report.txt",
        file_type="txt",
        chunk_id="",
        chunk_index=0,
    )


def test_short_page_produces_single_chunk():
    pages = [PageText(text="Hello world. " * 5, page_number=1)]
    chunks = chunk_pages(pages, chunk_size=1000, chunk_overlap=100,
                         base_metadata=_base())
    assert len(chunks) == 1
    assert chunks[0].metadata.chunk_id == "doc1__chunk_0"
    assert chunks[0].metadata.chunk_index == 0
    assert chunks[0].metadata.page_number == 1
    assert chunks[0].metadata.document_id == "doc1"


def test_long_page_is_split_with_overlap():
    text = "word " * 500  # 2500 chars
    pages = [PageText(text=text, page_number=3)]
    chunks = chunk_pages(pages, chunk_size=1000, chunk_overlap=200,
                         base_metadata=_base())
    assert len(chunks) > 1
    assert [c.metadata.chunk_id for c in chunks] == [
        f"doc1__chunk_{i}" for i in range(len(chunks))
    ]
    for c in chunks:
        assert c.metadata.page_number == 3


def test_consecutive_chunks_have_expected_character_overlap():
    # Distinct characters so the overlap is exact and unambiguous.
    # chunk_size=4, chunk_overlap=2 -> step=2 -> windows: abcd, cdef, efgh, ghij
    text = "abcdefghij"
    pages = [PageText(text=text, page_number=1)]
    chunk_overlap = 2
    chunks = chunk_pages(pages, chunk_size=4, chunk_overlap=chunk_overlap,
                         base_metadata=_base())
    assert [c.text for c in chunks] == ["abcd", "cdef", "efgh", "ghij"]
    for i in range(len(chunks) - 1):
        assert chunks[i].text[-chunk_overlap:] == chunks[i + 1].text[:chunk_overlap]


def test_chunk_index_continues_across_pages_not_reset():
    pages = [
        PageText(text="page one " * 100, page_number=1),
        PageText(text="page two " * 100, page_number=2),
    ]
    chunks = chunk_pages(pages, chunk_size=500, chunk_overlap=50,
                         base_metadata=_base())
    assert len(chunks) >= 2
    assert [c.metadata.chunk_index for c in chunks] == list(range(len(chunks)))
    assert chunks[0].metadata.page_number == 1
    assert chunks[-1].metadata.page_number == 2


def test_docx_page_number_none_is_preserved():
    pages = [PageText(text="docx content " * 100, page_number=None)]
    chunks = chunk_pages(pages, chunk_size=500, chunk_overlap=50,
                         base_metadata=_base())
    assert len(chunks) >= 1
    for c in chunks:
        assert c.metadata.page_number is None


def test_empty_or_blank_pages_produce_no_chunks():
    pages = [PageText(text="", page_number=1), PageText(text="   ", page_number=2)]
    assert chunk_pages(pages, chunk_size=1000, chunk_overlap=100,
                       base_metadata=_base()) == []


def test_base_metadata_fields_are_carried_into_chunks():
    base = ChunkMetadata(
        document_id="doc9", original_filename="r.pdf", file_type="pdf",
        chunk_id="", chunk_index=0, company_name="ACME", document_type="10-K",
        source="upload",
    )
    pages = [PageText(text="x " * 100, page_number=7)]
    chunks = chunk_pages(pages, chunk_size=500, chunk_overlap=50, base_metadata=base)
    assert len(chunks) >= 1
    m = chunks[0].metadata
    assert m.company_name == "ACME"
    assert m.document_type == "10-K"
    assert m.source == "upload"
    assert m.original_filename == "r.pdf"
    assert m.page_number == 7


def test_invalid_chunk_size_zero_raises():
    pages = [PageText(text="x", page_number=1)]
    with pytest.raises(DocumentAgentError):
        chunk_pages(pages, chunk_size=0, chunk_overlap=0, base_metadata=_base())


def test_invalid_overlap_not_smaller_than_size_raises():
    pages = [PageText(text="x", page_number=1)]
    with pytest.raises(DocumentAgentError):
        chunk_pages(pages, chunk_size=100, chunk_overlap=100, base_metadata=_base())
    with pytest.raises(DocumentAgentError):
        chunk_pages(pages, chunk_size=100, chunk_overlap=150, base_metadata=_base())
