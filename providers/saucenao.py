import httpx
import structlog
from providers.base import BaseProvider
from shared.schemas import ProviderSearchResult

logger = structlog.get_logger()


class SauceNAOProvider(BaseProvider):
    name = "saucenao"
    experimental = False
    description = "SauceNAO reverse image search API"

    API_URL = "https://saucenao.com/search.php"
    TIMEOUT = 30

    async def search(self, image_path: str, context: dict) -> list[ProviderSearchResult]:
        results = []
        api_key = context.get("saucenao_api_key", "")

        try:
            params = {
                "output_type": "2",  # JSON
                "numres": "10",
                "db": "999",  # All databases
            }
            if api_key:
                params["api_key"] = api_key

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            with open(image_path, "rb") as f:
                files = {"file": ("image.jpg", f, "image/jpeg")}
                async with httpx.AsyncClient(timeout=self.TIMEOUT, follow_redirects=True, headers=headers) as client:
                    resp = await client.post(self.API_URL, params=params, files=files)
                    resp.raise_for_status()

            data = resp.json()
            
            if "results" not in data:
                logger.warning("saucenao_no_results", response_header=data.get("header", {}))
                return results

            for item in data["results"]:
                header = item.get("header", {})
                result_data = item.get("data", {})

                similarity = float(header.get("similarity", 0)) / 100.0
                thumbnail = header.get("thumbnail", "")

                # Build source URL from various possible fields
                source_url = ""
                ext_urls = result_data.get("ext_urls", [])
                if ext_urls:
                    source_url = ext_urls[0]
                elif result_data.get("source"):
                    source_url = result_data["source"]

                # Build title
                title_parts = []
                if result_data.get("title"):
                    title_parts.append(result_data["title"])
                if result_data.get("member_name"):
                    title_parts.append(f"by {result_data['member_name']}")
                if result_data.get("author_name"):
                    title_parts.append(f"by {result_data['author_name']}")
                page_title = " ".join(title_parts) or header.get("index_name", "SauceNAO result")

                match_type = "exact" if similarity >= 0.90 else "similar"

                results.append(ProviderSearchResult(
                    source_url=source_url,
                    page_title=page_title,
                    thumbnail_url=thumbnail,
                    match_type=match_type,
                    similarity_score=similarity,
                    confidence=similarity * 0.80,
                    extracted_text=result_data.get("material", ""),
                    metadata={
                        "provider": "saucenao",
                        "index_id": header.get("index_id"),
                        "index_name": header.get("index_name"),
                        **{k: v for k, v in result_data.items() if isinstance(v, (str, int, float))},
                    },
                ))

            logger.info("saucenao_search_complete", result_count=len(results))
        except Exception as e:
            logger.error("saucenao_search_failed", error=str(e))

        return results

    async def healthcheck(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://saucenao.com/")
                return {
                    "healthy": resp.status_code == 200,
                    "message": f"SauceNAO responded with {resp.status_code}",
                }
        except Exception as e:
            return {"healthy": False, "message": str(e)}

    def enabled(self, settings) -> bool:
        return getattr(settings, "SAUCENAO_ENABLED", True)
