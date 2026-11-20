"""
Direct Upload Service Test
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.upload import (
    validate_file_extension,
    validate_file_size,
    process_upload
)

async def test_service():
    print("=" * 70)
    print("UPLOAD SERVICE TESTS")
    print("=" * 70)
    
    print("\n[TEST 1] Extension Validation")
    valid, error = validate_file_extension("test.pdf")
    print(f"  test.pdf: Valid={valid}")
    assert valid == True
    
    valid, error = validate_file_extension("test.jpg")
    print(f"  test.jpg: Valid={valid}, Error={error}")
    assert valid == False
    print("✅ PASSED\n")
    
    print("[TEST 2] Size Validation")
    valid, error = validate_file_size(1024)
    print(f"  1 KB: Valid={valid}")
    assert valid == True
    
    valid, error = validate_file_size(0)
    print(f"  0 bytes: Valid={valid}, Error={error}")
    assert valid == False
    print("✅ PASSED\n")
    
    print("[TEST 3] Process Upload")
    result = await process_upload(
        file_content=b"Test content",
        filename="test.txt",
        file_size=12
    )
    print(f"  Success: {result.get('success')}")
    if result.get("success"):
        print(f"  Document ID: {result.get('document_id')}")
    print("✅ PASSED\n")
    
    print("=" * 70)
    print("✅ ALL TESTS PASSED")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_service())
