"""Tests for PDF / DOCX / TXT text extraction.

The DOCX and PDF tests need their respective local libraries and skip
gracefully if those are not installed. The TXT and error tests need no
third-party dependency.
"""

from pathlib import Path

import pytest

from document_agent import extractors
from document_agent.exceptions import (
    EmptyDocumentError,
    MissingFileError,
    UnsupportedFormatError,
)


def test_identify_format_supported_extensions():
    assert extractors.identify_format(Path("report.pdf")) == "pdf"
    assert extractors.identify_format(Path("report.DOCX")) == "docx"  # case-insensitive
    assert extractors.identify_format(Path("report.Txt")) == "txt"


def test_identify_format_rejects_unsupported():
    with pytest.raises(UnsupportedFormatError):
        extractors.identify_format(Path("data.xlsx"))
    with pytest.raises(UnsupportedFormatError):
        extractors.identify_format(Path("no_extension"))


def test_extract_txt_returns_one_page_with_financial_text(txt_path):
    pages = extractors.extract_text(txt_path)
    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert "ACME Corporation" in pages[0].text
    assert "$1,250,000" in pages[0].text          # currency + figure preserved
    assert "12.5%" in pages[0].text               # percentage preserved
    assert "debt-to-equity" in pages[0].text       # financial term preserved


def test_extract_docx_includes_paragraph_and_table(docx_path):
    pages = extractors.extract_text(docx_path)
    assert len(pages) == 1
    assert pages[0].page_number is None           # DOCX has no page concept
    combined = pages[0].text
    assert "ACME Corporation" in combined
    assert "Revenue" in combined and "$1,250,000" in combined  # table text


def test_extract_pdf_preserves_page_number(pdf_path):
    pytest.importorskip("pypdf")  # reading needs pypdf; pdf_path fixture needs fpdf
    pages = extractors.extract_text(pdf_path)
    assert len(pages) >= 1
    assert pages[0].page_number == 1
    combined = "\n".join(p.text for p in pages)
    assert "ACME Corporation" in combined
    assert "$1,250,000" in combined


def test_extract_missing_file_raises(tmp_path):
    with pytest.raises(MissingFileError):
        extractors.extract_text(tmp_path / "does_not_exist.pdf")


def test_extract_unsupported_format_raises(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(UnsupportedFormatError):
        extractors.extract_text(path)


def test_extract_empty_file_raises(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    with pytest.raises(EmptyDocumentError):
        extractors.extract_text(path)


def test_extract_directory_raises_missing_file(tmp_path):
    # A directory is not a file -> MissingFileError.
    with pytest.raises(MissingFileError):
        extractors.extract_text(tmp_path)
