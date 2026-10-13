# ============================================================
# app/utils/file_handler.py
# Handles file uploads, temp storage, and PDF hashing
# The hash is critical - it's used as the ChromaDB collection ID
# so the same PDF is never re-processed
# ============================================================

import hashlib
from pathlib import Path
from app.utils.logger import get_logger
from config.settings import UPLOAD_DIR

logger = get_logger(__name__)


def save_uploaded_file(uploaded_file) -> str:
    """
    Saves a Streamlit UploadedFile to disk.
    Returns the full path as a string.

    Why save to disk? Docling needs a real file path, not a buffer.
    """
    save_path = Path(UPLOAD_DIR) / uploaded_file.name
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    logger.info("Saved uploaded file: %s", save_path)
    return str(save_path)


def get_pdf_hash(file_path: str) -> str:
    """
    Returns SHA-256 hash of a PDF file.
    This is used as the unique collection name in ChromaDB
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in 1MB chunks - handles large PDFs without loading all into RAM
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
