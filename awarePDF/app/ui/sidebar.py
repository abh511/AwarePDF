# ============================================================
# app/ui/sidebar.py
# Left sidebar - file upload, PDF info, settings
# ============================================================

import streamlit as st
from pathlib import Path
from app.utils.file_handler import save_uploaded_file, get_pdf_hash, get_file_size_mb
from app.core.pdf_processor import process_pdf
from app.core.chunker import chunk_with_metadata
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


def render_sidebar() -> dict:
    """
    Renders the sidebar and handles PDF upload + processing.

    Returns state dict:
    {
        "pdf_hash": str or None,
        "pdf_name": str or None,
        "is_ready": bool,  # True when PDF is processed and ready for Q&A
    }
    """
    state = {"pdf_hash": None, "pdf_name": None, "is_ready": False}

    with st.sidebar:
        st.title("📄 AwarePDF")
        st.caption("Upload your textbook and start learning smarter")

        readiness = initialize_vector_store(warmup_embeddings=False)
        if not readiness["ready"]:
            st.error(f"⚠️ Vector DB init failed: {readiness['error']}")
            logger.error("Vector DB initialization failed: %s", readiness["error"])
            return state

        # --- API KEY WARNINGS ---
        keys = validate_keys()
        if not keys["groq"]:
            st.error("⚠️ GROQ_API_KEY not set in .env")
        if not keys["google"]:
            st.warning("💡 GOOGLE_API_KEY not set (summaries will use Groq)")

        st.divider()

        # --- FILE UPLOAD ---
        uploaded_file = st.file_uploader(
            "Upload PDF",
            type=["pdf"],
            help=f"Max size: {MAX_UPLOAD_SIZE_MB}MB",
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

        # --- CHECK IF ALREADY PROCESSED ---
        if collection_exists(pdf_hash):
            stats = get_collection_stats(pdf_hash)
            chunk_count = stats.get("chunk_count", stats.get("count", 0))
            st.success(f"✅ Already indexed ({chunk_count} chunks)")
            state["is_ready"] = True
            return state

        # --- PROCESS PDF ---
        st.info("🔄 Processing PDF... (first time only)")
        progress_bar = st.progress(0)
        status_text = st.empty()

        def update_progress(percent: float, message: str):
            progress_bar.progress(percent)
            status_text.text(message)

        try:
            # Step 1: Parse PDF with Docling
            raw_chunks = process_pdf(file_path, progress_callback=update_progress)

            # Step 2: Chunk
            update_progress("Chunking content...", 0.7)
            final_chunks = chunk_with_metadata(raw_chunks)

            # Step 3: Store in ChromaDB
            update_progress("Storing in vector database...", 0.85)
            collection = create_or_get_collection(pdf_hash)
            add_documents(collection, final_chunks)

            update_progress("Done!", 1.0)
            st.success(f"✅ Indexed {len(final_chunks)} chunks!")
            state["is_ready"] = True

        except Exception as e:
            st.error(f"❌ Processing failed: {e}")
            logger.error(f"Processing failed: {e}")

        return state
