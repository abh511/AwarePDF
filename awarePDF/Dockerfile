# AwarePDF web app: one container serves the API and the frontend.
#   docker build -t awarepdf .
#   docker run -p 8000:8000 -e GROQ_API_KEY=... -e APP_PASSWORD=... -v awarepdf-data:/app/data awarepdf
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/data/hf-cache \
    PORT=8000

# Docling's layout models need these system libraries
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only PyTorch keeps the image a few GB smaller; drop the index URL on a GPU host
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY config ./config
COPY web ./web

# Uploads, the vector index, extracted figures and downloaded models all live here
VOLUME /app/data
EXPOSE 8000

# Keep a single worker: processing jobs and progress live in memory
CMD ["sh", "-c", "uvicorn app.server:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
