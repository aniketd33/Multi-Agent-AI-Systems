"""
Document text extraction for PDF, DOCX and TXT files.

This module turns a file on disk into a list of `PageText` objects (one per
"page"). The page concept is strongest for PDF (real pages); DOCX has no page
concept (page_number is None); a TXT file is treated as a single page.

Third-party libraries (pypdf, python-docx) are imported lazily inside the
extraction functions, so importing THIS module does not require those packages
to be installed — only calling the matching extraction function does.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from .config import SUPPORTED_FILE_TYPES
from .exceptions import (
    EmptyDocumentError,
    ExtractionError,
    MissingFileError,
    UnsupportedFormatError,
)
from .models import PageText

logger = logging.getLogger(__name__)


def identify_format(file_path) -> str:
    """Return the lowercased file type ("pdf", "docx" or "txt") from the path.

    Only the file extension is examined (the file does not need to exist yet).
    Raises UnsupportedFormatError if the extension is not supported.
    """
    ext = Path(file_path).suffix.lower().lstrip(".")
    if ext not in SUPPORTED_FILE_TYPES:
        raise UnsupportedFormatError(
            f"Unsupported file format '.{ext}'. Supported types: "
            f"{', '.join(SUPPORTED_FILE_TYPES)}."
        )
    return ext


def extract_text(file_path) -> List[PageText]:
    """Extract text from a PDF, DOCX or TXT file as a list of PageText objects.

    The file is checked for existence, its format is identified, and the right
    extractor is called. If no text can be extracted at all, EmptyDocumentError
    is raised. Other failures raise ExtractionError / MissingFileError /
    UnsupportedFormatError, all subclasses of DocumentAgentError.
    """
    path = Path(file_path)
    if not path.exists():
        raise MissingFileError(f"File not found: {path}")
    if not path.is_file():
        raise MissingFileError(f"Not a file: {path}")

    file_type = identify_format(path)

    if file_type == "pdf":
        pages = _extract_pdf(path)
    elif file_type == "docx":
        pages = _extract_docx(path)
    else:  # "txt"
        pages = _extract_txt(path)

    # Guard: a document that yields no usable text is treated as empty.
    if not any(p.text and p.text.strip() for p in pages):
        raise EmptyDocumentError(f"No text could be extracted from: {path.name}")
    return pages


# --- PDF --------------------------------------------------------------------

def _extract_pdf(path: Path) -> List[PageText]:
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover - depends on env
        raise ExtractionError(
            "pypdf is not installed. Run pip install -r requirements.txt"
        ) from e

    try:
        reader = PdfReader(str(path))
    except Exception as e:
        raise ExtractionError(f"Failed to open PDF '{path.name}': {e}") from e

    pages: List[PageText] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as e:  # one bad page should not fail the whole file
            logger.warning(
                "Failed to extract text from page %d of %s: %s",
                index, path.name, e,
            )
            text = ""
        pages.append(PageText(text=text, page_number=index))
    return pages


# --- DOCX -------------------------------------------------------------------

def _extract_docx(path: Path) -> List[PageText]:
    try:
        import docx  # python-docx
    except ImportError as e:  # pragma: no cover - depends on env
        raise ExtractionError(
            "python-docx is not installed. Run pip install -r requirements.txt"
        ) from e

    try:
        document = docx.Document(str(path))
    except Exception as e:
        raise ExtractionError(f"Failed to open DOCX '{path.name}': {e}") from e

    parts: List[str] = []
    for block in _iter_block_items(document):
        # Paragraphs expose `.text`; Tables expose `.rows`.
        if hasattr(block, "text"):
            parts.append(block.text)
        elif hasattr(block, "rows"):
            for row in block.rows:
                cells = [cell.text for cell in row.cells]
                parts.append(" | ".join(cells))

    text = "\n".join(part for part in parts if part and part.strip())
    # DOCX has no real page concept, so page_number is None.
    return [PageText(text=text, page_number=None)]


def _iter_block_items(parent):
    """Yield Paragraph and Table objects from a python-docx document in order.

    This is the standard python-docx recipe for walking the document body so
    that paragraphs and tables come out in the order they appear, rather than
    all paragraphs then all tables. Financial documents often interleave text
    and tables, so order matters.
    """
    from docx.document import Document as _DocxDocument
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    if isinstance(parent, _DocxDocument):
        parent_elm = parent.element.body
    else:
        # Only the top-level document body is supported here.
        raise ValueError("Unsupported parent for block iteration")

    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


# --- TXT --------------------------------------------------------------------

def _extract_txt(path: Path) -> List[PageText]:
    # Try common encodings; latin-1 is a permissive last resort that maps every
    # byte, so this loop always succeeds once it reaches latin-1.
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            text = path.read_text(encoding=encoding)
            return [PageText(text=text, page_number=1)]
        except UnicodeDecodeError:
            continue
    # Unreachable in practice (latin-1 always decodes) but keeps intent clear.
    raise ExtractionError(f"Could not decode text file '{path.name}'")
