"""Cross-encoder reranking: scores each (query, chunk) pair jointly.

Much more precise than vector similarity, but too slow to run on a whole
book, so it only reorders the ~30-60 fused candidates.
"""

from typing import Optional

from sentence_transformers import CrossEncoder

from app.utils.device import get_best_device
from app.utils.logger import get_logger
from config.settings import RERANKER_MODEL

logger = get_logger(__name__)

_reranker: Optional[CrossEncoder] = None


def _get_reranker() -> CrossEncoder:
    """Return singleton reranker model (local, ~80MB)."""
    global _reranker
    if _reranker is None:
        device = get_best_device()
        logger.info("Loading reranker %s on %s", RERANKER_MODEL, device)
        _reranker = CrossEncoder(RERANKER_MODEL, max_length=512, device=device)
    return _reranker


def rerank(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    """Return the top_k candidates by cross-encoder score."""
    if not candidates:
        return []
    scores = _get_reranker().predict(
        [(query, c["text"]) for c in candidates],
        batch_size=32,
        show_progress_bar=False,
    )
    ranked = sorted(
        ({**c, "rerank_score": float(s)} for c, s in zip(candidates, scores)),
        key=lambda c: c["rerank_score"],
        reverse=True,
    )
    return ranked[:top_k]
