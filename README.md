# AwarePDF

AI textbook assistant for large engineering PDFs (700+ pages). Upload a book, then ask questions with page citations, get whole-book or per-chapter summaries, a topic outline, exam key points, and search inside diagrams.

Everything runs on free, open-weight models: local embeddings and reranking, plus open-weight LLMs served by the free [Groq](https://console.groq.com) API.

## Quick start

```bash
cd awarePDF
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then add your free GROQ_API_KEY
python run.py               # opens http://localhost:8501
```

Get a free API key (no credit card) at https://console.groq.com/keys.

## Features

| Feature | How it works |
|---|---|
| 💬 Ask Questions | Hybrid search, then reranking, then an answer with page citations. Shows the diagrams it used. Handles follow-up questions. |
| 📝 Summary | Whole book: an even sample from the first page to the last. With a focus (e.g. "Chapter 4"): a detailed summary of that part. |
| 🗂️ Topics | Built from the book's real heading outline, in page order. |
| ⭐ Key Points | Exam-oriented points for the whole book or a single topic. |
| 📸 Images | Gallery of every extracted figure. The largest figures are described by a vision model, so their contents become searchable. |

## How it works

```
PDF ─► Docling (40-page batches) ─► section-aware chunks ─► BGE embeddings ─► ChromaDB
   └─► PyMuPDF image extraction ─► vision model descriptions (background) ─┘

Question ─► dense search + BM25 keyword search ─► rank fusion ─► cross-encoder rerank ─► LLM answer
```

- **Parsing:** [Docling](https://github.com/docling-project/docling) handles layout, headings and tables. Page headers and footers are dropped, and every chunk keeps its real page range and section.
- **Chunking:** paragraphs are merged into chunks of about 1,000 characters within a section. Long paragraphs split at sentence boundaries, and large tables split by rows with the header repeated.
- **Diagrams:** text is indexed first, so the book is usable right away. Figures are then described one at a time in the background, at the pace the free API allows, and become searchable as they finish. Progress shows in the sidebar.
- **Caching:** each book is processed once, keyed by file hash. Restarting the app resumes any unfinished diagram descriptions.

### Models

| Role | Model | Where it runs |
|---|---|---|
| Answers, summaries, topics | `openai/gpt-oss-120b` | Groq free API |
| Diagram descriptions | `qwen/qwen3.8-27b` | Groq free API |
| Embeddings | `BAAI/bge-small-en-v1.5` | Local (GPU if available) |
| Reranking | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Local (GPU if available) |

All models are open-weight. To swap one, change `LLM_MODEL` or `VISION_MODEL` in `.env` to any model listed at https://console.groq.com/docs/models.

## Large books: what to expect

Measured on a 1,126-page textbook (CPU parsing, GPU embeddings):

| Step | Time |
|---|---|
| Parse and index text | ~5 min for 1,126 pages (about 3 min for 700). This is a one-time step, and the app is ready afterwards. |
| Describe diagrams | ~20 s each in the background (free-tier limit of 8,000 tokens/min). 150 diagrams take about 50 min. |
| Answer a question | ~5–8 s |

Parsing needs about 6 GB of RAM at peak, since the layout models stay loaded.

Groq's free tier allows 1,000 requests per day per model. Q&A and diagram descriptions use different models, so they never compete for the same quota.

## Configuration

All settings live in `awarePDF/.env` (see `.env.example`). The ones you are most likely to change:

| Setting | Default | Notes |
|---|---|---|
| `GROQ_API_KEY` | (none) | Required. Free key. |
| `ENABLE_OCR` | `False` | Set `True` only for scanned books. Parsing becomes several times slower. |
| `TABLE_MODE` | `fast` | Use `accurate` for table-heavy books. |
| `MAX_IMAGES_TO_DESCRIBE` | `150` | Largest figures first. The rest still appear in the gallery. |
| `ENABLE_IMAGE_EXTRACTION` | `True` | Set `False` to skip figures entirely. |
| `RETRIEVAL_K` | `6` | Number of chunks given to the LLM per question. |
| `LLM_MAX_PROMPT_CHARS` | `16000` | Keeps requests within the free tier's per-minute token limit. |

## Project structure

```
awarePDF/
├── run.py                  # launcher: python run.py
├── requirements.txt
├── .env.example            # copy to .env
├── .streamlit/config.toml  # theme + upload limit
├── config/settings.py      # every setting, read from .env
├── app/
│   ├── main.py             # Streamlit entry point
│   ├── core/
│   │   ├── pdf_processor.py    # Docling parsing in page batches
│   │   ├── chunker.py          # section-aware chunking
│   │   ├── image_extractor.py  # figure extraction + background descriptions
│   │   ├── embedder.py         # BGE embeddings
│   │   ├── vector_store.py     # ChromaDB collections per PDF
│   │   ├── hybrid_search.py    # BM25 + reciprocal rank fusion
│   │   ├── reranker.py         # cross-encoder reranking
│   │   ├── retriever.py        # retrieval pipeline, outline, document sampling
│   │   └── llm.py              # Groq client + prompts
│   ├── features/           # qa, summarizer, topic_extractor, key_points
│   ├── ui/                 # sidebar, chat, features views
│   └── utils/              # logger, file hashing, device selection
├── tests/                  # pytest suite
└── data/                   # generated: uploads, cache, vector DB, images (git-ignored)
```

## Tests

```bash
cd awarePDF
pytest tests/
```

## Troubleshooting

- **"GROQ_API_KEY not set":** add the key to `awarePDF/.env`, then restart.
- **"No text found":** the PDF is scanned. Set `ENABLE_OCR=True`.
- **Slow answers or "rate limit" in the logs:** the free tier allows 8,000 tokens per minute per model. The app retries automatically. Lower `RETRIEVAL_K` or `LLM_MAX_PROMPT_CHARS` if it happens often.
- **Start over for a book:** delete its files under `awarePDF/data/processed/` and the `awarePDF/data/chroma_db/` folder, then upload the book again.
