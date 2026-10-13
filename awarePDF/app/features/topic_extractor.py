# ============================================================
# app/features/topic_extractor.py
# Generates a structured topic list from the PDF
#
# Uses the book's real heading outline (in page order) rather
# than similarity search, so all chapters of a long book appear.
# ============================================================

from app.core.retriever import get_outline, sample_across_document
from app.core.llm import call_llm, format_context, TOPICS_SYSTEM_PROMPT, TOPICS_USER_TEMPLATE
from app.utils.logger import get_logger
from config.settings import LLM_MAX_PROMPT_CHARS

logger = get_logger(__name__)


def extract_topics(pdf_hash: str) -> str:
    """Generates a structured list of topics and subtopics."""
    budget = LLM_MAX_PROMPT_CHARS - 1500

    lines: list[str] = []
    previous = ""
    for heading in get_outline(pdf_hash):
        text = heading["text"].strip()
        if text.lower() != previous.lower():
            lines.append(f"- {text} (Page {heading['metadata'].get('page_number', '?')})")
            previous = text

    if lines:
        # Evenly thin out very long outlines so the whole book still fits
        total = sum(len(line) + 1 for line in lines)
        if total > budget:
            keep = int(len(lines) * budget / total)
            step = len(lines) / keep
            lines = [lines[int(i * step)] for i in range(keep)]
        context = "\n".join(lines)
    else:
        # No headings detected: fall back to sampled content
        context = format_context(sample_across_document(pdf_hash, max_chars=budget), max_chars=budget)

    if not context:
        return "Could not extract topics from the document."

    return call_llm(
        system_prompt=TOPICS_SYSTEM_PROMPT,
        user_prompt=TOPICS_USER_TEMPLATE.format(context=context),
        temperature=0.2,
        max_tokens=2500,
    )
