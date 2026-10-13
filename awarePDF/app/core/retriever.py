"""Retrieval for Q&A plus whole-document views for summaries and outlines.

Q&A pipeline:
1. Dense search (BGE embeddings)  ┐
2. Keyword search (BM25)          ┴→ Reciprocal Rank Fusion → top candidates
3. Cross-encoder reranking → top-k

Whole-book features (summary, topics) can't rely on similarity search: a
handful of generic queries only reaches a small slice of a 700-page book.
They use the heading outline and an even sample across all pages instead.
"""

import re

from app.core import hybrid_search, reranker, vector_store
from app.utils.logger import get_logger
from config.settings import RETRIEVAL_K, CANDIDATES_K, USE_RERANKER

logger = get_logger(__name__)


def _require_collection(pdf_hash: str):
    collection = vector_store.get_collection(pdf_hash)
    if collection is None:
        raise ValueError("This PDF has not been indexed yet.")
    return collection


def retrieve(pdf_hash: str, query: str, k: int | None = None) -> list[dict]:
    """Return the k most relevant chunks for a query."""
    k = k or RETRIEVAL_K
    collection = _require_collection(pdf_hash)

    dense = vector_store.similarity_search(collection, query, k=CANDIDATES_K)
    sparse = hybrid_search.bm25_search(collection, query, k=CANDIDATES_K)
    candidates = hybrid_search.reciprocal_rank_fusion([dense, sparse], k=CANDIDATES_K)

    if USE_RERANKER and len(candidates) > k:
        results = reranker.rerank(query, candidates, top_k=k)
    else:
        results = candidates[:k]

    logger.info("Retrieval: %s dense + %s keyword → %s fused → %s final",
                len(dense), len(sparse), len(candidates), len(results))
    return results


def get_outline(pdf_hash: str) -> list[dict]:
    """All headings in reading order."""
    collection = _require_collection(pdf_hash)
    return vector_store.get_chunks(collection, where={"content_type": "heading"})


_SUBSECTION_RE = re.compile(r"^\d+(\.\d+)+\s")


def outline_text(pdf_hash: str, max_chars: int = 2500) -> str:
    """
    Compact heading outline with page numbers, for structure questions.
    Drops numbered subsections (1.2, 3.4.1 ...) first if the outline is too long.
    """
    lines: list[str] = []
    for heading in get_outline(pdf_hash):
        text = heading["text"].strip()
        line = f"- {text} (Page {heading['metadata'].get('page_number', '?')})"
        if not lines or not lines[-1].startswith(f"- {text} ("):
            lines.append(line)
    if sum(len(line) + 1 for line in lines) > max_chars:
        lines = [line for line in lines if not _SUBSECTION_RE.match(line[2:])]
    total = sum(len(line) + 1 for line in lines)
    if total > max_chars:
        keep = max(1, int(len(lines) * max_chars / total))
        lines = [lines[int(i * len(lines) / keep)] for i in range(keep)]
    return "\n".join(lines)


_NUMBER_RE = re.compile(r"^(?:chapter|unit|module|part)?\s*(\d+(?:\.\d+)*)\.?(?:\s|$)", re.IGNORECASE)


def _section_number(text: str) -> str | None:
    """"3.4 Stop wait" -> "3.4", "Chapter 2. Intro" -> "2", "ERROR CONTROL" -> None."""
    match = _NUMBER_RE.match(text)
    return match.group(1) if match else None


def _inside(number: str, prefix: str) -> bool:
    return number == prefix or number.startswith(prefix + ".")


def _section_pages(pdf_hash: str, focus: str) -> tuple[int, int] | None:
    """
    Page range of the heading that best matches `focus`. None if no heading matches.

    Numbered books end the range where numbering leaves the section ("3" covers
    3.1-3.9 and stops at 4.1); unnumbered books stop at the next heading of the
    same or higher level.
    """
    headings = [(h["text"].strip(), h["metadata"].get("page_number", 0)) for h in get_outline(pdf_hash)]
    counts: dict[str, int] = {}
    for text, _ in headings:
        counts[text.lower()] = counts.get(text.lower(), 0) + 1
    # Text repeated on many pages is a running header, not a section
    headings = [(t, p) for t, p in headings if counts[t.lower()] < 3]

    words = re.findall(r"\w+", focus.lower())
    matches = [
        (len((_section_number(t) or "").split(".")) if _section_number(t) else 0, i)
        for i, (t, _) in enumerate(headings)
        if words and all(w in t.lower() for w in words)
    ]
    if not matches:
        return None
    _, index = min(matches)  # prefer chapter titles over numbered subsections
    title, start = headings[index]

    number = _section_number(title)
    if number is None:
        # Chapter banners are unnumbered: take the number of their first subsection
        for text, page in headings[max(0, index - 5):index + 6]:
            sub = _section_number(text)
            if sub and start <= page <= start + 1:
                number = sub.split(".")[0]
                break

    if number is not None:
        for text, page in headings[index + 1:]:
            other = _section_number(text)
            if other and page > start and not _inside(other, number):
                # Chapters start on a fresh page; subsections share the boundary page
                return start, page if "." in number else page - 1
        return start, 10**9

    for text, page in headings[index + 1:]:
        if page > start and _section_number(text) is None:
            return start, page - 1
    return start, 10**9


def _even_sample(chunks: list[dict], max_chars: int) -> list[dict]:
    if not chunks:
        return []
    avg_len = sum(len(c["text"]) for c in chunks) / len(chunks) + 60  # + citation header
    n = max(1, min(len(chunks), int(max_chars // avg_len)))
    step = len(chunks) / n
    return [chunks[int(i * step)] for i in range(n)]


def chunks_for_topic(pdf_hash: str, topic: str, max_chars: int, k: int = 15) -> list[dict]:
    """
    Content for a focused summary/key points: the whole matching chapter or
    section when `topic` names a heading, otherwise the best search results.
    """
    pages = _section_pages(pdf_hash, topic)
    if pages:
        start, end = pages
        chunks = [
            c for c in vector_store.get_chunks(_require_collection(pdf_hash), where=vector_store.SEARCHABLE)
            if start <= c["metadata"].get("page_number", 0) <= end
        ]
        if chunks:
            logger.info("Topic '%s' → pages %s-%s (%s chunks)", topic, start, end, len(chunks))
            return _even_sample(chunks, max_chars)
    return retrieve(pdf_hash, topic, k=k)


def sample_across_document(pdf_hash: str, max_chars: int) -> list[dict]:
    """
    Evenly spaced chunks from the first page to the last, fitting max_chars.
    Gives summaries and key points coverage of the entire book.
    """
    chunks = vector_store.get_chunks(_require_collection(pdf_hash), where=vector_store.SEARCHABLE)
    return _even_sample(chunks, max_chars)

