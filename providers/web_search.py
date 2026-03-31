import httpx
from bs4 import BeautifulSoup
import structlog
from providers.base import BaseProvider
from shared.schemas import ProviderSearchResult

logger = structlog.get_logger()


class WebSearchProvider(BaseProvider):
    name = "web_search"
    experimental = False
    description = "Generic web search using OCR text and AI-generated search terms"

    DDG_URL = "https://html.duckduckgo.com/html/"
    TIMEOUT = 20

    async def search(self, image_path: str, context: dict) -> list[ProviderSearchResult]:
        results = []
        search_terms = context.get("search_terms", [])
        ocr_text = context.get("ocr_text", "")

        queries = []
        if search_terms:
            queries.extend(search_terms[:3])
        elif ocr_text:
            # Use first meaningful chunk of OCR text
            words = ocr_text.split()[:10]
            queries.append(" ".join(words))

        if not queries:
            logger.info("web_search_no_queries")
            return results

        seen_urls = set()

        for query in queries:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                async with httpx.AsyncClient(timeout=self.TIMEOUT, follow_redirects=True) as client:
                    resp = await client.post(
                        self.DDG_URL,
                        data={"q": query},
                        headers=headers,
                    )
                    resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "html.parser")
                result_links = soup.select(".result__a, .result__url")

                for i, link in enumerate(result_links[:5]):
                    href = link.get("href", "")
                    if not href or href in seen_urls:
                        continue
                    seen_urls.add(href)

                    title = link.get_text(strip=True)
                    
                    # Get snippet
                    snippet_el = link.find_next(".result__snippet")
                    snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                    results.append(ProviderSearchResult(
                        source_url=href,
                        page_title=title or "Web search result",
                        match_type="text",
                        similarity_score=0.3 - (i * 0.03),
                        confidence=0.3 - (i * 0.03),
                        extracted_text=snippet,
                        metadata={
                            "provider": "web_search",
                            "search_query": query,
                        },
                    ))

            except Exception as e:
                logger.warning("web_search_query_failed", query=query, error=str(e))

        logger.info("web_search_complete", result_count=len(results))
        return results

    async def healthcheck(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://html.duckduckgo.com/html/")
                return {
                    "healthy": resp.status_code == 200,
                    "message": "DuckDuckGo is reachable",
                }
        except Exception as e:
            return {"healthy": False, "message": str(e)}

    def enabled(self, settings) -> bool:
        return getattr(settings, "WEB_SEARCH_ENABLED", True)
