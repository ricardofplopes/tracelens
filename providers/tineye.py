import structlog
from urllib.parse import urlparse
from providers.base import BaseProvider
from shared.schemas import ProviderSearchResult

logger = structlog.get_logger()


class TinEyeProvider(BaseProvider):
    name = "tineye"
    experimental = True
    description = "[Experimental] TinEye reverse image search via browser automation"

    TINEYE_URL = "https://tineye.com"
    TIMEOUT = 45000  # ms

    async def search(self, image_path: str, context: dict) -> list[ProviderSearchResult]:
        results = []
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-blink-features=AutomationControlled",
                    ],
                )
                ctx = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                )
                page = await ctx.new_page()
                page.set_default_timeout(self.TIMEOUT)

                # Navigate to TinEye
                await page.goto(self.TINEYE_URL, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

                # Upload image file
                upload_input = page.locator('input[type="file"]').first
                await upload_input.set_input_files(image_path)

                # Wait for results page
                await page.wait_for_url("**/search/**", timeout=30000)
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(3000)

                # Check for "0 results" indicator
                try:
                    no_results = await page.query_selector(".no-results, .search-no-results")
                    if no_results:
                        logger.info("tineye_no_results")
                        await browser.close()
                        return results
                except Exception:
                    pass

                # Extract match count
                try:
                    count_el = await page.query_selector(".result-count, .results-summary h2, .match-count")
                    if count_el:
                        count_text = (await count_el.inner_text()).strip()
                        logger.info("tineye_result_count_text", text=count_text)
                except Exception:
                    pass

                # Extract results
                result_selectors = [
                    ".match-row",
                    ".match",
                    ".result-row",
                    ".search-result",
                ]

                for selector in result_selectors:
                    try:
                        rows = await page.query_selector_all(selector)
                        if rows:
                            results = await self._extract_results(page, rows)
                            break
                    except Exception:
                        continue

                # Fallback: extract all links from results area
                if not results:
                    results = await self._extract_links_fallback(page)

                await browser.close()

            logger.info("tineye_search_complete", result_count=len(results))
        except ImportError:
            logger.warning("playwright_not_installed")
        except Exception as e:
            logger.error("tineye_search_failed", error=str(e))

        return results

    async def _extract_results(self, page, rows) -> list[ProviderSearchResult]:
        """Extract results from TinEye match rows."""
        results = []
        seen_urls = set()

        for row in rows[:15]:
            try:
                # Get the link to the source page
                link = await row.query_selector("a[href*='http']:not([href*='tineye.com'])")
                if not link:
                    # Try any link in the row
                    link = await row.query_selector("a[href]")

                if not link:
                    continue

                href = await link.get_attribute("href") or ""
                if not href or "tineye.com" in href or href in seen_urls:
                    continue
                if not href.startswith("http"):
                    continue

                seen_urls.add(href)
                domain = urlparse(href).netloc

                # Get title/description
                title = ""
                title_el = await row.query_selector("h4, .match-title, .result-title, .match-link")
                if title_el:
                    title = (await title_el.inner_text()).strip()
                if not title:
                    title = (await link.inner_text()).strip()[:100]
                if not title:
                    title = f"Match on {domain}"

                # Get thumbnail
                thumb = ""
                img = await row.query_selector("img")
                if img:
                    thumb = await img.get_attribute("src") or ""
                    if thumb and not thumb.startswith("http"):
                        thumb = ""

                # Determine if it's from social media
                match_type = "exact"
                is_social = any(s in domain for s in [
                    "facebook.com", "instagram.com", "twitter.com", "x.com",
                    "pinterest.com", "reddit.com", "tumblr.com", "flickr.com",
                    "linkedin.com", "tiktok.com", "vk.com",
                ])
                if is_social:
                    match_type = "social_exact"

                results.append(ProviderSearchResult(
                    source_url=href,
                    page_title=title,
                    thumbnail_url=thumb,
                    match_type=match_type,
                    similarity_score=0.95,
                    confidence=0.9,
                    extracted_text="",
                    metadata={
                        "provider": "tineye",
                        "domain": domain,
                        "is_social": is_social,
                    },
                ))
            except Exception:
                continue

        return results

    async def _extract_links_fallback(self, page) -> list[ProviderSearchResult]:
        """Fallback: extract all external links from the results area."""
        results = []
        seen_urls = set()

        try:
            links = await page.query_selector_all("a[href*='http']:not([href*='tineye.com']):not([href*='google'])")
            for link in links[:10]:
                try:
                    href = await link.get_attribute("href") or ""
                    if not href or href in seen_urls or not href.startswith("http"):
                        continue

                    domain = urlparse(href).netloc
                    # Skip obvious non-result links
                    if any(skip in domain for skip in ["tineye.com", "google.com", "gstatic.com"]):
                        continue

                    seen_urls.add(href)
                    title = (await link.inner_text()).strip()[:100] or f"Match on {domain}"

                    is_social = any(s in domain for s in [
                        "facebook.com", "instagram.com", "twitter.com", "x.com",
                        "pinterest.com", "reddit.com",
                    ])

                    results.append(ProviderSearchResult(
                        source_url=href,
                        page_title=title,
                        thumbnail_url="",
                        match_type="social_exact" if is_social else "exact",
                        similarity_score=0.9,
                        confidence=0.85,
                        metadata={
                            "provider": "tineye",
                            "domain": domain,
                            "method": "fallback",
                        },
                    ))
                except Exception:
                    continue
        except Exception:
            pass

        return results

    async def healthcheck(self) -> dict:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(self.TINEYE_URL, follow_redirects=True)
                return {
                    "healthy": resp.status_code == 200,
                    "message": "TinEye is reachable",
                }
        except Exception as e:
            return {"healthy": False, "message": str(e)}

    def enabled(self, settings) -> bool:
        return getattr(settings, "TINEYE_ENABLED", False)
