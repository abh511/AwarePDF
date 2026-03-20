# ============================================================
# app/core/image_extractor.py
# Extracts images/diagrams from PDF pages using PyMuPDF (fitz)
# and generates text descriptions using Gemini Vision API.
#
# WHY MULTIMODAL?
# Engineering textbooks are full of diagrams, flowcharts, circuit
# diagrams, color-coded boxes, and figures. A text-only RAG system
# misses all of this. By extracting images, describing them with
# a vision LLM, and storing those descriptions as searchable chunks,
# we can answer questions about visual content too.
#
# PIPELINE:
# 1. PyMuPDF extracts all images from every page
# 2. Filter out tiny icons/decorations (< MIN_IMAGE_SIZE bytes)
# 3. Gemini Vision describes each significant image (with rate-limit handling)
# 4. Descriptions become chunks in ChromaDB (searchable)
# 5. Original images saved to disk for UI display
# ============================================================

import logging
import time
from pathlib import Path
from typing import Callable

import config.settings as settings

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float, str], None]


def _get_image_dir(pdf_hash: str) -> Path:
    """Get or create the image output directory for a specific PDF."""
    img_dir = Path(settings.IMAGE_OUTPUT_DIR) / pdf_hash
    img_dir.mkdir(parents=True, exist_ok=True)
    return img_dir


def _extract_images_from_pdf(pdf_path: str, pdf_hash: str) -> list[dict]:
    """
    Extract all significant images from a PDF using PyMuPDF.

    Returns list of dicts with image_path, page_number, image_index,
    width, height, image_bytes, ext.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning(
            "PyMuPDF (fitz) not installed. Install with: pip install PyMuPDF. "
            "Skipping image extraction."
        )
        return []

    img_dir = _get_image_dir(pdf_hash)
    extracted = []
    min_size = settings.MIN_IMAGE_SIZE

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        logger.exception("Failed to open PDF for image extraction: %s", pdf_path)
        return []

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            try:
                image_list = page.get_images(full=True)
            except Exception:
                logger.debug("Could not get images from page %s", page_num + 1)
                continue

            for img_idx, img_info in enumerate(image_list):
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                except Exception:
                    logger.debug("Could not extract image xref %s on page %s", xref, page_num + 1)
                    continue

                if not base_image:
                    continue

                image_bytes = base_image.get("image", b"")
                ext = base_image.get("ext", "png")
                width = base_image.get("width", 0)
                height = base_image.get("height", 0)

                # Skip tiny images (icons, bullets, decorations)
                if len(image_bytes) < min_size:
                    continue
                if width < 50 or height < 50:
                    continue

                img_filename = f"page_{page_num + 1}_img_{img_idx}.{ext}"
                img_path = img_dir / img_filename

                try:
                    img_path.write_bytes(image_bytes)
                except Exception:
                    logger.debug("Failed to save image: %s", img_path)
                    continue

                extracted.append({
                    "image_path": str(img_path),
                    "page_number": page_num + 1,
                    "image_index": img_idx,
                    "width": width,
                    "height": height,
                    "image_bytes": image_bytes,
                    "ext": ext,
                })
    finally:
        doc.close()

    logger.info("Extracted %s significant images from %s", len(extracted), pdf_path)
    return extracted


def _describe_image_with_gemini(image_bytes: bytes, page_number: int, retries: int = 2) -> str:
    """
    Use Gemini Vision API to generate a text description of an image.
    Includes retry logic with exponential backoff for rate limits.
    """
    if not settings.GOOGLE_API_KEY:
        return ""

    for attempt in range(retries + 1):
        try:
            import google.generativeai as genai
            from PIL import Image
            import io

            genai.configure(api_key=settings.GOOGLE_API_KEY)
            model = genai.GenerativeModel(settings.GEMINI_VISION_MODEL)

            img = Image.open(io.BytesIO(image_bytes))

            prompt = (
                f"You are analyzing an image from an engineering/technical textbook (page {page_number}). "
                "Describe this image in detail for a student studying this material. "
                "If it's a diagram, explain what it shows and label all components. "
                "If it's a graph/chart, describe the axes, data trends, and key values. "
                "If it's a circuit/flowchart, describe the flow and connections. "
                "If it's a formula or equation, write it out in text. "
                "If it's a color-coded box (note/warning/definition), transcribe the content. "
                "Be thorough and technical. Keep response under 400 words."
            )

            response = model.generate_content(
                [prompt, img],
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,
                    max_output_tokens=500,
                ),
            )
            description = response.text.strip()
            logger.debug("Generated description for page %s image: %s chars", page_number, len(description))
            return description

        except Exception as exc:
            err_str = str(exc).lower()
            # Rate limit: back off and retry
            if "429" in err_str or "quota" in err_str or "rate" in err_str:
                if attempt < retries:
                    wait = 2 ** (attempt + 1)  # 2s, 4s
                    logger.warning("Gemini rate limit hit, retrying in %ss...", wait)
                    time.sleep(wait)
                    continue
            logger.warning("Gemini Vision failed for page %s image: %s", page_number, exc)
            return ""

    return ""


def _describe_image_fallback(image_info: dict) -> str:
    """Basic description when Gemini Vision is unavailable."""
    page = image_info.get("page_number", "?")
    width = image_info.get("width", 0)
    height = image_info.get("height", 0)

    if width > 0 and height > 0:
        ratio = width / height
        if 0.8 <= ratio <= 1.2:
            shape = "square figure (possibly a diagram)"
        elif ratio > 2.0:
            shape = "wide figure (possibly a chart or table)"
        elif ratio < 0.5:
            shape = "tall figure (possibly a flowchart)"
        else:
            shape = "figure or diagram"
    else:
        shape = "figure"

    return (
        f"[Figure on page {page}]: A {shape} with dimensions {width}x{height}px "
        "extracted from the textbook. Enable Google API key for detailed description."
    )


def extract_images_as_chunks(
    pdf_path: str,
    pdf_hash: str,
    progress_callback: ProgressCallback | None = None,
) -> list[dict]:
    """
    Main entry point: extracts images from PDF, describes them with Gemini Vision,
    and returns structured chunks ready for ChromaDB indexing.

    For large PDFs (600+ pages), caps Gemini Vision calls at MAX_IMAGES_TO_DESCRIBE
    to avoid rate limits. Remaining images get fallback descriptions.
    """
    if not settings.ENABLE_IMAGE_EXTRACTION:
        logger.info("Image extraction disabled in settings.")
        return []

    if progress_callback:
        try:
            progress_callback(0.0, "Extracting images from PDF...")
        except Exception:
            pass

    images = _extract_images_from_pdf(pdf_path, pdf_hash)
    if not images:
        logger.info("No significant images found in PDF.")
        return []

    chunks: list[dict] = []
    total = len(images)
    max_vision_calls = settings.MAX_IMAGES_TO_DESCRIBE

    logger.info("Describing %s images (Gemini Vision cap: %s)", total, max_vision_calls)

    for i, img_info in enumerate(images):
        if progress_callback:
            try:
                progress_callback((i + 1) / total, f"Describing image {i + 1}/{total}...")
            except Exception:
                pass

        # Use Gemini Vision for the most important images (first N by page order)
        if i < max_vision_calls:
            description = _describe_image_with_gemini(
                img_info["image_bytes"],
                img_info["page_number"],
            )
        else:
            description = ""

        if not description:
            description = _describe_image_fallback(img_info)

        if not description.strip():
            continue

        chunks.append({
            "text": description,
            "page_number": img_info["page_number"],
            "content_type": "image_description",
            "section": f"Figure on page {img_info['page_number']}",
            "is_important": True,
            "chunk_index": 0,  # Re-indexed by pdf_processor
            "image_path": img_info["image_path"],
        })

    logger.info("Generated %s image description chunks from %s images.", len(chunks), total)
    return chunks


def get_image_paths_for_pdf(pdf_hash: str) -> list[dict]:
    """Returns list of all extracted images for a PDF (for UI gallery)."""
    img_dir = _get_image_dir(pdf_hash)
    if not img_dir.exists():
        return []

    images = []
    for img_path in sorted(img_dir.iterdir()):
        if img_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"):
            parts = img_path.stem.split("_")
            page_num = 0
            if len(parts) >= 2:
                try:
                    page_num = int(parts[1])
                except ValueError:
                    pass
            images.append({
                "path": str(img_path),
                "page_number": page_num,
                "filename": img_path.name,
            })

    return images
