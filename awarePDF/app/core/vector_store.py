"""ChromaDB storage: one persistent collection per PDF (keyed by file hash).

- Embeddings come from app.core.embedder (BGE, cosine similarity)
- Chunks are embedded with their section title prepended for context,
  while the stored document stays the original text shown to users
- A collection is only "indexed" once all batches were written, so an
  interrupted upload is re-indexed instead of silently serving partial data
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import chromadb
from chromadb.api import ClientAPI

from app.core import embedder
from app.utils.logger import get_logger
import config.settings as settings

if TYPE_CHECKING:
    from chromadb.api.models.Collection import Collection

logger = get_logger(__name__)

# Bump together with pdf_processor.CACHE_VERSION when the chunk format changes
_COLLECTION_PREFIX = "pdf_v3_"
_ADD_BATCH_SIZE = 1000

# Headings are stored for the outline but excluded from search
SEARCHABLE = {"content_type": {"$ne": "heading"}}

_client: ClientAPI | None = None


def _get_client() -> ClientAPI:
    """Return a singleton ChromaDB persistent client."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(settings.CHROMA_PERSIST_DIR))
        logger.info("Initialized ChromaDB client at %s", settings.CHROMA_PERSIST_DIR)
    return _client


def _collection_name(pdf_hash: str) -> str:
    """ChromaDB names must be 3-63 chars and start with a letter."""
    cleaned = pdf_hash.strip()
    if not cleaned:
        raise ValueError("pdf_hash must be a non-empty string")
    return f"{_COLLECTION_PREFIX}{cleaned[:63 - len(_COLLECTION_PREFIX)]}"


def get_collection(pdf_hash: str) -> Collection | None:
    """Return the collection for a PDF, or None if it does not exist."""
    name = _collection_name(pdf_hash)
    if name not in {c.name for c in _get_client().list_collections()}:
        return None
    return _get_client().get_collection(name=name, embedding_function=None)


def is_indexed(pdf_hash: str) -> bool:
    """True when the PDF has a fully written collection."""
    collection = get_collection(pdf_hash)
    return bool(collection and (collection.metadata or {}).get("complete"))


def get_chunk_count(pdf_hash: str) -> int:
    collection = get_collection(pdf_hash)
    return collection.count() if collection else 0


def delete_collection(pdf_hash: str) -> None:
    if get_collection(pdf_hash) is not None:
        _get_client().delete_collection(name=_collection_name(pdf_hash))
        logger.info("Deleted collection for %s", pdf_hash[:12])


def _metadata(chunk: dict) -> dict:
    metadata = {
        "page_number": int(chunk.get("page_number") or 0),
        "page_end": int(chunk.get("page_end") or chunk.get("page_number") or 0),
        "chunk_index": int(chunk.get("chunk_index", 0)),
        "content_type": chunk.get("content_type", "text"),
        "section": chunk.get("section", ""),
    }
    if chunk.get("image_path"):
        metadata["image_path"] = chunk["image_path"]
    return metadata


def _chunk_id(chunk: dict) -> str:
    return chunk.get("id") or str(chunk["chunk_index"])


def _embedding_text(chunk: dict) -> str:
    """Prepend section context so short chunks embed with their topic."""
    text = chunk["text"]
    if chunk.get("content_type") == "image_description":
        text = f"Diagram/figure on page {chunk.get('page_number')}: {text}"
    section = chunk.get("section", "")
    if section and chunk.get("content_type") != "heading":
        return f"{section}\n\n{text}"
    return text


def index_chunks(
    pdf_hash: str,
    chunks: list[dict],
    progress_callback: Callable[[float, str], None] | None = None,
) -> Collection:
    """Embed and store all chunks of a PDF, replacing any partial collection."""
    chunks = [c for c in chunks if c.get("text", "").strip()]
    if not chunks:
        raise ValueError("No chunks to index")

    delete_collection(pdf_hash)
    collection = _get_client().create_collection(
        name=_collection_name(pdf_hash),
        configuration={"hnsw": {"space": "cosine"}},
        metadata={"complete": False},
        embedding_function=None,
    )

    def report(fraction: float) -> None:
        if progress_callback:
            progress_callback(fraction, f"Embedding chunks ({int(fraction * len(chunks))}/{len(chunks)})")

    embeddings = embedder.embed_documents([_embedding_text(c) for c in chunks], progress_callback=report)

    for start in range(0, len(chunks), _ADD_BATCH_SIZE):
        batch = chunks[start:start + _ADD_BATCH_SIZE]
        collection.add(
            ids=[_chunk_id(c) for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[_metadata(c) for c in batch],
            embeddings=embeddings[start:start + _ADD_BATCH_SIZE],
        )

    collection.modify(metadata={"complete": True, "pdf_hash": pdf_hash})
    logger.info("Indexed %s chunks for %s", len(chunks), pdf_hash[:12])
    return collection


def add_image_chunks(pdf_hash: str, chunks: list[dict]) -> None:
    """
    Add (or re-add) diagram descriptions to an indexed PDF.

    Each image takes the section and reading position of the text on its page,
    so it appears in the right place in outlines and whole-book samples.
    Safe to call repeatedly with the same chunks (upsert by id).
    """
    collection = get_collection(pdf_hash)
    if collection is None or not chunks:
        return

    by_page: dict[int, dict] = {}
    text_metadatas = collection.get(where={"content_type": "text"}, include=["metadatas"])["metadatas"] or []
    for meta in text_metadatas:
        page = meta.get("page_number")
        if isinstance(page, int):
            by_page.setdefault(page, dict(meta))
    pages = sorted(by_page)

    for chunk in chunks:
        earlier = [p for p in pages if p <= chunk["page_number"]]
        anchor = by_page[earlier[-1]] if earlier else {}
        chunk["section"] = anchor.get("section", "")
        chunk["chunk_index"] = anchor.get("chunk_index", 0)

    collection.upsert(
        ids=[_chunk_id(c) for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[_metadata(c) for c in chunks],
        embeddings=embedder.embed_documents([_embedding_text(c) for c in chunks]),
    )
    logger.info("Added %s diagram descriptions for %s", len(chunks), pdf_hash[:12])


def images_pending(pdf_hash: str) -> bool:
    """True when an indexed PDF still has diagrams waiting to be described."""
    collection = get_collection(pdf_hash)
    metadata = (collection.metadata or {}) if collection else {}
    return bool(metadata.get("complete")) and not metadata.get("images_done")


def mark_images_done(pdf_hash: str) -> None:
    collection = get_collection(pdf_hash)
    if collection is not None:
        collection.modify(metadata={**(collection.metadata or {}), "images_done": True})


def _rows(ids: list, documents: list, metadatas: list, distances: list | None = None) -> list[dict]:
    rows = []
    for i, chunk_id in enumerate(ids):
        row = {"id": chunk_id, "text": documents[i], "metadata": metadatas[i] or {}}
        if distances is not None:
            row["distance"] = distances[i]
        rows.append(row)
    return rows


def similarity_search(collection: Collection, query: str, k: int = 5, where: dict | None = SEARCHABLE) -> list[dict]:
    """Dense vector search. Returns dicts with id, text, metadata, distance."""
    if not query.strip():
        return []
    k = min(max(1, k), collection.count())
    if k == 0:
        return []
    results = collection.query(
        query_embeddings=[embedder.embed_query(query)],
        n_results=k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    return _rows(
        results["ids"][0],
        (results["documents"] or [[]])[0],
        (results["metadatas"] or [[]])[0],
        (results["distances"] or [[]])[0],
    )


def get_chunks(collection: Collection, where: dict | None = None) -> list[dict]:
    """Fetch all chunks (optionally filtered), in document order."""
    results = collection.get(where=where, include=["documents", "metadatas"])
    rows = _rows(results["ids"], results["documents"] or [], results["metadatas"] or [])
    rows.sort(key=lambda r: r["metadata"].get("chunk_index", 0))
    return rows


def reset_runtime_state() -> None:
    """Reset cached singleton resources (useful for tests)."""
    global _client
    _client = None
