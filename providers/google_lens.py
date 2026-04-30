import base64
import structlog
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs
from providers.base import BaseProvider
from shared.schemas import ProviderSearchResult

logger = structlog.get_logger()


class GoogleLensProvider(BaseProvider):
    name = "google_lens"
    experimental = True
    description = "[Experimental] Google Lens reverse image search via browser automation"

    UPLOAD_URL = "https://www.google.com/searchbyimage/upload"
    LENS_UPLOAD_URL = "https://lens.google.com/v3/upload"
    TIMEOUT = 60000  # ms

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

                # Strategy 1: Use Google Images search-by-image via file upload
                results = await self._search_via_google_images(page, image_path)

                # Strategy 2: If no results, try Google Lens upload endpoint directly
                if not results:
                    results = await self._search_via_lens_upload(page, image_path)

                await browser.close()

            logger.info("google_lens_search_complete", result_count=len(results))
        except ImportError:
            logger.warning("playwright_not_installed")
        except Exception as e:
            logger.error("google_lens_search_failed", error=str(e))

        return results

    async def _search_via_google_images(self, page, image_path: str) -> list[ProviderSearchResult]:
        """Upload image via Google Images search-by-image flow."""
        results = []
        try:
            # Navigate to Google Images
            await page.goto("https://images.google.com", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # Accept cookies if shown
            try:
                consent = page.locator('button:has-text("Accept all"), button:has-text("I agree"), button[id*="agree"]').first
                await consent.click(timeout=5000)
                await page.wait_for_timeout(1000)
            except Exception:
                pass

            # Click the camera icon to open search-by-image
            try:
                camera = page.locator('[aria-label*="Search by image"], [aria-label*="search by image"], .Gdd5U, [data-base-uri*="searchbyimage"]').first
                await camera.click(timeout=10000)
                await page.wait_for_timeout(2000)
            except Exception:
                # Try alternative: go directly to the upload URL
                await page.goto("https://www.google.com/imghp?hl=en", wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                camera = page.locator('[aria-label*="Search by image"], .nDcEnd, svg').first
                await camera.click(timeout=10000)
                await page.wait_for_timeout(2000)

            # Upload file
            upload_input = page.locator('input[type="file"]').first
            await upload_input.set_input_files(image_path)

            # Wait for results page to load
            await page.wait_for_url("**/search**", timeout=30000)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(3000)

            # Extract results from the search results page
            results = await self._extract_search_results(page)

        except Exception as e:
            logger.debug("google_images_upload_failed", error=str(e))

        return results

    async def _search_via_lens_upload(self, page, image_path: str) -> list[ProviderSearchResult]:
        """Upload image directly to Google Lens."""
        results = []
        try:
            await page.goto("https://lens.google.com", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # Accept cookies
            try:
                consent = page.locator('button:has-text("Accept all"), button:has-text("I agree")').first
                await consent.click(timeout=5000)
                await page.wait_for_timeout(1000)
            except Exception:
                pass

            # Find and use file upload
            upload_input = page.locator('input[type="file"]').first
            await upload_input.set_input_files(image_path)

            # Wait for navigation to results
            await page.wait_for_timeout(8000)
            await page.wait_for_load_state("domcontentloaded")

            # Extract results
            results = await self._extract_lens_results(page)

        except Exception as e:
            logger.debug("lens_upload_failed", error=str(e))

        return results

    async def _extract_search_results(self, page) -> list[ProviderSearchResult]:
        """Extract results from Google search results page after image search."""
        results = []

        # Look for "Pages that include matching images" or "Visually similar images"
        # Also extract regular search results which are highly relevant
        selectors = [
            # Search result links
            "div.g a[href]:not([href*='google'])",
            "a[data-ved][href^='http']:not([href*='google.com'])",
            # Image result links  
            "a[href*='imgres']",
            # Knowledge panel links
            "a.fl[href^='http']",
        ]

        seen_urls = set()
        for selector in selectors:
            try:
                elements = await page.query_selector_all(selector)
                for el in elements[:8]:
                    try:
                        href = await el.get_attribute("href") or ""
                        if not href or "google.com" in href or href in seen_urls:
                            continue

                        # Parse imgres URLs to get actual page URL
                        if "imgres" in href:
                            parsed = urlparse(href)
                            params = parse_qs(parsed.query)
                            href = params.get("imgrefurl", [href])[0]

                        seen_urls.add(href)

                        # Get title
                        title_el = await el.query_selector("h3, span, div")
                        title = ""
                        if title_el:
                            title = (await title_el.inner_text()).strip()
                        if not title:
                            title = (await el.inner_text()).strip()[:100]

                        if href.startswith("http") and title:
                            results.append(ProviderSearchResult(
                                source_url=href,
                                page_title=title or "Google visual match",
                                thumbnail_url="",
                                match_type="similar",
                                similarity_score=0.75,
                                confidence=0.7,
                                metadata={"provider": "google_lens", "method": "search_by_image"},
                            ))
                    except Exception:
                        continue
            except Exception:
                continue

        # Also try to get the "best guess" description
        try:
            best_guess = await page.query_selector("a.fKDtNb, .biCjl a, [data-attrid='kc:/search/visual_search:best_guess'] a")
            if best_guess:
                guess_text = (await best_guess.inner_text()).strip()
                guess_href = await best_guess.get_attribute("href") or ""
                if guess_text:
                    results.insert(0, ProviderSearchResult(
                        source_url=f"https://www.google.com/search?q={quote_plus(guess_text)}",
                        page_title=f"Best guess: {guess_text}",
                        thumbnail_url="",
                        match_type="entity",
                        similarity_score=0.9,
                        confidence=0.85,
                        extracted_text=guess_text,
                        metadata={"provider": "google_lens", "type": "best_guess"},
                    ))
        except Exception:
            pass

        return results[:15]

    async def _extract_lens_results(self, page) -> list[ProviderSearchResult]:
        """Extract results from Google Lens results page."""
        results = []
        seen_urls = set()

        # Google Lens shows visual matches in various containers
        selectors = [
            "a[href*='http']:not([href*='google.com']):not([href*='gstatic'])",
            "[data-action-url]",
            ".Vd9M6 a",
            ".G19kAf a",
        ]

        for selector in selectors:
            try:
                elements = await page.query_selector_all(selector)
                for el in elements[:10]:
                    try:
                        href = await el.get_attribute("href") or await el.get_attribute("data-action-url") or ""
                        if not href or not href.startswith("http") or "google" in href or href in seen_urls:
                            continue
                        seen_urls.add(href)

                        title = ""
                        title_el = await el.query_selector("span, div, h3")
                        if title_el:
                            title = (await title_el.inner_text()).strip()
                        if not title:
                            title = (await el.inner_text()).strip()[:100]

                        img_el = await el.query_selector("img")
                        thumb = ""
                        if img_el:
                            thumb = await img_el.get_attribute("src") or ""

                        results.append(ProviderSearchResult(
                            source_url=href,
                            page_title=title or "Google Lens match",
                            thumbnail_url=thumb if thumb.startswith("http") else "",
                            match_type="similar",
                            similarity_score=0.7,
                            confidence=0.65,
                            metadata={"provider": "google_lens", "method": "lens"},
                        ))
                    except Exception:
                        continue
            except Exception:
                continue

        return results[:15]

    async def healthcheck(self) -> dict:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://images.google.com", follow_redirects=True)
                return {
                    "healthy": resp.status_code == 200,
                    "message": "Google Images is reachable",
                }
        except Exception as e:
            return {"healthy": False, "message": str(e)}

    def enabled(self, settings) -> bool:
        return getattr(settings, "GOOGLE_LENS_ENABLED", False)
