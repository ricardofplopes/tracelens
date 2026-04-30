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
    {"name": "Instagram", "site": "instagram.com", "weight": 0.7},
    {"name": "Facebook", "site": "facebook.com", "weight": 0.7},
    {"name": "LinkedIn", "site": "linkedin.com", "weight": 0.6},
    {"name": "TikTok", "site": "tiktok.com", "weight": 0.55},
    {"name": "VK", "site": "vk.com", "weight": 0.5},
]

# Person/portrait-specific search templates
PERSON_SEARCH_TEMPLATES = [
    "{query} profile photo",
    "{query} profile picture",
    "{query} photo",
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
        brands = context.get("brands", [])
        ocr_text = context.get("ocr_text", "")
        description = context.get("raw_description", "")

        # Detect if the image likely contains a person/face
        is_person = self._detect_person_context(description, entities)

        # Build search queries
        queries = self._build_queries(search_terms, entities, ocr_text, is_person)
        if not queries:
            logger.info("social_media_no_query")
            return results

        seen_urls = set()

        # Run platform-specific searches
        for platform in SOCIAL_PLATFORMS:
            for query in queries[:2]:  # Use top 2 queries per platform
                try:
                    site_query = f"site:{platform['site']} {query}"
                    platform_results = await self._search_ddg(
                        site_query, platform, seen_urls
                    )
                    results.extend(platform_results)
                except Exception as e:
                    logger.debug("social_media_platform_failed",
                                 platform=platform["name"], error=str(e))
                    continue

        # If person detected, also run cross-platform person searches
        if is_person and entities:
            person_results = await self._search_person_profiles(entities, seen_urls)
            results.extend(person_results)

        logger.info("social_media_search_complete", result_count=len(results))
        return results

    def _detect_person_context(self, description: str, entities: list) -> bool:
        """Detect if the image likely contains a person based on AI analysis."""
        person_keywords = [
            "person", "man", "woman", "face", "portrait", "selfie",
            "people", "individual", "profile", "headshot", "photo of",
            "smiling", "posing", "looking", "wearing", "hair",
        ]
        desc_lower = (description or "").lower()
        if any(kw in desc_lower for kw in person_keywords):
            return True
        # Check entities for person-like names
        for entity in entities:
            if len(entity.split()) >= 2:  # Multi-word likely a name
                return True
        return False

    def _build_queries(self, search_terms: list, entities: list, ocr_text: str,
                       is_person: bool) -> list[str]:
        """Build search queries, with person-specific variants if applicable."""
        queries = []

        if is_person and entities:
            # For people, prioritize name-based searches
            for entity in entities[:2]:
                queries.append(entity)
                for template in PERSON_SEARCH_TEMPLATES:
                    queries.append(template.format(query=entity))
        elif search_terms:
            queries.append(search_terms[0])
            if len(search_terms) > 1:
                queries.append(search_terms[1])
        elif entities:
            queries.append(" ".join(entities[:3]))
        elif ocr_text:
            queries.append(" ".join(ocr_text.split()[:8]))

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for q in queries:
            if q.lower() not in seen:
                seen.add(q.lower())
                unique.append(q)
        return unique[:4]

    async def _search_ddg(self, query: str, platform: dict,
                          seen_urls: set) -> list[ProviderSearchResult]:
        """Search DuckDuckGo for a specific platform query."""
        results = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
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

        for i, link in enumerate(result_links[:5]):
            href = link.get("href", "")
            if not href or href in seen_urls or not href.startswith("http"):
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

            score = platform["weight"] - (i * 0.04)
            results.append(ProviderSearchResult(
                source_url=href,
                page_title=title or f"{platform['name']} result",
                thumbnail_url="",
                match_type="social",
                similarity_score=score,
                confidence=score * 0.85,
                extracted_text=snippet[:300] if snippet else "",
                metadata={
                    "provider": "social_media",
                    "platform": platform["name"],
                    "search_query": query,
                },
            ))

        return results

    async def _search_person_profiles(self, entities: list,
                                       seen_urls: set) -> list[ProviderSearchResult]:
        """Run cross-platform person profile searches."""
        results = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
        }

        # Focused profile searches across key social platforms
        profile_queries = []
        for entity in entities[:2]:
            profile_queries.extend([
                f'"{entity}" facebook profile',
                f'"{entity}" instagram',
                f'"{entity}" linkedin profile',
            ])

        for query in profile_queries[:4]:
            try:
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
                    if not href or href in seen_urls or not href.startswith("http"):
                        continue

                    # Only keep social media links
                    is_social = any(s in href for s in [
                        "facebook.com", "instagram.com", "linkedin.com",
                        "twitter.com", "x.com",
                    ])
                    if not is_social:
                        continue

                    seen_urls.add(href)
                    title = link.get_text(strip=True)

                    snippet_el = link.find_parent(".result")
                    snippet = ""
                    if snippet_el:
                        snippet_div = snippet_el.select_one(".result__snippet")
                        if snippet_div:
                            snippet = snippet_div.get_text(strip=True)

                    results.append(ProviderSearchResult(
                        source_url=href,
                        page_title=title or "Social profile match",
                        thumbnail_url="",
                        match_type="social_profile",
                        similarity_score=0.7,
                        confidence=0.65,
                        extracted_text=snippet[:300] if snippet else "",
                        metadata={
                            "provider": "social_media",
                            "search_type": "person_profile",
                            "search_query": query,
                        },
                    ))

            except Exception as e:
                logger.debug("person_profile_search_failed", query=query, error=str(e))
                continue

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
