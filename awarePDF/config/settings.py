# ============================================================
# config/settings.py
# Central config - reads from .env file
# All other files import from here, never read .env directly
# ============================================================

import os
from pathlib import Path
from dotenv import load_dotenv

# --- BASE PATHS ---
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


def _path(name: str, default: str) -> Path:
    """Relative paths resolve against awarePDF/, never the current working directory."""
    path = Path(os.getenv(name, default))
    return path if path.is_absolute() else (BASE_DIR / path).resolve()


DATA_DIR = _path("DATA_DIR", "data")

# --- API KEYS ---
# Free key: https://console.groq.com (serves open-weight models)
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# --- STORAGE PATHS ---
CHROMA_PERSIST_DIR: Path = _path("CHROMA_PERSIST_DIR", str(DATA_DIR / "chroma_db"))
UPLOAD_DIR: Path = _path("UPLOAD_DIR", str(DATA_DIR / "uploads"))
PROCESSED_DIR: Path = _path("PROCESSED_DIR", str(DATA_DIR / "processed"))
IMAGE_OUTPUT_DIR: Path = _path("IMAGE_OUTPUT_DIR", str(DATA_DIR / "images"))

# --- MODELS ---
# Open-weight LLMs served for free by Groq
LLM_MODEL: str = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
VISION_MODEL: str = os.getenv("VISION_MODEL", "qwen/qwen3.8-27b")
# "low" | "medium" | "high" for reasoning models; leave empty for models that don't support it
LLM_REASONING_EFFORT: str = os.getenv("LLM_REASONING_EFFORT", "low")
# Q&A reasons more carefully (worked examples, calculations); summaries stay fast
QA_REASONING_EFFORT: str = os.getenv("QA_REASONING_EFFORT", "medium")
# Local models (run on your machine, downloaded once from Hugging Face)
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
RERANKER_MODEL: str = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# --- RAG SETTINGS ---
# Paragraphs are merged up to CHUNK_SIZE chars; only oversized paragraphs are split
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "150"))
RETRIEVAL_K: int = int(os.getenv("RETRIEVAL_K", "6"))
# Candidates pulled from each of dense + BM25 search before reranking
CANDIDATES_K: int = int(os.getenv("CANDIDATES_K", "30"))
USE_RERANKER: bool = _bool("USE_RERANKER", True)
# Max prompt size sent to the LLM (free tier allows 8000 tokens/min per model)
LLM_MAX_PROMPT_CHARS: int = int(os.getenv("LLM_MAX_PROMPT_CHARS", "16000"))

# --- PDF PARSING (tuned for 700+ page books) ---
# Pages parsed per Docling pass: bounds memory use and gives real progress updates
PAGE_BATCH_SIZE: int = int(os.getenv("PAGE_BATCH_SIZE", "40"))
# OCR is only needed for scanned PDFs and makes parsing several times slower
ENABLE_OCR: bool = _bool("ENABLE_OCR", False)
# "fast" or "accurate" table structure recognition
TABLE_MODE: str = os.getenv("TABLE_MODE", "fast").lower()

# --- IMAGE EXTRACTION ---
ENABLE_IMAGE_EXTRACTION: bool = _bool("ENABLE_IMAGE_EXTRACTION", True)
MIN_IMAGE_BYTES: int = int(os.getenv("MIN_IMAGE_BYTES", "5000"))
MIN_IMAGE_DIM: int = int(os.getenv("MIN_IMAGE_DIM", "100"))
# Largest images are described first; the rest stay viewable in the gallery
MAX_IMAGES_TO_DESCRIBE: int = int(os.getenv("MAX_IMAGES_TO_DESCRIBE", "150"))

# --- APP SETTINGS ---
APP_TITLE: str = os.getenv("APP_TITLE", "AwarePDF")
MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "200"))

# --- AUTO-CREATE DIRECTORIES ---
for directory in (CHROMA_PERSIST_DIR, UPLOAD_DIR, PROCESSED_DIR, IMAGE_OUTPUT_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def validate_keys() -> dict:
    """Check which API keys are configured. Called at app startup."""
    return {"groq": bool(GROQ_API_KEY)}
