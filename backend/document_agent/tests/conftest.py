"""
Shared pytest fixtures for the Document Agent tests.

Design goal: the WHOLE suite runs with ONLY pytest installed — no
sentence-transformers model download, no chromadb, and (for the heavy
extraction libs) graceful skips. We achieve this by:

  * FakeEmbedder — a deterministic offline embedder for storage/pipeline tests.
  * Installing FAKE `sentence_transformers` and `chromadb` modules into
    sys.modules, so the real packages are never imported (no model download,
    no chromadb required). Tests that need specific model behavior configure
    the fake via the `st_state` fixture; the DB is an in-memory fake collection.

All document fixtures are SMALL SYNTHETIC fixtures — invented financial-looking
text, NOT real company reports.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

# --- Make `import document_agent` work -------------------------------------
# parents[2] is the backend/ directory (this file lives at tests/conftest.py).
_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


# --- Synthetic fixture text ------------------------------------------------
SYNTHETIC_TEXT = (
    "ACME Corporation - Synthetic Test Fixture (not a real company)\n"
    "Annual Report 2024\n"
    "Total revenue for fiscal year 2024 was $1,250,000, up 12.5% year-over-year.\n"
    "Operating margin improved to 18.3% from 15.1% in the prior year.\n"
    "Net income was $210,000 and earnings per share (EPS) reached $2.45.\n"
    "The debt-to-equity ratio was 0.42 as of December 31, 2024.\n"
    "This is a synthetic test fixture and does not represent any real company.\n"
)


# --- Fake sentence_transformers (no model download) ------------------------
class _FakeSTState:
    """Mutable per-test state for the fake Sentence Transformers model."""
    dimension: int = 384
    fail_load: bool = False
    fail_encode: bool = False
    encode_dim_override = None  # if set, encode() returns vectors of THIS length


class _FakeVectors:
    """Mimics a numpy array just enough: .tolist() -> list[list[float]]."""
    def __init__(self, data):
        self._data = data

    def tolist(self):
        return self._data


class _FakeSTModel:
    def __init__(self, name):
        if _FakeSTState.fail_load:
            raise RuntimeError("fake model load failure")
        self._name = name

    def get_sentence_embedding_dimension(self):
        return _FakeSTState.dimension

    def encode(self, texts, convert_to_numpy=True, show_progress_bar=False):
        if _FakeSTState.fail_encode:
            raise RuntimeError("fake encode failure")
        dim = _FakeSTState.encode_dim_override
        if dim is None:
            dim = _FakeSTState.dimension
        return _FakeVectors(
            [[float((i + j) % 97) / 97.0 for j in range(dim)]
             for i, _ in enumerate(texts)]
        )


def _build_fake_sentence_transformers_module():
    mod = types.ModuleType("sentence_transformers")
    mod.SentenceTransformer = _FakeSTModel
    return mod


# --- Fake chromadb (in-memory; no external service) -----------------------
class _FakeCollection:
    def __init__(self, name):
        self.name = name
        self._records = {}  # id -> {"document", "metadata", "embedding"}

    def upsert(self, ids, embeddings, documents, metadatas):
        for i, _id in enumerate(ids):
            self._records[_id] = {
                "document": documents[i],
                "metadata": dict(metadatas[i]),
                "embedding": embeddings[i],
            }

    def _matches(self, record, where):
        if not where:
            return True
        return all(record["metadata"].get(k) == v for k, v in where.items())

    def get(self, where=None, include=None):
        ids, metas, docs = [], [], []
        for _id, rec in self._records.items():
            if self._matches(rec, where):
                ids.append(_id)
                metas.append(rec["metadata"])
                docs.append(rec["document"])
        return {"ids": ids, "metadatas": metas, "documents": docs}

    def query(self, query_embeddings, n_results, where=None):
        """Return up to `n_results` records matching `where`, in INSERTION ORDER.

        Deliberately simple: `query_embeddings` are IGNORED and `distances` are
        all 0.0 — no similarity is computed. Tests using this fake MUST verify
        STRUCTURE (counts, metadata, filtering, isolation), NOT semantic
        relevance, because no ranking by similarity is performed.
        """
        chosen = []
        for _id, rec in self._records.items():
            if self._matches(rec, where):
                chosen.append((_id, rec))
            if len(chosen) >= n_results:
                break
        return {
            "ids": [[c[0] for c in chosen]],
            "documents": [[c[1]["document"] for c in chosen]],
            "metadatas": [[c[1]["metadata"] for c in chosen]],
            "distances": [[0.0 for _ in chosen]],
        }

    def delete(self, ids):
        for _id in ids:
            self._records.pop(_id, None)


class _FakeClient:
    def __init__(self, path):
        self._path = path
        self._collections = {}

    def get_or_create_collection(self, name):
        if name not in self._collections:
            self._collections[name] = _FakeCollection(name)
        return self._collections[name]


def _build_fake_chromadb_module():
    mod = types.ModuleType("chromadb")
    mod.PersistentClient = lambda path=None, **kwargs: _FakeClient(path)
    return mod


# --- Install fakes once per session (autouse) ------------------------------
@pytest.fixture(scope="session", autouse=True)
def _install_fakes():
    saved_st = sys.modules.get("sentence_transformers")
    saved_ch = sys.modules.get("chromadb")
    sys.modules["sentence_transformers"] = _build_fake_sentence_transformers_module()
    sys.modules["chromadb"] = _build_fake_chromadb_module()
    yield
    for name, saved in (("sentence_transformers", saved_st), ("chromadb", saved_ch)):
        if saved is not None:
            sys.modules[name] = saved
        else:
            sys.modules.pop(name, None)


# --- Reset fake state + clear pipeline caches before every test ------------
@pytest.fixture(autouse=True)
def _reset_fakes():
    _FakeSTState.dimension = 384
    _FakeSTState.fail_load = False
    _FakeSTState.fail_encode = False
    _FakeSTState.encode_dim_override = None
    # Let import/cache-reset errors surface rather than silently hiding them.
    from document_agent import pipeline
    pipeline._embedders.clear()
    pipeline._vector_stores.clear()
    yield


@pytest.fixture
def st_state():
    """Expose the fake-model state so a test can configure it (after reset)."""
    return _FakeSTState


# --- Document path fixtures ------------------------------------------------
@pytest.fixture
def txt_path(tmp_path):
    path = tmp_path / "synthetic_report.txt"
    path.write_text(SYNTHETIC_TEXT, encoding="utf-8")
    return path


@pytest.fixture
def docx_path(tmp_path):
    pytest.importorskip("docx")  # python-docx
    import docx
    path = tmp_path / "synthetic_report.docx"
    document = docx.Document()
    document.add_heading("ACME Corporation Annual Report 2024", level=1)
    document.add_paragraph(SYNTHETIC_TEXT)
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Metric"
    table.rows[0].cells[1].text = "Value"
    table.rows[1].cells[0].text = "Revenue"
    table.rows[1].cells[1].text = "$1,250,000"
    document.save(str(path))
    return path


@pytest.fixture
def pdf_path(tmp_path):
    pytest.importorskip("fpdf")
    from fpdf import FPDF
    path = tmp_path / "synthetic_report.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for line in SYNTHETIC_TEXT.strip().split("\n"):
        pdf.cell(0, 10, txt=line, ln=True)
    pdf.output(str(path))
    return path


# --- Config fixture (per-test temp ChromaDB dir) ---------------------------
@pytest.fixture
def test_config(tmp_path):
    from document_agent.config import DocumentAgentConfig
    return DocumentAgentConfig(
        embedding_model_name="all-MiniLM-L6-v2",
        embedding_dimension=384,
        chroma_collection_name="financial_documents_test",
        chroma_persist_directory=tmp_path / "vector_db",
        chunk_size=1000,
        chunk_overlap=200,
        supported_file_types=("pdf", "docx", "txt"),
    )


# --- FakeEmbedder (offline, deterministic) ---------------------------------
class FakeEmbedder:
    """Deterministic, offline embedder. Vectors are not semantically meaningful;
    tests using it check STRUCTURE, not relevance."""

    def __init__(self, dimension=8):
        self._dimension = dimension

    @property
    def dimension(self):
        return self._dimension

    def embed(self, texts):
        out = []
        for text in texts:
            base = abs(hash(text)) or 1
            out.append([((base >> i) % 97) / 97.0 for i in range(self._dimension)])
        return out


@pytest.fixture
def fake_embedder():
    return FakeEmbedder(dimension=8)
