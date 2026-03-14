# ============================================================
# app/ui/chat.py
# Chat interface for Q&A
# ============================================================

import streamlit as st
from app.features.qa import answer_question


def render_chat(pdf_hash: str, pdf_name: str):
    """Renders the Q&A chat interface."""

    st.subheader("💬 Ask Questions")
    st.caption(f"Asking about: **{pdf_name}**")

    # Initialize chat history in session state
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display existing messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("📚 Sources"):
                    for src in msg["sources"]:
                        st.caption(f"📄 Page {src['page']} | {src['section']}")
                        st.text(src["preview"])

    # Chat input
    if question := st.chat_input("Ask anything about your PDF..."):

        # Show user message
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        # Get answer
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                result = answer_question(pdf_hash, question)

            st.markdown(result["answer"])

            if result["sources"]:
                with st.expander("📚 Sources used"):
                    for src in result["sources"]:
                        st.caption(f"📄 Page {src['page']} | {src['section']}")
                        st.text(src["preview"])

        # Save assistant message
        st.session_state.messages.append({
            "role": "assistant",
            "content": result["answer"],
            "sources": result["sources"],
        })

    # Clear chat button
    if st.session_state.messages:
        if st.button("🗑️ Clear Chat"):
            st.session_state.messages = []
            st.rerun()
