# ============================================================
# app/features/key_points.py
# Extracts key learning points from the PDF
# ============================================================

from app.core.retriever import chunks_for_topic, sample_across_document
from app.core.llm import call_llm, format_context, KEY_POINTS_SYSTEM_PROMPT, KEY_POINTS_USER_TEMPLATE
from app.utils.logger import get_logger
from config.settings import LLM_MAX_PROMPT_CHARS

logger = get_logger(__name__)


def extract_key_points(pdf_hash: str, topic: str | None = None) -> str:
    """
    Extracts key points about `topic`, or across the whole document if None.
    """
    budget = LLM_MAX_PROMPT_CHARS - 1500
    if topic:
        chunks = chunks_for_topic(pdf_hash, topic, max_chars=budget, k=12)
    else:
        chunks = sample_across_document(pdf_hash, max_chars=budget)

    if not chunks:
        return "No key points found."

    return call_llm(
        system_prompt=KEY_POINTS_SYSTEM_PROMPT,
        user_prompt=KEY_POINTS_USER_TEMPLATE.format(context=format_context(chunks, max_chars=budget)),
        temperature=0.3,
    )
