import structlog
from providers.base import BaseProvider
from shared.schemas import ProviderSearchResult

logger = structlog.get_logger()


class GoogleLensProvider(BaseProvider):
    name = "google_lens"
    experimental = True
    description = "[Experimental] Google Lens reverse image search via browser automation"

    LENS_URL = "https://lens.google.com"
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

                await page.goto(self.LENS_URL, wait_until="networkidle")
                
                # Look for upload button or drag area
                upload_input = page.locator('input[type="file"]').first
                await upload_input.set_input_files(image_path)
                
                # Wait for results
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(5000)

                # Try to extract visual matches
                # Google Lens UI changes frequently, so this is best-effort
                links = await page.query_selector_all("a[href*='imgres'], a[data-action-url]")
                
                for link in links[:10]:
                    try:
                        href = await link.get_attribute("href") or ""
                        title_el = await link.query_selector("div, span, h3")
                        title = await title_el.inner_text() if title_el else ""
                        
                        img_el = await link.query_selector("img")
                        thumb = await img_el.get_attribute("src") if img_el else ""

                        if href and not href.startswith("javascript"):
                            results.append(ProviderSearchResult(
                                source_url=href,
                                page_title=title or "Google Lens match",
                                thumbnail_url=thumb or "",
                                match_type="similar",
                                similarity_score=0.7,
                                confidence=0.6,
                                metadata={"provider": "google_lens"},
                            ))
                    except Exception:
                        continue

                # Also try to extract text matches / entity cards
                text_elements = await page.query_selector_all("[data-text-content], .UAiK1e")
                extracted_texts = []
                for el in text_elements[:5]:
                    try:
                        text = await el.inner_text()
                        if text.strip():
                            extracted_texts.append(text.strip())
                    except Exception:
                        continue

                if extracted_texts and not results:
                    results.append(ProviderSearchResult(
                        source_url=page.url,
                        page_title="Google Lens - Text/Entity Detection",
                        match_type="text",
                        similarity_score=0.5,
                        confidence=0.4,
                        extracted_text="; ".join(extracted_texts),
                        metadata={"provider": "google_lens", "type": "text_extraction"},
                    ))

                await browser.close()

            logger.info("google_lens_search_complete", result_count=len(results))
        except ImportError:
            logger.warning("playwright_not_installed")
        except Exception as e:
            logger.error("google_lens_search_failed", error=str(e))

        return results

    async def healthcheck(self) -> dict:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://lens.google.com")
                return {
                    "healthy": resp.status_code == 200,
                    "message": "Google Lens is reachable",
                }
        except Exception as e:
            return {"healthy": False, "message": str(e)}

    def enabled(self, settings) -> bool:
        return getattr(settings, "GOOGLE_LENS_ENABLED", False)
