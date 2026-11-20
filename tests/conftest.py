"""
Pytest configuration and shared fixtures for the Document Agent test suite.

Safety contract
---------------
All tests run against test_documents.db, never against the production
documents.db.  The DOCUMENTS_DATABASE_PATH environment variable is set here,
BEFORE any backend module is imported, so db.py picks up the test path when it
evaluates os.environ.get('DOCUMENTS_DATABASE_PATH', ...) at import time.

A hard assertion prevents the test database path from ever equalling the
production database path.  If that assertion fires, something in the
environment is misconfigured — the suite will refuse to run rather than corrupt
real data.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Redirect the database BEFORE any backend module is imported.
# pytest imports conftest.py before it imports any test module, so this runs
# first.  db.py reads:
#   DATABASE_PATH = os.environ.get('DOCUMENTS_DATABASE_PATH', '...documents.db')
# at module-level, so the env var must be in place before that import.
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
TEST_DB_PATH  = PROJECT_ROOT / "test_documents.db"
PROD_DB_PATH  = PROJECT_ROOT / "documents.db"

# Safety check: abort the entire test session if paths are equal.
assert TEST_DB_PATH.resolve() != PROD_DB_PATH.resolve(), (
    "SAFETY VIOLATION: test database path equals production database path.\n"
    f"  Test DB : {TEST_DB_PATH}\n"
    f"  Prod DB : {PROD_DB_PATH}\n"
    "Aborting to protect production data."
)

os.environ["DOCUMENTS_DATABASE_PATH"] = str(TEST_DB_PATH)

# ---------------------------------------------------------------------------
# Backend modules may now be imported — they will all read the test path.
# ---------------------------------------------------------------------------

import aiosqlite
import pytest
from fastapi.testclient import TestClient

pytest_plugins = ("pytest_asyncio",)


# ---------------------------------------------------------------------------
# Internal helper: collect file_path values from test_documents.db.
# Used to identify which physical files were created by tests so that only
# those files are deleted.  Files not in test_documents.db are never touched.
# ---------------------------------------------------------------------------

async def _test_db_file_paths() -> list:
    """Return file_path values recorded in test_documents.db."""
    try:
        async with aiosqlite.connect(str(TEST_DB_PATH)) as db:
            async with db.execute("SELECT file_path FROM documents") as cur:
                rows = await cur.fetchall()
        return [r[0] for r in rows if r[0]]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def client():
    """
    Session-scoped FastAPI test client.

    Using TestClient as a context manager guarantees that the ASGI lifespan
    (startup / shutdown events) runs exactly once per test session:
      - startup: initialises test_documents.db, creates the uploads directory
      - shutdown: logs clean shutdown

    The database is redirected to test_documents.db via the env var set above,
    so no production data is touched.
    """
    from backend.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
async def clean_test_db():
    """
    Auto-use fixture that runs around every test.

    Before each test
    ----------------
    1. Ensures test_documents.db schema exists (idempotent).
    2. Clears all rows from test_documents.db.

    After each test
    ---------------
    1. Reads file_path values that were inserted into test_documents.db
       during the test.
    2. Deletes only those physical files from data/uploads/ — files whose
       paths are recorded in test_documents.db.
    3. Clears all rows from test_documents.db again.

    Safety guarantees
    -----------------
    - Only files whose paths appear in test_documents.db are deleted.
    - Files linked to documents.db (production records) are never touched;
      there is no code path here that reads or modifies documents.db.
    - The production database path is never opened by this fixture.
    """
    from backend.database.db import initialize_database, clear_all_documents

    # --- setup ---
    await initialize_database()
    await clear_all_documents()

    yield

    # --- teardown: delete physical files created during this test ---
    paths_to_delete = await _test_db_file_paths()
    for path_str in paths_to_delete:
        p = Path(path_str)
        # Extra guard: only delete files that live inside data/uploads/
        try:
            p.relative_to(PROJECT_ROOT / "data" / "uploads")
            inside_uploads = True
        except ValueError:
            inside_uploads = False

        if inside_uploads and p.exists() and p.is_file():
            p.unlink()

    await clear_all_documents()
