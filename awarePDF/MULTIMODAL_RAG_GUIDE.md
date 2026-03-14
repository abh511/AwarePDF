# Multimodal RAG Implementation Guide

## 📚 Understanding Multimodal RAG

### What is Multimodal RAG?

**Traditional RAG (what you have now):**
- Extracts TEXT from PDFs
- Converts text to embeddings
- Retrieves relevant text chunks
- Sends text to LLM for answers

**Multimodal RAG (future enhancement):**
- Extracts TEXT + IMAGES + TABLES + DIAGRAMS
- Converts both text AND images to embeddings (in same vector space)
- Retrieves relevant text chunks AND images
- Sends both text AND images to vision-capable LLM
- LLM can "see" diagrams, charts, equations, etc.

### Why It Matters for Engineering Textbooks

Engineering PDFs are VISUAL:
- Circuit diagrams
- Flowcharts
- Mathematical equations (as images)
- Graphs and charts
- Mechanical drawings
- Architecture diagrams

Your current system only reads the captions like "Figure 3.2: Amplifier circuit" but can't see the actual circuit!

### Real Example

**User asks:** "Explain how the amplifier circuit works"

**Current System (Text-only RAG):**
- Finds: "Figure 3.2: Basic amplifier circuit with transistor"
- Answer: Generic explanation based on caption only

**Multimodal RAG:**
- Finds: Caption + actual circuit diagram image
- Sends image to GPT-4 Vision or Gemini Vision
- Answer: Specific explanation pointing to the transistor, resistors, capacitors visible in the diagram

---

## 🎓 Learning Resources

### 1. Concept Understanding

**Start Here (Easy):**
- [LangChain Multimodal RAG Tutorial](https://python.langchain.com/docs/tutorials/multimodal_rag/)
- [OpenAI Vision API Docs](https://platform.openai.com/docs/guides/vision)
- [Google Gemini Vision Guide](https://ai.google.dev/gemini-api/docs/vision)

**Video Tutorials:**
- Search YouTube: "Multimodal RAG tutorial"
- Search YouTube: "GPT-4 Vision RAG"
- Search YouTube: "CLIP embeddings for images"

**Deep Dive (Advanced):**
- [CLIP Paper](https://arxiv.org/abs/2103.00020) - Vision-language embeddings
- [ColPali Paper](https://arxiv.org/abs/2407.01449) - Document understanding
- [Unstructured.io Blog](https://unstructured.io/blog) - PDF multimodal extraction

### 2. Key Technologies to Learn

1. **CLIP (OpenAI)** - Embeds images and text in same vector space
2. **GPT-4 Vision / Gemini Vision** - LLMs that can see images
3. **Unstructured.io** - Better multimodal PDF extraction than Docling
4. **LangChain MultiModal** - Framework for multimodal RAG

### 3. Example Projects to Study

- [LangChain Cookbook - Multimodal RAG](https://github.com/langchain-ai/langchain/blob/master/cookbook/Multi_modal_RAG.ipynb)
- [Unstructured Multimodal RAG Example](https://github.com/Unstructured-IO/unstructured/tree/main/examples)

---

## 🏗️ Where to Implement in Your Project

### Phase 1: Image Extraction (Easiest)

**File to modify:** `app/core/pdf_processor.py`

**Current code (line ~150):**
```python
def _caption_from_figure(figure: Any) -> str:
    """Extract figure caption text from a Docling figure node."""
    for attr in ("caption", "text", "title"):
        value = getattr(figure, attr, None)
        caption = _safe_text(value)
        if caption:
            return caption
    return ""
```

**Add new function:**
```python
def _extract_figure_image(figure: Any, pdf_path: Path, output_dir: Path) -> str | None:
    """
    Extract the actual image from a figure node and save to disk.
    Returns the path to the saved image file.
    """
    # TODO: Implement image extraction
    # Use Docling's image extraction or pypdf/pdf2image
    # Save to output_dir / f"figure_{page}_{index}.png"
    # Return the file path
    pass
```

**Modify `_extract_structured_chunks` to save images:**
```python
# Around line 200, in the figures loop:
for figure in figures:
    caption = _caption_from_figure(figure)
    
    # NEW: Extract actual image
    image_path = _extract_figure_image(figure, pdf_path, image_output_dir)
    
    _append_chunk(
        chunks=chunks,
        text=caption,
        page_number=_extract_page_number(figure),
        content_type="figure_caption",
        section=active_section,
        is_important=_guess_is_important(figure, "figure_caption", caption),
        image_path=image_path,  # NEW: Add image path to chunk
    )
```

### Phase 2: Multimodal Embeddings

**Create new file:** `app/core/multimodal_embedder.py`

```python
"""
Multimodal embeddings using CLIP.
Embeds both text and images into the same vector space.
"""

from sentence_transformers import SentenceTransformer
from PIL import Image

# Use CLIP model that handles both text and images
MODEL_NAME = "clip-ViT-B-32"

def embed_text(text: str) -> list[float]:
    """Embed text using CLIP."""
    model = SentenceTransformer(MODEL_NAME)
    return model.encode(text).tolist()

def embed_image(image_path: str) -> list[float]:
    """Embed image using CLIP."""
    model = SentenceTransformer(MODEL_NAME)
    image = Image.open(image_path)
    return model.encode(image).tolist()

def embed_multimodal_chunk(chunk: dict) -> list[float]:
    """
    Embed a chunk that might have text, image, or both.
    CLIP allows us to search images with text queries!
    """
    if chunk.get("image_path"):
        # Prioritize image embedding for visual content
        return embed_image(chunk["image_path"])
    else:
        # Fall back to text embedding
        return embed_text(chunk["text"])
```

### Phase 3: Store Images in Vector DB

**File to modify:** `app/core/vector_store.py`

**Modify `_prepare_metadata` function (line ~60):**
```python
def _prepare_metadata(chunk: dict) -> dict:
    """Normalize and filter metadata fields before writing to ChromaDB."""
    source_meta = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}

    metadata = {
        "page_number": source_meta.get("page_number", chunk.get("page_number")),
        "chunk_index": source_meta.get("chunk_index", chunk.get("chunk_index")),
        "content_type": source_meta.get("content_type", chunk.get("content_type", "text")),
        "section": source_meta.get("section", chunk.get("section", "")),
        "is_important": source_meta.get("is_important", chunk.get("is_important", False)),
        "image_path": source_meta.get("image_path", chunk.get("image_path", "")),  # NEW
        "has_image": bool(source_meta.get("image_path", chunk.get("image_path"))),  # NEW
    }
    
    # ... rest of function
```

### Phase 4: Multimodal Retrieval

**Create new file:** `app/core/multimodal_retriever.py`

```python
"""
Retrieves both text chunks and image chunks for a query.
"""

from app.core.vector_store import similarity_search, create_or_get_collection

def retrieve_multimodal(pdf_hash: str, query: str, k: int = 5) -> dict:
    """
    Retrieve relevant chunks including images.
    
    Returns:
        {
            "text_chunks": [...],
            "image_chunks": [...],  # Chunks that have images
            "all_chunks": [...]
        }
    """
    collection = create_or_get_collection(pdf_hash)
    
    # Get all relevant chunks (text + images)
    all_chunks = similarity_search(collection, query, k=k*2)
    
    # Separate text-only and image chunks
    text_chunks = [c for c in all_chunks if not c["metadata"].get("has_image")]
    image_chunks = [c for c in all_chunks if c["metadata"].get("has_image")]
    
    return {
        "text_chunks": text_chunks[:k],
        "image_chunks": image_chunks[:k],
        "all_chunks": all_chunks[:k]
    }
```

### Phase 5: Vision-Capable LLM

**File to modify:** `app/core/llm.py`

**Add new function (around line 100):**
```python
def call_gemini_vision(
    prompt: str,
    image_paths: list[str],
    temperature: float = 0.3,
) -> str:
    """
    Call Gemini with both text and images.
    Gemini can analyze the images and answer based on what it sees.
    """
    import google.generativeai as genai
    from PIL import Image
    
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Load images
    images = [Image.open(path) for path in image_paths]
    
    # Send prompt + images
    response = model.generate_content(
        [prompt] + images,
        generation_config=genai.types.GenerationConfig(
            temperature=temperature,
        )
    )
    
    return response.text.strip()


def call_gpt4_vision(
    prompt: str,
    image_paths: list[str],
    temperature: float = 0.3,
) -> str:
    """
    Alternative: Use GPT-4 Vision (requires OpenAI API key).
    """
    import base64
    from openai import OpenAI
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    # Encode images to base64
    image_contents = []
    for path in image_paths:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
            image_contents.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"}
            })
    
    response = client.chat.completions.create(
        model="gpt-4-vision-preview",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                *image_contents
            ]
        }],
        temperature=temperature,
    )
    
    return response.choices[0].message.content
```

### Phase 6: Update Q&A Feature

**File to modify:** `app/features/qa.py`

**Add multimodal Q&A function:**
```python
def answer_question_multimodal(pdf_hash: str, question: str) -> dict:
    """
    Answer questions using both text and images.
    """
    from app.core.multimodal_retriever import retrieve_multimodal
    from app.core.llm import call_gemini_vision, format_context
    
    # Retrieve text + images
    results = retrieve_multimodal(pdf_hash, question, k=5)
    
    text_chunks = results["text_chunks"]
    image_chunks = results["image_chunks"]
    
    if not text_chunks and not image_chunks:
        return {
            "answer": "I couldn't find relevant information.",
            "sources": [],
            "images_used": []
        }
    
    # Format text context
    context = format_context(text_chunks)
    
    # Get image paths
    image_paths = [
        chunk["metadata"]["image_path"] 
        for chunk in image_chunks 
        if chunk["metadata"].get("image_path")
    ]
    
    # Build prompt
    prompt = f"""Context from the textbook:
{context}

Question: {question}

Answer the question based on the text context and the images provided. 
Reference specific elements you see in the images when relevant."""
    
    # Call vision LLM
    if image_paths:
        answer = call_gemini_vision(prompt, image_paths)
    else:
        # Fall back to text-only
        answer = call_groq(QA_SYSTEM_PROMPT, prompt)
    
    return {
        "answer": answer,
        "sources": text_chunks,
        "images_used": image_paths
    }
```

### Phase 7: Update UI to Show Images

**File to modify:** `app/ui/chat.py`

**Add image display (around line 40):**
```python
# After showing the answer
st.markdown(result["answer"])

# NEW: Show images that were used
if result.get("images_used"):
    with st.expander("🖼️ Images analyzed"):
        for img_path in result["images_used"]:
            st.image(img_path, caption=img_path, use_column_width=True)

# Show text sources
if result["sources"]:
    with st.expander("📚 Sources used"):
        # ... existing code
```

---

## 📋 Implementation Checklist

When you're ready to implement, follow this order:

### Week 1: Image Extraction
- [ ] Modify `pdf_processor.py` to extract images
- [ ] Save images to `data/images/{pdf_hash}/`
- [ ] Add `image_path` field to chunks
- [ ] Test: Upload PDF, verify images are saved

### Week 2: Multimodal Embeddings
- [ ] Create `multimodal_embedder.py`
- [ ] Install CLIP: `pip install sentence-transformers`
- [ ] Test embedding text and images
- [ ] Verify embeddings are in same vector space

### Week 3: Vector Store Updates
- [ ] Update `vector_store.py` metadata
- [ ] Store image paths in ChromaDB
- [ ] Test retrieval of image chunks

### Week 4: Multimodal Retrieval
- [ ] Create `multimodal_retriever.py`
- [ ] Implement mixed text+image retrieval
- [ ] Test: Query should return relevant images

### Week 5: Vision LLM Integration
- [ ] Add `call_gemini_vision()` to `llm.py`
- [ ] Test with sample images
- [ ] Handle API errors gracefully

### Week 6: Update Features
- [ ] Add `answer_question_multimodal()` to `qa.py`
- [ ] Update UI to show images
- [ ] Add toggle: "Use multimodal mode"

### Week 7: Testing & Polish
- [ ] Test with engineering textbooks
- [ ] Compare text-only vs multimodal answers
- [ ] Add documentation
- [ ] Update README

---

## 🔧 Dependencies to Add

When implementing, add these to `requirements.txt`:

```txt
# Multimodal RAG additions
clip-by-openai          # CLIP embeddings
pdf2image               # Extract images from PDFs
Pillow                  # Image processing
openai                  # Optional: GPT-4 Vision
```

---

## 💡 Quick Start When Ready

```bash
# 1. Install additional dependencies
pip install clip-by-openai pdf2image Pillow

# 2. Start with Phase 1 (image extraction)
# Modify app/core/pdf_processor.py

# 3. Test incrementally
python test_multimodal.py  # You'll create this

# 4. Gradually add phases 2-7
```

---

## 🎯 Expected Results

**Before Multimodal RAG:**
- Q: "Explain the circuit diagram"
- A: Generic explanation based on caption only

**After Multimodal RAG:**
- Q: "Explain the circuit diagram"
- A: "Looking at the circuit, I can see a transistor (Q1) connected to resistors R1 and R2. The input signal enters through C1..."
- Shows the actual diagram image used

---

## 📚 Further Reading

1. **CLIP Tutorial**: https://github.com/openai/CLIP
2. **LangChain Multimodal**: https://python.langchain.com/docs/tutorials/multimodal_rag/
3. **Gemini Vision API**: https://ai.google.dev/gemini-api/docs/vision
4. **Unstructured.io**: https://unstructured.io/blog/multimodal-rag

---

## ⚠️ Important Notes

1. **Cost**: Vision APIs (GPT-4 Vision, Gemini Vision) cost more than text-only
2. **Speed**: Processing images is slower than text
3. **Storage**: Images take more disk space
4. **Quality**: Works best with clear diagrams, not blurry scans

---

## 🚀 When You're Ready

Come back to this guide when you want to implement multimodal RAG. Everything is documented here with exact file locations and code snippets.

For now, focus on getting the text-only version working perfectly. Multimodal is an enhancement, not a requirement!
