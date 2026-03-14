#!/usr/bin/env python3
"""
Test script to verify AwarePDF setup is correct.
Run this after setup to check if everything is working.
"""

import sys
from pathlib import Path

def test_imports():
    """Test if all required packages can be imported."""
    print("🔍 Testing imports...")
    
    required_packages = [
        ("streamlit", "Streamlit"),
        ("chromadb", "ChromaDB"),
        ("sentence_transformers", "Sentence Transformers"),
        ("groq", "Groq"),
        ("langchain", "LangChain"),
        ("pypdf", "PyPDF"),
        ("dotenv", "python-dotenv"),
        ("rich", "Rich"),
        ("tenacity", "Tenacity"),
    ]
    
    failed = []
    for package, name in required_packages:
        try:
            __import__(package)
            print(f"  ✅ {name}")
        except ImportError as e:
            print(f"  ❌ {name} - {e}")
            failed.append(name)
    
    if failed:
        print(f"\n❌ Missing packages: {', '.join(failed)}")
        print("Run: pip install -r requirements.txt")
        return False
    
    print("✅ All packages imported successfully\n")
    return True


def test_directories():
    """Test if required directories exist."""
    print("🔍 Testing directories...")
    
    required_dirs = [
        "data/chroma_db",
        "data/uploads",
        "data/processed",
    ]
    
    failed = []
    for dir_path in required_dirs:
        path = Path(dir_path)
        if path.exists():
            print(f"  ✅ {dir_path}")
        else:
            print(f"  ❌ {dir_path} - does not exist")
            failed.append(dir_path)
    
    if failed:
        print(f"\n❌ Missing directories: {', '.join(failed)}")
        print("Run: mkdir -p data/chroma_db data/uploads data/processed")
        return False
    
    print("✅ All directories exist\n")
    return True


def test_env_file():
    """Test if .env file exists and has required keys."""
    print("🔍 Testing .env configuration...")
    
    env_path = Path(".env")
    if not env_path.exists():
        print("  ❌ .env file not found")
        print("Run: cp .env.example .env")
        return False
    
    print("  ✅ .env file exists")
    
    # Load and check keys
    from dotenv import load_dotenv
    import os
    
    load_dotenv()
    
    groq_key = os.getenv("GROQ_API_KEY", "")
    google_key = os.getenv("GOOGLE_API_KEY", "")
    
    if not groq_key or groq_key == "your_groq_api_key_here":
        print("  ⚠️  GROQ_API_KEY not set or using placeholder")
        print("     Get a key from: https://console.groq.com")
    else:
        print(f"  ✅ GROQ_API_KEY set ({groq_key[:10]}...)")
    
    if not google_key or google_key == "your_google_api_key_here":
        print("  ℹ️  GOOGLE_API_KEY not set (optional)")
    else:
        print(f"  ✅ GOOGLE_API_KEY set ({google_key[:10]}...)")
    
    print()
    return True


def test_config():
    """Test if config loads correctly."""
    print("🔍 Testing configuration...")
    
    try:
        import config.settings as settings
        
        print(f"  ✅ Chunk size: {settings.CHUNK_SIZE}")
        print(f"  ✅ Chunk overlap: {settings.CHUNK_OVERLAP}")
        print(f"  ✅ Retrieval K: {settings.RETRIEVAL_K}")
        print(f"  ✅ Embedding model: {settings.EMBEDDING_MODEL}")
        print(f"  ✅ ChromaDB path: {settings.CHROMA_PERSIST_DIR}")
        print("✅ Configuration loaded successfully\n")
        return True
    except Exception as e:
        print(f"  ❌ Configuration error: {e}\n")
        return False


def test_vector_store():
    """Test if ChromaDB can initialize."""
    print("🔍 Testing ChromaDB initialization...")
    
    try:
        from app.core.vector_store import initialize_vector_store
        
        result = initialize_vector_store(warmup_embeddings=False)
        
        if result["ready"]:
            print(f"  ✅ ChromaDB initialized")
            print(f"  ✅ Persist directory: {result['persist_directory']}")
            print(f"  ✅ Embedding model: {result['embedding_model']}")
            print(f"  ✅ Collections: {result['collection_count']}")
            print("✅ Vector store working\n")
            return True
        else:
            print(f"  ❌ ChromaDB initialization failed: {result.get('error')}\n")
            return False
    except Exception as e:
        print(f"  ❌ Vector store error: {e}\n")
        return False


def test_embedding_model():
    """Test if embedding model can be loaded."""
    print("🔍 Testing embedding model (this may download ~80MB on first run)...")
    
    try:
        from app.core.embedder import embed_text
        
        test_text = "This is a test sentence."
        embedding = embed_text(test_text)
        
        print(f"  ✅ Embedding generated (dimension: {len(embedding)})")
        print("✅ Embedding model working\n")
        return True
    except Exception as e:
        print(f"  ❌ Embedding error: {e}\n")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("AwarePDF Setup Test")
    print("=" * 60)
    print()
    
    tests = [
        ("Imports", test_imports),
        ("Directories", test_directories),
        ("Environment", test_env_file),
        ("Configuration", test_config),
        ("Vector Store", test_vector_store),
        ("Embedding Model", test_embedding_model),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ {name} test crashed: {e}\n")
            results.append((name, False))
    
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    print()
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Your setup is ready.")
        print("\nNext steps:")
        print("1. Make sure GROQ_API_KEY is set in .env")
        print("2. Run: python run.py")
        print("3. Upload a PDF and start asking questions!")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
