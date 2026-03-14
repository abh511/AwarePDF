# ============================================================
# app/core/llm.py
# LLM clients and prompt templates
#
# TWO LLM STRATEGY:
# - Groq (Llama 3.3 70b): Q&A, key points, topics - fast, free
# - Gemini 1.5 Flash: Summarization - handles huge context (1M tokens)
#
# WHY GEMINI FOR SUMMARIES?
# Summarizing a whole textbook chapter needs to see ALL the content.
# RAG retrieval gives you fragments - bad for summaries.
# Gemini's 1M token context window can take 50-100 chunks at once.
# Groq's context is smaller and better for focused Q&A.
# ============================================================

from tenacity import retry, stop_after_attempt, wait_exponential
from app.utils.logger import get_logger
from config.settings import GROQ_API_KEY, GOOGLE_API_KEY, GROQ_MODEL, GEMINI_MODEL

logger = get_logger(__name__)


# ============================================================
# GROQ CLIENT (Q&A, key points, topics)
# ============================================================

def get_groq_client():
    """Returns initialized Groq client."""
    from groq import Groq
    return Groq(api_key=GROQ_API_KEY)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def call_groq(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 1500,
) -> str:
    """
    Calls Groq API with retry logic.
    Temperature 0.3 = mostly deterministic but not rigid.
    Lower = more factual (good for Q&A).
    Higher = more creative (bad for Q&A, you want accuracy).
    """
    client = get_groq_client()
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


# ============================================================
# GEMINI CLIENT (Summarization)
# ============================================================

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def call_gemini(
    prompt: str,
    temperature: float = 0.4,
    max_tokens: int = 2000,
) -> str:
    """
    Calls Gemini API. Used for summarization with large context.
    """
    import google.generativeai as genai
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)

    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )
    return response.text.strip()


# ============================================================
# PROMPT TEMPLATES
# These are carefully engineered - change with caution.
# "Based only on the context" prevents hallucination.
# ============================================================

QA_SYSTEM_PROMPT = """You are an expert academic assistant helping students understand their textbook.

RULES:
- Answer ONLY based on the provided context chunks
- If the answer is not in the context, say "I couldn't find this in the uploaded document"
- Always cite the page number when available, like: (Page 12)
- Be clear and educational - explain like a knowledgeable tutor
- For technical concepts, give a brief definition before elaborating
- Do NOT make up information not present in the context"""

QA_USER_TEMPLATE = """Context from the textbook:
{context}

Student's question: {question}

Answer the question clearly, citing page numbers where available."""


KEY_POINTS_SYSTEM_PROMPT = """You are an expert at extracting key learning points from academic content.
Extract only what is explicitly stated in the provided text."""

KEY_POINTS_USER_TEMPLATE = """Extract the most important key points from this textbook content.

Content:
{context}

Format your response as a numbered list of clear, concise key points.
Focus on: definitions, formulas, important concepts, rules, and warnings.
Maximum 10 points."""


TOPICS_SYSTEM_PROMPT = """You are an expert at analyzing academic documents and identifying their structure."""

TOPICS_USER_TEMPLATE = """Based on the following content from a textbook, identify the main topics and subtopics covered.

Content (section headings and key chunks):
{context}

Output a structured topic list like:
1. Main Topic
   - Subtopic
   - Subtopic
2. Main Topic
   ...

Only include topics clearly present in the content."""


SUMMARY_PROMPT_TEMPLATE = """You are an expert academic summarizer. 

Summarize the following textbook content clearly and comprehensively.
The summary should:
- Cover all major topics mentioned
- Be organized with clear sections
- Highlight key concepts, formulas, and definitions
- Be useful for exam preparation
- Be approximately 300-500 words

Textbook content:
{context}

Write the summary now:"""


def format_context(chunks: list[dict]) -> str:
    """
    Formats retrieved chunks into a single context string for the LLM.
    Includes page numbers and section names for citations.
    """
    parts = []
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        page = meta.get("page_number", "?")
        section = meta.get("section", "")
        content_type = meta.get("content_type", "text")

        # Add type label for tables so LLM knows it's structured data
        type_label = f"[{content_type.upper()}] " if content_type != "text" else ""
        section_label = f" | Section: {section}" if section else ""

        parts.append(f"[Page {page}{section_label}]\n{type_label}{chunk['text']}")

    return "\n\n---\n\n".join(parts)
