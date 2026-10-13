"""Keyword (BM25) search and rank fusion with dense results.

- BM25 indices are built lazily from the ChromaDB collection and kept in
  memory, so they survive app restarts (rebuilt on first query, ~1s for a
  700-page book)
- Dense and BM25 lists are merged with Reciprocal Rank Fusion (RRF), which
  needs no score normalization and is robust to their different scales
"""

import re
import threading

import numpy as np
from rank_bm25 import BM25Okapi

from app.core import vector_store
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_RRF_K = 60

# collection name -> (chunk count when built, index, chunks)
_bm25_indices: dict[str, tuple[int, BM25Okapi, list[dict]]] = {}
_lock = threading.Lock()


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _get_index(collection) -> tuple[BM25Okapi, list[dict]] | None:
    count = collection.count()
    with _lock:
        cached = _bm25_indices.get(collection.name)
        if cached and cached[0] == count:
            return cached[1], cached[2]
        chunks = vector_store.get_chunks(collection, where=vector_store.SEARCHABLE)
        if not chunks:
            return None
        index = BM25Okapi([_tokenize(c["text"] + " " + c["metadata"].get("section", "")) for c in chunks])
        _bm25_indices[collection.name] = (count, index, chunks)
        logger.info("Built BM25 index for '%s' with %s chunks", collection.name, len(chunks))
        return index, chunks


def bm25_search(collection, query: str, k: int = 20) -> list[dict]:
    """Keyword search. Returns chunks with a bm25_score, best first."""
    tokens = _tokenize(query)
    loaded = _get_index(collection) if tokens else None
    if loaded is None:
        return []
    index, chunks = loaded
    scores = index.get_scores(tokens)
    top = np.argsort(scores)[::-1][:k]
    return [{**chunks[i], "bm25_score": float(scores[i])} for i in top if scores[i] > 0]


def reciprocal_rank_fusion(result_lists: list[list[dict]], k: int) -> list[dict]:
    """Merge ranked lists by id: score = sum(1 / (60 + rank))."""
    scores: dict[str, float] = {}
    chunks: dict[str, dict] = {}
    for results in result_lists:
        for rank, chunk in enumerate(results):
            scores[chunk["id"]] = scores.get(chunk["id"], 0.0) + 1.0 / (_RRF_K + rank + 1)
            chunks.setdefault(chunk["id"], chunk)
    ranked = sorted(scores, key=scores.get, reverse=True)[:k]
    return [{**chunks[i], "fusion_score": scores[i]} for i in ranked]


def clear_bm25_indices() -> None:
    """Clear all BM25 indices from memory."""
    with _lock:
        _bm25_indices.clear()
