import structlog
from providers.base import BaseProvider
from shared.schemas import ProviderSearchResult

logger = structlog.get_logger()


class YandexProvider(BaseProvider):
    name = "yandex"
    experimental = True
    description = "[Experimental] Yandex Images reverse search via browser automation"

    YANDEX_URL = "https://yandex.com/images/search"
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

                # Navigate to Yandex Images
                await page.goto("https://yandex.com/images/", wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

                # Dismiss any popups/consent
                try:
                    popup_btn = page.locator('button:has-text("Accept"), button:has-text("agree"), .Button2_view_action').first
                    await popup_btn.click(timeout=3000)
                    await page.wait_for_timeout(1000)
                except Exception:
                    pass

                # Click the camera/search-by-image button
                camera_selectors = [
                    '[aria-label*="image" i]',
                    '.input__cbir-button',
                    '.HeaderDesktopForm-CbirButton',
                    'button.input__button_type_cbir',
                    '[class*="CbirButton"]',
                    '.nDcEnd',
                ]
                camera_clicked = False
                for sel in camera_selectors:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=3000):
                            await btn.click()
                            camera_clicked = True
                            await page.wait_for_timeout(2000)
                            break
                    except Exception:
                        continue

                if not camera_clicked:
                    # Try going directly to the upload page with query params
                    await page.goto("https://yandex.com/images/search?rpt=imageview", wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)

                # Upload the file
                upload_input = page.locator('input[type="file"]').first
                await upload_input.set_input_files(image_path)

                # Wait for results page
                await page.wait_for_timeout(8000)
                await page.wait_for_load_state("domcontentloaded")

                # Try multiple extraction strategies
                results = await self._extract_results(page)

                await browser.close()

            logger.info("yandex_search_complete", result_count=len(results))
        except ImportError:
            logger.warning("playwright_not_installed")
        except Exception as e:
            logger.error("yandex_search_failed", error=str(e))

        return results

    async def _extract_results(self, page) -> list[ProviderSearchResult]:
        """Extract results from Yandex image search results."""
        results = []
        seen_urls = set()

        # Try "Sites with this image" section
        site_selectors = [
            ".CbirSites-Item",
            ".other-sites__item",
            '[class*="CbirSites"]',
            ".CbirOtherSizes-Item",
        ]

        for selector in site_selectors:
            try:
                items = await page.query_selector_all(selector)
                for item in items[:10]:
                    result = await self._parse_yandex_item(item)
                    if result and result.source_url not in seen_urls:
                        seen_urls.add(result.source_url)
                        results.append(result)
            except Exception:
                continue

        # If no structured results, try generic link extraction from results area
        if not results:
            try:
                links = await page.query_selector_all("a[href^='http']:not([href*='yandex'])")
                for link in links[:15]:
                    try:
                        href = await link.get_attribute("href") or ""
                        if not href or "yandex" in href or "yastatic" in href or href in seen_urls:
                            continue
                        seen_urls.add(href)

                        text = (await link.inner_text()).strip()
                        if not text or len(text) < 3:
                            continue

                        results.append(ProviderSearchResult(
                            source_url=href,
                            page_title=text[:120],
                            thumbnail_url="",
                            match_type="similar",
                            similarity_score=0.6,
                            confidence=0.5,
                            metadata={"provider": "yandex", "method": "link_extraction"},
                        ))
                    except Exception:
                        continue
            except Exception:
                pass

        # Try to get "Image description" from Yandex
        try:
            desc_el = await page.query_selector('.CbirObjectResponse-Description, [class*="Tags"] span, .CbirTags-Tag')
            if desc_el:
                desc_text = (await desc_el.inner_text()).strip()
                if desc_text and len(desc_text) > 3:
                    results.insert(0, ProviderSearchResult(
                        source_url=page.url,
                        page_title=f"Yandex detected: {desc_text}",
                        thumbnail_url="",
                        match_type="entity",
                        similarity_score=0.8,
                        confidence=0.7,
                        extracted_text=desc_text,
                        metadata={"provider": "yandex", "type": "description"},
                    ))
        except Exception:
            pass

        return results[:15]

    async def _parse_yandex_item(self, item) -> ProviderSearchResult | None:
        """Parse a single Yandex result item."""
        try:
            link = await item.query_selector("a[href^='http']")
            if not link:
                return None

            href = await link.get_attribute("href") or ""
            if not href or "yandex" in href:
                return None

            title_el = await item.query_selector("[class*='Title'], h3, .other-sites__title")
            title = ""
            if title_el:
                title = (await title_el.inner_text()).strip()
            if not title:
                title = (await link.inner_text()).strip()[:100]

            img_el = await item.query_selector("img")
            thumb = ""
            if img_el:
                thumb = await img_el.get_attribute("src") or ""

            desc_el = await item.query_selector("[class*='Description'], .other-sites__snippet")
            desc = ""
            if desc_el:
                desc = (await desc_el.inner_text()).strip()

            return ProviderSearchResult(
                source_url=href,
                page_title=title or "Yandex match",
                thumbnail_url=thumb if thumb.startswith("http") else "",
                match_type="similar",
                similarity_score=0.7,
                confidence=0.6,
                extracted_text=desc,
                metadata={"provider": "yandex"},
            )
        except Exception:
            return None

    async def healthcheck(self) -> dict:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://yandex.com/images/", follow_redirects=True)
                return {
                    "healthy": resp.status_code == 200,
                    "message": "Yandex Images is reachable",
                }
        except Exception as e:
            return {"healthy": False, "message": str(e)}

    def enabled(self, settings) -> bool:
        return getattr(settings, "YANDEX_ENABLED", False)
