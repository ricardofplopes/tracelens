from abc import ABC, abstractmethod
from typing import Any
from shared.schemas import ProviderSearchResult
import structlog

logger = structlog.get_logger()


class BaseProvider(ABC):
    """Abstract base class for all search providers."""

    name: str = "base"
    experimental: bool = False
    description: str = ""

    @abstractmethod
    async def search(self, image_path: str, context: dict) -> list[ProviderSearchResult]:
        """Search for image matches. Returns list of normalized results."""
        ...

    @abstractmethod
    async def healthcheck(self) -> dict:
        """Check if the provider is available. Returns {healthy: bool, message: str}."""
        ...

    @abstractmethod
    def enabled(self, settings: Any) -> bool:
        """Check if this provider is enabled in settings."""
        ...

    async def safe_search(self, image_path: str, context: dict) -> list[ProviderSearchResult]:
        """Wrapper that catches exceptions and returns empty list on failure."""
        try:
            return await self.search(image_path, context)
        except Exception as e:
            logger.error("provider_search_failed", provider=self.name, error=str(e))
            return []
