"""
Embedding generation with Sentence Transformers.

The Embedder owns the model and is the ONLY place embeddings are created, so
document chunks and search queries always use the same model. The model is
loaded lazily (on first use) so importing this module is cheap and does not
require sentence-transformers to be installed.

Dimension validation (two layers, per project requirement):
  1. PRIMARY: the actual dimension is read from the loaded model itself
     (model.get_sentence_embedding_dimension()). Every generated embedding is
     checked against THIS value.
  2. ADDITIONAL: the model's actual dimension is compared with the configured
     `embedding_dimension` (DA_EMBEDDING_DIMENSION). A mismatch means the
     configured model name and expected size disagree — caught before use.
"""

from __future__ import annotations

import logging
from typing import List, Sequence

from .config import DocumentAgentConfig
from .exceptions import EmbeddingDimensionError, EmbeddingError

logger = logging.getLogger(__name__)


class Embedder:
    """Wraps a Sentence Transformers model and validates embeddings."""

    def __init__(self, config: DocumentAgentConfig):
        self._config = config
        self._model = None
        self._actual_dimension = None

    def _ensure_loaded(self):
        """Load the model on first use and run dimension checks. Cached after."""
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:  # pragma: no cover - depends on env
            raise EmbeddingError(
                "sentence-transformers is not installed. "
                "Run pip install -r requirements.txt"
            ) from e

        try:
            self._model = SentenceTransformer(self._config.embedding_model_name)
        except Exception as e:
            raise EmbeddingError(
                f"Failed to load embedding model "
                f"'{self._config.embedding_model_name}': {e}"
            ) from e

        try:
            self._actual_dimension = int(
                self._model.get_sentence_embedding_dimension()
            )
        except Exception as e:
            raise EmbeddingError(
                "Could not determine the model's actual embedding dimension"
            ) from e

        # ADDITIONAL consistency check: configured expected dimension vs actual.
        if self._actual_dimension != self._config.embedding_dimension:
            raise EmbeddingDimensionError(
                f"Model '{self._config.embedding_model_name}' reports dimension "
                f"{self._actual_dimension}, but DA_EMBEDDING_DIMENSION is "
                f"{self._config.embedding_dimension}. Update the config to match "
                f"the model."
            )

        logger.info(
            "Loaded embedding model '%s' (actual dimension=%d)",
            self._config.embedding_model_name,
            self._actual_dimension,
        )
        return self._model

    @property
    def dimension(self) -> int:
        """The model's actual embedding dimension (loads the model if needed)."""
        self._ensure_loaded()
        return self._actual_dimension

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        """Return a list of embedding vectors, one per input text.

        Empty input returns an empty list. Each returned vector's length is
        validated against the model's actual dimension (PRIMARY check).
        """
        if not isinstance(texts, (list, tuple)):
            raise EmbeddingError("embed() expects a list (or tuple) of strings")
        if len(texts) == 0:
            return []

        model = self._ensure_loaded()
        try:
            vectors = model.encode(
                list(texts), convert_to_numpy=True, show_progress_bar=False
            )
        except Exception as e:
            raise EmbeddingError(f"Embedding generation failed: {e}") from e

        # Convert to plain Python lists for easy storage in ChromaDB.
        result = vectors.tolist() if hasattr(vectors, "tolist") else list(vectors)

        # PRIMARY validation: every embedding must match the model's actual dim.
        for vector in result:
            if len(vector) != self._actual_dimension:
                raise EmbeddingDimensionError(
                    f"An embedding has length {len(vector)} but the model's "
                    f"actual dimension is {self._actual_dimension}."
                )
        return result
