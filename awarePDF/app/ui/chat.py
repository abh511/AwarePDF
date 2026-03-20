# ============================================================
# app/ui/chat.py
# Chat interface for Q&A with image support
# ============================================================

import streamlit as st
from pathlib import Path
from app.features.qa import answer_question


def _chat_key(pdf_hash: str) -> str:
    """Per-PDF session key so switching PDFs clears the chat."""
    return f"messages_{pdf_hash}"


def render_chat(pdf_hash: str, pdf_name: str):
    """Renders the Q&A chat interface with image display support."""

    st.subheader("💬 Ask Questions")
    st.caption(f"Asking about: **{pdf_name}**")

    chat_key = _chat_key(pdf_hash)

    # Initialize per-PDF chat history
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []

    messages = st.session_state[chat_key]

    # Display existing messages
    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

            # Show referenced images if any
            if msg.get("images"):
                for img in msg["images"]:
                    img_path = Path(img["path"])
                    if img_path.exists():
                        st.image(str(img_path), caption=f"📄 Page {img['page']}", width=300)

            if msg.get("sources"):
                with st.expander("📚 Sources"):
                    for src in msg["sources"]:
                        st.caption(f"📄 Page {src['page']} | {src['section']}")
                        if src.get("content_type") == "image_description":
                            st.caption("🖼️ *From diagram/image analysis*")
                        st.text(src["preview"])

    # Chat input
    if question := st.chat_input("Ask anything about your PDF..."):
        messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                result = answer_question(pdf_hash, question)

            st.markdown(result["answer"])

            # Display referenced images inline
            referenced_images = []
            if result["sources"]:
                for src in result["sources"]:
                    if src.get("content_type") == "image_description" and src.get("image_path"):
                        img_path = Path(src["image_path"])
                        if img_path.exists():
                            st.image(
                                str(img_path),
                                caption=f"📄 Referenced diagram (Page {src['page']})",
                                width=400,
                            )
                            referenced_images.append({"path": src["image_path"], "page": src["page"]})

                with st.expander("📚 Sources used"):
                    for src in result["sources"]:
                        st.caption(f"📄 Page {src['page']} | {src['section']}")
                        if src.get("content_type") == "image_description":
                            st.caption("🖼️ *From diagram/image analysis*")
                        st.text(src["preview"])

        messages.append({
            "role": "assistant",
            "content": result["answer"],
            "sources": result["sources"],
            "images": referenced_images,
        })

    # Clear chat button
    if messages:
        if st.button("🗑️ Clear Chat"):
            st.session_state[chat_key] = []
            st.rerun()
