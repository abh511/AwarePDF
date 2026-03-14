# AwarePDF

RAG-based PDF intelligence app for engineering textbooks with support for Q&A, summarization, key points extraction, and topic listing.

## Project Layout

- `app/core`: PDF processing, chunking, embedding, retrieval, vector DB logic
- `app/features`: Task-specific RAG flows (Q&A, summary, topics, key points)
- `app/ui`: Streamlit interface components
- `config`: Environment-aware settings
- `data/chroma_db`: Persistent ChromaDB data

## Full Setup (Including ChromaDB Activation)

1. Clone and enter the project

```bash
git clone <your-repo-url>
cd awarePDF
```

2. Create and activate virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set:

- `GROQ_API_KEY`
- Optional: `GOOGLE_API_KEY`
- Optional tuning: `EMBEDDING_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `RETRIEVAL_K`
- Optional path overrides: `CHROMA_PERSIST_DIR`, `UPLOAD_DIR`, `PROCESSED_DIR`

5. Start the app

```bash
python run.py
```

6. Activate and verify ChromaDB

- Upload any PDF from the sidebar.
- On first upload, AwarePDF will:
	- parse and chunk the document,
	- create the Chroma collection by PDF hash,
	- store embeddings in `data/chroma_db` (or `CHROMA_PERSIST_DIR`).
- Re-uploading the same PDF should show `Already indexed (...)`.

7. Manual verification (optional)

```bash
ls -la data/chroma_db
```

You should see Chroma persistence files/directories after first indexing.

## Common Issues

- `Vector DB init failed`: verify `CHROMA_PERSIST_DIR` is writable.
- Embedding model download errors: ensure internet access on first run for sentence-transformers model pull.
- Missing API keys: set `GROQ_API_KEY` in `.env`.

## Dev Notes

- Vector store settings are read from `config/settings.py`.
- ChromaDB client and embedding function are initialized lazily.
- Processed PDF cache is stored in `PROCESSED_DIR`.
