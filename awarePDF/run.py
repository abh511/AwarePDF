# ============================================================
# run.py
# Single command launcher: python run.py
# Run from the awarePDF/ directory with the venv active, or
# use the venv directly: .venv/bin/python run.py
# ============================================================

import subprocess
import sys
import os
from pathlib import Path

# Ensure we're always running from the directory that contains this file
# so that app/main.py resolves correctly regardless of where you call it from.
SCRIPT_DIR = Path(__file__).parent.resolve()
os.chdir(SCRIPT_DIR)


def check_env():
    env_path = SCRIPT_DIR / ".env"
    if not env_path.exists():
        print("⚠️  WARNING: .env file not found!")
        print(f"   Run: cp {SCRIPT_DIR}/.env.example {SCRIPT_DIR}/.env")
        print("   Then fill in your API keys.\n")
    else:
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
        except ImportError:
            pass  # dotenv check is best-effort here

        groq_key = os.getenv("GROQ_API_KEY", "")
        if not groq_key:
            print("⚠️  GROQ_API_KEY is empty in your .env file!")
            print("   Get a free key at https://console.groq.com\n")


def main():
    check_env()
    print(f"🚀 Starting AwarePDF at http://localhost:8501")
    print(f"   Working directory: {SCRIPT_DIR}\n")

    subprocess.run([
        sys.executable, "-m", "streamlit", "run", "app/main.py",
        "--server.maxUploadSize", "200",
        "--server.headless", "false",
    ])


if __name__ == "__main__":
    main()
