"""
Stage 5 Final Tests: Document Management APIs
Covers all three tasks:
  - 404 handler passes through endpoint detail message
  - GET /api/documents/ with status / file_type / search filters (independent + combined)
  - Existing endpoints: list all, get by id, delete, physical file removal

Safety:
  DATABASE_PATH is patched to test_documents.db BEFORE any backend import.
  Production documents.db is never touched.
"""

import asyncio, sys
from pathlib import Path
from httpx import AsyncClient, ASGITransport
import aiosqlite

# ------------------------------------------------------------------
# Safety: redirect the database before any backend import resolves
# ------------------------------------------------------------------
TEST_DB_PATH = Path(__file__).parent / "test_documents.db"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

sys.path.insert(0, str(Path(__file__).parent))
import backend.database.db as _db_mod
_db_mod.DATABASE_PATH = str(TEST_DB_PATH)

from backend.main import app
from backend.database.db import initialize_database, clear_all_documents

# Real PDF magic bytes (python-magic -> application/pdf -> stored as PDF)
MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
    b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n9\n%%EOF\n"
)
MINIMAL_TXT  = b"Plain text document content.\n" * 20

BASE_URL  = "http://testserver"
UP_EP     = "/api/documents/upload"
DOCS_EP   = "/api/documents/"

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def hdr(name):
    print(f"\n{'='*60}\nTEST: {name}\n{'='*60}")

def ok(msg):
    print(f"[OK] PASS: {msg}")

def fail(msg):
    print(f"[X]  FAIL: {msg}")


async def setup():
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    await initialize_database()
    print(f"[DB] Test DB : {TEST_DB_PATH}")
    print( "[DB] documents.db : UNTOUCHED (production database)")


async def upload(client, name, body):
    r = await client.post(UP_EP, files={"file": (name, body, "application/octet-stream")})
    assert r.status_code == 201, f"Upload {name!r} failed ({r.status_code}): {r.text}"
    return r.json()["document"]


# ------------------------------------------------------------------
# Tests — existing endpoints
# ------------------------------------------------------------------

async def test_list_empty(client):
    hdr("test_list_empty")
    await clear_all_documents()
    r = await client.get(DOCS_EP)
    assert r.status_code == 200
    d = r.json()
    assert d["count"] == 0 and d["documents"] == []
    ok("count=0, documents=[]")


async def test_list_all(client):
    hdr("test_list_all")
    await clear_all_documents()
    for n, b in [("a.pdf", MINIMAL_PDF), ("b.txt", MINIMAL_TXT), ("c.txt", MINIMAL_TXT)]:
        await upload(client, n, b)
    r = await client.get(DOCS_EP)
    d = r.json()
    assert d["count"] == 3, f"expected 3 got {d['count']}"
    ok(f"{d['count']} documents returned (no filter)")


async def test_get_by_id_pdf(client):
    hdr("test_get_by_id_pdf  (real PDF bytes, file_type must be PDF)")
    await clear_all_documents()
    doc = await upload(client, "sample.pdf", MINIMAL_PDF)
    r = await client.get(f"{DOCS_EP}{doc['document_id']}")
    assert r.status_code == 200
    d = r.json()["document"]
    assert d["filename"] == "sample.pdf"
    assert d["file_type"] == "PDF", (
        f"Expected PDF, got {d['file_type']}. "
        "MIME detection did not identify real PDF bytes as application/pdf."
    )
    ok(f"file_type={d['file_type']}")


async def test_get_by_id_txt(client):
    hdr("test_get_by_id_txt")
    await clear_all_documents()
    doc = await upload(client, "notes.txt", MINIMAL_TXT)
    r = await client.get(f"{DOCS_EP}{doc['document_id']}")
    assert r.status_code == 200
    d = r.json()["document"]
    assert d["file_type"] == "TXT", f"Expected TXT, got {d['file_type']}"
    ok(f"file_type={d['file_type']}")


async def test_delete_existing(client):
    hdr("test_delete_existing")
    await clear_all_documents()
    doc = await upload(client, "todel.txt", MINIMAL_TXT)
    dr = await client.delete(f"{DOCS_EP}{doc['document_id']}")
    assert dr.status_code == 200
    d = dr.json()
    assert d["status"] == "success" and "deleted" in d["message"].lower()
    gr = await client.get(f"{DOCS_EP}{doc['document_id']}")
    assert gr.status_code == 404, "document must be gone after DELETE"
    ok("deleted; subsequent GET returns 404")


async def test_delete_removes_physical_file(client):
    hdr("test_delete_removes_physical_file")
    await clear_all_documents()
    doc = await upload(client, "phys.txt", MINIMAL_TXT)
    async with aiosqlite.connect(_db_mod.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT file_path FROM documents WHERE document_id = ?",
            (doc["document_id"],)
        ) as cur:
            row = await cur.fetchone()
    assert row, "row not found in test DB"
    file_path = Path(row["file_path"])
    assert file_path.exists(), f"file missing before DELETE: {file_path}"
    dr = await client.delete(f"{DOCS_EP}{doc['document_id']}")
    assert dr.status_code == 200
    assert not file_path.exists(), "physical file must be removed after DELETE"
    ok("physical file removed from disk")


# ------------------------------------------------------------------
# Tests — 404 detail message (Task 1)
# ------------------------------------------------------------------

FAKE_ID = "00000000-0000-0000-0000-000000000000"

async def test_get_not_found_detail(client):
    hdr("test_get_not_found_detail  (404 must carry document-specific message)")
    r = await client.get(f"{DOCS_EP}{FAKE_ID}")
    assert r.status_code == 404, f"expected 404 got {r.status_code}"
    body = r.json()
    # Must have a 'detail' key containing the document id
    assert "detail" in body, f"response has no 'detail' key: {body}"
    assert FAKE_ID in body["detail"], (
        f"'detail' does not contain the document id.\n"
        f"Expected substring: {FAKE_ID!r}\n"
        f"Got: {body['detail']!r}"
    )
    ok(f"detail={body['detail']!r}")


async def test_delete_not_found_detail(client):
    hdr("test_delete_not_found_detail  (404 must carry document-specific message)")
    r = await client.delete(f"{DOCS_EP}{FAKE_ID}")
    assert r.status_code == 404, f"expected 404 got {r.status_code}"
    body = r.json()
    assert "detail" in body, f"response has no 'detail' key: {body}"
    assert FAKE_ID in body["detail"], (
        f"'detail' does not contain the document id.\n"
        f"Got: {body['detail']!r}"
    )
    ok(f"detail={body['detail']!r}")


# ------------------------------------------------------------------
# Tests — filtering (Task 2)
# ------------------------------------------------------------------

async def test_filter_by_status(client):
    hdr("test_filter_by_status")
    await clear_all_documents()
    # Upload two docs; manually set one to 'indexed' in test DB
    doc1 = await upload(client, "f1.pdf", MINIMAL_PDF)
    doc2 = await upload(client, "f2.txt", MINIMAL_TXT)
    async with aiosqlite.connect(_db_mod.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE documents SET status='indexed' WHERE document_id=?",
            (doc1["document_id"],)
        )
        await db.commit()

    r_up = await client.get(DOCS_EP, params={"status": "uploaded"})
    assert r_up.status_code == 200
    d_up = r_up.json()
    assert d_up["count"] == 1, f"expected 1 'uploaded', got {d_up['count']}"
    assert d_up["documents"][0]["document_id"] == doc2["document_id"]

    r_ix = await client.get(DOCS_EP, params={"status": "indexed"})
    d_ix = r_ix.json()
    assert d_ix["count"] == 1, f"expected 1 'indexed', got {d_ix['count']}"
    assert d_ix["documents"][0]["document_id"] == doc1["document_id"]

    r_no = await client.get(DOCS_EP, params={"status": "failed"})
    assert r_no.json()["count"] == 0
    ok("status filter works (uploaded=1, indexed=1, failed=0)")


async def test_filter_by_file_type(client):
    hdr("test_filter_by_file_type")
    await clear_all_documents()
    await upload(client, "r1.pdf", MINIMAL_PDF)
    await upload(client, "r2.pdf", MINIMAL_PDF)
    await upload(client, "t1.txt", MINIMAL_TXT)

    r_pdf = await client.get(DOCS_EP, params={"file_type": "PDF"})
    assert r_pdf.json()["count"] == 2, f"expected 2 PDF, got {r_pdf.json()['count']}"

    r_txt = await client.get(DOCS_EP, params={"file_type": "TXT"})
    assert r_txt.json()["count"] == 1, f"expected 1 TXT, got {r_txt.json()['count']}"

    r_doc = await client.get(DOCS_EP, params={"file_type": "DOCX"})
    assert r_doc.json()["count"] == 0
    ok("file_type filter works (PDF=2, TXT=1, DOCX=0)")


async def test_filter_by_search(client):
    hdr("test_filter_by_search")
    await clear_all_documents()
    await upload(client, "annual_report.pdf", MINIMAL_PDF)
    await upload(client, "quarterly_report.pdf", MINIMAL_PDF)
    await upload(client, "meeting_notes.txt", MINIMAL_TXT)

    r = await client.get(DOCS_EP, params={"search": "report"})
    d = r.json()
    assert d["count"] == 2, f"expected 2 for 'report', got {d['count']}"

    r2 = await client.get(DOCS_EP, params={"search": "notes"})
    assert r2.json()["count"] == 1

    r3 = await client.get(DOCS_EP, params={"search": "ANNUAL"})  # case-insensitive
    assert r3.json()["count"] == 1, f"case-insensitive search failed: got {r3.json()['count']}"

    r4 = await client.get(DOCS_EP, params={"search": "budget"})
    assert r4.json()["count"] == 0
    ok("search filter works (report=2, notes=1, ANNUAL=1, budget=0)")


async def test_filter_combined(client):
    hdr("test_filter_combined  (file_type + search)")
    await clear_all_documents()
    await upload(client, "q1_report.pdf", MINIMAL_PDF)
    await upload(client, "q2_report.pdf", MINIMAL_PDF)
    await upload(client, "q1_notes.txt",  MINIMAL_TXT)

    r = await client.get(DOCS_EP, params={"file_type": "PDF", "search": "report"})
    d = r.json()
    assert d["count"] == 2, f"expected 2 (PDF+report), got {d['count']}"
    for doc in d["documents"]:
        assert doc["file_type"] == "PDF"
        assert "report" in doc["filename"].lower()

    r2 = await client.get(DOCS_EP, params={"file_type": "TXT", "search": "report"})
    assert r2.json()["count"] == 0, "no TXT files are named 'report'"
    ok("combined filter (file_type=PDF, search=report) -> 2 results")


async def test_filter_combined_all_three(client):
    hdr("test_filter_combined_all_three  (status + file_type + search)")
    await clear_all_documents()
    doc = await upload(client, "indexed_report.pdf", MINIMAL_PDF)
    await upload(client, "uploaded_report.pdf", MINIMAL_PDF)
    await upload(client, "indexed_notes.txt", MINIMAL_TXT)

    # Promote one doc to 'indexed'
    async with aiosqlite.connect(_db_mod.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE documents SET status='indexed' WHERE document_id=?",
            (doc["document_id"],)
        )
        await db.commit()

    r = await client.get(DOCS_EP, params={
        "status": "indexed", "file_type": "PDF", "search": "report"
    })
    d = r.json()
    assert d["count"] == 1, f"expected 1, got {d['count']}"
    assert d["documents"][0]["document_id"] == doc["document_id"]
    ok("three-way filter returns exactly the right document")


# ------------------------------------------------------------------
# Full workflow smoke test
# ------------------------------------------------------------------

async def test_full_workflow(client):
    hdr("test_full_workflow")
    await clear_all_documents()
    ids = []
    for n, b in [("w1.pdf", MINIMAL_PDF), ("w2.txt", MINIMAL_TXT), ("w3.txt", MINIMAL_TXT)]:
        doc = await upload(client, n, b)
        ids.append(doc["document_id"])
    assert (await client.get(DOCS_EP)).json()["count"] == 3
    for i in ids:
        assert (await client.get(f"{DOCS_EP}{i}")).status_code == 200
    assert (await client.delete(f"{DOCS_EP}{ids[0]}")).status_code == 200
    assert (await client.get(DOCS_EP)).json()["count"] == 2
    ok("upload/list/get/delete/list all consistent")


# ------------------------------------------------------------------
# Runner
# ------------------------------------------------------------------

async def main():
    print("\n" + "="*60)
    print("STAGE 5 FINAL TESTS - isolated test database")
    print("="*60)
    print(f"Test DB  : {TEST_DB_PATH}")
    print( "Prod DB  : documents.db  [NOT MODIFIED]")
    print("="*60)

    await setup()

    all_tests = [
        # Existing endpoint behaviour
        test_list_empty,
        test_list_all,
        test_get_by_id_pdf,
        test_get_by_id_txt,
        test_delete_existing,
        test_delete_removes_physical_file,
        # Task 1: 404 detail
        test_get_not_found_detail,
        test_delete_not_found_detail,
        # Task 2: filtering
        test_filter_by_status,
        test_filter_by_file_type,
        test_filter_by_search,
        test_filter_combined,
        test_filter_combined_all_three,
        # Smoke test
        test_full_workflow,
    ]

    results = []
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL) as client:
        for t in all_tests:
            try:
                await clear_all_documents()
                await t(client)
                results.append((t.__name__, True, None))
            except AssertionError as e:
                fail(str(e))
                results.append((t.__name__, False, str(e)))
            except Exception as e:
                fail(f"Unexpected: {e}")
                results.append((t.__name__, False, str(e)))

    n_pass = sum(1 for _, o, _ in results if o)
    n_fail = len(results) - n_pass
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for name, o, err in results:
        sym = "OK" if o else "X"
        print(f"[{sym}] {name}")
        if err:
            print(f"      -> {err}")
    print(f"\nPassed : {n_pass}/{len(results)}")
    print(f"Failed : {n_fail}/{len(results)}")
    print("="*60)
    return n_fail == 0


if __name__ == "__main__":
    ok_flag = asyncio.run(main())
    sys.exit(0 if ok_flag else 1)
