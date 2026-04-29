"""Tests for the image validation service."""

import os
import struct
import tempfile

import pytest
from PIL import Image

from backend.app.services.validation import (
    get_mime_from_magic,
    strip_gps_exif,
    validate_image,
)


@pytest.fixture
def tmp_dir(tmp_path):
    return str(tmp_path)


def _create_jpeg(path: str, width: int = 10, height: int = 10) -> str:
    """Create a minimal valid JPEG file."""
    img = Image.new("RGB", (width, height), color="red")
    img.save(path, format="JPEG")
    return path


def _create_png(path: str, width: int = 10, height: int = 10) -> str:
    """Create a minimal valid PNG file."""
    img = Image.new("RGBA", (width, height), color="blue")
    img.save(path, format="PNG")
    return path


class TestValidateImage:
    def test_valid_jpeg(self, tmp_dir):
        path = os.path.join(tmp_dir, "test.jpg")
        _create_jpeg(path)
        is_valid, msg = validate_image(path)
        assert is_valid is True
        assert msg == ""

    def test_valid_png(self, tmp_dir):
        path = os.path.join(tmp_dir, "test.png")
        _create_png(path)
        is_valid, msg = validate_image(path)
        assert is_valid is True
        assert msg == ""

    def test_non_image_file_fails(self, tmp_dir):
        path = os.path.join(tmp_dir, "fake.jpg")
        with open(path, "w") as f:
            f.write("This is just a text file pretending to be an image.")
        is_valid, msg = validate_image(path)
        assert is_valid is False
        assert "supported image type" in msg

    def test_oversized_file_fails(self, tmp_dir):
        path = os.path.join(tmp_dir, "big.jpg")
        _create_jpeg(path)
        # Validate with a very small limit (smaller than any real image)
        is_valid, msg = validate_image(path, max_size_mb=0)
        # 0 MB limit means 0 bytes allowed
        assert is_valid is False
        assert "exceeds limit" in msg

    def test_empty_file_fails(self, tmp_dir):
        path = os.path.join(tmp_dir, "empty.jpg")
        with open(path, "wb") as f:
            pass
        is_valid, msg = validate_image(path)
        assert is_valid is False
        assert "empty" in msg

    def test_nonexistent_file_fails(self, tmp_dir):
        path = os.path.join(tmp_dir, "nope.jpg")
        is_valid, msg = validate_image(path)
        assert is_valid is False
        assert "does not exist" in msg

    def test_corrupted_image_fails(self, tmp_dir):
        path = os.path.join(tmp_dir, "corrupt.jpg")
        # Write JPEG magic bytes followed by garbage
        with open(path, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        is_valid, msg = validate_image(path)
        assert is_valid is False
        assert "corrupted" in msg


class TestGetMimeFromMagic:
    def test_jpeg(self, tmp_dir):
        path = os.path.join(tmp_dir, "test.jpg")
        _create_jpeg(path)
        assert get_mime_from_magic(path) == "image/jpeg"

    def test_png(self, tmp_dir):
        path = os.path.join(tmp_dir, "test.png")
        _create_png(path)
        assert get_mime_from_magic(path) == "image/png"

    def test_webp(self, tmp_dir):
        path = os.path.join(tmp_dir, "test.webp")
        img = Image.new("RGB", (10, 10), color="green")
        img.save(path, format="WEBP")
        assert get_mime_from_magic(path) == "image/webp"

    def test_unknown(self, tmp_dir):
        path = os.path.join(tmp_dir, "test.txt")
        with open(path, "w") as f:
            f.write("not an image")
        assert get_mime_from_magic(path) == "application/octet-stream"


class TestStripGpsExif:
    def test_strips_gps_data(self, tmp_dir):
        path = os.path.join(tmp_dir, "gps.jpg")
        # Create a JPEG image, then manually inject GPS IFD tag into EXIF
        img = Image.new("RGB", (10, 10), color="red")
        # Build EXIF with GPS IFD tag using raw bytes
        # Minimal EXIF: Exif header + IFD0 with GPS IFD pointer tag
        import struct

        # Build a minimal TIFF/EXIF structure with GPSInfo tag
        # Byte order: little-endian (II)
        bo = b"II"
        magic = struct.pack("<H", 42)
        ifd_offset = struct.pack("<I", 8)  # IFD starts at offset 8

        # IFD0: 1 entry (GPSInfo pointer)
        num_entries = struct.pack("<H", 1)
        # Tag 0x8825 (GPSInfo), type LONG (4), count 1, value offset = 26
        # (pointing past end of IFD0 which ends at 8+2+12+4=26)
        gps_tag = struct.pack("<HHII", 0x8825, 4, 1, 26)
        next_ifd = struct.pack("<I", 0)  # no next IFD

        # GPS IFD: 1 entry - GPSVersionID (tag 0, type BYTE, count 4, value 2.3.0.0)
        gps_num = struct.pack("<H", 1)
        gps_entry = struct.pack("<HHII", 0x0000, 1, 4, 0x00000302)
        gps_next = struct.pack("<I", 0)

        tiff_data = (
            bo + magic + ifd_offset + num_entries + gps_tag + next_ifd
            + gps_num + gps_entry + gps_next
        )
        exif_bytes = b"Exif\x00\x00" + tiff_data

        img.save(path, format="JPEG", exif=exif_bytes)

        # Verify GPS tag exists before stripping
        with Image.open(path) as check_img:
            check_exif = check_img.getexif()
            assert 0x8825 in check_exif

        # Strip GPS
        strip_gps_exif(path)

        # Verify GPS tag is gone
        with Image.open(path) as result_img:
            result_exif = result_img.getexif()
            assert 0x8825 not in result_exif

    def test_no_crash_on_image_without_exif(self, tmp_dir):
        path = os.path.join(tmp_dir, "no_exif.png")
        _create_png(path)
        # Should not raise
        strip_gps_exif(path)
