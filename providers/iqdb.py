import httpx
from bs4 import BeautifulSoup
import structlog
from providers.base import BaseProvider
from shared.schemas import ProviderSearchResult

logger = structlog.get_logger()


class IQDBProvider(BaseProvider):
    name = "iqdb"
    experimental = False
    description = "IQDB multi-service image search (anime, artwork, photos)"

    IQDB_URL = "https://iqdb.org/"
    TIMEOUT = 30

    async def search(self, image_path: str, context: dict) -> list[ProviderSearchResult]:
        results = []
        try:
            with open(image_path, "rb") as f:
                files = {"file": ("image.jpg", f, "image/jpeg")}
                async with httpx.AsyncClient(timeout=self.TIMEOUT, follow_redirects=True) as client:
                    resp = await client.post(self.IQDB_URL, files=files)
                    resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            tables = soup.find_all("table")

            for table in tables:
                # Skip the "Your image" table and "No relevant matches" tables
                header = table.find("th")
                if not header:
                    continue
                header_text = header.get_text(strip=True).lower()
                if "your image" in header_text or "no relevant" in header_text:
                    continue

                # Find match info
                links = table.find_all("a")
                for link in links:
                    href = link.get("href", "")
                    if not href or href.startswith("#"):
                        continue
                    if href.startswith("//"):
                        href = "https:" + href

                    # Get similarity from table text
                    table_text = table.get_text()
                    similarity = 0.0
                    if "% similarity" in table_text:
                        try:
                            sim_text = table_text.split("% similarity")[0].split()[-1]
                            similarity = float(sim_text) / 100.0
                        except (ValueError, IndexError):
                            pass

                    # Get dimensions
                    img_tag = link.find("img")
                    title = img_tag.get("title", "") if img_tag else ""
                    thumb = img_tag.get("src", "") if img_tag else ""
                    if thumb and thumb.startswith("//"):
                        thumb = "https:" + thumb
                    elif thumb and thumb.startswith("/"):
                        thumb = f"https://iqdb.org{thumb}"

                    # Determine match type
                    match_type = "similar"
                    if similarity >= 0.95:
                        match_type = "exact"
                    elif "best match" in header_text:
                        match_type = "similar"

                    results.append(ProviderSearchResult(
                        source_url=href,
                        page_title=title or header_text,
                        thumbnail_url=thumb,
                        match_type=match_type,
                        similarity_score=similarity,
                        confidence=similarity * 0.75,
                        metadata={"provider": "iqdb", "header": header_text},
                    ))
                    break  # One result per table

            logger.info("iqdb_search_complete", result_count=len(results))
        except Exception as e:
            logger.error("iqdb_search_failed", error=str(e))

        return results

    async def healthcheck(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(self.IQDB_URL)
                return {
                    "healthy": resp.status_code == 200,
                    "message": f"IQDB responded with {resp.status_code}",
                }
        except Exception as e:
            return {"healthy": False, "message": str(e)}

    def enabled(self, settings) -> bool:
        return getattr(settings, "IQDB_ENABLED", True)
