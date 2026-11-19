"""
Upload API Tests
Tests for document upload endpoint and validation
"""

import pytest
import sys
from pathlib import Path
from io import BytesIO

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from backend.main import app
from backend.database import clear_all_documents, get_document_count
from backend.services.upload import UPLOAD_DIR

# Create test client
client = TestClient(app)

# ============================================
# FIXTURES
# ============================================

@pytest.fixture
async def clean_test_environment():
    """
    Clean database and uploads before each test
    """
    # Clear database
    await clear_all_documents()
    
    # Clean upload directory (test files only)
    if UPLOAD_DIR.exists():
        for file in UPLOAD_DIR.glob("test-*"):
            file.unlink()
    
    yield
    
    # Cleanup after test
    await clear_all_documents()


def create_test_file(filename: str, content: bytes, size: int = None) -> BytesIO:
    """
    Create a test file for upload
    
    Args:
        filename: Filename to use
        content: File content
        size: Optional size override
    """
    if size:
        # Create file of specific size
        file_content = b"0" * size
    else:
        file_content = content
    
    return ("file", (filename, BytesIO(file_content), "application/octet-stream"))


# ============================================
# VALID UPLOAD TESTS
# ============================================

@pytest.mark.asyncio
async def test_upload_valid_pdf(clean_test_environment):
    """
    Test uploading a valid PDF file
    """
    # Create fake PDF content
    pdf_content = b"%PDF-1.4\n%\xE2\xE3\xCF\xD3\n" + b"0" * 1000
    
    response = client.post(
        "/api/documents/upload",
        files={"file": ("test_document.pdf", BytesIO(pdf_content), "application/pdf")}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Document uploaded successfully"
    assert data["document"]["filename"] == "test_document.pdf"
    assert data["document"]["file_type"] == "PDF"
    assert data["document"]["status"] == "uploaded"
    assert "document_id" in data["document"]


@pytest.mark.asyncio
async def test_upload_valid_txt(clean_test_environment):
    """
    Test uploading a valid TXT file
    """
    txt_content = b"This is a test text file content."
    
    response = client.post(
        "/api/documents/upload",
        files={"file": ("test_document.txt", BytesIO(txt_content), "text/plain")}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["document"]["file_type"] == "TXT"


@pytest.mark.asyncio
async def test_upload_valid_docx(clean_test_environment):
    """
    Test uploading a valid DOCX file
    """
    # Minimal valid DOCX signature
    docx_content = b"PK\x03\x04" + b"0" * 1000
    
    response = client.post(
        "/api/documents/upload",
        files={"file": ("test_document.docx", BytesIO(docx_content), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["document"]["file_type"] in ["DOCX", "ZIP"]  # May detect as ZIP


# ============================================
# INVALID EXTENSION TESTS
# ============================================

@pytest.mark.asyncio
async def test_upload_invalid_extension_jpg(clean_test_environment):
    """
    Test uploading JPG file (not allowed)
    """
    jpg_content = b"\xFF\xD8\xFF\xE0" + b"0" * 1000
    
    response = client.post(
        "/api/documents/upload",
        files={"file": ("image.jpg", BytesIO(jpg_content), "image/jpeg")}
    )
    
    assert response.status_code == 400
    data = response.json()
    assert "not allowed" in data["detail"].lower()


@pytest.mark.asyncio
async def test_upload_invalid_extension_exe(clean_test_environment):
    """
    Test uploading EXE file (not allowed)
    """
    exe_content = b"MZ" + b"0" * 1000
    
    response = client.post(
        "/api/documents/upload",
        files={"file": ("malware.exe", BytesIO(exe_content), "application/octet-stream")}
    )
    
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_no_extension(clean_test_environment):
    """
    Test uploading file without extension
    """
    content = b"Some content"
    
    response = client.post(
        "/api/documents/upload",
        files={"file": ("noextension", BytesIO(content), "application/octet-stream")}
    )
    
    assert response.status_code == 400


# ============================================
# FILE SIZE TESTS
# ============================================

@pytest.mark.asyncio
async def test_upload_empty_file(clean_test_environment):
    """
    Test uploading empty file (0 bytes)
    """
    empty_content = b""
    
    response = client.post(
        "/api/documents/upload",
        files={"file": ("empty.pdf", BytesIO(empty_content), "application/pdf")}
    )
    
    assert response.status_code == 400
    data = response.json()
    assert "empty" in data["detail"].lower()


@pytest.mark.asyncio
async def test_upload_oversized_file(clean_test_environment):
    """
    Test uploading file larger than 20 MB
    """
    # Create 21 MB file
    large_content = b"0" * (21 * 1024 * 1024)
    
    response = client.post(
        "/api/documents/upload",
        files={"file": ("large.pdf", BytesIO(large_content), "application/pdf")}
    )
    
    assert response.status_code == 400
    data = response.json()
    assert "too large" in data["detail"].lower() or "maximum" in data["detail"].lower()


@pytest.mark.asyncio
async def test_upload_max_size_boundary(clean_test_environment):
    """
    Test uploading file at exactly 20 MB (boundary test)
    """
    # Create exactly 20 MB file with PDF signature
    max_content = b"%PDF-1.4\n" + b"0" * (20 * 1024 * 1024 - 10)
    
    response = client.post(
        "/api/documents/upload",
        files={"file": ("max_size.pdf", BytesIO(max_content), "application/pdf")}
    )
    
    # Should succeed (exactly at limit)
    assert response.status_code == 201


# ============================================
# DATABASE INTEGRATION TESTS
# ============================================

@pytest.mark.asyncio
async def test_upload_stores_in_database(clean_test_environment):
    """
    Test that upload stores metadata in database
    """
    txt_content = b"Database integration test"
    
    # Check initial count
    count_before = await get_document_count()
    
    # Upload file
    response = client.post(
        "/api/documents/upload",
        files={"file": ("db_test.txt", BytesIO(txt_content), "text/plain")}
    )
    
    assert response.status_code == 201
    
    # Check count after upload
    count_after = await get_document_count()
    assert count_after == count_before + 1


@pytest.mark.asyncio
async def test_upload_multiple_files(clean_test_environment):
    """
    Test uploading multiple files sequentially
    """
    files = [
        ("file1.pdf", b"%PDF" + b"0" * 100),
        ("file2.txt", b"Text content"),
        ("file3.docx", b"PK\x03\x04" + b"0" * 100)
    ]
    
    for filename, content in files:
        response = client.post(
            "/api/documents/upload",
            files={"file": (filename, BytesIO(content))}
        )
        assert response.status_code == 201
    
    # Check all files stored
    count = await get_document_count()
    assert count == 3


@pytest.mark.asyncio
async def test_upload_duplicate_filename_allowed(clean_test_environment):
    """
    Test that uploading same filename twice is allowed (different document IDs)
    """
    content = b"Test content"
    
    # Upload first file
    response1 = client.post(
        "/api/documents/upload",
        files={"file": ("duplicate.txt", BytesIO(content), "text/plain")}
    )
    assert response1.status_code == 201
    doc1_id = response1.json()["document"]["document_id"]
    
    # Upload same filename again
    response2 = client.post(
        "/api/documents/upload",
        files={"file": ("duplicate.txt", BytesIO(content), "text/plain")}
    )
    assert response2.status_code == 201
    doc2_id = response2.json()["document"]["document_id"]
    
    # Document IDs should be different
    assert doc1_id != doc2_id
    
    # Both should be in database
    count = await get_document_count()
    assert count == 2


# ============================================
# FILE STORAGE TESTS
# ============================================

@pytest.mark.asyncio
async def test_upload_creates_physical_file(clean_test_environment):
    """
    Test that upload creates actual file in uploads directory
    """
    content = b"Physical file test"
    
    response = client.post(
        "/api/documents/upload",
        files={"file": ("physical_test.txt", BytesIO(content), "text/plain")}
    )
    
    assert response.status_code == 201
    data = response.json()
    
    # Check file exists
    file_path = Path(data["document"]["file_path"]) if "file_path" in data["document"] else None
    
    # File should exist in uploads directory
    uploaded_files = list(UPLOAD_DIR.glob("*physical_test*"))
    assert len(uploaded_files) > 0


# ============================================
# ERROR HANDLING TESTS
# ============================================

@pytest.mark.asyncio
async def test_upload_without_file(clean_test_environment):
    """
    Test upload request without file
    """
    response = client.post("/api/documents/upload")
    
    assert response.status_code == 422  # Unprocessable Entity


@pytest.mark.asyncio
async def test_upload_with_special_characters_filename(clean_test_environment):
    """
    Test uploading file with special characters in filename
    """
    content = b"Special chars test"
    
    response = client.post(
        "/api/documents/upload",
        files={"file": ("file with spaces & special@chars!.txt", BytesIO(content), "text/plain")}
    )
    
    assert response.status_code == 201
    data = response.json()
    # Original filename should be preserved
    assert data["document"]["filename"] == "file with spaces & special@chars!.txt"


# ============================================
# RESPONSE FORMAT TESTS
# ============================================

@pytest.mark.asyncio
async def test_upload_response_format(clean_test_environment):
    """
    Test that upload response has correct format
    """
    content = b"Response format test"
    
    response = client.post(
        "/api/documents/upload",
        files={"file": ("format_test.txt", BytesIO(content), "text/plain")}
    )
    
    assert response.status_code == 201
    data = response.json()
    
    # Check required fields
    assert "status" in data
    assert "message" in data
    assert "document" in data
    
    doc = data["document"]
    assert "document_id" in doc
    assert "filename" in doc
    assert "file_type" in doc
    assert "file_size" in doc
    assert "upload_date" in doc
    assert "status" in doc
    
    # Check values
    assert data["status"] == "success"
    assert doc["status"] == "uploaded"
