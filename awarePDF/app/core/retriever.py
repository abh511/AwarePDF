# ============================================================
# app/core/retriever.py
# Retrieval logic - given a query, finds the best chunks
#
# TWO STAGE RETRIEVAL:
# Stage 1 - Vector search: Fast, finds semantically similar chunks
# Stage 2 - Reranking: Slower but more precise, reorders by relevance
#
# WHY RERANK?
# Vector search finds "nearby" vectors but doesn't deeply compare
# query vs chunk. A cross-encoder reranker reads both together
# and gives a much better relevance score. Think of it as:
# - Vector search = shortlist 10 candidates quickly
# - Reranker = carefully interview those 10, pick top 3
# ============================================================

from app.core.vector_store import similarity_search, create_or_get_collection
from app.utils.logger import get_logger
from config.settings import RETRIEVAL_K

logger = get_logger(__name__)

_cross_encoder = None


def _get_cross_encoder():
    """Return cached CrossEncoder model (singleton)."""
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder
        logger.info("Loading CrossEncoder model (one-time)...")
        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _cross_encoder


def _rerank(query: str, candidates: list[dict]) -> list[dict]:
    """
    Uses a cross-encoder to rerank candidates by true relevance.
    Cross-encoder reads query+chunk together for much better scoring
    than cosine similarity alone.
    """
    model = _get_cross_encoder()
    pairs = [[query, chunk["text"]] for chunk in candidates]
    scores = model.predict(pairs)
    for chunk, score in zip(candidates, scores):
        chunk["rerank_score"] = float(score)
    return sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)


def retrieve(
    pdf_hash: str,
    query: str,
    k: int = None,
    use_reranker: bool = True,
) -> list[dict]:
    """
    Main retrieval function. Returns top-k most relevant chunks.

    Args:
        pdf_hash: The PDF's SHA-256 hash (ChromaDB collection ID)
        query: User's question
        k: Number of final chunks to return
        use_reranker: Whether to apply cross-encoder reranking
    """
    k = k or RETRIEVAL_K
    collection = create_or_get_collection(pdf_hash)

    # Fetch more candidates than needed so reranker has room to work
    candidates_k = k * 3 if use_reranker else k
    candidates = similarity_search(collection, query, k=candidates_k)

    if not candidates:
        logger.warning("No results found for query: %s", query)
        return []

    if not use_reranker:
        return candidates[:k]

    try:
        reranked = _rerank(query, candidates)
        logger.info("Reranked %s candidates → returning top %s", len(candidates), k)
        return reranked[:k]
    except Exception as exc:
        logger.warning("Reranking failed (%s), falling back to vector results", exc)
        return candidates[:k]


def retrieve_for_summary(pdf_hash: str, max_chunks: int = 40) -> list[dict]:
    """
    Special retrieval for summarization - gets a broad spread of chunks
    from across the document rather than focusing on one query.

    Deduplicates by section to ensure coverage across the whole document.
    """
    collection = create_or_get_collection(pdf_hash)

    important = similarity_search(
        collection,
        query="main topics key concepts summary overview introduction",
        k=max_chunks,
    )

    # Deduplicate by section to get broad coverage
    seen_sections: set[str] = set()
    diverse_chunks: list[dict] = []
    for chunk in important:
        # metadata is nested under "metadata" key in similarity_search results
        meta = chunk.get("metadata", {})
        section = meta.get("section", chunk.get("section", ""))
        if section not in seen_sections or not section:
            diverse_chunks.append(chunk)
            seen_sections.add(section)

    return diverse_chunks[:max_chunks]
