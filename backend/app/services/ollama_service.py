import base64
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from backend.app.core.config import settings

logger = structlog.get_logger()


class OllamaService:
    """Service for interacting with Ollama LLM for image analysis."""

    def __init__(self):
        self.host = settings.OLLAMA_HOST
        self.vision_model = settings.OLLAMA_VISION_MODEL
        self.text_model = settings.OLLAMA_TEXT_MODEL
        self.timeout = 600.0

    def _encode_image(self, image_path: str) -> str:
        """Encode image to base64 for Ollama API."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout)),
    )
    async def _generate(self, model: str, prompt: str, images: list[str] | None = None) -> str:
        """Call Ollama generate API."""
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 1024,
            },
        }
        if images:
            payload["images"] = images

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.host}/api/generate",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")

    async def analyze_image(self, image_path: str) -> dict:
        """Run comprehensive vision analysis on an image.
        
        Returns dict with description, entities, landmarks, brands, objects.
        """
        image_b64 = self._encode_image(image_path)
        
        prompt = """Analyze this image in detail. Provide:
1. **Description**: A detailed description of what you see in the image.
2. **Entities**: List any people, characters, or named entities you can identify.
3. **Objects**: List all notable objects visible in the image.
4. **Brands/Logos**: List any visible brand names, logos, or trademarks.
5. **Landmarks**: List any recognizable landmarks or locations.
6. **Text**: List any visible text in the image.
7. **Style**: Describe the visual style (photo, illustration, screenshot, meme, etc.).

Format your response as structured text with clear labels for each category."""

        try:
            response = await self._generate(
                model=self.vision_model,
                prompt=prompt,
                images=[image_b64],
            )
            
            result = self._parse_analysis(response)
            result["raw_description"] = response
            logger.info("ollama_vision_analysis_complete", model=self.vision_model)
            return result
        except Exception as e:
            logger.error("ollama_vision_analysis_failed", error=str(e))
            return {
                "raw_description": "",
                "description": "",
                "entities": [],
                "objects": [],
                "brands": [],
                "landmarks": [],
                "text_found": [],
                "style": "",
                "error": str(e),
            }

    async def generate_search_terms(self, analysis: dict, ocr_text: str | None = None, exif_data: dict | None = None) -> list[str]:
        """Generate optimized search terms based on all collected evidence.
        
        Uses the text model to synthesize search queries from vision analysis, OCR, and metadata.
        """
        evidence_parts = []
        
        if analysis.get("raw_description"):
            evidence_parts.append(f"Image description: {analysis['raw_description'][:500]}")
        
        if analysis.get("entities"):
            evidence_parts.append(f"Entities found: {', '.join(analysis['entities'])}")
        
        if analysis.get("brands"):
            evidence_parts.append(f"Brands/logos: {', '.join(analysis['brands'])}")
        
        if analysis.get("landmarks"):
            evidence_parts.append(f"Landmarks: {', '.join(analysis['landmarks'])}")
        
        if ocr_text:
            evidence_parts.append(f"OCR text: {ocr_text[:300]}")
        
        if exif_data:
            camera = exif_data.get("Model", "")
            date = exif_data.get("DateTimeOriginal", "")
            if camera:
                evidence_parts.append(f"Camera: {camera}")
            if date:
                evidence_parts.append(f"Date taken: {date}")

        evidence = "\n".join(evidence_parts)

        # Detect if this is a person/portrait photo for social-media-oriented queries
        is_person_photo = any(
            kw in (analysis.get("raw_description", "") or "").lower()
            for kw in ["person", "man", "woman", "face", "portrait", "selfie", "headshot", "profile"]
        )

        if is_person_photo:
            prompt = f"""Based on the following evidence about a person's photo, generate 5-7 search queries to find this person or this image online, especially on social media.

Focus on:
- The person's distinguishing features (apparent age, hair, facial features, glasses, etc.)
- Any name, text, or username visible
- The setting/context (professional photo, casual, event, etc.)
- Include at least 2 queries specifically targeting social media (e.g., "site:facebook.com" or "site:instagram.com" variations)
- Include a physical description query that could match social media profiles

Evidence:
{evidence}

Generate search queries (one per line, no numbering or bullets):"""
        else:
            prompt = f"""Based on the following evidence about an image, generate 3-5 specific search queries that would help find this image or similar images online. Each query should be on a separate line.

Focus on:
- Specific identifiable elements (people, brands, landmarks)
- Unique text or phrases visible
- Distinctive visual features
- Context clues

Evidence:
{evidence}

Generate search queries (one per line, no numbering or bullets):"""

        try:
            response = await self._generate(model=self.text_model, prompt=prompt)
            terms = [line.strip() for line in response.strip().split("\n") if line.strip()]
            # Clean up: remove numbering, bullets, quotes
            cleaned = []
            for term in terms:
                term = term.lstrip("0123456789.-) ").strip('"\'')
                if term and len(term) > 3:
                    cleaned.append(term)
            logger.info("search_terms_generated", count=len(cleaned))
            return cleaned[:7 if is_person_photo else 5]
        except Exception as e:
            logger.error("search_term_generation_failed", error=str(e))
            # Fallback: use entities and OCR text directly
            fallback = []
            if analysis.get("entities"):
                fallback.extend(analysis["entities"][:2])
            if analysis.get("brands"):
                fallback.extend(analysis["brands"][:2])
            if ocr_text:
                fallback.append(ocr_text[:50])
            return fallback[:5]

    async def synthesize_report(self, analysis: dict, candidates: list[dict], features: dict) -> str:
        """Generate a final synthesis report combining all evidence.
        
        Uses the text model to produce a human-readable summary.
        """
        evidence_parts = []
        
        if analysis.get("raw_description"):
            evidence_parts.append(f"AI Vision Analysis:\n{analysis['raw_description'][:600]}")
        
        if features.get("ocr_text"):
            evidence_parts.append(f"OCR Text Found:\n{features['ocr_text'][:300]}")
        
        if features.get("exif_data"):
            exif_summary = {k: v for k, v in features["exif_data"].items() 
                          if k in ("Model", "Make", "DateTimeOriginal", "GPSLatitude", "GPSLongitude", "Software")}
            if exif_summary:
                evidence_parts.append(f"EXIF Metadata:\n{exif_summary}")

        if candidates:
            top = candidates[:5]
            matches_text = "\n".join(
                f"- [{c.get('match_type', 'similar')}] {c.get('page_title', 'Untitled')} "
                f"(confidence: {c.get('confidence', 0):.0%}, source: {c.get('source_url', '')[:80]})"
                for c in top
            )
            evidence_parts.append(f"Top Search Matches:\n{matches_text}")

        evidence = "\n\n".join(evidence_parts)

        prompt = f"""You are an image investigation analyst. Based on the following evidence collected about an image, write a concise investigation summary report.

Include:
1. What the image appears to show
2. Key identifiable elements (people, places, brands, text)
3. What the reverse image search results suggest about the image's origin or context
4. Any notable metadata findings
5. Confidence assessment: how confident are we in the identification

Evidence:
{evidence}

Write a clear, professional summary (3-5 paragraphs):"""

        try:
            response = await self._generate(model=self.text_model, prompt=prompt)
            logger.info("synthesis_report_generated")
            return response.strip()
        except Exception as e:
            logger.error("synthesis_failed", error=str(e))
            return f"Report generation failed: {str(e)}. Raw analysis: {analysis.get('raw_description', 'N/A')}"

    def _parse_analysis(self, text: str) -> dict:
        """Parse structured analysis response into components."""
        result = {
            "description": "",
            "entities": [],
            "objects": [],
            "brands": [],
            "landmarks": [],
            "text_found": [],
            "style": "",
        }
        
        # Simple section-based parsing
        current_section = "description"
        section_map = {
            "description": "description",
            "entities": "entities",
            "objects": "objects",
            "brands": "brands",
            "logos": "brands",
            "landmarks": "landmarks",
            "locations": "landmarks",
            "text": "text_found",
            "style": "style",
        }
        
        lines = text.split("\n")
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # Check if this line is a section header
            lower = line_stripped.lower()
            for keyword, section in section_map.items():
                if keyword in lower and (":" in line_stripped or "**" in line_stripped):
                    current_section = section
                    # Check if content is on the same line after ':'
                    if ":" in line_stripped:
                        content = line_stripped.split(":", 1)[1].strip().strip("*").strip()
                        if content:
                            if isinstance(result[current_section], list):
                                items = [i.strip() for i in content.split(",")]
                                result[current_section].extend(items)
                            else:
                                result[current_section] = content
                    break
            else:
                # Content line
                content = line_stripped.lstrip("-•* ").strip()
                if content and content.lower() not in ("none", "n/a", "none visible", "none detected"):
                    if isinstance(result[current_section], list):
                        result[current_section].append(content)
                    else:
                        if result[current_section]:
                            result[current_section] += " " + content
                        else:
                            result[current_section] = content

        return result

    async def check_health(self) -> dict:
        """Check if Ollama is reachable and models are available."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.host}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                models = [m["name"] for m in data.get("models", [])]
                has_vision = any(self.vision_model in m for m in models)
                has_text = any(self.text_model in m for m in models)
                return {
                    "healthy": True,
                    "models_available": models,
                    "vision_model_ready": has_vision,
                    "text_model_ready": has_text,
                    "message": f"Ollama OK. Vision: {'✓' if has_vision else '✗'} Text: {'✓' if has_text else '✗'}",
                }
        except Exception as e:
            return {
                "healthy": False,
                "message": f"Ollama unreachable: {str(e)}",
            }
