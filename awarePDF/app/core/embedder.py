"""Local BGE embeddings (normalized, batched, GPU when available).

Embeddings are computed here rather than by ChromaDB so that queries get the
BGE retrieval instruction prefix, which noticeably improves search quality.
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from app.utils.device import get_best_device
from app.utils.logger import get_logger
import config.settings as settings

logger = get_logger(__name__)

_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_embedding_model: Optional[SentenceTransformer] = None


def _get_model() -> SentenceTransformer:
    """Return singleton embedding model instance."""
    global _embedding_model
    if _embedding_model is None:
        device = get_best_device()
        logger.info("Loading embedding model %s on %s", settings.EMBEDDING_MODEL, device)
        _embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL, device=device)
    return _embedding_model


def embed_documents(
    texts: list[str],
    batch_size: int = 64,
    progress_callback: Callable[[float], None] | None = None,
) -> np.ndarray:
    """Embed passages in batches. Reports progress as a 0-1 fraction."""
    model = _get_model()
    parts: list[np.ndarray] = []
    done = 0
    step = batch_size * 8
    for start in range(0, len(texts), step):
        batch = texts[start:start + step]
        parts.append(model.encode(
            batch,
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ))
        done += len(batch)
        if progress_callback:
            progress_callback(done / len(texts))
    return np.concatenate(parts).astype(np.float32)


def embed_query(query: str) -> np.ndarray:
    """Embed a search query (with the BGE instruction prefix for BGE models)."""
    if "bge" in settings.EMBEDDING_MODEL.lower():
        query = _BGE_QUERY_PREFIX + query
    return _get_model().encode(query, normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)
