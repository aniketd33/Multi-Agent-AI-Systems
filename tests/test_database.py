"""
Database Operations Tests
Tests for SQLite database CRUD operations
"""

import pytest
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.database.db import (
    initialize_database,
    insert_document,
    get_all_documents,
    get_document_by_id,
    delete_document,
    update_document_status,
    get_document_count,
    clear_all_documents,
    check_database_health,
    DATABASE_PATH
)

# ============================================
# TEST FIXTURES
# ============================================

@pytest.fixture
async def clean_database():
    """
    Fixture that initializes and cleans the database before each test
    """
    # Initialize database
    await initialize_database()
    
    # Clear any existing data
    await clear_all_documents()
    
    yield
    
    # Cleanup after test (optional)
    # await clear_all_documents()


@pytest.fixture
def sample_document_data():
    """
    Fixture providing sample document data for testing
    """
    return {
        "document_id": "test-doc-123",
        "filename": "test_report.pdf",
        "file_type": "PDF",
        "file_size": 1024000,
        "file_path": "/test/path/test_report.pdf",
        "status": "uploaded",
        "company_name": "Test Company"
    }

# ============================================
# INITIALIZATION TESTS
# ============================================

@pytest.mark.asyncio
async def test_database_initialization():
    """Test that database initializes correctly"""
    success = await initialize_database()
    
    assert success is True, "Database initialization should succeed"
    assert os.path.exists(DATABASE_PATH), "Database file should exist"


@pytest.mark.asyncio
async def test_database_health_check(clean_database):
    """Test database health check"""
    health = await check_database_health()
    
    assert health["status"] == "healthy", "Database should be healthy"
    assert health["database_exists"] is True, "Database file should exist"
    assert "total_documents" in health, "Health check should include document count"

# ============================================
# CREATE (INSERT) TESTS
# ============================================

@pytest.mark.asyncio
async def test_insert_document(clean_database, sample_document_data):
    """Test inserting a document"""
    success = await insert_document(**sample_document_data)
    
    assert success is True, "Document insertion should succeed"
    
    # Verify document was inserted
    count = await get_document_count()
    assert count == 1, "Database should have 1 document"


@pytest.mark.asyncio
async def test_insert_multiple_documents(clean_database):
    """Test inserting multiple documents"""
    documents = [
        {
            "document_id": f"doc-{i}",
            "filename": f"file_{i}.pdf",
            "file_type": "PDF",
            "file_size": 1000 * i,
            "file_path": f"/test/path/file_{i}.pdf"
        }
        for i in range(1, 4)
    ]
    
    for doc_data in documents:
        success = await insert_document(**doc_data)
        assert success is True, f"Document {doc_data['document_id']} should insert successfully"
    
    count = await get_document_count()
    assert count == 3, "Database should have 3 documents"

# ============================================
# READ TESTS
# ============================================

@pytest.mark.asyncio
async def test_get_all_documents(clean_database, sample_document_data):
    """Test retrieving all documents"""
    # Insert test document
    await insert_document(**sample_document_data)
    
    # Retrieve all documents
    documents = await get_all_documents()
    
    assert len(documents) == 1, "Should retrieve 1 document"
    assert documents[0]["document_id"] == sample_document_data["document_id"]
    assert documents[0]["filename"] == sample_document_data["filename"]


@pytest.mark.asyncio
async def test_get_document_by_id(clean_database, sample_document_data):
    """Test retrieving a document by ID"""
    # Insert test document
    await insert_document(**sample_document_data)
    
    # Retrieve by ID
    document = await get_document_by_id(sample_document_data["document_id"])
    
    assert document is not None, "Document should be found"
    assert document["document_id"] == sample_document_data["document_id"]
    assert document["filename"] == sample_document_data["filename"]
    assert document["file_type"] == sample_document_data["file_type"]


@pytest.mark.asyncio
async def test_get_document_by_invalid_id(clean_database):
    """Test retrieving a document with non-existent ID"""
    document = await get_document_by_id("non-existent-id")
    
    assert document is None, "Should return None for non-existent ID"


@pytest.mark.asyncio
async def test_get_empty_documents_list(clean_database):
    """Test retrieving documents from empty database"""
    documents = await get_all_documents()
    
    assert documents == [], "Should return empty list"
    assert len(documents) == 0, "Length should be 0"

# ============================================
# UPDATE TESTS
# ============================================

@pytest.mark.asyncio
async def test_update_document_status(clean_database, sample_document_data):
    """Test updating document status"""
    # Insert test document
    await insert_document(**sample_document_data)
    
    # Update status
    success = await update_document_status(
        sample_document_data["document_id"],
        "processing"
    )
    
    assert success is True, "Status update should succeed"
    
    # Verify status was updated
    document = await get_document_by_id(sample_document_data["document_id"])
    assert document["status"] == "processing", "Status should be updated to 'processing'"


@pytest.mark.asyncio
async def test_update_status_multiple_times(clean_database, sample_document_data):
    """Test updating document status multiple times"""
    await insert_document(**sample_document_data)
    
    statuses = ["processing", "indexed", "completed"]
    
    for status in statuses:
        success = await update_document_status(
            sample_document_data["document_id"],
            status
        )
        assert success is True, f"Should update to {status}"
        
        document = await get_document_by_id(sample_document_data["document_id"])
        assert document["status"] == status, f"Status should be {status}"

# ============================================
# DELETE TESTS
# ============================================

@pytest.mark.asyncio
async def test_delete_document(clean_database, sample_document_data):
    """Test deleting a document"""
    # Insert test document
    await insert_document(**sample_document_data)
    
    # Verify it exists
    count_before = await get_document_count()
    assert count_before == 1
    
    # Delete document
    success = await delete_document(sample_document_data["document_id"])
    
    assert success is True, "Delete should succeed"
    
    # Verify it's gone
    count_after = await get_document_count()
    assert count_after == 0, "Document should be deleted"
    
    # Try to retrieve deleted document
    document = await get_document_by_id(sample_document_data["document_id"])
    assert document is None, "Deleted document should not be found"


@pytest.mark.asyncio
async def test_delete_non_existent_document(clean_database):
    """Test deleting a document that doesn't exist"""
    success = await delete_document("non-existent-id")
    
    assert success is False, "Should return False for non-existent document"

# ============================================
# UTILITY TESTS
# ============================================

@pytest.mark.asyncio
async def test_get_document_count(clean_database):
    """Test getting document count"""
    # Initially empty
    count = await get_document_count()
    assert count == 0, "Count should be 0"
    
    # Insert documents
    for i in range(5):
        await insert_document(
            document_id=f"doc-{i}",
            filename=f"file_{i}.pdf",
            file_type="PDF",
            file_size=1000,
            file_path=f"/test/file_{i}.pdf"
        )
    
    # Check count
    count = await get_document_count()
    assert count == 5, "Count should be 5"


@pytest.mark.asyncio
async def test_clear_all_documents(clean_database):
    """Test clearing all documents"""
    # Insert multiple documents
    for i in range(3):
        await insert_document(
            document_id=f"doc-{i}",
            filename=f"file_{i}.pdf",
            file_type="PDF",
            file_size=1000,
            file_path=f"/test/file_{i}.pdf"
        )
    
    count_before = await get_document_count()
    assert count_before == 3
    
    # Clear all
    success = await clear_all_documents()
    assert success is True
    
    count_after = await get_document_count()
    assert count_after == 0, "All documents should be cleared"

# ============================================
# INTEGRATION TESTS
# ============================================

@pytest.mark.asyncio
async def test_complete_crud_workflow(clean_database):
    """Test complete Create-Read-Update-Delete workflow"""
    doc_id = "workflow-test-doc"
    
    # CREATE
    success = await insert_document(
        document_id=doc_id,
        filename="workflow_test.pdf",
        file_type="PDF",
        file_size=2048,
        file_path="/test/workflow.pdf",
        status="uploaded"
    )
    assert success is True, "Create should succeed"
    
    # READ
    document = await get_document_by_id(doc_id)
    assert document is not None, "Should read created document"
    assert document["status"] == "uploaded"
    
    # UPDATE
    success = await update_document_status(doc_id, "indexed")
    assert success is True, "Update should succeed"
    
    document = await get_document_by_id(doc_id)
    assert document["status"] == "indexed", "Status should be updated"
    
    # DELETE
    success = await delete_document(doc_id)
    assert success is True, "Delete should succeed"
    
    document = await get_document_by_id(doc_id)
    assert document is None, "Document should be deleted"


@pytest.mark.asyncio
async def test_multiple_documents_different_statuses(clean_database):
    """Test managing multiple documents with different statuses"""
    documents_data = [
        ("doc-1", "file1.pdf", "uploaded"),
        ("doc-2", "file2.docx", "processing"),
        ("doc-3", "file3.txt", "indexed"),
        ("doc-4", "file4.pdf", "uploaded"),
    ]
    
    # Insert all documents
    for doc_id, filename, status in documents_data:
        await insert_document(
            document_id=doc_id,
            filename=filename,
            file_type=filename.split('.')[-1].upper(),
            file_size=1000,
            file_path=f"/test/{filename}",
            status=status
        )
    
    # Retrieve all
    all_docs = await get_all_documents()
    assert len(all_docs) == 4, "Should have 4 documents"
    
    # Check statuses
    statuses = [doc["status"] for doc in all_docs]
    assert "uploaded" in statuses
    assert "processing" in statuses
    assert "indexed" in statuses

# ============================================
# ERROR HANDLING TESTS
# ============================================

@pytest.mark.asyncio
async def test_insert_duplicate_id(clean_database, sample_document_data):
    """Test inserting document with duplicate ID"""
    # Insert first time
    success1 = await insert_document(**sample_document_data)
    assert success1 is True
    
    # Try to insert with same ID (should fail due to PRIMARY KEY constraint)
    success2 = await insert_document(**sample_document_data)
    assert success2 is False, "Should fail to insert duplicate ID"
