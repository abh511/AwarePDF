# ============================================================
# app/main.py
# Streamlit app entry point (theme lives in .streamlit/config.toml)
# ============================================================

import sys
from pathlib import Path

# Make `app` and `config` importable when launched via `streamlit run app/main.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from app.ui.sidebar import render_sidebar
from app.ui.chat import render_chat
from app.ui.features import render_features
from config.settings import APP_TITLE

# --- PAGE CONFIG (must be first Streamlit call) ---
st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown("<style>.block-container {max-width: 1200px;}</style>", unsafe_allow_html=True)

state = render_sidebar()

if not state["is_ready"]:
    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.markdown("<h1 style='text-align: center;'>📄 AwarePDF</h1>", unsafe_allow_html=True)
        st.markdown(
            "<p style='text-align: center; font-size: 1.2rem; opacity: 0.7;'>"
            "Your AI-powered textbook assistant</p>",
            unsafe_allow_html=True,
        )
        st.markdown("---")
        st.markdown("""
        ### What I can do:

        - 💬 **Ask Questions** - Get accurate answers with page citations
        - 📝 **Summaries** - Whole-book or per-chapter summaries
        - 🗂️ **Topics** - Chapter and section outline of the book
        - ⭐ **Key Points** - Important points for exam prep
        - 📸 **Diagrams** - Figures are described and searchable

        ### How it works:

        1. Upload your PDF in the sidebar (books of 700+ pages are fine)
        2. Wait for processing (first time only)
        3. Choose a feature from the sidebar

        ---

        **👈 Upload a PDF in the sidebar to get started**
        """)
else:
    st.markdown(f"<h2 style='text-align: center;'>📄 {state['pdf_name']}</h2>", unsafe_allow_html=True)
    st.markdown("---")

    if state["view"] == "chat":
        render_chat(state["pdf_hash"], state["pdf_name"])
    else:
        render_features(state["pdf_hash"], state["pdf_name"], state["view"])
