"""Tests for ChromaDB storage/retrieval/re-indexing.

Uses a FAKE in-memory chromadb (installed in conftest) and a FakeEmbedder, so no
real model download and no chromadb package are required. Checks STRUCTURE
(counts, metadata, filtering, isolation), not semantic relevance.
"""

import pytest

from document_agent.chunker import chunk_pages
from document_agent.exceptions import VectorStoreError
from document_agent.models import ChunkMetadata, PageText
from document_agent.vector_store import VectorStore


def _base(document_id="doc1"):
    return ChunkMetadata(
        document_id=document_id, original_filename="report.txt", file_type="txt",
        chunk_id="", chunk_index=0, company_name="ACME",
    )


def _make_chunks(text, document_id, chunk_size=200, chunk_overlap=20):
    pages = [PageText(text=text, page_number=1)]
    return chunk_pages(pages, chunk_size, chunk_overlap,
                       base_metadata=_base(document_id))


def _store(test_config, fake_embedder):
    return VectorStore(test_config, fake_embedder)


def test_index_and_count_chunks(test_config, fake_embedder):
    store = _store(test_config, fake_embedder)
    chunks = _make_chunks("revenue growth margin profit " * 40, "docA")
    indexed = store.index_chunks(chunks, "docA")
    assert indexed == len(chunks)
    raw = store._ensure_collection().get(where={"document_id": "docA"})
    assert len(raw["ids"]) == len(chunks)


def test_search_returns_results_with_metadata(test_config, fake_embedder):
    store = _store(test_config, fake_embedder)
    store.index_chunks(_make_chunks("the operating margin improved significantly", "docB"), "docB")
    results = store.search("operating margin", top_k=3)
    assert 0 <= len(results) <= 3
    for r in results:
        assert isinstance(r.text, str)
        assert isinstance(r.metadata, dict)
        assert r.metadata.get("document_id") == "docB"


def test_document_filter_restricts_results(test_config, fake_embedder):
    store = _store(test_config, fake_embedder)
    store.index_chunks(_make_chunks("alpha beta gamma " * 30, "docX"), "docX")
    store.index_chunks(_make_chunks("one two three " * 30, "docY"), "docY")
    results = store.search("alpha", top_k=10, document_id="docX")
    assert len(results) > 0
    for r in results:
        assert r.metadata["document_id"] == "docX"


def test_reindex_same_document_replaces_chunks(test_config, fake_embedder):
    store = _store(test_config, fake_embedder)
    v1 = _make_chunks("first version content " * 40, "docR")
    store.index_chunks(v1, "docR")
    assert len(store._ensure_collection().get(where={"document_id": "docR"})["ids"]) == len(v1)
    v2 = _make_chunks("second version content " * 5, "docR")
    store.index_chunks(v2, "docR")
    after = len(store._ensure_collection().get(where={"document_id": "docR"})["ids"])
    assert after == len(v2)
    assert after < len(v1)


def test_reindex_does_not_touch_other_documents(test_config, fake_embedder):
    store = _store(test_config, fake_embedder)
    store.index_chunks(_make_chunks("doc A content " * 40, "docA"), "docA")
    store.index_chunks(_make_chunks("doc B content " * 40, "docB"), "docB")
    before = len(store._ensure_collection().get(where={"document_id": "docB"})["ids"])
    store.index_chunks(_make_chunks("doc A new shorter " * 5, "docA"), "docA")
    after = len(store._ensure_collection().get(where={"document_id": "docB"})["ids"])
    assert before == after


def test_empty_collection_search_returns_empty(test_config, fake_embedder):
    store = _store(test_config, fake_embedder)
    assert store.search("anything", top_k=5) == []


def test_no_none_values_stored_in_metadata(test_config, fake_embedder):
    store = _store(test_config, fake_embedder)
    # _base leaves document_type/section/source as None -> must be dropped.
    store.index_chunks(_make_chunks("ensure no none values stored " * 30, "docN"), "docN")
    raw = store._ensure_collection().get(where={"document_id": "docN"})
    for metadata in raw["metadatas"]:
        for value in metadata.values():
            assert value is not None


def test_search_invalid_top_k_raises(test_config, fake_embedder):
    store = _store(test_config, fake_embedder)
    with pytest.raises(VectorStoreError):
        store.search("x", top_k=0)


def test_index_empty_chunks_returns_zero(test_config, fake_embedder):
    store = _store(test_config, fake_embedder)
    assert store.index_chunks([], "docEmpty") == 0
