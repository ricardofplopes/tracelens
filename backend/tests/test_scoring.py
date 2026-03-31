"""Tests for the scoring and ranking service."""
import pytest
from backend.app.services.scoring import (
    compute_hash_similarity,
    compute_text_overlap,
    compute_entity_overlap,
    score_candidate,
    cluster_duplicates,
)


class TestHashSimilarity:
    def test_identical_hashes(self):
        h = "a0b0c0d0e0f01020"
        assert compute_hash_similarity(h, h) == 1.0

    def test_none_hashes(self):
        assert compute_hash_similarity(None, "abc") == 0.0
        assert compute_hash_similarity("abc", None) == 0.0
        assert compute_hash_similarity(None, None) == 0.0

    def test_different_hashes(self):
        # Completely different hashes should give low similarity
        h1 = "0000000000000000"
        h2 = "ffffffffffffffff"
        sim = compute_hash_similarity(h1, h2)
        assert sim < 0.5

    def test_similar_hashes(self):
        # Hashes differing by a few bits
        h1 = "0000000000000000"
        h2 = "0000000000000001"
        sim = compute_hash_similarity(h1, h2)
        assert sim > 0.9


class TestTextOverlap:
    def test_identical_text(self):
        assert compute_text_overlap("hello world", "hello world") == 1.0

    def test_empty_text(self):
        assert compute_text_overlap("", "hello") == 0.0
        assert compute_text_overlap("hello", "") == 0.0
        assert compute_text_overlap(None, None) == 0.0

    def test_partial_overlap(self):
        sim = compute_text_overlap("hello world", "hello there")
        assert 0.3 < sim < 0.9

    def test_no_overlap(self):
        sim = compute_text_overlap("abc", "xyz")
        assert sim < 0.5

    def test_case_insensitive(self):
        sim = compute_text_overlap("Hello World", "hello world")
        assert sim == 1.0


class TestEntityOverlap:
    def test_identical_entities(self):
        entities = ["cat", "dog", "bird"]
        assert compute_entity_overlap(entities, entities) == 1.0

    def test_empty_entities(self):
        assert compute_entity_overlap([], ["cat"]) == 0.0
        assert compute_entity_overlap(["cat"], []) == 0.0

    def test_partial_overlap(self):
        e1 = ["cat", "dog", "bird"]
        e2 = ["cat", "fish", "bird"]
        sim = compute_entity_overlap(e1, e2)
        assert sim == 0.5  # 2 out of 4 unique

    def test_case_insensitive(self):
        e1 = ["Cat", "DOG"]
        e2 = ["cat", "dog"]
        assert compute_entity_overlap(e1, e2) == 1.0

    def test_no_overlap(self):
        e1 = ["cat", "dog"]
        e2 = ["fish", "bird"]
        assert compute_entity_overlap(e1, e2) == 0.0


class TestScoreCandidate:
    def test_basic_scoring(self):
        candidate = {
            "source_url": "https://example.com/img.jpg",
            "page_title": "Test Image",
            "similarity_score": 0.8,
            "extracted_text": "",
            "metadata": {},
        }
        features = {"sha256": "abc123", "phash": None, "ocr_text": ""}
        score = score_candidate(candidate, features, "iqdb")
        assert 0 <= score <= 1

    def test_high_provider_score(self):
        candidate = {
            "similarity_score": 0.95,
            "extracted_text": "",
            "metadata": {},
        }
        features = {}
        score = score_candidate(candidate, features, "google_lens")
        assert score > 0.5

    def test_source_confidence_affects_score(self):
        candidate = {
            "similarity_score": 0.7,
            "extracted_text": "",
            "metadata": {},
        }
        features = {}
        score_google = score_candidate(candidate, features, "google_lens")
        score_web = score_candidate(candidate, features, "web_search")
        assert score_google > score_web

    def test_exact_hash_match(self):
        candidate = {
            "similarity_score": 0.5,
            "extracted_text": "",
            "metadata": {"sha256": "abc123"},
        }
        features = {"sha256": "abc123"}
        score = score_candidate(candidate, features, "iqdb")
        assert score > 0.7


class TestClusterDuplicates:
    def test_no_duplicates(self):
        candidates = [
            {"source_url": "https://alpha-images.example.com/gallery/photo123.jpg", "page_title": "Mountain Landscape"},
            {"source_url": "https://beta-artwork.different.org/collection/piece-456", "page_title": "Abstract Art"},
        ]
        clusters = cluster_duplicates(candidates)
        assert len(clusters) == 2

    def test_identical_urls(self):
        candidates = [
            {"source_url": "https://example.com/image.jpg", "page_title": "Same"},
            {"source_url": "https://example.com/image.jpg", "page_title": "Same"},
        ]
        clusters = cluster_duplicates(candidates)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2

    def test_similar_urls(self):
        candidates = [
            {"source_url": "https://example.com/image1.jpg", "page_title": "Image Gallery"},
            {"source_url": "https://example.com/image2.jpg", "page_title": "Image Gallery"},
            {"source_url": "https://other.com/photo.jpg", "page_title": "Photo"},
        ]
        clusters = cluster_duplicates(candidates)
        assert len(clusters) >= 2  # At least the other.com one should be separate

    def test_empty_candidates(self):
        clusters = cluster_duplicates([])
        assert clusters == []
