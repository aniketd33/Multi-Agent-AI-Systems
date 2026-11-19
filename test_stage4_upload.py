"""
Stage 4 Upload API Verification Tests
Simple tests without Unicode characters that cause encoding issues
"""
from fastapi.testclient import TestClient
from backend.main import app
from io import BytesIO
import sys

client = TestClient(app)

def test_valid_pdf_upload():
    """Test 1: Valid PDF upload"""
    print("\n[TEST 1] Valid PDF Upload")
    response = client.post(
        "/api/documents/upload",
        files={"file": ("test_report.pdf", BytesIO(b"%PDF-1.4\n" + b"0" * 1000), "application/pdf")}
    )
    
    assert response.status_code == 201, f"Expected 201, got {response.status_code}"
    data = response.json()
    assert data["status"] == "success"
    assert data["document"]["file_type"] == "PDF"
    print("  Status: 201 Created")
    print(f"  Document ID: {data['document']['document_id']}")
    print("  Result: PASSED")
    return True

def test_valid_txt_upload():
    """Test 2: Valid TXT upload"""
    print("\n[TEST 2] Valid TXT Upload")
    response = client.post(
        "/api/documents/upload",
        files={"file": ("notes.txt", BytesIO(b"Test content"), "text/plain")}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["document"]["file_type"] == "TXT"
    print("  Status: 201 Created")
    print("  Result: PASSED")
    return True

def test_invalid_extension():
    """Test 3: Invalid file extension (JPG)"""
    print("\n[TEST 3] Invalid Extension (JPG - should reject)")
    response = client.post(
        "/api/documents/upload",
        files={"file": ("image.jpg", BytesIO(b"fake image"), "image/jpeg")}
    )
    
    assert response.status_code == 400, f"Expected 400, got {response.status_code}"
    print("  Status: 400 Bad Request")
    print(f"  Error: {response.json()['detail']}")
    print("  Result: PASSED")
    return True

def test_empty_file():
    """Test 4: Empty file"""
    print("\n[TEST 4] Empty File (should reject)")
    response = client.post(
        "/api/documents/upload",
        files={"file": ("empty.pdf", BytesIO(b""), "application/pdf")}
    )
    
    assert response.status_code == 400
    print("  Status: 400 Bad Request")
    print(f"  Error: {response.json()['detail']}")
    print("  Result: PASSED")
    return True

def test_oversized_file():
    """Test 5: File larger than 20MB"""
    print("\n[TEST 5] Oversized File (should reject)")
    # Create 21MB file
    large_content = b"0" * (21 * 1024 * 1024)
    response = client.post(
        "/api/documents/upload",
        files={"file": ("huge.pdf", BytesIO(large_content), "application/pdf")}
    )
    
    assert response.status_code == 400
    print("  Status: 400 Bad Request")
    print("  Error: File too large")
    print("  Result: PASSED")
    return True

def test_no_extension():
    """Test 6: File without extension"""
    print("\n[TEST 6] File Without Extension (should reject)")
    response = client.post(
        "/api/documents/upload",
        files={"file": ("noextension", BytesIO(b"content"), "application/octet-stream")}
    )
    
    assert response.status_code == 400
    print("  Status: 400 Bad Request")
    print("  Result: PASSED")
    return True

def run_all_tests():
    """Run all tests"""
    print("=" * 70)
    print("STAGE 4: UPLOAD API VERIFICATION TESTS")
    print("=" * 70)
    
    tests = [
        test_valid_pdf_upload,
        test_valid_txt_upload,
        test_invalid_extension,
        test_empty_file,
        test_oversized_file,
        test_no_extension
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  Result: FAILED - {e}")
            failed += 1
        except Exception as e:
            print(f"  Result: ERROR - {e}")
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"TEST SUMMARY: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 70)
    
    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
