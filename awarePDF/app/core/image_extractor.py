# ============================================================
# app/core/image_extractor.py
# Extracts images/diagrams from PDF pages using PyMuPDF (fitz)
# and generates text descriptions with an open-weight vision model.
#
# WHY MULTIMODAL?
# Engineering textbooks are full of diagrams, flowcharts, circuit
# diagrams and figures. A text-only RAG system misses all of this.
# Descriptions become searchable chunks; the images are shown in the UI.
#
# PIPELINE:
# 1. During processing, PyMuPDF saves every significant image (fast)
# 2. After the text is indexed, a background thread describes the
#    largest MAX_IMAGES_TO_DESCRIBE images one at a time, paced by the
#    API rate limit, and adds each batch to the index as it goes.
#    The book is usable immediately; diagrams become searchable gradually.
# 3. Descriptions are cached per image, so a restart resumes the work.
# ============================================================

import io
import json
import threading
from pathlib import Path
from typing import Callable

import config.settings as settings
from app.core import llm
from app.utils.logger import get_logger

logger = get_logger(__name__)

_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")
_MANIFEST_FILE = "images.json"
_DESCRIPTIONS_FILE = "descriptions.json"
_DECORATIVE = "DECORATIVE"

_PROMPT = (
    "You are analyzing an image from an engineering/technical textbook (page {page}). "
    "Describe it for a student studying this material. "
    "Diagram: explain what it shows and name the labelled components. "
    "Graph/chart: describe the axes, trends, and key values. "
    "Circuit/flowchart: describe the flow and connections. "
    "Formula: write it out in text. Note/warning/definition box: transcribe it. "
    "If it is purely decorative (logo, photo of a person, cover art), reply only with: DECORATIVE. "
    "Be technical and concise: under 200 words."
)

# pdf_hash -> background worker / (described, total) progress
_workers: dict[str, threading.Thread] = {}
_progress: dict[str, tuple[int, int]] = {}
_workers_lock = threading.Lock()


def _get_image_dir(pdf_hash: str) -> Path:
    """Get or create the image output directory for a specific PDF."""
    img_dir = Path(settings.IMAGE_OUTPUT_DIR) / pdf_hash
    img_dir.mkdir(parents=True, exist_ok=True)
    return img_dir


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default


def extract_images(pdf_path: str, pdf_hash: str) -> list[dict]:
    """
    Save every significant image in the PDF to disk and write a manifest.

    Returns list of dicts with image_path, page_number, width, height.
    """
    import fitz  # PyMuPDF

    img_dir = _get_image_dir(pdf_hash)
    extracted: list[dict] = []
    seen_xrefs: set[int] = set()

    with fitz.open(pdf_path) as doc:
        for page_index in range(doc.page_count):
            page = doc[page_index]
            page_number = page_index + 1
            for img_idx, img_info in enumerate(page.get_images(full=True)):
                xref, width, height = img_info[0], img_info[2], img_info[3]
                # The same xref on many pages is a logo/header graphic
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)

                if min(width, height) < settings.MIN_IMAGE_DIM:
                    continue
                if max(width, height) / max(1, min(width, height)) > 8:
                    continue  # horizontal/vertical rules and borders

                try:
                    base_image = doc.extract_image(xref)
                except Exception:
                    logger.debug("Could not extract image xref %s on page %s", xref, page_number)
                    continue
                if not base_image or len(base_image.get("image", b"")) < settings.MIN_IMAGE_BYTES:
                    continue

                ext = base_image.get("ext", "png").lower()
                stem = f"page_{page_number}_img_{img_idx}"
                try:
                    if ext in ("png", "jpg", "jpeg"):
                        img_path = img_dir / f"{stem}.{ext}"
                        img_path.write_bytes(base_image["image"])
                    else:
                        # JPX/JBIG2/CMYK etc. are not browser-friendly: convert to PNG
                        pix = fitz.Pixmap(doc, xref)
                        if pix.n - pix.alpha >= 4:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        img_path = img_dir / f"{stem}.png"
                        pix.save(str(img_path))
                except Exception:
                    logger.debug("Failed to save image xref %s on page %s", xref, page_number)
                    continue

                extracted.append({
                    "image_path": str(img_path),
                    "page_number": page_number,
                    "width": width,
                    "height": height,
                })

    (img_dir / _MANIFEST_FILE).write_text(json.dumps(extracted), encoding="utf-8")
    logger.info("Extracted %s significant images from %s", len(extracted), pdf_path)
    return extracted


def _to_jpeg(image_path: str, max_dim: int = 1024) -> bytes:
    """Downscale and re-encode an image to keep vision requests small."""
    from PIL import Image

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()


def _images_to_describe(pdf_hash: str) -> list[dict]:
    """The largest images (diagrams, not icons), capped at MAX_IMAGES_TO_DESCRIBE."""
    manifest = _read_json(_get_image_dir(pdf_hash) / _MANIFEST_FILE, [])
    manifest.sort(key=lambda i: i["width"] * i["height"], reverse=True)
    return manifest[:settings.MAX_IMAGES_TO_DESCRIBE]


def _to_chunk(image: dict, description: str) -> dict:
    return {
        "id": f"img_{Path(image['image_path']).name}",
        "text": description,
        "page_number": image["page_number"],
        "page_end": image["page_number"],
        "content_type": "image_description",
        "image_path": image["image_path"],
    }


def describe_images(pdf_hash: str, on_batch: Callable[[list[dict]], None], batch_size: int = 5) -> bool:
    """
    Describe pending images one at a time, calling on_batch with new chunks.

    Already-cached descriptions are replayed first (on_batch must be idempotent).
    Returns True when every image was handled; failed ones are retried next run.
    """
    images = _images_to_describe(pdf_hash)
    cache_path = _get_image_dir(pdf_hash) / _DESCRIPTIONS_FILE
    descriptions: dict[str, str] = _read_json(cache_path, {})

    def name(image: dict) -> str:
        return Path(image["image_path"]).name

    cached = [_to_chunk(i, descriptions[name(i)]) for i in images if descriptions.get(name(i))]
    if cached:
        on_batch(cached)

    pending = [i for i in images if name(i) not in descriptions]
    done = len(images) - len(pending)
    _progress[pdf_hash] = (done, len(images))
    logger.info("Describing %s images in background (%s already cached)", len(pending), done)

    batch: list[dict] = []
    failures = 0
    for image in pending:
        try:
            description = llm.describe_image(
                _to_jpeg(image["image_path"]),
                _PROMPT.format(page=image["page_number"]),
                max_tokens=400,
            )
        except Exception as exc:
            failures += 1
            logger.warning("Vision model failed for %s: %s", name(image), exc)
            continue

        if description.strip().upper().startswith(_DECORATIVE):
            description = ""
        descriptions[name(image)] = description
        cache_path.write_text(json.dumps(descriptions), encoding="utf-8")
        if description:
            batch.append(_to_chunk(image, description))

        done += 1
        _progress[pdf_hash] = (done, len(images))
        if len(batch) >= batch_size:
            on_batch(batch)
            batch = []

    if batch:
        on_batch(batch)
    return failures == 0


def start_background_description(pdf_hash: str, on_batch: Callable[[list[dict]], None],
                                 on_finished: Callable[[], None]) -> None:
    """Start describing images in a daemon thread (no-op if already running)."""
    if not settings.ENABLE_IMAGE_EXTRACTION or not settings.GROQ_API_KEY:
        return

    def run() -> None:
        try:
            if describe_images(pdf_hash, on_batch):
                on_finished()
        except Exception:
            logger.exception("Background image description failed for %s", pdf_hash[:12])

    with _workers_lock:
        worker = _workers.get(pdf_hash)
        if worker and worker.is_alive():
            return
        worker = threading.Thread(target=run, name=f"describe-{pdf_hash[:8]}", daemon=True)
        _workers[pdf_hash] = worker
        worker.start()


def description_progress(pdf_hash: str) -> tuple[int, int] | None:
    """(described, total) while a background worker is running, else None."""
    worker = _workers.get(pdf_hash)
    if worker and worker.is_alive():
        return _progress.get(pdf_hash, (0, 0))
    return None


def get_image_paths_for_pdf(pdf_hash: str) -> list[dict]:
    """Returns list of all extracted images for a PDF (for UI gallery), in page order."""
    img_dir = Path(settings.IMAGE_OUTPUT_DIR) / pdf_hash
    if not img_dir.exists():
        return []

    images = []
    for img_path in img_dir.iterdir():
        if img_path.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        parts = img_path.stem.split("_")
        page_num = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
        images.append({
            "path": str(img_path),
            "page_number": page_num,
            "filename": img_path.name,
        })

    images.sort(key=lambda i: (i["page_number"], i["filename"]))
    return images
