"""Tests for feature extraction (using test images)."""
import os
import tempfile
import pytest
from PIL import Image


@pytest.fixture
def test_image():
    """Create a simple test image."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img = Image.new("RGB", (200, 150), color=(255, 0, 0))
        # Add some variation for better hash testing
        for x in range(50, 100):
            for y in range(50, 100):
                img.putpixel((x, y), (0, 0, 255))
        img.save(f.name)
        yield f.name
    os.unlink(f.name)


class TestIngestion:
    def test_compute_sha256(self, test_image):
        from backend.app.services.ingestion import compute_sha256
        h = compute_sha256(test_image)
        assert len(h) == 64
        assert h == compute_sha256(test_image)  # Deterministic

    def test_generate_variants(self, test_image):
        from backend.app.services.ingestion import generate_variants
        with tempfile.TemporaryDirectory() as tmpdir:
            variants = generate_variants(test_image, tmpdir)
            assert "resized" in variants
            assert "cropped" in variants
            assert "grayscale" in variants
            assert "sharpened" in variants
            assert "recompressed" in variants
            for name, info in variants.items():
                assert os.path.exists(info["file_path"])
                assert info["width"] > 0
                assert info["height"] > 0


class TestFeatureExtraction:
    def test_compute_hashes(self, test_image):
        from backend.app.services.feature_extraction import compute_hashes
        hashes = compute_hashes(test_image)
        assert hashes["phash"] is not None
        assert hashes["dhash"] is not None
        assert hashes["ahash"] is not None

    def test_compute_color_histogram(self, test_image):
        from backend.app.services.feature_extraction import compute_color_histogram
        hist = compute_color_histogram(test_image)
        assert hist is not None
        assert "r" in hist
        assert "g" in hist
        assert "b" in hist
        assert len(hist["r"]) == 32

    def test_compute_orb_descriptors(self, test_image):
        from backend.app.services.feature_extraction import compute_orb_descriptors
        count = compute_orb_descriptors(test_image)
        assert isinstance(count, int)
        assert count >= 0

    def test_get_image_dimensions(self, test_image):
        from backend.app.services.feature_extraction import get_image_dimensions
        w, h, mime = get_image_dimensions(test_image)
        assert w == 200
        assert h == 150
        assert "image" in mime

    def test_extract_all_features(self, test_image):
        from backend.app.services.feature_extraction import extract_all_features
        features = extract_all_features(test_image)
        assert features["sha256"] is not None
        assert features["phash"] is not None
        assert features["dimensions"] == "200x150"
