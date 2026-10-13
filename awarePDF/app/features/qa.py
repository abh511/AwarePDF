# ============================================================
# app/features/qa.py
# Question & Answer feature
# - Follow-up questions use the previous question for retrieval
#   and the last exchanges as conversation context for the LLM
# ============================================================

import re

from app.core.retriever import retrieve, outline_text
from app.core.llm import call_llm, format_context, QA_SYSTEM_PROMPT, QA_USER_TEMPLATE
from app.utils.logger import get_logger
from config.settings import LLM_MAX_PROMPT_CHARS, QA_REASONING_EFFORT

logger = get_logger(__name__)

# Questions about the book itself ("how many chapters", "what topics are covered")
_STRUCTURE_RE = re.compile(
    r"\b(topics?|chapters?|units?|modules?|sections?|contents|index|syllabus|outline|covered|covers?)\b",
    re.IGNORECASE,
)


def _history_block(chat_history: list[dict]) -> str:
    recent = chat_history[-4:]
    if not recent:
        return ""
    lines = [f"{m['role'].title()}: {m['content'][:500]}" for m in recent]
    return "\nPrevious conversation (for resolving follow-up questions):\n" + "\n".join(lines) + "\n"


def answer_question(pdf_hash: str, question: str, chat_history: list | None = None) -> dict:
    """
    Answers a question about the PDF using RAG.

    Args:
        chat_history: earlier messages, NOT including the current question.

    Returns:
        {"answer": str, "sources": list of dicts with page/section/preview/image_path}
    """
    chat_history = chat_history or []

    # Short follow-ups ("what about its units?") retrieve better with the previous question
    previous_questions = [m["content"] for m in chat_history if m.get("role") == "user"]
    retrieval_query = question
    if previous_questions and len(question.split()) < 8:
        retrieval_query = f"{previous_questions[-1]} {question}"

    is_structure_question = bool(_STRUCTURE_RE.search(question))
    if is_structure_question:
        retrieval_query += " table of contents index chapters"
    chunks = retrieve(pdf_hash, retrieval_query)
    if not chunks:
        return {
            "answer": "I couldn't find relevant information in the document for this question.",
            "sources": [],
        }

    history = _history_block(chat_history)
    outline = ""
    if is_structure_question:
        outline = f"Book outline (headings in page order):\n{outline_text(pdf_hash)}\n\n"
    context = format_context(chunks, max_chars=LLM_MAX_PROMPT_CHARS - len(history) - len(outline) - 1500)
    answer = call_llm(
        system_prompt=QA_SYSTEM_PROMPT,
        user_prompt=QA_USER_TEMPLATE.format(outline=outline, context=context, history=history, question=question),
        temperature=0.2,
        reasoning_effort=QA_REASONING_EFFORT,
    )

    sources = []
    for chunk in chunks:
        meta = chunk["metadata"]
        text = chunk["text"]
        sources.append({
            "page": meta.get("page_number", "?"),
            "page_end": meta.get("page_end"),
            "section": meta.get("section", ""),
            "preview": text[:300] + "..." if len(text) > 300 else text,
            "content_type": meta.get("content_type", "text"),
            "image_path": meta.get("image_path", ""),
        })

    return {"answer": answer, "sources": sources}
