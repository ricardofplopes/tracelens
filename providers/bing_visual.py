import structlog
from urllib.parse import urlparse
from providers.base import BaseProvider
from shared.schemas import ProviderSearchResult

logger = structlog.get_logger()


class BingVisualProvider(BaseProvider):
    name = "bing_visual"
    experimental = False
    description = "Bing Visual Search - reverse image search with strong social media indexing"

    BING_IMAGES_URL = "https://www.bing.com/images"
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

                # Strategy 1: Bing Images search by image upload
                results = await self._search_via_upload(page, image_path)

                # Strategy 2: If that fails, try Bing Visual Search URL
                if not results:
                    results = await self._search_via_visual(page, image_path)

                await browser.close()

            logger.info("bing_visual_search_complete", result_count=len(results))
        except ImportError:
            logger.warning("playwright_not_installed")
        except Exception as e:
            logger.error("bing_visual_search_failed", error=str(e))

        return results

    async def _search_via_upload(self, page, image_path: str) -> list[ProviderSearchResult]:
        """Upload image via Bing Images search-by-image flow."""
        results = []
        try:
            await page.goto(self.BING_IMAGES_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # Click the camera/visual search icon
            camera_selectors = [
                "#sb_sbip",  # Bing image search icon
                "[aria-label='Search using an image']",
                ".sb_biICon",
                "#sbi_b",
                "input[aria-label='Paste image or URL']",
            ]

            clicked = False
            for sel in camera_selectors:
                try:
                    el = page.locator(sel).first
                    await el.click(timeout=5000)
                    clicked = True
                    await page.wait_for_timeout(1500)
                    break
                except Exception:
                    continue

            if not clicked:
                # Try going directly to visual search page
                await page.goto("https://www.bing.com/visualsearch", wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

            # Upload the image file
            upload_input = page.locator('input[type="file"]').first
            await upload_input.set_input_files(image_path)

            # Wait for results to load
            await page.wait_for_timeout(8000)
            await page.wait_for_load_state("domcontentloaded")

            # Try to find "Pages with this image" section
            results = await self._extract_results(page)

        except Exception as e:
            logger.debug("bing_upload_failed", error=str(e))

        return results

    async def _search_via_visual(self, page, image_path: str) -> list[ProviderSearchResult]:
        """Try Bing Visual Search directly."""
        results = []
        try:
            await page.goto("https://www.bing.com/visualsearch", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # Find file upload input
            upload_input = page.locator('input[type="file"]').first
            await upload_input.set_input_files(image_path)

            await page.wait_for_timeout(8000)
            await page.wait_for_load_state("domcontentloaded")

            results = await self._extract_results(page)

        except Exception as e:
            logger.debug("bing_visual_direct_failed", error=str(e))

        return results

    async def _extract_results(self, page) -> list[ProviderSearchResult]:
        """Extract results from Bing Visual Search results page."""
        results = []
        seen_urls = set()

        # Strategy 1: Look for "Pages including this image" cards
        page_selectors = [
            ".pages a[href]",
            ".pagesIncluding a[href]",
            "[data-idx] a[href^='http']",
            ".imgpt a[href^='http']",
            ".img_cont a[href^='http']",
        ]

        for selector in page_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for el in elements[:15]:
                    try:
                        href = await el.get_attribute("href") or ""
                        if not href or not href.startswith("http"):
                            continue
                        if "bing.com" in href or "microsoft.com" in href:
                            continue
                        if href in seen_urls:
                            continue
                        seen_urls.add(href)

                        domain = urlparse(href).netloc
                        title = ""
                        title_el = await el.query_selector("span, div, h3, p")
                        if title_el:
                            title = (await title_el.inner_text()).strip()
                        if not title:
                            title = (await el.inner_text()).strip()[:100]
                        if not title:
                            title = f"Match on {domain}"

                        # Get thumbnail
                        thumb = ""
                        img = await el.query_selector("img")
                        if img:
                            thumb = await img.get_attribute("src") or ""
                            if thumb and not thumb.startswith("http"):
                                thumb = ""

                        # Determine match type based on domain
                        is_social = any(s in domain for s in [
                            "facebook.com", "instagram.com", "twitter.com", "x.com",
                            "pinterest.com", "reddit.com", "linkedin.com",
                            "tiktok.com", "flickr.com", "tumblr.com", "vk.com",
                        ])
                        match_type = "social_exact" if is_social else "similar"
                        score = 0.9 if is_social else 0.8

                        results.append(ProviderSearchResult(
                            source_url=href,
                            page_title=title,
                            thumbnail_url=thumb,
                            match_type=match_type,
                            similarity_score=score,
                            confidence=score * 0.95,
                            extracted_text="",
                            metadata={
                                "provider": "bing_visual",
                                "domain": domain,
                                "is_social": is_social,
                            },
                        ))
                    except Exception:
                        continue
            except Exception:
                continue

        # Strategy 2: Extract from general result cards/links
        if not results:
            try:
                all_links = await page.query_selector_all(
                    "a[href^='http']:not([href*='bing.com']):not([href*='microsoft.com'])"
                    ":not([href*='gstatic']):not([href*='google.com'])"
                )
                for link in all_links[:20]:
                    try:
                        href = await link.get_attribute("href") or ""
                        if not href or href in seen_urls or not href.startswith("http"):
                            continue

                        domain = urlparse(href).netloc
                        # Skip navigation/utility links
                        if any(skip in domain for skip in [
                            "bing.com", "microsoft.com", "w3.org",
                            "schema.org", "gstatic.com",
                        ]):
                            continue

                        seen_urls.add(href)
                        title = (await link.inner_text()).strip()[:100]
                        if not title or len(title) < 3:
                            title = f"Match on {domain}"

                        is_social = any(s in domain for s in [
                            "facebook.com", "instagram.com", "twitter.com",
                            "pinterest.com", "reddit.com", "linkedin.com",
                        ])

                        results.append(ProviderSearchResult(
                            source_url=href,
                            page_title=title,
                            thumbnail_url="",
                            match_type="social_exact" if is_social else "similar",
                            similarity_score=0.75 if is_social else 0.65,
                            confidence=0.7 if is_social else 0.6,
                            metadata={
                                "provider": "bing_visual",
                                "domain": domain,
                                "method": "fallback",
                            },
                        ))
                    except Exception:
                        continue
            except Exception:
                pass

        return results[:15]

    async def healthcheck(self) -> dict:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://www.bing.com/images", follow_redirects=True)
                return {
                    "healthy": resp.status_code == 200,
                    "message": "Bing Images is reachable",
                }
        except Exception as e:
            return {"healthy": False, "message": str(e)}

    def enabled(self, settings) -> bool:
        return getattr(settings, "BING_VISUAL_ENABLED", True)
