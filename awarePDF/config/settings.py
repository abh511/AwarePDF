# ============================================================
# config/settings.py
# Central config - reads from .env file
# All other files import from here, never read .env directly
# ============================================================

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- BASE PATHS ---
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

# --- API KEYS ---
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")

# --- STORAGE PATHS ---
CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", str(DATA_DIR / "chroma_db"))
UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", str(DATA_DIR / "uploads"))
PROCESSED_DIR: str = os.getenv("PROCESSED_DIR", str(DATA_DIR / "processed"))
IMAGE_OUTPUT_DIR: str = os.getenv("IMAGE_OUTPUT_DIR", str(DATA_DIR / "images"))

# --- MODELS ---
# SentenceTransformer accepts short names directly (no "sentence-transformers/" prefix needed)
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_VISION_MODEL: str = os.getenv("GEMINI_VISION_MODEL", "gemini-1.5-flash")

# --- RAG SETTINGS ---
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "200"))
RETRIEVAL_K: int = int(os.getenv("RETRIEVAL_K", "5"))

# --- APP SETTINGS ---
APP_TITLE: str = os.getenv("APP_TITLE", "AwarePDF")
MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "200"))
DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"

# --- IMAGE EXTRACTION SETTINGS ---
ENABLE_IMAGE_EXTRACTION: bool = os.getenv("ENABLE_IMAGE_EXTRACTION", "True").lower() == "true"
MIN_IMAGE_SIZE: int = int(os.getenv("MIN_IMAGE_SIZE", "5000"))  # min bytes to keep an image
# Max images to describe with Gemini Vision per PDF (prevents rate-limit hammering on 600-page books)
MAX_IMAGES_TO_DESCRIBE: int = int(os.getenv("MAX_IMAGES_TO_DESCRIBE", "100"))

# --- AUTO-CREATE DIRECTORIES ---
for directory in [CHROMA_PERSIST_DIR, UPLOAD_DIR, PROCESSED_DIR, IMAGE_OUTPUT_DIR]:
    Path(directory).mkdir(parents=True, exist_ok=True)


def validate_keys() -> dict:
    """Check which API keys are configured. Called at app startup."""
    return {
        "groq": bool(GROQ_API_KEY),
        "google": bool(GOOGLE_API_KEY),
    }
