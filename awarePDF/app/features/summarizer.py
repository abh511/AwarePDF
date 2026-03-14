# ============================================================
# app/features/summarizer.py
# Summarization - uses Gemini for large context
# ============================================================

from app.core.retriever import retrieve_for_summary
from app.core.llm import call_gemini, call_groq, format_context, SUMMARY_PROMPT_TEMPLATE
from app.utils.logger import get_logger
from config.settings import GOOGLE_API_KEY

logger = get_logger(__name__)


def summarize_pdf(pdf_hash: str) -> str:
    """
    Generates a comprehensive summary of the entire PDF.

    Strategy:
    - Collect a broad spread of chunks (headings + key content)
    - Send ALL of them to Gemini (large context window)
    - Gemini synthesizes a proper summary

    Falls back to Groq if Gemini key not set.
    """
    chunks = retrieve_for_summary(pdf_hash, max_chunks=40)

    if not chunks:
        return "Could not retrieve content for summarization."

    context = format_context(chunks)
    prompt = SUMMARY_PROMPT_TEMPLATE.format(context=context)

    # Use Gemini if available (better for large context)
    if GOOGLE_API_KEY:
        logger.info("Using Gemini for summarization")
        return call_gemini(prompt, temperature=0.4, max_tokens=2000)
    else:
        logger.info("Gemini key not set, using Groq for summarization")
        return call_groq(
            system_prompt="You are an expert academic summarizer.",
            user_prompt=prompt,
            temperature=0.4,
            max_tokens=1500,
        )
