"""
ChromaDB persistent storage and similarity search.

A single persistent collection holds every document's chunks. Per-document
isolation is done with metadata filtering (where={"document_id": ...}), NOT by
deleting the collection or using separate collections.

Safe re-indexing (per project requirement):
  - Replacement chunks (text, ids, embeddings, metadata) are prepared FIRST.
  - They are upserted by their deterministic chunk_id ("{document_id}__chunk_{i}").
  - Only then are STALE chunks of the SAME document_id removed (those whose ids
    are not in the new set). Chunks of any OTHER document_id are never touched.

chromadb is imported lazily so importing this module is cheap and does not
require chromadb to be installed.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from .config import DocumentAgentConfig
from .exceptions import VectorStoreError
from .models import Chunk, SearchResult

logger = logging.getLogger(__name__)


class VectorStore:
    """Persistent vector store backed by ChromaDB, using a provided embedder."""

    def __init__(self, config: DocumentAgentConfig, embedder):
        """
        Args:
            config: DocumentAgentConfig with collection name and persist dir.
            embedder: anything with an `embed(list_of_strings) -> list[vectors]`
                method (the real Embedder, or a fake in tests). The VectorStore
                depends only on that method, which keeps it easy to unit-test.
        """
        self._config = config
        self._embedder = embedder
        self._client = None
        self._collection = None

    def _ensure_collection(self):
        """Create/open the persistent collection on first use. Cached after."""
        if self._collection is not None:
            return self._collection
        try:
            import chromadb
        except ImportError as e:  # pragma: no cover - depends on env
            raise VectorStoreError(
                "chromadb is not installed. Run pip install -r requirements.txt"
            ) from e
        try:
            self._client = chromadb.PersistentClient(
                path=str(self._config.chroma_persist_directory)
            )
            self._collection = self._client.get_or_create_collection(
                name=self._config.chroma_collection_name
            )
        except Exception as e:
            raise VectorStoreError(f"Failed to initialize ChromaDB: {e}") from e
        return self._collection

    def index_chunks(self, chunks: List[Chunk], document_id: str) -> int:
        """Store chunks for one document, with safe re-indexing.

        Returns the number of chunks indexed. Other documents in the collection
        are never modified.
        """
        if not chunks:
            logger.warning(
                "index_chunks called with no chunks for document %s", document_id
            )
            return 0

        collection = self._ensure_collection()

        # --- Prepare replacement chunks FIRST (requirement) ---
        texts = [chunk.text for chunk in chunks]
        ids = [chunk.metadata.chunk_id for chunk in chunks]
        # to_storage_dict() drops None values, so ChromaDB never stores None.
        metadatas = [chunk.metadata.to_storage_dict() for chunk in chunks]
        embeddings = self._embedder.embed(texts)  # may raise EmbeddingError

        # --- Upsert new chunks (add or update by chunk_id) ---
        try:
            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
        except Exception as e:
            raise VectorStoreError(
                f"Failed to upsert chunks for document {document_id}: {e}"
            ) from e

        # --- Remove STALE chunks of THIS document only ---
        try:
            existing = collection.get(where={"document_id": document_id})
        except Exception as e:
            raise VectorStoreError(
                f"Failed to read existing chunks for document {document_id}: {e}"
            ) from e
        existing_ids = list(existing.get("ids", []))
        new_id_set = set(ids)
        stale_ids = [cid for cid in existing_ids if cid not in new_id_set]
        if stale_ids:
            try:
                collection.delete(ids=stale_ids)
            except Exception as e:
                raise VectorStoreError(
                    f"Failed to remove stale chunks for document {document_id}: {e}"
                ) from e
            logger.info(
                "Removed %d stale chunk(s) for document %s",
                len(stale_ids), document_id,
            )

        return len(ids)

    def search(
        self,
        query: str,
        top_k: int = 5,
        document_id: Optional[str] = None,
    ) -> List[SearchResult]:
        """Embed the query and return the most similar chunks from ChromaDB.

        If document_id is given, results are restricted to that document. An
        empty collection (or no matches) returns an empty list.
        """
        if top_k <= 0:
            raise VectorStoreError("top_k must be a positive integer")

        collection = self._ensure_collection()
        query_embeddings = self._embedder.embed([query])  # list of one vector

        where = {"document_id": document_id} if document_id else None
        try:
            raw = collection.query(
                query_embeddings=query_embeddings,
                n_results=top_k,
                where=where,
            )
        except Exception as e:
            raise VectorStoreError(f"Similarity search failed: {e}") from e

        # collection.query returns lists-of-lists (one per query); we sent one.
        ids = (raw.get("ids") or [[]])[0]
        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]

        results: List[SearchResult] = []
        for i, _id in enumerate(ids):
            results.append(
                SearchResult(
                    text=documents[i] if i < len(documents) else "",
                    metadata=metadatas[i] if i < len(metadatas) else {},
                    score=distances[i] if i < len(distances) else None,
                )
            )
        return results
