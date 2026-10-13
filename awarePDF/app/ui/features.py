# ============================================================
# app/ui/features.py
# Features view - Summary, Topics, Key Points, Images
# ============================================================

from typing import Callable

import streamlit as st

from app.features.summarizer import summarize_pdf
from app.features.key_points import extract_key_points
from app.features.topic_extractor import extract_topics
from app.core.image_extractor import get_image_paths_for_pdf

IMAGES_PER_PAGE = 24


def render_features(pdf_hash: str, pdf_name: str, view: str):
    """Renders the selected feature view."""
    if view == "summary":
        _render_generated(
            pdf_hash, "summary", "### 📝 Summary",
            "Whole-book overview, or a detailed summary of one chapter/topic",
            "Generate Summary", summarize_pdf,
            filter_label="Focus on a chapter or topic (optional)",
            filter_placeholder="e.g. 'Chapter 4' or 'gradient descent' — leave empty for the whole book",
        )
    elif view == "topics":
        _render_generated(
            pdf_hash, "topics", "### 🗂️ Topics",
            "Main topics and subtopics, built from the book's headings",
            "Extract Topics", lambda h, _: extract_topics(h),
        )
    elif view == "keypoints":
        _render_generated(
            pdf_hash, "keypoints", "### ⭐ Key Points",
            "Important points for exam preparation",
            "Extract Key Points", extract_key_points,
            filter_label="Filter by topic (optional)",
            filter_placeholder="e.g. 'neural networks' or leave empty for the whole book",
        )
    elif view == "images":
        render_images(pdf_hash)


def _render_generated(
    pdf_hash: str,
    name: str,
    title: str,
    caption: str,
    button_label: str,
    generate: Callable[[str, str | None], str],
    filter_label: str | None = None,
    filter_placeholder: str = "",
):
    """Shared layout: optional filter, generate button, result kept per PDF."""
    st.markdown(title)
    st.caption(caption)

    focus = None
    if filter_label:
        focus = st.text_input(filter_label, placeholder=filter_placeholder, key=f"{name}_filter").strip() or None

    result_key = f"{name}_{pdf_hash}"
    if st.button(button_label, type="primary", width="stretch"):
        try:
            with st.spinner("Working on it..."):
                st.session_state[result_key] = generate(pdf_hash, focus)
        except Exception as exc:
            st.error(f"❌ {exc}")

    if st.session_state.get(result_key):
        st.markdown("---")
        st.markdown(st.session_state[result_key])


def render_images(pdf_hash: str):
    """Display extracted images gallery (paged, so large books stay fast)."""
    st.markdown("### 📸 Extracted Images")
    st.caption("Diagrams, figures, and images from the document")

    images = get_image_paths_for_pdf(pdf_hash)
    if not images:
        st.info("No images were extracted from this document.")
        return

    pages = (len(images) + IMAGES_PER_PAGE - 1) // IMAGES_PER_PAGE
    st.success(f"📸 Found {len(images)} images/diagrams")
    page = st.number_input("Gallery page", 1, pages, 1) if pages > 1 else 1
    st.markdown("---")

    cols = st.columns(2)
    start = (page - 1) * IMAGES_PER_PAGE
    for idx, img_info in enumerate(images[start:start + IMAGES_PER_PAGE]):
        with cols[idx % 2]:
            st.image(img_info["path"], caption=f"Page {img_info['page_number']}", width="stretch")
