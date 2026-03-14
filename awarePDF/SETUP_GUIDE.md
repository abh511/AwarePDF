# AwarePDF Setup Guide

## Quick Start (Automated)

```bash
cd awarePDF
chmod +x setup.sh
./setup.sh
```

Then edit `.env` and add your API keys, then run:

```bash
source .venv/bin/activate
python run.py
```

## Manual Setup

### 1. Create Virtual Environment

```bash
cd awarePDF
python3 -m venv .venv
source .venv/bin/activate  # On Linux/Mac
# OR
.venv\Scripts\activate  # On Windows
```

### 2. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This will install:
- Streamlit (UI framework)
- ChromaDB (vector database)
- Sentence Transformers (embeddings)
- Docling (PDF processing)
- Groq & Google AI (LLM APIs)
- LangChain (RAG utilities)

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set:

```env
GROQ_API_KEY=your_actual_groq_key_here
GOOGLE_API_KEY=your_google_key_here  # Optional
```

**Get API Keys:**
- Groq (Required): https://console.groq.com - Free tier available
- Google AI (Optional): https://makersuite.google.com/app/apikey - For better summaries

### 4. Create Data Directories

```bash
mkdir -p data/chroma_db data/uploads data/processed
```

### 5. Run the App

```bash
python run.py
```

Or directly:

```bash
streamlit run app/main.py
```

The app will open at http://localhost:8501

## Troubleshooting

### "No module named 'docling'"

```bash
pip install docling
```

### "ChromaDB initialization failed"

Check that `data/chroma_db` directory exists and is writable:

```bash
mkdir -p data/chroma_db
chmod 755 data/chroma_db
```

### "GROQ_API_KEY not set"

Make sure you:
1. Created `.env` file (copy from `.env.example`)
2. Added your actual API key (not the placeholder text)
3. Restarted the app after editing `.env`

### Embedding model download fails

First run needs internet to download the embedding model (~80MB). If it fails:

```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

### Port 8501 already in use

```bash
streamlit run app/main.py --server.port 8502
```

## Testing the Setup

After starting the app:

1. Upload a small PDF (< 5MB for first test)
2. Wait for "✅ Indexed X chunks!" message
3. Try asking: "What is this document about?"
4. Check the Summary tab

If all works, your setup is complete!

## Development Mode

For development with auto-reload:

```bash
streamlit run app/main.py --server.runOnSave true
```

## Updating Dependencies

```bash
source .venv/bin/activate
pip install --upgrade -r requirements.txt
```
