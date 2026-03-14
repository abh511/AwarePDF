# AwarePDF - Quick Start Guide

## 🚀 Get Running in 3 Minutes

### Step 1: Setup (One-time)

```bash
cd awarePDF
chmod +x setup.sh
./setup.sh
```

### Step 2: Get API Key

1. Go to https://console.groq.com
2. Sign up (free)
3. Create an API key
4. Copy the key (starts with `gsk_`)

### Step 3: Configure

```bash
nano .env  # or use any text editor
```

Replace `your_groq_api_key_here` with your actual key:

```env
GROQ_API_KEY=gsk_your_actual_key_here
```

Save and exit (Ctrl+X, then Y, then Enter in nano).

### Step 4: Test

```bash
source .venv/bin/activate
python test_setup.py
```

You should see all tests pass ✅

### Step 5: Run

```bash
python run.py
```

Browser opens automatically at http://localhost:8501

### Step 6: Use It

1. Click "Browse files" in sidebar
2. Upload a PDF (textbook, paper, etc.)
3. Wait for "✅ Indexed X chunks!"
4. Ask questions in the chat
5. Try the Summary, Topics, and Key Points tabs

## 🎯 Example Questions to Try

- "What is this document about?"
- "Explain the main concepts"
- "What are the key formulas?"
- "Summarize chapter 3"
- "What topics are covered?"

## ⚡ Tips

- First upload takes longer (downloads embedding model ~80MB)
- Same PDF is never reprocessed (cached)
- Use Summary tab for overview
- Use Topics tab to see structure
- Use Key Points for exam prep
- Chat for specific questions

## 🐛 If Something Goes Wrong

### Setup script fails
```bash
# Manual setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
mkdir -p data/chroma_db data/uploads data/processed
```

### "GROQ_API_KEY not set"
- Check `.env` file exists
- Make sure you replaced the placeholder with real key
- Restart the app

### "ChromaDB initialization failed"
```bash
mkdir -p data/chroma_db
chmod 755 data/chroma_db
```

### Port already in use
```bash
streamlit run app/main.py --server.port 8502
```

## 📚 What's Next?

- Read full README.md for architecture details
- Check SETUP_GUIDE.md for advanced configuration
- See config/settings.py for tuning options
- Try different PDFs (works best with textbooks)

## 🆘 Still Stuck?

Run the diagnostic:
```bash
python test_setup.py
```

This will tell you exactly what's wrong.
