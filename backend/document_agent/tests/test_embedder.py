"""Tests for the Embedder, using a FAKE Sentence Transformers model.

The fake model is installed in conftest (no real download). Configure it via
the `st_state` fixture. These cover the two-layer dimension validation and
error handling of document_agent.embedder.Embedder.
"""

import pytest

from document_agent.config import DocumentAgentConfig
from document_agent.embedder import Embedder
from document_agent.exceptions import EmbeddingDimensionError, EmbeddingError


def _config(tmp_path, dim=384):
    return DocumentAgentConfig(
        embedding_model_name="all-MiniLM-L6-v2",
        embedding_dimension=dim,
        chroma_collection_name="financial_documents_test",
        chroma_persist_directory=tmp_path / "vector_db",
        chunk_size=1000,
        chunk_overlap=200,
        supported_file_types=("pdf", "docx", "txt"),
    )


def test_dimension_matches_model_and_config(st_state, tmp_path):
    assert Embedder(_config(tmp_path, 384)).dimension == 384


def test_embed_single_returns_vector_of_configured_dim(st_state, tmp_path):
    vecs = Embedder(_config(tmp_path, 384)).embed(["hello world"])
    assert len(vecs) == 1
    assert len(vecs[0]) == 384


def test_embed_batch(st_state, tmp_path):
    vecs = Embedder(_config(tmp_path, 384)).embed(["hello", "world", "finance"])
    assert len(vecs) == 3
    for v in vecs:
        assert len(v) == 384


def test_embed_empty_list_returns_empty(st_state, tmp_path):
    assert Embedder(_config(tmp_path)).embed([]) == []


def test_configured_vs_actual_dimension_mismatch_raises(st_state, tmp_path):
    st_state.dimension = 999  # model reports 999, config says 384
    with pytest.raises(EmbeddingDimensionError):
        Embedder(_config(tmp_path, 384)).dimension


def test_primary_dimension_check_on_bad_vector_length(st_state, tmp_path):
    # Model reports 384 (matches config) but encode returns short vectors.
    st_state.encode_dim_override = 5
    with pytest.raises(EmbeddingDimensionError):
        Embedder(_config(tmp_path, 384)).embed(["x"])


def test_model_load_failure_raises_embedding_error(st_state, tmp_path):
    st_state.fail_load = True
    with pytest.raises(EmbeddingError):
        Embedder(_config(tmp_path)).dimension


def test_encode_failure_raises_embedding_error(st_state, tmp_path):
    st_state.fail_encode = True
    with pytest.raises(EmbeddingError):
        Embedder(_config(tmp_path)).embed(["x"])


def test_embed_non_list_input_raises(st_state, tmp_path):
    with pytest.raises(EmbeddingError):
        Embedder(_config(tmp_path)).embed("not a list")
