# ============================================================
# app/features/topic_extractor.py
# Generates a structured topic list from the PDF
# ============================================================

from app.core.vector_store import create_or_get_collection, similarity_search
from app.core.llm import call_groq, format_context, TOPICS_SYSTEM_PROMPT, TOPICS_USER_TEMPLATE
from app.utils.logger import get_logger

logger = get_logger(__name__)


def extract_topics(pdf_hash: str) -> str:
    """
    Generates a structured list of topics and subtopics.

    Strategy: Focus on headings and section titles specifically,
    since they directly represent the document's topic structure.
    """
    collection = create_or_get_collection(pdf_hash)

    # Get heading-type chunks first
    heading_chunks = similarity_search(
        collection,
        query="chapter section topic introduction overview",
        k=20,
        filter_type="heading",
    )

    # Also get some general content for context
    general_chunks = similarity_search(
        collection,
        query="main topics covered in this document",
        k=10,
    )

    # Combine, deduplicate
    all_chunks = heading_chunks + general_chunks
    seen_texts = set()
    unique_chunks = []
    for chunk in all_chunks:
        if chunk["text"] not in seen_texts:
            unique_chunks.append(chunk)
            seen_texts.add(chunk["text"])

    if not unique_chunks:
        return "Could not extract topics from the document."

    context = format_context(unique_chunks[:25])
    user_prompt = TOPICS_USER_TEMPLATE.format(context=context)

    return call_groq(
        system_prompt=TOPICS_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.3,
    )
