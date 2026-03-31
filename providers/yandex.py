import structlog
from providers.base import BaseProvider
from shared.schemas import ProviderSearchResult

logger = structlog.get_logger()


class YandexProvider(BaseProvider):
    name = "yandex"
    experimental = True
    description = "[Experimental] Yandex Images reverse search via browser automation"

    YANDEX_URL = "https://yandex.com/images/"
    TIMEOUT = 45000  # ms

    async def search(self, image_path: str, context: dict) -> list[ProviderSearchResult]:
        results = []
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox"],
                )
                page = await browser.new_page()
                page.set_default_timeout(self.TIMEOUT)

                await page.goto(self.YANDEX_URL, wait_until="networkidle")

                # Click the camera/search-by-image button
                camera_btn = page.locator('[class*="CbirButton"], .input__cbir-button, button[aria-label*="image"]').first
                try:
                    await camera_btn.click(timeout=10000)
                except Exception:
                    pass

                # Look for file upload input
                upload_input = page.locator('input[type="file"]').first
                await upload_input.set_input_files(image_path)

                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(5000)

                # Extract similar images
                items = await page.query_selector_all(".CbirSites-Item, .serp-item, .other-sites__item")

                for item in items[:10]:
                    try:
                        link = await item.query_selector("a")
                        href = await link.get_attribute("href") if link else ""

                        title_el = await item.query_selector(".CbirSites-ItemTitle, .serp-item__title, h3")
                        title = await title_el.inner_text() if title_el else ""

                        img_el = await item.query_selector("img")
                        thumb = await img_el.get_attribute("src") if img_el else ""

                        desc_el = await item.query_selector(".CbirSites-ItemDescription, .serp-item__text")
                        desc = await desc_el.inner_text() if desc_el else ""

                        if href:
                            results.append(ProviderSearchResult(
                                source_url=href,
                                page_title=title or "Yandex match",
                                thumbnail_url=thumb or "",
                                match_type="similar",
                                similarity_score=0.65,
                                confidence=0.55,
                                extracted_text=desc,
                                metadata={"provider": "yandex"},
                            ))
                    except Exception:
                        continue

                await browser.close()

            logger.info("yandex_search_complete", result_count=len(results))
        except ImportError:
            logger.warning("playwright_not_installed")
        except Exception as e:
            logger.error("yandex_search_failed", error=str(e))

        return results

    async def healthcheck(self) -> dict:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://yandex.com/images/")
                return {
                    "healthy": resp.status_code == 200,
                    "message": "Yandex Images is reachable",
                }
        except Exception as e:
            return {"healthy": False, "message": str(e)}

    def enabled(self, settings) -> bool:
        return getattr(settings, "YANDEX_ENABLED", False)
