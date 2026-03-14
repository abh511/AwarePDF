# ============================================================
# app/features/qa.py
# Question & Answer feature
# ============================================================

from app.core.retriever import retrieve
from app.core.llm import call_groq, format_context, QA_SYSTEM_PROMPT, QA_USER_TEMPLATE
from app.utils.logger import get_logger

logger = get_logger(__name__)


def answer_question(pdf_hash: str, question: str, chat_history: list = None) -> dict:
    """
    Answers a question about the PDF using RAG.

    Returns:
        {
            "answer": str,
            "sources": list of source chunks with page numbers,
            "context_used": str
        }
    """
    # Retrieve relevant chunks
    chunks = retrieve(pdf_hash, question, k=5, use_reranker=True)

    if not chunks:
        return {
            "answer": "I couldn't find relevant information in the document for this question.",
            "sources": [],
            "context_used": "",
        }

    context = format_context(chunks)
    user_prompt = QA_USER_TEMPLATE.format(context=context, question=question)

    answer = call_groq(
        system_prompt=QA_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.2,  # Low temp for factual accuracy
    )

    # Build source list for UI (show user where answer came from)
    sources = []
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        sources.append({
            "page": meta.get("page_number", "?"),
            "section": meta.get("section", ""),
            "preview": chunk["text"][:150] + "...",
        })

    return {"answer": answer, "sources": sources, "context_used": context}
