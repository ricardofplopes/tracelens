import structlog
from providers.base import BaseProvider
from shared.schemas import ProviderSearchResult

logger = structlog.get_logger()


class FaceCheckProvider(BaseProvider):
    name = "facecheck"
    experimental = True
    description = "[Experimental] FaceCheck.ID face recognition search via browser automation"

    FACECHECK_URL = "https://facecheck.id"
    TIMEOUT = 90000  # Face search takes longer (30-90s)

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

                # Navigate to FaceCheck.ID
                logger.info("facecheck_navigating")
                await page.goto(self.FACECHECK_URL, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)

                # Look for file upload input
                upload_input = page.locator('input[type="file"]').first
                await upload_input.set_input_files(image_path)
                logger.info("facecheck_image_uploaded")
                await page.wait_for_timeout(3000)

                # Click search/upload button - try multiple selectors
                search_btn = None
                for selector in [
                    'button:has-text("Search")',
                    'button:has-text("search")',
                    'button[type="submit"]',
                    '#search-btn',
                    '.search-button',
                    'button:has-text("Upload")',
                    'a:has-text("Search Internet")',
                ]:
                    try:
                        btn = page.locator(selector).first
                        if await btn.is_visible(timeout=2000):
                            search_btn = btn
                            break
                    except Exception:
                        continue

                if search_btn:
                    await search_btn.click()
                    logger.info("facecheck_search_clicked")
                else:
                    # Try pressing Enter or submitting form
                    await page.keyboard.press("Enter")
                    logger.info("facecheck_enter_pressed")

                # Wait for results - FaceCheck takes 30-90 seconds
                # Look for result indicators
                try:
                    await page.wait_for_selector(
                        '.face-result, .result-card, .match-card, [class*="result"], [class*="match"], img[src*="face"]',
                        timeout=75000,
                    )
                except Exception:
                    # Maybe results loaded differently, check page content
                    logger.info("facecheck_waiting_for_results_timeout")

                await page.wait_for_timeout(5000)

                # Try to accept any consent/terms if they appear
                for consent_sel in ['button:has-text("Agree")', 'button:has-text("Accept")', 'button:has-text("I agree")']:
                    try:
                        consent_btn = page.locator(consent_sel).first
                        if await consent_btn.is_visible(timeout=1000):
                            await consent_btn.click()
                            await page.wait_for_timeout(3000)
                    except Exception:
                        pass

                # Extract results from the page
                results = await self._extract_results(page)

                await browser.close()

        except Exception as e:
            logger.error("facecheck_search_failed", error=str(e))

        return results

    async def _extract_results(self, page) -> list[ProviderSearchResult]:
        """Extract face match results from FaceCheck.ID results page."""
        results = []

        try:
            # Get page content for analysis
            content = await page.content()

            # Strategy 1: Look for result cards with links
            result_links = await page.locator('a[href*="facebook.com"], a[href*="instagram.com"], a[href*="linkedin.com"], a[href*="twitter.com"], a[href*="tiktok.com"]').all()

            for link in result_links[:20]:
                try:
                    href = await link.get_attribute("href")
                    text = await link.inner_text()
                    if href and ("facebook" in href or "instagram" in href or "linkedin" in href or "twitter" in href or "tiktok" in href):
                        # Try to get associated image
                        parent = link.locator("..")
                        img = parent.locator("img").first
                        thumb = ""
                        try:
                            thumb = await img.get_attribute("src") or ""
                        except Exception:
                            pass

                        results.append(ProviderSearchResult(
                            source_url=href,
                            page_title=text.strip()[:200] if text else f"Face match on {self._get_platform(href)}",
                            thumbnail_url=thumb,
                            match_type="face_match",
                            similarity_score=0.80,
                            confidence=0.75,
                            extracted_text=f"Face recognition match found on {self._get_platform(href)}",
                            metadata={"provider": "facecheck", "platform": self._get_platform(href)},
                        ))
                except Exception:
                    continue

            # Strategy 2: Look for any result containers with images and scores
            result_containers = await page.locator('[class*="result"], [class*="match"], .face-card').all()

            for container in result_containers[:15]:
                try:
                    # Get link from container
                    link = container.locator("a").first
                    href = await link.get_attribute("href") if link else None
                    if not href or href.startswith("#") or href.startswith("javascript"):
                        continue

                    # Skip non-social/non-relevant links
                    if "facecheck.id" in href:
                        continue

                    text = await container.inner_text()
                    img = container.locator("img").first
                    thumb = ""
                    try:
                        thumb = await img.get_attribute("src") or ""
                    except Exception:
                        pass

                    # Check for percentage/score in text
                    import re
                    score_match = re.search(r'(\d{1,3})%', text)
                    score = int(score_match.group(1)) / 100.0 if score_match else 0.70

                    results.append(ProviderSearchResult(
                        source_url=href,
                        page_title=text.strip()[:150] if text else "Face match",
                        thumbnail_url=thumb,
                        match_type="face_match",
                        similarity_score=score,
                        confidence=score * 0.9,
                        extracted_text=f"Face recognition match (score: {score:.0%})",
                        metadata={"provider": "facecheck", "score_raw": score},
                    ))
                except Exception:
                    continue

            # Strategy 3: Extract all external links with social media domains
            if not results:
                all_links = await page.locator("a[href]").all()
                for link in all_links[:50]:
                    try:
                        href = await link.get_attribute("href")
                        if not href:
                            continue
                        social_domains = ["facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com", "tiktok.com", "youtube.com"]
                        if any(domain in href for domain in social_domains):
                            text = await link.inner_text()
                            results.append(ProviderSearchResult(
                                source_url=href,
                                page_title=text.strip()[:200] if text else f"Match on {self._get_platform(href)}",
                                thumbnail_url="",
                                match_type="face_match",
                                similarity_score=0.65,
                                confidence=0.60,
                                extracted_text=f"Potential face match on {self._get_platform(href)}",
                                metadata={"provider": "facecheck", "platform": self._get_platform(href)},
                            ))
                    except Exception:
                        continue

        except Exception as e:
            logger.error("facecheck_extraction_failed", error=str(e))

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in results:
            if r.source_url not in seen_urls:
                seen_urls.add(r.source_url)
                unique_results.append(r)

        logger.info("facecheck_results_extracted", count=len(unique_results))
        return unique_results[:15]

    def _get_platform(self, url: str) -> str:
        """Get readable platform name from URL."""
        if "facebook" in url: return "Facebook"
        if "instagram" in url: return "Instagram"
        if "linkedin" in url: return "LinkedIn"
        if "twitter" in url or "x.com" in url: return "Twitter/X"
        if "tiktok" in url: return "TikTok"
        if "youtube" in url: return "YouTube"
        return "Social Media"

    async def healthcheck(self) -> dict:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(self.FACECHECK_URL)
                return {
                    "healthy": resp.status_code == 200,
                    "message": "FaceCheck.ID is reachable",
                }
        except Exception as e:
            return {"healthy": False, "message": str(e)}

    def enabled(self, settings) -> bool:
        return getattr(settings, "FACECHECK_ENABLED", True)
