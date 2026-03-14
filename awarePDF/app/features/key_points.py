# ============================================================
# app/features/key_points.py
# Extracts key learning points from the PDF
# ============================================================

from app.core.retriever import retrieve
from app.core.llm import call_groq, format_context, KEY_POINTS_SYSTEM_PROMPT, KEY_POINTS_USER_TEMPLATE
from app.utils.logger import get_logger

logger = get_logger(__name__)


def extract_key_points(pdf_hash: str, topic: str = None) -> str:
    """
    Extracts key points from the PDF.

    Args:
        pdf_hash: PDF identifier
        topic: Optional - extract key points about a specific topic.
               If None, gets general key points from important chunks.
    """
    query = topic if topic else "key concepts definitions important points formulas rules"
    chunks = retrieve(pdf_hash, query, k=8, use_reranker=True)

    if not chunks:
        return "No key points found."

    context = format_context(chunks)
    user_prompt = KEY_POINTS_USER_TEMPLATE.format(context=context)

    return call_groq(
        system_prompt=KEY_POINTS_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.3,
    )
