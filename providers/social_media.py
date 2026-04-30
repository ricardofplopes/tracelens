import httpx
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
import structlog
from providers.base import BaseProvider
from shared.schemas import ProviderSearchResult

logger = structlog.get_logger()

# Social media platforms to search
SOCIAL_PLATFORMS = [
    {"name": "Reddit", "site": "reddit.com", "weight": 0.7},
    {"name": "Twitter/X", "site": "twitter.com OR x.com", "weight": 0.7},
    {"name": "Pinterest", "site": "pinterest.com", "weight": 0.65},
    {"name": "Flickr", "site": "flickr.com", "weight": 0.6},
    {"name": "Tumblr", "site": "tumblr.com", "weight": 0.55},
    {"name": "Instagram", "site": "instagram.com", "weight": 0.6},
]


class SocialMediaProvider(BaseProvider):
    name = "social_media"
    experimental = False
    description = "Search social media platforms for image matches using AI-generated terms"

    DDG_URL = "https://html.duckduckgo.com/html/"
    TIMEOUT = 20

    async def search(self, image_path: str, context: dict) -> list[ProviderSearchResult]:
        results = []
        search_terms = context.get("search_terms", [])
        entities = context.get("entities", [])
        ocr_text = context.get("ocr_text", "")

        # Build the best query from available context
        base_query = ""
        if search_terms:
            base_query = search_terms[0]
        elif entities:
            base_query = " ".join(entities[:3])
        elif ocr_text:
            base_query = " ".join(ocr_text.split()[:8])

        if not base_query:
            logger.info("social_media_no_query")
            return results

        seen_urls = set()

        for platform in SOCIAL_PLATFORMS:
            try:
                query = f"site:{platform['site']} {base_query}"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }

                async with httpx.AsyncClient(timeout=self.TIMEOUT, follow_redirects=True) as client:
                    resp = await client.post(
                        self.DDG_URL,
                        data={"q": query},
                        headers=headers,
                    )
                    resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "html.parser")
                result_links = soup.select(".result__a")

                for i, link in enumerate(result_links[:3]):
                    href = link.get("href", "")
                    if not href or href in seen_urls:
                        continue
                    if not href.startswith("http"):
                        continue
                    seen_urls.add(href)

                    title = link.get_text(strip=True)

                    # Get snippet
                    snippet_el = link.find_parent(".result")
                    snippet = ""
                    if snippet_el:
                        snippet_div = snippet_el.select_one(".result__snippet")
                        if snippet_div:
                            snippet = snippet_div.get_text(strip=True)

                    score = platform["weight"] - (i * 0.05)
                    results.append(ProviderSearchResult(
                        source_url=href,
                        page_title=title or f"{platform['name']} result",
                        thumbnail_url="",
                        match_type="social",
                        similarity_score=score,
                        confidence=score * 0.8,
                        extracted_text=snippet[:300] if snippet else "",
                        metadata={
                            "provider": "social_media",
                            "platform": platform["name"],
                            "search_query": query,
                        },
                    ))

            except Exception as e:
                logger.debug("social_media_platform_failed", platform=platform["name"], error=str(e))
                continue

        logger.info("social_media_search_complete", result_count=len(results))
        return results

    async def healthcheck(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://html.duckduckgo.com/html/")
                return {
                    "healthy": resp.status_code == 200,
                    "message": "DuckDuckGo (social search) is reachable",
                }
        except Exception as e:
            return {"healthy": False, "message": str(e)}

    def enabled(self, settings) -> bool:
        return getattr(settings, "SOCIAL_MEDIA_ENABLED", True)
