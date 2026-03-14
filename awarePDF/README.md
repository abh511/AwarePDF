# AwarePDF

RAG-based PDF intelligence app for engineering textbooks with support for Q&A, summarization, key points extraction, and topic listing.

## 🚀 Quick Start

```bash
cd awarePDF
chmod +x setup.sh
./setup.sh
```

Edit `.env` and add your API keys, then:

```bash
source .venv/bin/activate
python run.py
```

Visit http://localhost:8501

## 📋 What Was Fixed

### Code Issues Fixed:
1. ✅ Fixed `chunk_documents` → `chunk_with_metadata` function name mismatch
2. ✅ Fixed progress callback parameter order in `sidebar.py`
3. ✅ Removed invalid `filter_type` parameter from `similarity_search`
4. ✅ Fixed metadata field names (`section_heading` → `section`)
5. ✅ Implemented missing `embedder.py` module
6. ✅ Added missing dependencies (`google-generativeai`, `tenacity`, `rich`)

### Setup Issues Fixed:
1. ✅ Created `.env` file from template
2. ✅ Added automated setup script (`setup.sh`)
3. ✅ Created comprehensive setup guide (`SETUP_GUIDE.md`)
4. ✅ Added setup verification script (`test_setup.py`)
5. ✅ Ensured all data directories are created automatically

## 📁 Project Layout

```
awarePDF/
├── app/
│   ├── core/           # Core RAG components
│   │   ├── pdf_processor.py   # Docling-based PDF parsing
│   │   ├── chunker.py          # Text chunking logic
│   │   ├── embedder.py         # Sentence transformer embeddings
│   │   ├── vector_store.py     # ChromaDB operations
│   │   ├── retriever.py        # Semantic search + reranking
│   │   └── llm.py              # Groq & Gemini API clients
│   ├── features/       # Task-specific RAG flows
│   │   ├── qa.py               # Question answering
│   │   ├── summarizer.py       # Document summarization
│   │   ├── key_points.py       # Key points extraction
│   │   └── topic_extractor.py  # Topic structure analysis
│   ├── ui/             # Streamlit interface
│   │   ├── sidebar.py          # File upload & processing
│   │   ├── chat.py             # Q&A chat interface
│   │   └── dashboard.py        # Summary/Topics/Key Points tabs
│   ├── utils/          # Utilities
│   │   ├── file_handler.py     # File operations & hashing
│   │   └── logger.py           # Rich logging setup
│   └── main.py         # App entry point
├── config/
│   └── settings.py     # Environment configuration
├── data/
│   ├── chroma_db/      # Persistent vector database
│   ├── uploads/        # Temporary uploaded PDFs
│   └── processed/      # Cached processed chunks
├── tests/              # Unit tests
├── .env                # Environment variables (create from .env.example)
├── requirements.txt    # Python dependencies
├── run.py              # Launch script
├── setup.sh            # Automated setup script
└── test_setup.py       # Setup verification script
```

## 🔧 Manual Setup (If Automated Fails)

### 1. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# OR
.venv\Scripts\activate     # Windows
```

### 2. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set:
- `GROQ_API_KEY` (required) - Get from https://console.groq.com
- `GOOGLE_API_KEY` (optional) - For better summaries

### 4. Create Data Directories

```bash
mkdir -p data/chroma_db data/uploads data/processed
```

### 5. Test Setup

```bash
python test_setup.py
```

### 6. Run the App

```bash
python run.py
```

## 🧪 Verify Installation

Run the test script to check everything is working:

```bash
python test_setup.py
```

This will verify:
- ✅ All Python packages are installed
- ✅ Data directories exist
- ✅ .env file is configured
- ✅ ChromaDB initializes correctly
- ✅ Embedding model loads successfully

## 📚 How It Works

### Architecture

1. **PDF Processing** (Docling)
   - Extracts text, tables, figures, headings
   - Preserves document structure
   - Caches results by file hash

2. **Chunking** (LangChain)
   - Splits long text into 512-char chunks
   - 50-char overlap for context continuity
   - Keeps tables/headings intact

3. **Embedding** (Sentence Transformers)
   - Converts text to vectors using `all-MiniLM-L6-v2`
   - 384-dimensional embeddings
   - Fast on CPU

4. **Vector Storage** (ChromaDB)
   - Persistent local database
   - One collection per PDF (by hash)
   - Automatic deduplication

5. **Retrieval** (Two-stage)
   - Stage 1: Vector similarity search (fast, broad)
   - Stage 2: Cross-encoder reranking (slow, precise)
   - Returns top-k most relevant chunks

6. **Generation** (Groq + Gemini)
   - Groq (Llama 3.3 70B): Q&A, key points, topics
   - Gemini 1.5 Flash: Summarization (large context)

## 🎯 Features

### 💬 Question Answering
- Ask natural language questions
- Get answers with page citations
- See source chunks used

### 📝 Summarization
- Comprehensive document summaries
- Uses Gemini's 1M token context window
- Organized by sections

### 🗂️ Topic Extraction
- Automatic topic structure analysis
- Hierarchical topic/subtopic lists
- Based on headings and content

### ⭐ Key Points
- Extract important concepts
- Filter by specific topics
- Perfect for exam prep

## 🔑 API Keys

### Groq (Required)
1. Visit https://console.groq.com
2. Sign up (free tier available)
3. Create API key
4. Add to `.env`: `GROQ_API_KEY=gsk_...`

### Google AI (Optional)
1. Visit https://makersuite.google.com/app/apikey
2. Create API key
3. Add to `.env`: `GOOGLE_API_KEY=AIza...`

Without Google AI, summaries will use Groq (works fine, just smaller context window).

## 🐛 Troubleshooting

### "No module named 'X'"
```bash
pip install -r requirements.txt
```

### "ChromaDB initialization failed"
```bash
mkdir -p data/chroma_db
chmod 755 data/chroma_db
```

### "GROQ_API_KEY not set"
1. Check `.env` file exists
2. Verify key is not placeholder text
3. Restart app after editing `.env`

### Embedding model download fails
First run downloads ~80MB model. Ensure internet connection:
```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

### Port 8501 already in use
```bash
streamlit run app/main.py --server.port 8502
```

## 📊 Performance Tips

- First PDF upload takes longer (downloads embedding model)
- Same PDF is never reprocessed (cached by hash)
- Larger PDFs (>100 pages) may take 1-2 minutes to process
- Reranking improves accuracy but adds ~1s per query

## 🧪 Testing

Run unit tests:
```bash
pytest tests/
```

Test specific module:
```bash
pytest tests/test_chunker.py -v
```

## 🔄 Updating

```bash
source .venv/bin/activate
git pull
pip install --upgrade -r requirements.txt
```

## 📝 Configuration

Edit `.env` to customize:

```env
# Models
EMBEDDING_MODEL=all-MiniLM-L6-v2
GROQ_MODEL=llama-3.3-70b-versatile
GEMINI_MODEL=gemini-1.5-flash

# RAG Settings
CHUNK_SIZE=512
CHUNK_OVERLAP=50
RETRIEVAL_K=5

# Storage Paths
CHROMA_PERSIST_DIR=./data/chroma_db
UPLOAD_DIR=./data/uploads
PROCESSED_DIR=./data/processed

# App Settings
MAX_UPLOAD_SIZE_MB=50
```

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature-name`
3. Make changes and test: `pytest tests/`
4. Commit: `git commit -m "Add feature"`
5. Push: `git push origin feature-name`
6. Create Pull Request

## 📄 License

See LICENSE file for details.

## 🙏 Acknowledgments

- Docling for PDF processing
- ChromaDB for vector storage
- Sentence Transformers for embeddings
- Groq for fast LLM inference
- Google for Gemini API
- Streamlit for the UI framework
