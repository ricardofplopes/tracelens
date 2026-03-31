"""Tests for provider result normalization."""
import pytest
from shared.schemas import ProviderSearchResult
from providers.base import BaseProvider


class MockProvider(BaseProvider):
    name = "mock"
    description = "Test provider"

    async def search(self, image_path, context):
        return [
            ProviderSearchResult(
                source_url="https://example.com/img.jpg",
                page_title="Test Result",
                match_type="similar",
                similarity_score=0.85,
                confidence=0.7,
            )
        ]

    async def healthcheck(self):
        return {"healthy": True, "message": "OK"}

    def enabled(self, settings):
        return True


class FailingProvider(BaseProvider):
    name = "failing"
    description = "Always fails"

    async def search(self, image_path, context):
        raise RuntimeError("Provider failure")

    async def healthcheck(self):
        return {"healthy": False, "message": "Broken"}

    def enabled(self, settings):
        return True


@pytest.mark.asyncio
class TestProviderBase:
    async def test_mock_search(self):
        provider = MockProvider()
        results = await provider.search("test.jpg", {})
        assert len(results) == 1
        assert results[0].source_url == "https://example.com/img.jpg"
        assert results[0].similarity_score == 0.85

    async def test_safe_search_success(self):
        provider = MockProvider()
        results = await provider.safe_search("test.jpg", {})
        assert len(results) == 1

    async def test_safe_search_handles_failure(self):
        provider = FailingProvider()
        results = await provider.safe_search("test.jpg", {})
        assert results == []

    async def test_healthcheck(self):
        provider = MockProvider()
        health = await provider.healthcheck()
        assert health["healthy"] is True

    async def test_enabled(self):
        provider = MockProvider()
        assert provider.enabled(None) is True


class TestProviderSearchResult:
    def test_default_values(self):
        r = ProviderSearchResult()
        assert r.source_url == ""
        assert r.match_type == "similar"
        assert r.similarity_score == 0.0
        assert r.confidence == 0.0
        assert r.metadata == {}

    def test_custom_values(self):
        r = ProviderSearchResult(
            source_url="https://example.com",
            page_title="Test",
            match_type="exact",
            similarity_score=0.95,
            confidence=0.9,
            metadata={"key": "value"},
        )
        assert r.match_type == "exact"
        assert r.metadata == {"key": "value"}
