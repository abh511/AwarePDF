# ============================================================
# config/settings.py
# Central config - reads from .env file
# All other files import from here, never read .env directly
# ============================================================

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # Loads .env file into os.environ

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

# --- MODELS ---
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# --- RAG SETTINGS ---
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))
RETRIEVAL_K: int = int(os.getenv("RETRIEVAL_K", "5"))

# --- APP SETTINGS ---
APP_TITLE: str = os.getenv("APP_TITLE", "AwarePDF")
MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"

# --- AUTO-CREATE DIRECTORIES ---
# This runs when settings.py is imported - ensures folders always exist
for directory in [CHROMA_PERSIST_DIR, UPLOAD_DIR, PROCESSED_DIR]:
    Path(directory).mkdir(parents=True, exist_ok=True)


def validate_keys() -> dict:
    """
    Call this at app startup to check which API keys are set.
    Returns a dict so the UI can show warnings if keys are missing.
    """
    return {
        "groq": bool(GROQ_API_KEY),
        "google": bool(GOOGLE_API_KEY),
    }
