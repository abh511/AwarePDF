"""Sentence-transformer embedding generation for document chunks.

Note: ChromaDB manages its own embeddings via SentenceTransformerEmbeddingFunction
in vector_store.py. This module is available for standalone embedding needs
(e.g. custom similarity scoring, reranking helpers, or future extensions).
"""

from __future__ import annotations

import logging
from sentence_transformers import SentenceTransformer
import config.settings as settings

logger = logging.getLogger(__name__)

_embedding_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Return singleton embedding model instance."""
    global _embedding_model
    if _embedding_model is None:
        # Strip "sentence-transformers/" prefix if present - SentenceTransformer
        # accepts short names like "all-MiniLM-L6-v2" directly.
        model_name = settings.EMBEDDING_MODEL.replace("sentence-transformers/", "")
        logger.info("Loading embedding model: %s", model_name)
        _embedding_model = SentenceTransformer(model_name)
        logger.info("Embedding model loaded successfully")
    return _embedding_model


def embed_text(text: str) -> list[float]:
    """Generate embedding vector for a single text string."""
    model = _get_model()
    return model.encode(text, convert_to_numpy=True).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts efficiently."""
    if not texts:
        return []
    model = _get_model()
    return model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=len(texts) > 10,
        batch_size=32,
    ).tolist()


def get_embedding_dimension() -> int:
    """Return the dimension of the embedding vectors."""
    return _get_model().get_sentence_embedding_dimension()
