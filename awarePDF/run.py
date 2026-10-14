# ============================================================
# run.py
# Single command launcher (works from any directory):
#   python run.py              web app at http://localhost:8000
#   python run.py --streamlit  the original Streamlit UI
# ============================================================

import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
os.chdir(SCRIPT_DIR)  # so Streamlit picks up .streamlit/config.toml

# Re-launch with the project's virtual environment if run with another Python
VENV_PYTHON = SCRIPT_DIR / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
if VENV_PYTHON.exists() and Path(sys.prefix).resolve() != (SCRIPT_DIR / ".venv").resolve():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])


def main():
    try:
        import dotenv, fastapi, uvicorn  # noqa: F401
    except ImportError:
        print("❌ Dependencies are not installed. Run:")
        print(f"   cd {SCRIPT_DIR}")
        print("   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt")
        sys.exit(1)

    if not (SCRIPT_DIR / ".env").exists():
        print("⚠️  .env file not found!")
        print(f"   Run: cp {SCRIPT_DIR}/.env.example {SCRIPT_DIR}/.env")
        print("   Then add your free GROQ_API_KEY from https://console.groq.com\n")

    sys.path.insert(0, str(SCRIPT_DIR))
    from config.settings import GROQ_API_KEY, MAX_UPLOAD_SIZE_MB

    if not GROQ_API_KEY:
        print("⚠️  GROQ_API_KEY is empty. Get a free key at https://console.groq.com\n")

    if "--streamlit" in sys.argv:
        print("🚀 Starting AwarePDF (Streamlit) at http://localhost:8501\n")
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", "app/main.py",
            "--server.maxUploadSize", str(MAX_UPLOAD_SIZE_MB),
        ])
        return

    port = os.getenv("PORT", "8000")
    print(f"🚀 Starting AwarePDF at http://localhost:{port}\n")
    subprocess.run([sys.executable, "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", port])


if __name__ == "__main__":
    main()
