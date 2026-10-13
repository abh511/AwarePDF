# ============================================================
# app/features/summarizer.py
# Summarization
# - Whole book: evenly spaced sample across all pages, so the
#   summary covers every chapter instead of the first few
# - Focused: retrieval on a chapter/topic for a detailed summary
# ============================================================

from app.core.retriever import chunks_for_topic, sample_across_document
from app.core.llm import call_llm, format_context, SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_TEMPLATE
from app.utils.logger import get_logger
from config.settings import LLM_MAX_PROMPT_CHARS

logger = get_logger(__name__)


def summarize_pdf(pdf_hash: str, focus: str | None = None) -> str:
    """Summarize the whole document, or only the part about `focus`."""
    budget = LLM_MAX_PROMPT_CHARS - 1500
    if focus:
        chunks = chunks_for_topic(pdf_hash, focus, max_chars=budget)
        scope = f"Focus only on: {focus}\n"
    else:
        chunks = sample_across_document(pdf_hash, max_chars=budget)
        scope = "The content is a sample spread evenly across the whole book; cover every major part.\n"

    if not chunks:
        return "Could not retrieve content for summarization."

    return call_llm(
        system_prompt=SUMMARY_SYSTEM_PROMPT,
        user_prompt=SUMMARY_USER_TEMPLATE.format(scope=scope, context=format_context(chunks, max_chars=budget)),
        temperature=0.4,
        max_tokens=2500,
    )
