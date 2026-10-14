# ============================================================
# app/server.py
# Web API + static frontend (web/) for deployment.
# Wraps the same pipeline the Streamlit UI uses.
#
#   uvicorn app.server:app --host 0.0.0.0 --port 8000
# ============================================================

import hashlib
import hmac
import json
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config.settings as settings
from app.core.image_extractor import (
    description_progress, get_image_paths_for_pdf, start_background_description,
)
from app.core.pdf_processor import get_page_count, process_pdf
from app.core.vector_store import (
    add_image_chunks, delete_collection, get_chunk_count, images_pending,
    index_chunks, is_indexed, mark_images_done,
)
from app.features.key_points import extract_key_points
from app.features.qa import answer_question
from app.features.summarizer import summarize_pdf
from app.features.topic_extractor import extract_topics
from app.utils.file_handler import get_pdf_hash
from app.utils.logger import get_logger

logger = get_logger(__name__)

WEB_DIR = settings.BASE_DIR / "web"
LIBRARY_FILE = Path(settings.DATA_DIR) / "library.json"
AUTH_COOKIE = "awarepdf_session"

# ------------------------------------------------------------
# Library: every uploaded book, keyed by file hash
# ------------------------------------------------------------

_library_lock = threading.Lock()


def _load_library() -> dict[str, dict]:
    try:
        return json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def _save_library(library: dict[str, dict]) -> None:
    tmp = LIBRARY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(library, indent=2), encoding="utf-8")
    tmp.replace(LIBRARY_FILE)


def _get_book(pdf_hash: str) -> dict:
    book = _load_library().get(pdf_hash)
    if not book:
        raise HTTPException(404, "Book not found")
    return book


def _backfill_library() -> None:
    """Register PDFs that were processed before the library existed (e.g. via Streamlit)."""
    with _library_lock:
        library = _load_library()
        known = {b["path"] for b in library.values()}
        for pdf in Path(settings.UPLOAD_DIR).glob("*.pdf"):
            if str(pdf) in known:
                continue
            pdf_hash = get_pdf_hash(str(pdf))
            if pdf_hash in library or not is_indexed(pdf_hash):
                continue
            try:
                pages = get_page_count(pdf)
            except Exception:
                continue
            library[pdf_hash] = {
                "name": pdf.name, "path": str(pdf), "pages": pages,
                "size_mb": round(pdf.stat().st_size / 2**20, 1), "added": pdf.stat().st_mtime,
            }
        _save_library(library)


# ------------------------------------------------------------
# Processing jobs: one book parses at a time (Docling is memory-heavy)
# ------------------------------------------------------------

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="process")
_jobs: dict[str, dict] = {}


def _start_image_descriptions(pdf_hash: str) -> None:
    if images_pending(pdf_hash):
        start_background_description(
            pdf_hash,
            on_batch=lambda chunks: add_image_chunks(pdf_hash, chunks),
            on_finished=lambda: mark_images_done(pdf_hash),
        )


def _process_job(pdf_hash: str, file_path: str) -> None:
    job = _jobs[pdf_hash]
    job.update(status="processing", progress=0.0, message="Starting", started=time.time())

    def update(fraction: float, message: str) -> None:
        job.update(progress=min(1.0, fraction), message=message)

    try:
        chunks = process_pdf(file_path, progress_callback=lambda p, m: update(0.85 * p, m))
        try:
            index_chunks(pdf_hash, chunks, progress_callback=lambda p, m: update(0.85 + 0.15 * p, m))
        except Exception:
            delete_collection(pdf_hash)
            raise
    except Exception as exc:
        logger.exception("Processing failed for %s", pdf_hash[:12])
        job.update(status="error", message=str(exc) or "Processing failed")
        return

    job.update(status="ready", progress=1.0, message="Complete")
    _start_image_descriptions(pdf_hash)


def _book_status(pdf_hash: str, book: dict) -> dict:
    job = _jobs.get(pdf_hash)
    if is_indexed(pdf_hash):
        status = {"status": "ready", "progress": 1.0, "message": "Ready"}
    elif job:
        status = {k: job[k] for k in ("status", "progress", "message")}
    else:
        status = {"status": "error", "progress": 0.0, "message": "Processing was interrupted. Re-upload to retry."}

    figures = description_progress(pdf_hash)
    return {
        "id": pdf_hash,
        "name": book["name"],
        "pages": book.get("pages"),
        "size_mb": book.get("size_mb"),
        "added": book.get("added"),
        **status,
        "chunks": get_chunk_count(pdf_hash) if status["status"] == "ready" else 0,
        "figures_described": {"done": figures[0], "total": figures[1]} if figures else None,
    }


# ------------------------------------------------------------
# App
# ------------------------------------------------------------

@asynccontextmanager
async def lifespan(_: FastAPI):
    _backfill_library()
    for pdf_hash in _load_library():
        if is_indexed(pdf_hash):
            _start_image_descriptions(pdf_hash)
    yield
    _executor.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title=settings.APP_TITLE, lifespan=lifespan)


def _session_token() -> str:
    return hmac.new(settings.APP_PASSWORD.encode(), b"awarepdf-session", hashlib.sha256).hexdigest()


@app.middleware("http")
async def require_password(request: Request, call_next):
    """When APP_PASSWORD is set, every /api route except config and login needs the session cookie."""
    path = request.url.path
    if (settings.APP_PASSWORD and path.startswith("/api/")
            and path not in ("/api/config", "/api/login")
            and not hmac.compare_digest(request.cookies.get(AUTH_COOKIE, ""), _session_token())):
        return JSONResponse({"detail": "Login required"}, status_code=401)
    return await call_next(request)


class LoginRequest(BaseModel):
    password: str


@app.post("/api/login")
def login(body: LoginRequest, response: Response):
    if not settings.APP_PASSWORD or not hmac.compare_digest(body.password, settings.APP_PASSWORD):
        raise HTTPException(401, "Wrong password")
    response.set_cookie(AUTH_COOKIE, _session_token(), httponly=True, samesite="strict",
                        max_age=60 * 60 * 24 * 30)
    return {"ok": True}


@app.get("/api/config")
def get_config(request: Request):
    return {
        "title": settings.APP_TITLE,
        "max_upload_mb": settings.MAX_UPLOAD_SIZE_MB,
        "llm_ready": bool(settings.GROQ_API_KEY),
        "auth_required": bool(settings.APP_PASSWORD),
        "authenticated": (not settings.APP_PASSWORD
                          or hmac.compare_digest(request.cookies.get(AUTH_COOKIE, ""), _session_token())),
    }


@app.get("/api/books")
def list_books():
    library = _load_library()
    books = [_book_status(h, b) for h, b in library.items()]
    books.sort(key=lambda b: b.get("added") or 0, reverse=True)
    return books


@app.post("/api/books")
def upload_book(file: UploadFile = File(...)):
    name = Path(file.filename or "document.pdf").name
    if not name.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    # Stream to a temp file while hashing, enforcing the size limit
    limit = settings.MAX_UPLOAD_SIZE_MB * 2**20
    tmp_path = Path(settings.UPLOAD_DIR) / f".upload-{threading.get_ident()}-{time.time_ns()}.part"
    hasher, size = hashlib.sha256(), 0
    try:
        with open(tmp_path, "wb") as out:
            while chunk := file.file.read(2**20):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"File is larger than {settings.MAX_UPLOAD_SIZE_MB} MB")
                hasher.update(chunk)
                out.write(chunk)
        pdf_hash = hasher.hexdigest()
        final_path = Path(settings.UPLOAD_DIR) / f"{pdf_hash[:16]}.pdf"
        shutil.move(tmp_path, final_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    try:
        pages = get_page_count(final_path)
    except Exception as exc:
        final_path.unlink(missing_ok=True)
        raise HTTPException(400, str(exc))

    with _library_lock:
        library = _load_library()
        library[pdf_hash] = {
            "name": name, "path": str(final_path), "pages": pages,
            "size_mb": round(size / 2**20, 1), "added": time.time(),
        }
        _save_library(library)

    job = _jobs.get(pdf_hash)
    if not is_indexed(pdf_hash) and not (job and job["status"] in ("queued", "processing")):
        _jobs[pdf_hash] = {"status": "queued", "progress": 0.0, "message": "Waiting in queue"}
        _executor.submit(_process_job, pdf_hash, str(final_path))
    return _book_status(pdf_hash, library[pdf_hash])


@app.get("/api/books/{pdf_hash}")
def get_book(pdf_hash: str):
    return _book_status(pdf_hash, _get_book(pdf_hash))


@app.delete("/api/books/{pdf_hash}")
def delete_book(pdf_hash: str):
    job = _jobs.get(pdf_hash)
    if job and job["status"] in ("queued", "processing"):
        raise HTTPException(409, "This book is still processing")
    with _library_lock:
        library = _load_library()
        book = library.pop(pdf_hash, None)
        if not book:
            raise HTTPException(404, "Book not found")
        _save_library(library)
    delete_collection(pdf_hash)
    Path(book["path"]).unlink(missing_ok=True)
    _jobs.pop(pdf_hash, None)
    return {"ok": True}


@app.get("/api/books/{pdf_hash}/file")
def get_book_file(pdf_hash: str):
    book = _get_book(pdf_hash)
    return FileResponse(book["path"], media_type="application/pdf",
                        headers={"Content-Disposition": "inline", "Cache-Control": "private, max-age=86400"})


def _require_ready(pdf_hash: str) -> None:
    _get_book(pdf_hash)
    if not is_indexed(pdf_hash):
        raise HTTPException(409, "This book is still being processed")
    if not settings.GROQ_API_KEY:
        raise HTTPException(503, "GROQ_API_KEY is not configured on the server")


def _image_url(pdf_hash: str, image_path: str) -> str:
    return f"/api/books/{pdf_hash}/images/{Path(image_path).name}" if image_path else ""


class ChatMessage(BaseModel):
    role: str
    content: str = Field(max_length=20000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = []


@app.post("/api/books/{pdf_hash}/ask")
def ask(pdf_hash: str, body: AskRequest):
    _require_ready(pdf_hash)
    history = [m.model_dump() for m in body.history[-8:] if m.role in ("user", "assistant")]
    try:
        result = answer_question(pdf_hash, body.question.strip(), chat_history=history)
    except Exception as exc:
        logger.exception("Q&A failed")
        raise HTTPException(502, f"Could not answer: {exc}")
    for src in result["sources"]:
        src["image_url"] = _image_url(pdf_hash, src.pop("image_path", ""))
    return result


class GenerateRequest(BaseModel):
    focus: str | None = Field(default=None, max_length=300)


_GENERATORS = {
    "summary": lambda h, focus: summarize_pdf(h, focus),
    "topics": lambda h, _: extract_topics(h),
    "keypoints": lambda h, focus: extract_key_points(h, focus),
}


@app.post("/api/books/{pdf_hash}/{kind}")
def generate(pdf_hash: str, kind: str, body: GenerateRequest):
    if kind not in _GENERATORS:
        raise HTTPException(404, "Unknown feature")
    _require_ready(pdf_hash)
    focus = (body.focus or "").strip() or None
    try:
        return {"content": _GENERATORS[kind](pdf_hash, focus)}
    except Exception as exc:
        logger.exception("%s failed", kind)
        raise HTTPException(502, f"Generation failed: {exc}")


@app.get("/api/books/{pdf_hash}/images")
def list_images(pdf_hash: str):
    _get_book(pdf_hash)
    return [
        {"url": _image_url(pdf_hash, img["path"]), "page": img["page_number"]}
        for img in get_image_paths_for_pdf(pdf_hash)
    ]


@app.get("/api/books/{pdf_hash}/images/{filename}")
def get_image(pdf_hash: str, filename: str):
    _get_book(pdf_hash)
    image_dir = (Path(settings.IMAGE_OUTPUT_DIR) / pdf_hash).resolve()
    path = (image_dir / Path(filename).name).resolve()
    if path.parent != image_dir or not path.is_file():
        raise HTTPException(404, "Image not found")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
