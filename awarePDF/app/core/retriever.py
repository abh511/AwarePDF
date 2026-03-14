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


def retrieve(
    pdf_hash: str,
    query: str,
    k: int = None,
    use_reranker: bool = True,
) -> list[dict]:
    """
    Main retrieval function. Returns top-k most relevant chunks.

    Args:
        pdf_hash: The PDF's MD5 hash (used to find correct collection)
        query: User's question
        k: Number of final chunks to return
        use_reranker: Whether to apply reranking (slower but better)

    Returns:
        List of chunk dicts ordered by relevance
    """
    k = k or RETRIEVAL_K

    collection = create_or_get_collection(pdf_hash)

    # Stage 1: Get more candidates than needed (we'll rerank and cut down)
    candidates_k = k * 3 if use_reranker else k
    candidates = similarity_search(collection, query, k=candidates_k)

    if not candidates:
        logger.warning(f"No results found for query: {query}")
        return []

    if not use_reranker:
        return candidates[:k]

    # Stage 2: Rerank
    try:
        reranked = _rerank(query, candidates)
        return reranked[:k]
    except Exception as e:
        logger.warning(f"Reranking failed ({e}), falling back to vector results")
        return candidates[:k]


def _rerank(query: str, candidates: list[dict]) -> list[dict]:
    """
    Uses a cross-encoder to rerank candidates by true relevance.

    Cross-encoder model: 'cross-encoder/ms-marco-MiniLM-L-6-v2'
    - Small (~80MB), fast on CPU
    - Much more accurate than cosine similarity for final ranking
    """
    from sentence_transformers import CrossEncoder

    model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

    # Build pairs of [query, chunk_text] for the cross-encoder
    pairs = [[query, chunk["text"]] for chunk in candidates]
    scores = model.predict(pairs)

    # Attach scores and sort descending (higher = more relevant)
    for chunk, score in zip(candidates, scores):
        chunk["rerank_score"] = float(score)

    reranked = sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)
    logger.info(f"Reranked {len(candidates)} candidates")
    return reranked


def retrieve_for_summary(pdf_hash: str, max_chunks: int = 30) -> list[dict]:
    """
    Special retrieval for summarization - gets a broad spread of chunks
    from across the document rather than focusing on one query.
    Used by the summarizer feature.
    """
    collection = create_or_get_collection(pdf_hash)

    # Get headings and important chunks first (they represent key ideas)
    important = similarity_search(
        collection,
        query="main topics key concepts summary overview",
        k=max_chunks,
    )

    # Deduplicate by section
    seen_sections = set()
    diverse_chunks = []
    for chunk in important:
        section = chunk["metadata"].get("section", "")
        if section not in seen_sections or not section:
            diverse_chunks.append(chunk)
            seen_sections.add(section)

    return diverse_chunks[:max_chunks]
