"""
Upload API Tests
Tests for the Document Agent upload endpoint and validation.

The 'client' fixture (session-scoped TestClient) is defined in conftest.py.
All tests run against test_documents.db, never against documents.db.
"""

import pytest
from pathlib import Path
from io import BytesIO

from backend.database import get_document_count
from backend.services.upload import UPLOAD_DIR

# ---------------------------------------------------------------------------
# Real ZIP bytes for DOCX fixtures.
# A DOCX is a ZIP archive.  python-magic returns application/zip for a
# structurally valid ZIP file; the production mapping accepts that as DOCX.
# Plain b"PK\x03\x04" + zeros is detected as application/octet-stream and
# is correctly rejected, so we must use a real ZIP payload here.
# ---------------------------------------------------------------------------
_REAL_DOCX_BYTES = bytes.fromhex(
    "504b03041400000000000bbe735d3ff2f44f0500000005000000130000005b436f6e74656e745f54797065735d"
    "2e786d6c64756d6d79504b03041400000000000bbe735d3ff2f44f050000000500000011000000776f72642f646f"
    "63756d656e742e786d6c64756d6d79504b010214001400000000000bbe735d3ff2f44f050000000500000013000000"
    "00000000000000008001000000005b436f6e74656e745f54797065735d2e786d6c504b01021400140000000000"
    "0bbe735d3ff2f44f0500000005000000110000000000000000000000800136000000776f72642f646f63756d656e74"
    "2e786d6c504b05060000000002000200800000006a0000000000"
)


# ============================================
# VALID UPLOAD TESTS
# ============================================

@pytest.mark.asyncio
async def test_upload_valid_pdf(client):
    pdf_content = b"%PDF-1.4\n%\xE2\xE3\xCF\xD3\n" + b"0" * 1000

    response = client.post(
        "/api/documents/upload",
        files={"file": ("test_document.pdf", BytesIO(pdf_content), "application/pdf")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert "Document uploaded successfully" in data["message"]
    assert data["document"]["filename"] == "test_document.pdf"
    assert data["document"]["file_type"] == "PDF"
    assert data["document"]["status"] == "uploaded"
    assert "document_id" in data["document"]


@pytest.mark.asyncio
async def test_upload_valid_txt(client):
    txt_content = b"This is a test text file content."

    response = client.post(
        "/api/documents/upload",
        files={"file": ("test_document.txt", BytesIO(txt_content), "text/plain")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["document"]["file_type"] == "TXT"


@pytest.mark.asyncio
async def test_upload_valid_docx(client):
    """DOCX is a ZIP archive; libmagic returns application/zip for valid ZIP bytes."""
    response = client.post(
        "/api/documents/upload",
        files={
            "file": (
                "test_document.docx",
                BytesIO(_REAL_DOCX_BYTES),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["document"]["file_type"] in ("DOCX", "ZIP")


# ============================================
# INVALID EXTENSION TESTS
# ============================================

@pytest.mark.asyncio
async def test_upload_invalid_extension_jpg(client):
    jpg_content = b"\xFF\xD8\xFF\xE0" + b"0" * 1000

    response = client.post(
        "/api/documents/upload",
        files={"file": ("image.jpg", BytesIO(jpg_content), "image/jpeg")},
    )

    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_invalid_extension_exe(client):
    exe_content = b"MZ" + b"0" * 1000

    response = client.post(
        "/api/documents/upload",
        files={"file": ("malware.exe", BytesIO(exe_content), "application/octet-stream")},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_no_extension(client):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("noextension", BytesIO(b"Some content"), "application/octet-stream")},
    )

    assert response.status_code == 400


# ============================================
# FILE SIZE TESTS
# ============================================

@pytest.mark.asyncio
async def test_upload_empty_file(client):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("empty.pdf", BytesIO(b""), "application/pdf")},
    )

    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_oversized_file(client):
    large_content = b"0" * (101 * 1024 * 1024)  # 101 MB > 100 MB limit

    response = client.post(
        "/api/documents/upload",
        files={"file": ("large.pdf", BytesIO(large_content), "application/pdf")},
    )

    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "too large" in detail or "maximum" in detail


@pytest.mark.asyncio
async def test_upload_max_size_boundary(client):
    """File at exactly 20 MB should be accepted."""
    max_content = b"%PDF-1.4\n" + b"0" * (20 * 1024 * 1024 - 10)

    response = client.post(
        "/api/documents/upload",
        files={"file": ("max_size.pdf", BytesIO(max_content), "application/pdf")},
    )

    assert response.status_code == 201


# ============================================
# DATABASE INTEGRATION TESTS
# ============================================

@pytest.mark.asyncio
async def test_upload_stores_in_database(client):
    """Upload should increment the test database row count."""
    count_before = await get_document_count()

    response = client.post(
        "/api/documents/upload",
        files={"file": ("db_test.txt", BytesIO(b"Database integration test"), "text/plain")},
    )

    assert response.status_code == 201
    assert await get_document_count() == count_before + 1


@pytest.mark.asyncio
async def test_upload_multiple_files(client):
    files = [
        ("file1.pdf", b"%PDF" + b"0" * 100),
        ("file2.txt", b"Text content"),
        ("file3.docx", _REAL_DOCX_BYTES),
    ]

    for filename, content in files:
        r = client.post(
            "/api/documents/upload",
            files={"file": (filename, BytesIO(content))},
        )
        assert r.status_code == 201, f"Upload of {filename} failed: {r.text}"

    assert await get_document_count() == 3


@pytest.mark.asyncio
async def test_upload_duplicate_filename_allowed(client):
    content = b"Test content"

    r1 = client.post(
        "/api/documents/upload",
        files={"file": ("duplicate.txt", BytesIO(content), "text/plain")},
    )
    assert r1.status_code == 201
    id1 = r1.json()["document"]["document_id"]

    r2 = client.post(
        "/api/documents/upload",
        files={"file": ("duplicate.txt", BytesIO(content), "text/plain")},
    )
    assert r2.status_code == 201
    id2 = r2.json()["document"]["document_id"]

    assert id1 != id2
    assert await get_document_count() == 2


# ============================================
# FILE STORAGE TESTS
# ============================================

@pytest.mark.asyncio
async def test_upload_creates_physical_file(client):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("physical_test.txt", BytesIO(b"Physical file test"), "text/plain")},
    )

    assert response.status_code == 201
    uploaded_files = list(UPLOAD_DIR.glob("*physical_test*"))
    assert len(uploaded_files) > 0


# ============================================
# ERROR HANDLING TESTS
# ============================================

@pytest.mark.asyncio
async def test_upload_without_file(client):
    response = client.post("/api/documents/upload")
    assert response.status_code == 422  # Unprocessable Entity


@pytest.mark.asyncio
async def test_upload_with_special_characters_filename(client):
    response = client.post(
        "/api/documents/upload",
        files={
            "file": (
                "file with spaces & special@chars!.txt",
                BytesIO(b"Special chars test"),
                "text/plain",
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["document"]["filename"] == "file with spaces & special@chars!.txt"


# ============================================
# RESPONSE FORMAT TESTS
# ============================================

@pytest.mark.asyncio
async def test_upload_response_format(client):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("format_test.txt", BytesIO(b"Response format test"), "text/plain")},
    )

    assert response.status_code == 201
    data = response.json()

    assert "status"   in data
    assert "message"  in data
    assert "document" in data

    doc = data["document"]
    for field in ("document_id", "filename", "file_type", "file_size", "upload_date", "status"):
        assert field in doc, f"Missing field: {field}"

    assert data["status"]   == "success"
    assert doc["status"]    == "uploaded"

# ============================================
# EXTRACTION AGENT INTEGRATION TESTS
# ============================================

@pytest.mark.asyncio
async def test_extraction_agent_import():
    # Extraction Agent is importable and extract_financials is callable.
    from backend.extraction_agent import extract_financials, ExtractionResult
    assert callable(extract_financials)


@pytest.mark.asyncio
async def test_extraction_in_pipeline_wiring(client):
    # Verify extract_financials is present in _run_pipeline source code,
    # and that uploading a text file returns HTTP 201 (pipeline is queued).
    import inspect
    from backend.api.documents import _run_pipeline
    pipeline_src = inspect.getsource(_run_pipeline)
    assert "extract_financials" in pipeline_src, "extract_financials not wired into _run_pipeline"

    response = client.post(
        "/api/documents/upload",
        files={"file": ("wiring_test.txt", BytesIO(b"Revenue: 500 million"), "text/plain")},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_extraction_failure_isolated():
    # extract_financials raises DocumentAgentError for a missing file;
    # verify the exception type and that it does not propagate silently.
    import asyncio
    from pathlib import Path
    from backend.extraction_agent import extract_financials
    from backend.document_agent.exceptions import DocumentAgentError

    missing = str(Path("does_not_exist_xyz.txt").resolve())
    try:
        await asyncio.to_thread(extract_financials, missing, "test-doc-id")
        assert False, "Expected DocumentAgentError for missing file"
    except DocumentAgentError:
        pass  # expected
    except Exception as exc:
        assert False, f"Unexpected exception type: {type(exc).__name__}: {exc}"

