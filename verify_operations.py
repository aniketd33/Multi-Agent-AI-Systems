"""
Individual Database Operations Verification
Tests each operation step by step
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from backend.database import (
    initialize_database,
    insert_document,
    get_all_documents,
    get_document_by_id,
    update_document_status,
    delete_document,
    get_document_count,
    clear_all_documents
)

async def verify_operations():
    print("=" * 70)
    print("DATABASE OPERATIONS VERIFICATION")
    print("=" * 70)
    
    # Clear database first
    print("\n[SETUP] Clearing database...")
    await clear_all_documents()
    print("✅ Database cleared\n")
    
    # Test 1: Initialize
    print("[TEST 1] Initialize Database")
    result = await initialize_database()
    print(f"Result: {result}")
    assert result == True, "❌ Initialization failed"
    print("✅ PASSED\n")
    
    # Test 2: Insert Document
    print("[TEST 2] Insert Document")
    result = await insert_document(
        document_id="test-doc-001",
        filename="verification_test.pdf",
        file_type="PDF",
        file_size=2048,
        file_path="/test/path/verification_test.pdf",
        company_name="Test Company"
    )
    print(f"Result: {result}")
    assert result == True, "❌ Insert failed"
    print("✅ PASSED\n")
    
    # Test 3: Get Document Count
    print("[TEST 3] Get Document Count")
    count = await get_document_count()
    print(f"Count: {count}")
    assert count == 1, f"❌ Expected 1, got {count}"
    print("✅ PASSED\n")
    
    # Test 4: Get All Documents
    print("[TEST 4] Get All Documents")
    docs = await get_all_documents()
    print(f"Found: {len(docs)} document(s)")
    if docs:
        print(f"  Document ID: {docs[0]['document_id']}")
        print(f"  Filename: {docs[0]['filename']}")
        print(f"  Status: {docs[0]['status']}")
    assert len(docs) == 1, "❌ Should have 1 document"
    print("✅ PASSED\n")
    
    # Test 5: Get Document by ID
    print("[TEST 5] Get Document by ID")
    doc = await get_document_by_id("test-doc-001")
    print(f"Found: {doc is not None}")
    if doc:
        print(f"  Filename: {doc['filename']}")
        print(f"  File Type: {doc['file_type']}")
        print(f"  Status: {doc['status']}")
    assert doc is not None, "❌ Document not found"
    assert doc['filename'] == "verification_test.pdf", "❌ Wrong filename"
    print("✅ PASSED\n")
    
    # Test 6: Update Document Status
    print("[TEST 6] Update Document Status")
    result = await update_document_status("test-doc-001", "processing")
    print(f"Update Result: {result}")
    assert result == True, "❌ Update failed"
    
    # Verify update
    doc = await get_document_by_id("test-doc-001")
    print(f"New Status: {doc['status']}")
    assert doc['status'] == "processing", "❌ Status not updated"
    print("✅ PASSED\n")
    
    # Test 7: Delete Document
    print("[TEST 7] Delete Document")
    result = await delete_document("test-doc-001")
    print(f"Delete Result: {result}")
    assert result == True, "❌ Delete failed"
    
    # Verify deletion
    count = await get_document_count()
    print(f"Final Count: {count}")
    assert count == 0, "❌ Document not deleted"
    print("✅ PASSED\n")
    
    # Test 8: Duplicate ID Handling
    print("[TEST 8] Duplicate Document ID Handling")
    await insert_document("dup-test", "file1.pdf", "PDF", 100, "/test/file1.pdf")
    print("First insert: Success")
    result2 = await insert_document("dup-test", "file2.pdf", "PDF", 200, "/test/file2.pdf")
    print(f"Duplicate insert: {result2}")
    assert result2 == False, "❌ Should reject duplicate ID"
    count = await get_document_count()
    print(f"Count after duplicate attempt: {count}")
    assert count == 1, "❌ Should still have only 1 document"
    print("✅ PASSED\n")
    
    # Cleanup
    await clear_all_documents()
    
    print("=" * 70)
    print("✅ ALL 8 VERIFICATION TESTS PASSED!")
    print("=" * 70)
    return True

if __name__ == "__main__":
    try:
        result = asyncio.run(verify_operations())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"\n❌ VERIFICATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
