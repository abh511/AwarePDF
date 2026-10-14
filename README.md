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
python run.py               # opens http://localhost:8000
```

`python run.py --streamlit` starts the original Streamlit UI instead (port 8501). Both share the same data.

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

## Web app

The web UI (`awarePDF/web/`) is a single page served by a FastAPI backend (`awarePDF/app/server.py`). It has no build step.

- **Library:** every uploaded book stays available. Drag a PDF anywhere on the page to add one. Processing runs on the server with live progress, so you can close the tab.
- **Clickable citations:** page references in answers, like (Page 12), open that page in a resizable PDF panel next to the chat.
- **Answers:** rendered with formulas (KaTeX), tables and code. Each answer shows the figures it used and its source passages.
- **Study tools:** summary, topics and key points. Results are kept per book, and you can copy them or download them as Markdown.
- **Figures:** a gallery you can filter by page range, with a lightbox (arrow keys move between figures).
- Light and dark themes, a mobile layout, and keyboard shortcuts (<kbd>/</kbd> focuses the question box, <kbd>Esc</kbd> closes panels).

## Deploy

The app is one container. It needs about **6 GB of RAM** while parsing a large book (Docling's layout models) and a **persistent disk** for `/app/data`. That disk holds uploads, the vector index, extracted figures and the downloaded models.

```bash
cd awarePDF
docker build -t awarepdf .
docker run -d -p 8000:8000 \
  -e GROQ_API_KEY=your_key \
  -e APP_PASSWORD=choose-a-password \
  -v awarepdf-data:/app/data \
  awarepdf
```

- **Set `APP_PASSWORD` on any public deployment.** Without it, anyone with the URL can upload books and use up your Groq quota. With it, visitors see a login screen, and every API route needs the session cookie.
- The container listens on `$PORT` (default 8000), so it works as-is on hosts that set `PORT`, such as Render, Railway, Fly.io or a VPS behind a reverse proxy.
- Run a **single worker**. Processing jobs and progress are held in memory.
- If you use a reverse proxy, allow request bodies up to `MAX_UPLOAD_SIZE_MB` (nginx: `client_max_body_size 200m;`).
- Free tiers with 512 MB to 1 GB of RAM can't parse large books. Use an instance with at least 8 GB.

Without Docker: `pip install -r requirements.txt`, then `uvicorn app.server:app --host 0.0.0.0 --port 8000` from `awarePDF/`.

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
| `APP_PASSWORD` | (none) | Web app login. Set it before deploying publicly. |
| `RETRIEVAL_K` | `6` | Number of chunks given to the LLM per question. |
| `LLM_MAX_PROMPT_CHARS` | `16000` | Keeps requests within the free tier's per-minute token limit. |

## Project structure

```
awarePDF/
├── run.py                  # launcher: python run.py (--streamlit for the old UI)
├── Dockerfile              # one-container deployment
├── requirements.txt
├── .env.example            # copy to .env
├── .streamlit/config.toml  # theme + upload limit
├── config/settings.py      # every setting, read from .env
├── app/
│   ├── server.py           # FastAPI backend for the web UI
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
├── web/                    # web UI: index.html, styles.css, app.js
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
