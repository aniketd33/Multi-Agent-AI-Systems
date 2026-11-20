"""
Text cleaning and preprocessing.

The goal is to NORMALIZE the text (whitespace, control characters, line
endings) WITHOUT altering financial meaning. We deliberately do NOT:

  - lowercase the text (case carries company names and proper nouns),
  - remove currency symbols ($, EUR, %, etc.),
  - strip numbers, dates, percentages or ratios,
  - aggressively re-join words split by a hard hyphen at a line break, because
    that could corrupt terms like "year-over-year" or "10-K". (Soft hyphens,
    which are invisible hyphenation markers, ARE removed because that is safe.)

The cleaning is intentionally conservative: preserving meaning matters more
than perfect tidiness.
"""

from __future__ import annotations

import logging
import re

from .exceptions import DocumentAgentError

logger = logging.getLogger(__name__)

# Control characters EXCEPT tab (\x09), newline (\x0a) and carriage return
# (\x0d). Removing these clears PDF/DOCX extraction noise without touching the
# text we care about.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Runs of spaces and tabs -> a single space (applied per line).
_SPACES_AND_TABS = re.compile(r"[ \t]+")
# Three or more newlines -> exactly two (keep paragraph breaks, drop excess).
_EXCESS_NEWLINES = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Clean extracted text while preserving financial information.

    Steps:
      1. Remove soft hyphens (invisible hyphenation markers).
      2. Remove control characters (except tab/newline/return).
      3. Normalize Windows/Mac newlines to \\n.
      4. Strip trailing spaces on every line.
      5. Collapse runs of spaces/tabs to a single space.
      6. Collapse 3+ blank lines to a single blank line.
      7. Strip leading/trailing whitespace from the whole text.
    """
    if text is None:
        raise DocumentAgentError("clean_text received None instead of a string")
    if not isinstance(text, str):
        raise DocumentAgentError(
            f"clean_text expects a string, got {type(text).__name__}"
        )
    if not text:
        return text

    # 1. Soft hyphens are invisible markers from justified text; safe to drop.
    text = text.replace("\u00ad", "")
    # 2. Drop control characters (keep tab/newline/return).
    text = _CONTROL_CHARS.sub("", text)
    # 3. Normalize newlines: Windows \r\n and old Mac \r both become \n.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 4. Strip trailing spaces on each line (avoids dangling spaces after joins).
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    # 5. Collapse internal runs of spaces/tabs to a single space, per line, so
    #    newlines are preserved as structure.
    text = "\n".join(_SPACES_AND_TABS.sub(" ", line) for line in text.split("\n"))
    # 6. Collapse 3+ consecutive newlines to 2 (one blank line between paragraphs).
    text = _EXCESS_NEWLINES.sub("\n\n", text)
    # 7. Trim the whole text.
    return text.strip()
