# TraceLens Architecture

## Overview

TraceLens is a self-hosted image investigation platform composed of 6 Docker services working together to analyze images and find their origins across the web.

## Services

### Backend (FastAPI)
- REST API serving the frontend
- Handles image uploads and URL downloads
- Manages job lifecycle and database operations
- Serves static uploaded files

### Worker (Celery)
- Executes the 7-step investigation pipeline asynchronously
- Uses Redis as message broker
- Manages provider execution with error isolation

### Providers
- Pluggable adapter pattern (`BaseProvider` abstract class)
- Each provider implements `search()`, `healthcheck()`, `enabled()`
- Results normalized to `ProviderSearchResult` schema
- Failures are isolated — one provider failing doesn't affect others

### Database (PostgreSQL)
- 6 tables: jobs, assets, extracted_features, provider_runs, candidate_results, final_reports
- Async access from backend via SQLAlchemy + asyncpg
- Sync access from worker via SQLAlchemy + psycopg2

### Ollama (LLM Runtime)
- Runs vision and text models locally
- Vision model: image captioning, entity extraction
- Text model: search term generation, report synthesis
- Accessed via HTTP API

## Pipeline Steps

1. **Ingest** — Store original, generate variants (resized, cropped, grayscale, sharpened, recompressed)
2. **Extract** — SHA-256, perceptual hashes, color histogram, ORB keypoints, EXIF, OCR
3. **Analyze** — Ollama vision model describes the image, extracts entities
4. **Search Terms** — Ollama text model generates optimized search queries
5. **Providers** — Run enabled providers in sequence with error isolation
6. **Score** — Weighted scoring: hash similarity + text overlap + entity overlap + source confidence
7. **Report** — Ollama synthesizes final investigation report

## Scoring Algorithm

Confidence = weighted combination of:
- Perceptual hash distance (weight: 3.0)
- Exact SHA-256 match (weight: 5.0)
- OCR/text overlap via SequenceMatcher (weight: 1.5)
- Provider's own similarity score (weight: 2.0)
- Source confidence multiplier (0.5-0.9 depending on provider)

Final score: `raw_score * 0.7 + source_confidence * 0.3`

## Data Model

```
jobs ──1:N──▶ assets
jobs ──1:1──▶ extracted_features
jobs ──1:N──▶ provider_runs ──1:N──▶ candidate_results
jobs ──1:1──▶ final_reports
```
