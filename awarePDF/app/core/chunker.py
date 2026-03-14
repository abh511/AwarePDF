# ============================================================
# app/core/chunker.py
# Splits extracted text into chunks for embedding
#
# WHY CHUNKING MATTERS:
# - Too small (< 100 chars): loses context, retrieval gets fragments
# - Too large (> 1000 chars): dilutes the relevant part, wastes tokens
# - 512 chars with 50 overlap is the sweet spot for textbooks
#
# We use RecursiveCharacterTextSplitter because it tries to split
# on paragraphs first, then sentences, then words - preserving meaning.
# ============================================================

from langchain.text_splitter import RecursiveCharacterTextSplitter
from app.utils.logger import get_logger
from config.settings import CHUNK_SIZE, CHUNK_OVERLAP

logger = get_logger(__name__)


def chunk_with_metadata(raw_chunks: list[dict]) -> list[dict]:
    """
    Takes raw chunks from pdf_processor and splits long ones further.
    Tables, headings, and figure captions are NOT split - they're kept whole.

    Returns list of final chunks ready for embedding.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        # Split order: paragraph > sentence > word > character
        # This preserves meaning better than hard cuts
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )

    final_chunks = []

    for raw_chunk in raw_chunks:
        content_type = raw_chunk.get("content_type", "text")

        # --- DON'T SPLIT TABLES, HEADINGS, CAPTIONS ---
        # These need to stay whole to be useful
        if content_type in ("table", "heading", "figure_caption"):
            final_chunks.append(raw_chunk)
            continue

        text = raw_chunk.get("text", "")

        # --- SHORT ENOUGH - NO SPLIT NEEDED ---
        if len(text) <= CHUNK_SIZE:
            final_chunks.append(raw_chunk)
            continue

        # --- SPLIT LONG TEXT CHUNKS ---
        sub_texts = splitter.split_text(text)
        for i, sub_text in enumerate(sub_texts):
            new_chunk = raw_chunk.copy()
            new_chunk["text"] = sub_text
            # Add sub-index so we can trace back to original
            new_chunk["chunk_index"] = float(f"{raw_chunk['chunk_index']}.{i}")
            final_chunks.append(new_chunk)

    logger.info(f"Chunking: {len(raw_chunks)} raw → {len(final_chunks)} final chunks")
    return final_chunks
