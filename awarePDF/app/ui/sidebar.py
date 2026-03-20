# ============================================================
# app/ui/sidebar.py
# Left sidebar - file upload, PDF info, processing pipeline
# ============================================================

import streamlit as st
from pathlib import Path
from pypdf import PdfReader

from app.utils.file_handler import save_uploaded_file, get_pdf_hash, get_file_size_mb
from app.core.pdf_processor import process_pdf
from app.core.vector_store import (
    collection_exists,
    add_documents,
    get_collection_stats,
    create_or_get_collection,
    initialize_vector_store,
)
from app.utils.logger import get_logger
from config.settings import MAX_UPLOAD_SIZE_MB, validate_keys

logger = get_logger(__name__)


def _get_page_count(file_path: str) -> int:
    """Quick page count using pypdf (no full parse needed)."""
    try:
        return len(PdfReader(file_path).pages)
    except Exception:
        return 0


def render_sidebar() -> dict:
    """
    Renders the sidebar and handles PDF upload + processing.

    Returns state dict:
    {
        "pdf_hash": str | None,
        "pdf_name": str | None,
        "is_ready": bool,
    }
    """
    state = {"pdf_hash": None, "pdf_name": None, "is_ready": False}

    with st.sidebar:
        st.title("📄 AwarePDF")
        st.caption("Upload your textbook and start learning smarter")

        readiness = initialize_vector_store(warmup_embeddings=False)
        if not readiness["ready"]:
            st.error(f"⚠️ Vector DB init failed: {readiness.get('error', 'unknown error')}")
            return state

        # --- API KEY WARNINGS ---
        keys = validate_keys()
        if not keys["groq"]:
            st.error("⚠️ GROQ_API_KEY not set in .env")
        if not keys["google"]:
            st.warning("💡 GOOGLE_API_KEY not set — summaries will use Groq, image descriptions disabled")

        st.divider()

        # --- FILE UPLOAD ---
        uploaded_file = st.file_uploader(
            "Upload PDF",
            type=["pdf"],
            help=f"Max size: {MAX_UPLOAD_SIZE_MB}MB. Large textbooks (600+ pages) may take 5-15 min to process.",
        )

        if uploaded_file is None:
            st.info("👆 Upload a PDF to get started")
            return state

        # --- SIZE CHECK ---
        file_size = len(uploaded_file.getbuffer()) / (1024 * 1024)
        if file_size > MAX_UPLOAD_SIZE_MB:
            st.error(f"File too large ({file_size:.1f}MB). Max: {MAX_UPLOAD_SIZE_MB}MB")
            return state

        st.success(f"✅ {uploaded_file.name} ({file_size:.1f}MB)")

        # --- SAVE + HASH ---
        file_path = save_uploaded_file(uploaded_file)
        pdf_hash = get_pdf_hash(file_path)

        state["pdf_hash"] = pdf_hash
        state["pdf_name"] = uploaded_file.name

        # --- ALREADY PROCESSED? ---
        if collection_exists(pdf_hash):
            stats = get_collection_stats(pdf_hash)
            chunk_count = stats.get("chunk_count", stats.get("count", 0))
            st.success(f"✅ Already indexed ({chunk_count} chunks)")
            state["is_ready"] = True
            return state

        # --- SHOW PAGE COUNT + TIME ESTIMATE ---
        page_count = _get_page_count(file_path)
        if page_count > 0:
            est_minutes = max(1, round(page_count / 60))
            st.info(
                f"📖 {page_count} pages detected. "
                f"Estimated processing time: ~{est_minutes} min. "
                "Processing happens once — results are cached."
            )

        # --- PROCESS PDF ---
        st.info("🔄 Processing PDF... (first time only, results cached)")
        progress_bar = st.progress(0.0)
        status_text = st.empty()

        def update_progress(percent: float, message: str):
            progress_bar.progress(float(percent))
            status_text.text(message)

        try:
            # Step 1: Parse + chunk + extract images
            final_chunks = process_pdf(file_path, progress_callback=update_progress)

            # Step 2: Store in ChromaDB
            update_progress(0.92, "Storing in vector database...")
            collection = create_or_get_collection(pdf_hash)
            add_documents(collection, final_chunks)

            update_progress(1.0, "Done!")
            progress_bar.progress(1.0)

            text_chunks = sum(1 for c in final_chunks if c.get("content_type") != "image_description")
            img_chunks = len(final_chunks) - text_chunks
            st.success(
                f"✅ Indexed {len(final_chunks)} chunks "
                f"({text_chunks} text, {img_chunks} image descriptions)"
            )
            state["is_ready"] = True

        except Exception as exc:
            st.error(f"❌ Processing failed: {exc}")
            logger.exception("Processing failed for %s", uploaded_file.name)

        return state
