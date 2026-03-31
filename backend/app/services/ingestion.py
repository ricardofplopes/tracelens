import os
import hashlib
from PIL import Image, ImageFilter, ImageEnhance
import structlog

logger = structlog.get_logger()

VARIANTS = ["resized", "cropped", "recompressed", "grayscale", "sharpened"]


def generate_variants(original_path: str, job_dir: str) -> dict[str, dict]:
    """Generate normalized image variants for better matching across providers.
    
    Returns dict mapping variant name to {file_path, width, height, mime_type, file_size}.
    """
    results = {}
    
    try:
        img = Image.open(original_path)
        if img.mode == "RGBA":
            img = img.convert("RGB")
    except Exception as e:
        logger.error("variant_generation_failed", error=str(e), path=original_path)
        return results

    # Resized (max 800px on longest side)
    try:
        resized = img.copy()
        resized.thumbnail((800, 800), Image.LANCZOS)
        path = os.path.join(job_dir, "resized.jpg")
        resized.save(path, "JPEG", quality=90)
        results["resized"] = _file_info(path, resized)
    except Exception as e:
        logger.warning("variant_failed", variant="resized", error=str(e))

    # Center-cropped (512x512)
    try:
        w, h = img.size
        min_dim = min(w, h)
        left = (w - min_dim) // 2
        top = (h - min_dim) // 2
        cropped = img.crop((left, top, left + min_dim, top + min_dim))
        cropped = cropped.resize((512, 512), Image.LANCZOS)
        path = os.path.join(job_dir, "cropped.jpg")
        cropped.save(path, "JPEG", quality=90)
        results["cropped"] = _file_info(path, cropped)
    except Exception as e:
        logger.warning("variant_failed", variant="cropped", error=str(e))

    # Recompressed (JPEG 85%)
    try:
        path = os.path.join(job_dir, "recompressed.jpg")
        img.save(path, "JPEG", quality=85)
        recomp = Image.open(path)
        results["recompressed"] = _file_info(path, recomp)
    except Exception as e:
        logger.warning("variant_failed", variant="recompressed", error=str(e))

    # Grayscale
    try:
        gray = img.convert("L").convert("RGB")
        path = os.path.join(job_dir, "grayscale.jpg")
        gray.save(path, "JPEG", quality=90)
        results["grayscale"] = _file_info(path, gray)
    except Exception as e:
        logger.warning("variant_failed", variant="grayscale", error=str(e))

    # Sharpened
    try:
        enhancer = ImageEnhance.Sharpness(img)
        sharpened = enhancer.enhance(2.0)
        sharpened = sharpened.filter(ImageFilter.SHARPEN)
        path = os.path.join(job_dir, "sharpened.jpg")
        sharpened.save(path, "JPEG", quality=90)
        results["sharpened"] = _file_info(path, sharpened)
    except Exception as e:
        logger.warning("variant_failed", variant="sharpened", error=str(e))

    logger.info("variants_generated", count=len(results), job_dir=job_dir)
    return results


def compute_sha256(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _file_info(path: str, img: Image.Image) -> dict:
    """Helper to build file info dict."""
    w, h = img.size
    return {
        "file_path": path,
        "width": w,
        "height": h,
        "mime_type": "image/jpeg",
        "file_size": os.path.getsize(path),
    }
