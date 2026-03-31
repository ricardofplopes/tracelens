import os
import json
import subprocess
from PIL import Image
import imagehash
import cv2
import numpy as np
import structlog

logger = structlog.get_logger()


def compute_hashes(image_path: str) -> dict:
    """Compute perceptual hashes for an image."""
    try:
        img = Image.open(image_path)
        return {
            "phash": str(imagehash.phash(img)),
            "dhash": str(imagehash.dhash(img)),
            "ahash": str(imagehash.average_hash(img)),
        }
    except Exception as e:
        logger.error("hash_computation_failed", error=str(e))
        return {"phash": None, "dhash": None, "ahash": None}


def compute_color_histogram(image_path: str) -> dict | None:
    """Compute color histogram using OpenCV."""
    try:
        img = cv2.imread(image_path)
        if img is None:
            return None
        
        histograms = {}
        colors = ("b", "g", "r")
        for i, color in enumerate(colors):
            hist = cv2.calcHist([img], [i], None, [32], [0, 256])
            hist = cv2.normalize(hist, hist).flatten().tolist()
            histograms[color] = [round(v, 4) for v in hist]
        
        return histograms
    except Exception as e:
        logger.error("histogram_computation_failed", error=str(e))
        return None


def compute_orb_descriptors(image_path: str) -> int:
    """Compute ORB keypoints and return count."""
    try:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return 0
        
        orb = cv2.ORB_create(nfeatures=500)
        keypoints, descriptors = orb.detectAndCompute(img, None)
        return len(keypoints) if keypoints else 0
    except Exception as e:
        logger.error("orb_computation_failed", error=str(e))
        return 0


def get_image_dimensions(image_path: str) -> tuple[int | None, int | None, str | None]:
    """Get image dimensions and MIME type."""
    try:
        with Image.open(image_path) as img:
            w, h = img.size
            mime = Image.MIME.get(img.format, "image/jpeg")
            return w, h, mime
    except Exception as e:
        logger.error("dimension_extraction_failed", error=str(e))
        return None, None, None


def extract_exif(image_path: str) -> dict | None:
    """Extract EXIF data using exiftool."""
    try:
        result = subprocess.run(
            ["exiftool", "-json", "-n", image_path],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if data and isinstance(data, list):
                # Filter out binary/large fields
                exif = {}
                for k, v in data[0].items():
                    if isinstance(v, (str, int, float, bool)) and len(str(v)) < 500:
                        exif[k] = v
                return exif
    except FileNotFoundError:
        logger.warning("exiftool_not_found")
    except Exception as e:
        logger.error("exif_extraction_failed", error=str(e))
    return None


def extract_ocr(image_path: str) -> str | None:
    """Extract text from image using Tesseract OCR."""
    try:
        import pytesseract
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, timeout=30)
        text = text.strip()
        return text if text else None
    except Exception as e:
        logger.error("ocr_extraction_failed", error=str(e))
        return None


def extract_all_features(image_path: str) -> dict:
    """Run all feature extraction on an image and return combined results."""
    from backend.app.services.ingestion import compute_sha256
    
    w, h, mime = get_image_dimensions(image_path)
    hashes = compute_hashes(image_path)
    
    return {
        "sha256": compute_sha256(image_path),
        "phash": hashes.get("phash"),
        "dhash": hashes.get("dhash"),
        "ahash": hashes.get("ahash"),
        "color_histogram": compute_color_histogram(image_path),
        "orb_descriptor_count": compute_orb_descriptors(image_path),
        "dimensions": f"{w}x{h}" if w and h else None,
        "mime_type": mime,
        "exif_data": extract_exif(image_path),
        "ocr_text": extract_ocr(image_path),
    }
