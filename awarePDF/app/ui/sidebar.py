# ============================================================
# app/ui/sidebar.py
# Sidebar - file upload, processing, and navigation
# ============================================================

import streamlit as st

from app.utils.file_handler import save_uploaded_file, get_pdf_hash
from app.core.pdf_processor import process_pdf, get_page_count
from app.core.image_extractor import start_background_description, description_progress
from app.core.vector_store import (
    is_indexed, index_chunks, get_chunk_count, delete_collection,
    images_pending, add_image_chunks, mark_images_done,
)
from app.utils.logger import get_logger
from config.settings import MAX_UPLOAD_SIZE_MB, validate_keys

logger = get_logger(__name__)

VIEWS = {
    "💬 Ask Questions": "chat",
    "📝 Summary": "summary",
    "🗂️ Topics": "topics",
    "⭐ Key Points": "keypoints",
    "📸 Images": "images",
}


def _process(file_path: str, pdf_hash: str) -> None:
    """Parse, describe images, embed and index - with one progress bar."""
    progress_bar = st.progress(0.0)
    status_text = st.empty()

    def update(fraction: float, message: str) -> None:
        progress_bar.progress(min(1.0, fraction))
        status_text.caption(message)

    chunks = process_pdf(file_path, progress_callback=lambda p, m: update(0.85 * p, m))
    try:
        index_chunks(pdf_hash, chunks, progress_callback=lambda p, m: update(0.85 + 0.15 * p, m))
    except Exception:
        delete_collection(pdf_hash)
        raise
    update(1.0, "Complete!")


@st.fragment(run_every=5)
def _image_status(pdf_hash: str) -> None:
    """Live status of the background diagram descriptions."""
    progress = description_progress(pdf_hash)
    if progress:
        done, total = progress
        st.caption(f"🖼️ Making diagrams searchable in the background: {done}/{total}")


def render_sidebar() -> dict:
    """
    Renders the sidebar with upload, processing, and navigation.

    Returns state dict:
    {"pdf_hash": str | None, "pdf_name": str | None, "is_ready": bool, "view": str}
    """
    state = {"pdf_hash": None, "pdf_name": None, "is_ready": False, "view": "chat"}

    with st.sidebar:
        st.markdown("### 📄 AwarePDF")
        st.caption("AI-powered textbook assistant")

        if not validate_keys()["groq"]:
            st.error("⚠️ GROQ_API_KEY not set in .env — get a free key at console.groq.com")

        st.markdown("---")
        st.markdown("#### 📤 Upload Document")
        uploaded_file = st.file_uploader(
            "Choose a PDF file",
            type=["pdf"],
            help=f"Max size: {MAX_UPLOAD_SIZE_MB}MB",
            label_visibility="collapsed",
        )

        if uploaded_file is None:
            for key in ("current_pdf_id", "current_pdf_hash", "current_pdf_path"):
                st.session_state.pop(key, None)
            st.info("👆 Upload a PDF to begin")
            return state

        file_size = uploaded_file.size / (1024 * 1024)
        if file_size > MAX_UPLOAD_SIZE_MB:
            st.error(f"File too large ({file_size:.1f}MB)")
            return state

        # --- SAVE + HASH (once per uploaded file) ---
        if st.session_state.get("current_pdf_id") != uploaded_file.file_id:
            file_path = save_uploaded_file(uploaded_file)
            st.session_state["current_pdf_id"] = uploaded_file.file_id
            st.session_state["current_pdf_hash"] = get_pdf_hash(file_path)
            st.session_state["current_pdf_path"] = file_path
        pdf_hash = st.session_state["current_pdf_hash"]
        file_path = st.session_state["current_pdf_path"]

        state["pdf_hash"] = pdf_hash
        state["pdf_name"] = uploaded_file.name
        st.success(f"✅ {uploaded_file.name}")

        # --- PROCESS ONCE ---
        if not is_indexed(pdf_hash):
            try:
                page_count = get_page_count(file_path)
            except Exception as exc:
                st.error(f"❌ {exc}")
                return state

            st.info(
                f"📖 {page_count} pages · {file_size:.1f}MB\n\n"
                f"⏱️ Est. time: ~{max(1, round(page_count / 60))}-{max(2, round(page_count / 30))} min "
                "(one time only)"
            )
            try:
                _process(file_path, pdf_hash)
            except Exception as exc:
                logger.exception("Processing failed for %s", uploaded_file.name)
                st.error(f"❌ Processing failed:\n\n{exc}")
                return state
            st.rerun()

        if images_pending(pdf_hash):
            start_background_description(
                pdf_hash,
                on_batch=lambda chunks: add_image_chunks(pdf_hash, chunks),
                on_finished=lambda: mark_images_done(pdf_hash),
            )
        st.caption(f"Indexed: {get_chunk_count(pdf_hash)} chunks")
        _image_status(pdf_hash)
        state["is_ready"] = True

        # --- NAVIGATION ---
        st.markdown("---")
        st.markdown("#### 🧭 Features")
        choice = st.radio("Feature", list(VIEWS), label_visibility="collapsed")
        state["view"] = VIEWS[choice]
        return state
