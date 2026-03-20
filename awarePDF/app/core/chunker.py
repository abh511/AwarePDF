# ============================================================
# app/core/chunker.py
# Splits extracted text into chunks for embedding
#
# WHY CHUNKING MATTERS:
# - Too small (< 100 chars): loses context, retrieval gets fragments
# - Too large (> 1000 chars): dilutes the relevant part, wastes tokens
# - 1000 chars with 200 overlap is the sweet spot for textbooks
#
# We use RecursiveCharacterTextSplitter because it tries to split
# on paragraphs first, then sentences, then words - preserving meaning.
# ============================================================

from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.utils.logger import get_logger
from config.settings import CHUNK_SIZE, CHUNK_OVERLAP

logger = get_logger(__name__)


def chunk_with_metadata(raw_chunks: list[dict]) -> list[dict]:
    """
    Takes raw chunks from pdf_processor and splits long ones further.
    Tables, headings, and figure captions are NOT split - kept whole.

    Returns list of final chunks ready for embedding.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )

    final_chunks = []
    sub_chunk_counter = 0  # global counter to ensure unique integer chunk_index

    for raw_chunk in raw_chunks:
        content_type = raw_chunk.get("content_type", "text")

        # Tables, headings, captions and image descriptions stay whole
        if content_type in ("table", "heading", "figure_caption", "image_description"):
            new_chunk = raw_chunk.copy()
            new_chunk["chunk_index"] = sub_chunk_counter
            sub_chunk_counter += 1
            final_chunks.append(new_chunk)
            continue

        text = raw_chunk.get("text", "")
        if not text.strip():
            continue

        # Short enough - no split needed
        if len(text) <= CHUNK_SIZE:
            new_chunk = raw_chunk.copy()
            new_chunk["chunk_index"] = sub_chunk_counter
            sub_chunk_counter += 1
            final_chunks.append(new_chunk)
            continue

        # Split long text chunks - chunk_index stays int (required by ChromaDB)
        sub_texts = splitter.split_text(text)
        for sub_text in sub_texts:
            if not sub_text.strip():
                continue
            new_chunk = raw_chunk.copy()
            new_chunk["text"] = sub_text
            new_chunk["chunk_index"] = sub_chunk_counter
            sub_chunk_counter += 1
            final_chunks.append(new_chunk)

    logger.info("Chunking: %s raw → %s final chunks", len(raw_chunks), len(final_chunks))
    return final_chunks
