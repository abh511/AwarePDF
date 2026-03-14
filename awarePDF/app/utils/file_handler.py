# ============================================================
# app/utils/file_handler.py
# Handles file uploads, temp storage, and PDF hashing
# The hash is critical - it's used as the ChromaDB collection ID
# so the same PDF is never re-processed
# ============================================================

import hashlib
import shutil
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
    logger.info(f"Saved uploaded file: {save_path}")
    return str(save_path)


def get_pdf_hash(file_path: str) -> str:
    """
    Returns MD5 hash of a PDF file.
    This is used as the unique collection name in ChromaDB.

    Why MD5? It's fast and we're not doing security here,
    just checking if this exact file was already processed.
    """
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        # Read in chunks - handles large PDFs without loading all into RAM
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def cleanup_upload(file_path: str) -> None:
    """
    Deletes a temporary uploaded file after processing.
    Call this after PDF has been processed and stored in ChromaDB.
    """
    try:
        Path(file_path).unlink(missing_ok=True)
        logger.info(f"Cleaned up temp file: {file_path}")
    except Exception as e:
        logger.warning(f"Could not delete temp file {file_path}: {e}")


def get_file_size_mb(file_path: str) -> float:
    """Returns file size in MB - used for upload validation."""
    return Path(file_path).stat().st_size / (1024 * 1024)
