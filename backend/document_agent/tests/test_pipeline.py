"""End-to-end tests for process_document / search_documents.

The success/search/reindex tests run against FAKE model + FAKE chromadb
(installed in conftest), so no real model download or chromadb is required.
Error-handling tests fail before reaching the vector store, so they need no
dependencies either.

Note: process_document catches DocumentAgentError and returns a FAILURE result
(does not raise), while search_documents RAISES DocumentAgentError on bad input.
The tests below reflect that actual behavior.
"""

import pytest

from document_agent.exceptions import DocumentAgentError
from document_agent.pipeline import process_document, search_documents


def test_process_txt_success(txt_path, test_config):
    result = process_document(
        str(txt_path), "doc_e2e_1",
        metadata={"company_name": "ACME Corp",
                  "document_type": "annual_report",
                  "source": "synthetic_test"},
        config=test_config,
    )
    assert result.success is True
    assert result.document_id == "doc_e2e_1"
    assert result.chunks_generated > 0
    assert result.chunks_indexed == result.chunks_generated
    assert result.pages_extracted == 1   # txt is treated as one page
    assert result.error is None


def test_search_returns_relevant_chunk(txt_path, test_config):
    process_document(str(txt_path), "doc_e2e_2",
                     metadata={"company_name": "ACME Corp"}, config=test_config)
    hits = search_documents("What was the revenue?", top_k=3,
                            document_id="doc_e2e_2", config=test_config)
    assert isinstance(hits, list)
    assert len(hits) >= 1
    combined = " ".join(h.text for h in hits)
    assert "revenue" in combined.lower() or "1,250,000" in combined


def test_reindex_does_not_duplicate(txt_path, test_config):
    r1 = process_document(str(txt_path), "doc_reindex", config=test_config)
    assert r1.success
    r2 = process_document(str(txt_path), "doc_reindex", config=test_config)
    assert r2.success
    assert r2.chunks_indexed == r1.chunks_indexed


def test_process_missing_file_returns_failure(test_config):
    result = process_document("/nonexistent/file.pdf", "doc_bad", config=test_config)
    assert result.success is False
    assert result.error is not None
    assert result.document_id == "doc_bad"


def test_process_unsupported_format_returns_failure(tmp_path, test_config):
    path = tmp_path / "data.xlsx"
    path.write_text("not a real xlsx", encoding="utf-8")
    result = process_document(str(path), "doc_bad2", config=test_config)
    assert result.success is False
    assert "unsupported" in result.error.lower()


def test_process_empty_file_returns_failure(tmp_path, test_config):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    result = process_document(str(path), "doc_bad3", config=test_config)
    assert result.success is False
    assert "no text" in result.error.lower() or "empty" in result.error.lower()


def test_invalid_query_raises(test_config):
    # search_documents RAISES on bad input (does not return a result).
    with pytest.raises(DocumentAgentError):
        search_documents("", top_k=3, config=test_config)


def test_invalid_document_id_returns_failure(tmp_path, test_config):
    path = tmp_path / "r.txt"
    path.write_text("hello", encoding="utf-8")
    result = process_document(str(path), "", config=test_config)  # empty id
    assert result.success is False
    assert result.error is not None


def test_unknown_metadata_key_is_ignored(txt_path, test_config):
    result = process_document(
        str(txt_path), "doc_meta",
        metadata={"company_name": "ACME", "unknown_key": "ignored"},
        config=test_config,
    )
    assert result.success is True


def test_invalid_metadata_type_returns_failure(tmp_path, test_config):
    path = tmp_path / "r.txt"
    path.write_text("hello", encoding="utf-8")
    result = process_document(str(path), "doc_meta_bad",
                              metadata="not a dict", config=test_config)
    assert result.success is False
    assert "metadata" in result.error.lower() or "dict" in result.error.lower()
