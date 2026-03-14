# ============================================================
# app/ui/dashboard.py
# Dashboard - Summary, Topics, Key Points tabs
# ============================================================

import streamlit as st
from app.features.summarizer import summarize_pdf
from app.features.key_points import extract_key_points
from app.features.topic_extractor import extract_topics


def render_dashboard(pdf_hash: str, pdf_name: str):
    """Renders the 3-tab dashboard: Summary | Topics | Key Points"""

    st.subheader("📊 Document Intelligence")
    st.caption(f"Analyzing: **{pdf_name}**")

    tab1, tab2, tab3 = st.tabs(["📝 Summary", "🗂️ Topics", "⭐ Key Points"])

    # --- SUMMARY TAB ---
    with tab1:
        st.write("Get a comprehensive summary of the entire document.")
        if st.button("Generate Summary", key="btn_summary"):
            with st.spinner("Generating summary (using Gemini for large context)..."):
                summary = summarize_pdf(pdf_hash)
            st.markdown(summary)

    # --- TOPICS TAB ---
    with tab2:
        st.write("See all topics and subtopics covered in the document.")
        if st.button("Extract Topics", key="btn_topics"):
            with st.spinner("Extracting topic structure..."):
                topics = extract_topics(pdf_hash)
            st.markdown(topics)

    # --- KEY POINTS TAB ---
    with tab3:
        st.write("Extract the most important points for exam prep.")
        topic_filter = st.text_input(
            "Filter by topic (optional)",
            placeholder="e.g. 'sorting algorithms' or leave empty for all",
        )
        if st.button("Extract Key Points", key="btn_keypoints"):
            with st.spinner("Extracting key points..."):
                key_points = extract_key_points(
                    pdf_hash,
                    topic=topic_filter if topic_filter else None,
                )
            st.markdown(key_points)
