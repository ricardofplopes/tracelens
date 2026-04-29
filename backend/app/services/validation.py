"""Image validation and sanitization service."""

import os

import structlog
from PIL import Image

logger = structlog.get_logger()

# Magic byte signatures for supported image types
MAGIC_SIGNATURES: list[tuple[str, bytes, int | None, bytes | None]] = [
    # (mime_type, header_bytes, offset_for_extra, extra_bytes)
    ("image/jpeg", b"\xff\xd8\xff", None, None),
    ("image/png", b"\x89PNG", None, None),
    ("image/gif", b"GIF", None, None),
    ("image/webp", b"RIFF", 8, b"WEBP"),
]

GPS_IFD_TAG = 0x8825


def get_mime_from_magic(file_path: str) -> str:
    """Read the first 12 bytes and determine MIME type from magic bytes."""
    with open(file_path, "rb") as f:
        header = f.read(12)

    for mime, signature, extra_offset, extra_bytes in MAGIC_SIGNATURES:
        if not header.startswith(signature):
            continue
        if extra_offset is not None and extra_bytes is not None:
            if header[extra_offset : extra_offset + len(extra_bytes)] != extra_bytes:
                continue
        return mime

    return "application/octet-stream"


def validate_image(file_path: str, max_size_mb: int = 50) -> tuple[bool, str]:
    """Validate that a file is a readable, correctly-typed, non-corrupt image.

    Returns (is_valid, error_message). error_message is empty on success.
    """
    # File exists and is readable
    if not os.path.isfile(file_path):
        return False, "File does not exist"
    if not os.access(file_path, os.R_OK):
        return False, "File is not readable"

    # File size check
    file_size = os.path.getsize(file_path)
    max_bytes = max_size_mb * 1024 * 1024
    if file_size > max_bytes:
        return False, f"File size {file_size} bytes exceeds limit of {max_size_mb} MB"
    if file_size == 0:
        return False, "File is empty"

    # Magic byte check
    mime = get_mime_from_magic(file_path)
    if mime == "application/octet-stream":
        return False, "File does not match any supported image type (JPEG, PNG, GIF, WebP)"

    # Pillow integrity check
    try:
        with Image.open(file_path) as img:
            img.verify()
    except Exception as exc:
        return False, f"Image file is corrupted or unreadable: {exc}"

    logger.debug("image_validated", file_path=file_path, mime=mime, size=file_size)
    return True, ""


def strip_gps_exif(file_path: str) -> None:
    """Remove GPS-related EXIF tags from the image file in-place."""
    try:
        with Image.open(file_path) as img:
            if img.format not in ("JPEG", "TIFF"):
                return

            exif_data = img.getexif()
            if not exif_data:
                return

            changed = False

            # Remove the GPSInfo IFD pointer
            if GPS_IFD_TAG in exif_data:
                del exif_data[GPS_IFD_TAG]
                changed = True

            if changed:
                img.save(file_path, exif=exif_data.tobytes())
                logger.info("gps_exif_stripped", file_path=file_path)
            else:
                logger.debug("no_gps_exif_found", file_path=file_path)
    except Exception:
        # Non-fatal: if we can't strip EXIF, log and continue
        logger.warning("exif_strip_failed", file_path=file_path, exc_info=True)
