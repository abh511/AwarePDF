# ============================================================
# app/ui/chat.py
# Chat interface with page citations and referenced diagrams
# ============================================================

from pathlib import Path

import streamlit as st

from app.features.qa import answer_question


def _page_label(src: dict) -> str:
    if src.get("page_end") and src["page_end"] != src["page"]:
        return f"Pages {src['page']}-{src['page_end']}"
    return f"Page {src['page']}"


def _render_extras(sources: list[dict]) -> None:
    """Show diagrams used for the answer, then the sources."""
    for src in sources:
        if src.get("image_path") and Path(src["image_path"]).exists():
            st.image(src["image_path"], caption=f"📄 Page {src['page']}", width=400)

    if sources:
        with st.expander("📚 View Sources"):
            for idx, src in enumerate(sources, 1):
                st.markdown(f"**Source {idx}** - {_page_label(src)}")
                if src.get("section"):
                    st.caption(f"Section: {src['section']}")
                if src.get("content_type") == "image_description":
                    st.caption("🖼️ From diagram/image")
                st.text(src["preview"])
                st.markdown("---")


def render_chat(pdf_hash: str, pdf_name: str):
    """Renders the Q&A chat interface."""
    st.markdown("### 💬 Ask Questions")
    st.caption("Get accurate answers with page citations")

    chat_key = f"messages_{pdf_hash}"
    messages = st.session_state.setdefault(chat_key, [])

    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            _render_extras(msg.get("sources", []))

    if question := st.chat_input("Ask anything about your PDF..."):
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            try:
                with st.spinner("Thinking..."):
                    result = answer_question(pdf_hash, question, chat_history=messages)
            except Exception as exc:
                st.error(f"❌ {exc}")
                return
            st.markdown(result["answer"])
            _render_extras(result["sources"])

        messages.append({"role": "user", "content": question})
        messages.append({"role": "assistant", "content": result["answer"], "sources": result["sources"]})

    if messages and st.button("🗑️ Clear Chat History", width="stretch"):
        st.session_state[chat_key] = []
        st.rerun()
