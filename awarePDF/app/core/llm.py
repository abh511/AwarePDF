# ============================================================
# app/core/llm.py
# Groq client (free API serving open-weight models) and prompt templates
#
# - LLM_MODEL (gpt-oss-120b): Q&A, summaries, topics, key points
# - VISION_MODEL (Qwen): describes diagrams/figures during ingestion
#
# Rate limits (HTTP 429) and server errors are retried by the Groq SDK,
# which honours the retry-after header sent by the API.
# ============================================================

import base64
import re

from app.utils.logger import get_logger
from config.settings import (
    GROQ_API_KEY, LLM_MODEL, VISION_MODEL, LLM_REASONING_EFFORT, LLM_MAX_PROMPT_CHARS,
)

logger = get_logger(__name__)

_groq_client = None

# Some open models emit their chain of thought inline; never show it to the user
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMError(Exception):
    """Raised when the LLM API is not configured or the request fails."""


def get_groq_client():
    """Return a cached Groq client instance."""
    global _groq_client
    if not GROQ_API_KEY:
        raise LLMError("GROQ_API_KEY is not set. Get a free key at https://console.groq.com")
    if _groq_client is None:
        from groq import Groq
        _groq_client = Groq(api_key=GROQ_API_KEY, max_retries=5, timeout=120)
    return _groq_client


def _complete(model: str, messages: list[dict], temperature: float, max_tokens: int, **extra) -> str:
    try:
        response = get_groq_client().chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra,
        )
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(f"LLM request to '{model}' failed: {exc}") from exc
    content = response.choices[0].message.content or ""
    return _THINK_RE.sub("", content).strip()


def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    reasoning_effort: str | None = None,
) -> str:
    """
    Calls the text LLM.
    Low temperature = more factual (good for engineering Q&A).
    Truncates prompts above LLM_MAX_PROMPT_CHARS to stay inside free-tier limits.
    """
    if len(user_prompt) > LLM_MAX_PROMPT_CHARS:
        logger.warning("User prompt too long (%s chars), truncating to %s",
                       len(user_prompt), LLM_MAX_PROMPT_CHARS)
        user_prompt = user_prompt[:LLM_MAX_PROMPT_CHARS] + "\n\n[Content truncated due to length...]"

    effort = reasoning_effort if reasoning_effort is not None else LLM_REASONING_EFFORT
    extra = {"reasoning_effort": effort} if effort else {}
    return _complete(
        LLM_MODEL,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature,
        max_tokens,
        **extra,
    )


def describe_image(jpeg_bytes: bytes, prompt: str, max_tokens: int = 600) -> str:
    """Calls the vision LLM with a single JPEG image."""
    data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")
    return _complete(
        VISION_MODEL,
        [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        temperature=0.2,
        max_tokens=max_tokens,
    )


# ============================================================
# PROMPT TEMPLATES
# Engineered for engineering/technical textbooks.
# "Based only on the context" prevents hallucination.
# ============================================================

QA_SYSTEM_PROMPT = """You are an expert engineering and science tutor helping students understand their textbook.

RULES:
- Answer ONLY based on the provided context chunks
- If the answer is not in the context, say "I couldn't find this in the uploaded document"
- Always cite the page number when available, like: (Page 12)
- Be clear and educational - explain like a knowledgeable tutor
- For technical concepts, give a brief definition before elaborating
- For mathematical formulas and equations, write them clearly with proper notation
- If image/diagram descriptions are provided in the context, use them to enhance your answer
- For engineering problems, show step-by-step solutions when relevant
- Include units and dimensional analysis where applicable
- Do NOT make up information not present in the context
- Do NOT invent your own examples unless the student asks for one; use the book's examples instead
- If the student asks for an example the book lacks, label it "Example (not from the book)" and recheck every bit, digit and calculation in it before answering
- For questions about the book's structure (chapters, topics, contents), use the book outline when provided"""

QA_USER_TEMPLATE = """{outline}Context from the textbook:
{context}
{history}
Student's question: {question}

Answer the question clearly and thoroughly, citing page numbers where available. If the context includes image/diagram descriptions, reference them in your answer. For numerical or formula-based questions, show the relevant equations and steps."""


KEY_POINTS_SYSTEM_PROMPT = """You are an expert at extracting key learning points from academic engineering and science content.
Extract only what is explicitly stated in the provided text. Pay special attention to:
- Definitions and key terminology
- Mathematical formulas and equations
- Physical laws and principles
- Important numerical values and constants
- Design rules and engineering constraints
- Warnings and common mistakes"""

KEY_POINTS_USER_TEMPLATE = """Extract the most important key points from this textbook content.

Content:
{context}

Format your response as a numbered list of clear, concise key points, each ending with its page citation like (Page 12).
Focus on: definitions, formulas, important concepts, rules, warnings, and diagram descriptions.
Maximum 15 points. For formulas, write them out clearly.
Use ONLY facts and formulas that appear in the content; never invent any."""


TOPICS_SYSTEM_PROMPT = """You are an expert at analyzing academic engineering and science documents and identifying their structure."""

TOPICS_USER_TEMPLATE = """Below are the section headings of a textbook in reading order, each with its page number.

{context}

Organize them into a clean structured outline of main topics (chapters) and subtopics:
1. Main Topic (Page X)
   - Subtopic (Page Y)
   - Subtopic (Page Z)
2. Main Topic (Page X)
   ...

Merge duplicates, drop noise (running headers, exercise numbers, index entries), and only include topics present in the list."""


SUMMARY_SYSTEM_PROMPT = """You are an expert academic summarizer specializing in engineering and technical content."""

SUMMARY_USER_TEMPLATE = """Summarize the following textbook content clearly and comprehensively.
{scope}
The summary should:
- Be organized with clear sections using headers
- Highlight key concepts, formulas, and definitions
- Note any diagrams, figures, or visual content described in the text
- Include important equations in proper notation
- Cite page numbers for the main points, like (Page 12)
- Be useful for exam preparation
- Be approximately 400-700 words
- Use ONLY facts, formulas and page numbers that appear in the content below; never invent formulas, terms or examples

Textbook content:
{context}

Write the summary now:"""


def _page_label(meta: dict) -> str:
    page = meta.get("page_number") or "?"
    page_end = meta.get("page_end")
    if page_end and page_end != page:
        return f"Pages {page}-{page_end}"
    return f"Page {page}"


def format_context(chunks: list[dict], max_chars: int | None = None) -> str:
    """
    Formats retrieved chunks into a single context string for the LLM.
    Stops adding chunks once max_chars would be exceeded.
    """
    type_labels = {
        "image_description": "[IMAGE/DIAGRAM DESCRIPTION] ",
        "table": "[TABLE] ",
    }
    parts: list[str] = []
    total = 0
    for chunk in chunks:
        text = chunk.get("text", "")
        if not text.strip():
            continue
        meta = chunk.get("metadata") or {}
        section = meta.get("section", "")
        section_label = f" | Section: {section}" if section else ""
        type_label = type_labels.get(meta.get("content_type", "text"), "")
        part = f"[{_page_label(meta)}{section_label}]\n{type_label}{text}"
        if max_chars is not None and parts and total + len(part) > max_chars:
            break
        parts.append(part)
        total += len(part) + 7

    return "\n\n---\n\n".join(parts)
