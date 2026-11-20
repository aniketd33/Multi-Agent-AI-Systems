# Document Agent — Document Processing + AI Pipeline

Part of the **Multi-Agent Financial Research System**. This package is owned by
**Durga** and lives on the `Durga/document-agent` branch.

The Document Agent turns financial documents (PDF / DOCX / TXT) into searchable
vector data so other AI agents in the system can retrieve relevant passages.

---

## Current status: Core pipeline implemented

The package now includes configuration, public pipeline functions, PDF/DOCX/TXT
text extraction, financial-text cleaning, character-based chunking, real
Sentence Transformers embeddings, persistent ChromaDB indexing, and similarity
search retrieval.

Automated unit and end-to-end tests are present. A real, offline integration
smoke test has also passed with `all-MiniLM-L6-v2` and real ChromaDB for a
synthetic TXT document. This smoke-test result does not claim that PDF or DOCX
has passed a real end-to-end test.

---

## Folder structure

```
backend/document_agent/
├── __init__.py            package marker + (later) public API exports
├── config.py              configuration via environment variables      [Phase 1]
├── exceptions.py           custom exception classes                     [Phase 1]
├── models.py              dataclasses: Chunk, ChunkMetadata, etc.      [Phase 1]
├── extractors.py          PDF/DOCX/TXT text extraction                 [Phase 3]
├── cleaner.py             text cleaning (preserves financial info)     [Phase 4]
├── chunker.py             text chunking with overlap                   [Phase 5]
├── embedder.py            Sentence Transformers embeddings             [Phase 6]
├── vector_store.py        ChromaDB setup, storage, retrieval           [Phases 7-9]
├── pipeline.py            orchestrates process_document()             [Phase 8+]
├── seed_loader.py         processes the 3-4 seed documents            [Phase 10]
├── requirements.txt       module-local dependencies                   [Phase 1]
├── README.md              this file                                    [Phase 1]
├── .gitignore             nested ignore rules                         [Phase 1]
├── data/
│   ├── seed_documents/    3-4 seed financial docs (after approval)    [Phase 10]
│   └── vector_db/         ChromaDB persistent storage (gitignored)    [Phase 7]
└── tests/                 unit + end-to-end tests                     [Phase 3+]
```

---

## Dependencies

See `requirements.txt`. Summary:

| Package | Purpose |
|---|---|
| `sentence-transformers` | Generate vector embeddings (initial model: `all-MiniLM-L6-v2`, 384-dim) |
| `chromadb` | Persistent vector database + similarity search |
| `pypdf` | PDF text extraction (lightweight, pure-Python) |
| `python-docx` | DOCX text extraction (paragraphs + tables) |
| `pytest` | Test runner |

TXT extraction uses Python's built-in `open()` — no extra dependency.

**Install dependencies:**

```bash
python -m pip install -r backend/document_agent/requirements.txt
```

> The version pins in `requirements.txt` are recommended minimums.

---

## Configuration

All settings come from environment variables with sensible defaults (see
`config.py`). None of these need to be set to run with defaults.

| Env var | Default | Meaning |
|---|---|---|
| `DA_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence Transformers model name |
| `DA_EMBEDDING_DIMENSION` | `384` | Expected embedding length — *additional* consistency check vs the model's actual dimension |
| `DA_CHROMA_COLLECTION` | `financial_documents` | ChromaDB collection name |
| `DA_CHROMA_PERSIST_DIR` | `…/data/vector_db` | ChromaDB on-disk storage path |
| `DA_CHUNK_SIZE` | `1000` | Chunk size in characters |
| `DA_CHUNK_OVERLAP` | `200` | Chunk overlap in characters |

---

## Public API

```python
from document_agent import process_document, search_documents

result = process_document(
    file_path="path/to/report.pdf",
    document_id="doc_2026_0001",
    metadata={"company_name": "Acme Corp", "document_type": "10-K"},
)
# result: ProcessingResult(success, document_id, pages_extracted,
#                          chunks_generated, chunks_indexed, message, error)

hits = search_documents("What was the operating margin in 2024?",
                        document_id="doc_2026_0001", top_k=5)
# hits: list[SearchResult(text, metadata, score)]
```

### Integration with the future upload API

The teammate's FastAPI endpoint (in `backend/main.py`, NOT this module) is
expected to:
1. Receive an uploaded file and save it to disk (their file management).
2. Generate a `document_id` (their id generation).
3. Call `process_document(saved_path, document_id, metadata)`.
4. Return the `ProcessingResult` fields as the HTTP response.

This module contains **no HTTP code** and does not import FastAPI; it stays a
plain, importable Python library so it can be unit-tested independently and
wired into any caller later.

---

## Key design decisions (per project requirements)

- **Metadata None-stripping:** `ChunkMetadata.to_storage_dict()` drops `None`
  fields before a record is written to ChromaDB, so only present values are
  stored. In-memory metadata still keeps `None` for traceability.
- **Safe re-indexing:** when a document is reprocessed, replacement chunks are
  prepared and inserted BEFORE stale chunks of the *same* `document_id` are
  removed. Chunks belonging to any other `document_id` are never deleted.
- **Embedding dimension validation (two layers):** the *actual* embedding
  dimension is obtained at runtime from the loaded Sentence Transformers model
  (e.g. via `model.get_sentence_embedding_dimension()`), and every generated
  embedding is validated against that actual dimension (primary, authoritative
  check). The configured `DA_EMBEDDING_DIMENSION` is an *additional*
  consistency check against the model's actual dimension, used to catch a
  model-name / config mismatch early. A failure in either layer raises
  `EmbeddingDimensionError`. The configured dimension is **not** the only
  validation.
- **Page information:** preserved wherever available (PDF). `None` is used when
  page info is unavailable (DOCX), never fabricated.
- **Single ChromaDB collection:** per-document isolation is done via metadata
  filtering (`where={"document_id": ...}`), not via separate collections.
- **No fabricated metadata:** optional fields are `None` when the information
  genuinely does not exist.
- **Seed documents:** none are downloaded or created without explicit approval.

---

## Verification status

- Automated test files are present for chunking, cleaning, embeddings,
  extractors, the pipeline, and vector storage.
- The real smoke test used `sentence-transformers/all-MiniLM-L6-v2` in local-only
  mode, real Sentence Transformers, real ChromaDB, a temporary TXT document,
  temporary persistence storage, and a document-id-filtered search.
- The smoke test confirmed TXT extraction, chunk generation, 384-dimensional
  embeddings, chunk indexing, and retrieval of the synthetic revenue content.
- PDF and DOCX extraction are implemented, but this record does not claim that
  each format has passed a real end-to-end integration test.

---

## Phase roadmap

1. ✅ Skeleton & architecture (this phase)
2. Dependency selection & project setup
3. PDF/DOCX/TXT extraction
4. Text cleaning & preprocessing
5. Text chunking
6. Embedding generation
7. ChromaDB setup & persistent storage
8. Chunk/embedding/metadata indexing
9. Similarity search & retrieval
10. Seed company document processing
11. Unit + end-to-end testing
12. Documentation & integration instructions

Each phase is implemented only after explicit approval, one at a time.
