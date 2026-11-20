"""Tests for text cleaning/preprocessing (no third-party dependencies)."""

import pytest

from document_agent.cleaner import clean_text
from document_agent.exceptions import DocumentAgentError


def test_preserves_currency_and_figures():
    text = "Revenue was $1,250,000 and EPS was $2.45, up 12.5%."
    assert clean_text(text) == "Revenue was $1,250,000 and EPS was $2.45, up 12.5%."


def test_preserves_percentages_ratios_and_terms():
    cleaned = clean_text("Operating margin 18.3%; debt-to-equity 0.42; growth 9.1%.")
    assert "18.3%" in cleaned
    assert "0.42" in cleaned
    assert "debt-to-equity" in cleaned


def test_preserves_dates():
    assert "December 31, 2024" in clean_text(
        "As of December 31, 2024, the company held assets."
    )


def test_preserves_company_name_case():
    assert "ACME Corporation" in clean_text("ACME Corporation reported revenue.")


def test_removes_soft_hyphens():
    assert clean_text("revenue\u00adgrowth") == "revenuegrowth"


def test_collapses_runs_of_spaces_and_tabs():
    assert clean_text("Hello     world\t\tend") == "Hello world end"


def test_collapses_excess_blank_lines():
    assert clean_text("para1\n\n\n\npara2") == "para1\n\npara2"


def test_removes_control_characters():
    assert clean_text("abc\x00\x07def\x0bghi") == "abcdefghi"


def test_normalizes_windows_and_mac_newlines():
    assert clean_text("line1\r\nline2\rline3") == "line1\nline2\nline3"


def test_strips_leading_and_trailing_whitespace():
    assert clean_text("  \n hello \n  ") == "hello"


def test_empty_string_is_unchanged():
    assert clean_text("") == ""


def test_none_input_raises():
    with pytest.raises(DocumentAgentError):
        clean_text(None)


def test_non_string_input_raises():
    with pytest.raises(DocumentAgentError):
        clean_text(123)
