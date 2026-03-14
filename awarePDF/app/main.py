# ============================================================
# app/main.py
# Streamlit app entry point
# Run with: streamlit run app/main.py
# ============================================================

import streamlit as st
from app.ui.sidebar import render_sidebar
from app.ui.chat import render_chat
from app.ui.dashboard import render_dashboard
from config.settings import APP_TITLE

# --- PAGE CONFIG (must be first Streamlit call) ---
st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- RENDER SIDEBAR (handles upload + processing) ---
state = render_sidebar()

# --- MAIN CONTENT ---
if not state["is_ready"]:
    # Landing screen
    st.title("📄 AwarePDF")
    st.markdown("""
    ### Your AI-powered textbook assistant

    **What I can do:**
    - 💬 Answer questions about your PDF with page citations
    - 📝 Generate comprehensive summaries
    - 🗂️ Extract topics and subtopics
    - ⭐ Pull out key points for exam prep

    **👈 Upload a PDF in the sidebar to get started.**

    > Works best with engineering textbooks, research papers, and academic PDFs.
    """)

else:
    # --- TWO COLUMN LAYOUT ---
    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        render_chat(state["pdf_hash"], state["pdf_name"])

    with col2:
        render_dashboard(state["pdf_hash"], state["pdf_name"])
