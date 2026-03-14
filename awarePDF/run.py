# ============================================================
# run.py
# Single command launcher: python run.py
# ============================================================

import subprocess
import sys
from pathlib import Path


def check_env():
    if not Path(".env").exists():
        print("⚠️  WARNING: .env file not found!")
        print("   Run: cp .env.example .env")
        print("   Then fill in your API keys.\n")
    else:
        from dotenv import load_dotenv
        import os
        load_dotenv()
        if not os.getenv("GROQ_API_KEY"):
            print("⚠️  GROQ_API_KEY is empty in your .env file!")
            print("   Get a free key at https://console.groq.com\n")


def main():
    check_env()
    print("🚀 Starting AwarePDF at http://localhost:8501")
    subprocess.run([
        sys.executable, "-m", "streamlit", "run", "app/main.py",
        "--server.maxUploadSize", "50",
        "--server.headless", "false",
    ])


if __name__ == "__main__":
    main()
