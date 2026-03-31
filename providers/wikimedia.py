import httpx
import structlog
from providers.base import BaseProvider
from shared.schemas import ProviderSearchResult

logger = structlog.get_logger()


class WikimediaProvider(BaseProvider):
    name = "wikimedia"
    experimental = False
    description = "Wikimedia Commons search using AI-generated terms"

    API_URL = "https://commons.wikimedia.org/w/api.php"
    TIMEOUT = 20

    async def search(self, image_path: str, context: dict) -> list[ProviderSearchResult]:
        results = []
        search_terms = context.get("search_terms", [])
        entities = context.get("entities", [])

        # Combine search terms
        queries = []
        if search_terms:
            queries.extend(search_terms[:3])
        if entities:
            queries.extend(entities[:2])

        if not queries:
            logger.info("wikimedia_no_search_terms")
            return results

        seen_urls = set()

        for query in queries:
            try:
                params = {
                    "action": "query",
                    "format": "json",
                    "generator": "search",
                    "gsrnamespace": "6",  # File namespace
                    "gsrsearch": query,
                    "gsrlimit": "5",
                    "prop": "imageinfo",
                    "iiprop": "url|size|mime|extmetadata",
                    "iiurlwidth": "300",
                }

                headers = {
                    "User-Agent": "TraceLens/1.0 (https://github.com/ricardofplopes/tracelens; image-investigation-tool)",
                    "Accept": "application/json",
                }
                async with httpx.AsyncClient(timeout=self.TIMEOUT, headers=headers) as client:
                    resp = await client.get(self.API_URL, params=params)
                    resp.raise_for_status()

                data = resp.json()
                pages = data.get("query", {}).get("pages", {})

                for page_id, page in pages.items():
                    imageinfo = page.get("imageinfo", [{}])[0]
                    page_url = imageinfo.get("descriptionurl", "")

                    if page_url in seen_urls:
                        continue
                    seen_urls.add(page_url)

                    thumb_url = imageinfo.get("thumburl", "")
                    title = page.get("title", "").replace("File:", "")
                    
                    # Extract description from metadata
                    extmeta = imageinfo.get("extmetadata", {})
                    description = ""
                    if extmeta.get("ImageDescription"):
                        description = extmeta["ImageDescription"].get("value", "")
                        # Strip HTML tags
                        from html import unescape
                        import re
                        description = re.sub(r"<[^>]+>", "", unescape(description))

                    results.append(ProviderSearchResult(
                        source_url=page_url,
                        page_title=title,
                        thumbnail_url=thumb_url,
                        match_type="entity",
                        similarity_score=0.5,
                        confidence=0.4,
                        extracted_text=description[:500] if description else "",
                        metadata={
                            "provider": "wikimedia",
                            "search_query": query,
                            "mime": imageinfo.get("mime", ""),
                            "width": imageinfo.get("width"),
                            "height": imageinfo.get("height"),
                        },
                    ))

            except Exception as e:
                logger.warning("wikimedia_search_failed", query=query, error=str(e))

        logger.info("wikimedia_search_complete", result_count=len(results))
        return results

    async def healthcheck(self) -> dict:
        try:
            headers = {
                "User-Agent": "TraceLens/1.0 (https://github.com/ricardofplopes/tracelens; image-investigation-tool)",
            }
            async with httpx.AsyncClient(timeout=10, headers=headers) as client:
                resp = await client.get(self.API_URL, params={"action": "query", "meta": "siteinfo", "format": "json"})
                return {
                    "healthy": resp.status_code == 200,
                    "message": "Wikimedia Commons API is reachable",
                }
        except Exception as e:
            return {"healthy": False, "message": str(e)}

    def enabled(self, settings) -> bool:
        return getattr(settings, "WIKIMEDIA_ENABLED", True)
