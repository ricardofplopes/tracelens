# 🔍 TraceLens

**Self-hosted image investigation platform** — uses local AI (Ollama) and multiple reverse image search engines to thoroughly analyze and trace images.

![Status](https://img.shields.io/badge/status-MVP-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## What It Does

TraceLens accepts an image (upload or URL) and runs a comprehensive investigation pipeline:

1. **Ingests** the image and generates normalized variants (resized, cropped, grayscale, sharpened)
2. **Extracts features** — SHA-256, perceptual hashes (pHash, dHash, aHash), ORB keypoints, color histograms, EXIF metadata, OCR text
3. **Analyzes with AI** — uses Ollama vision models for captioning, entity extraction, landmark/brand detection
4. **Searches** multiple reverse image search engines in parallel (10 providers)
5. **Scores and ranks** results using perceptual similarity, text overlap, entity matching
6. **Generates a report** with AI-synthesized findings
7. **Exports** results as PDF, JSON, or HTML reports

Supports **batch processing** (multiple images at once) and **scheduled re-checks** (periodic re-investigation).

## Architecture

```
┌────────────┐    ┌────────────┐    ┌────────────┐
│  Frontend   │───▶│  Backend    │───▶│   Redis    │
│  (Next.js)  │    │  (FastAPI)  │    │  (broker)  │
└────────────┘    └─────┬──────┘    └─────┬──────┘
                        │                  │
                   ┌────▼──────┐    ┌─────▼──────┐
                   │ PostgreSQL │    │   Worker    │
                   │   (data)   │    │  (Celery)   │
                   └───────────┘    └──┬───┬─────┘
                                       │   │
                              ┌────────▼┐ ┌▼────────┐
                              │ Ollama   │ │Providers │
                              │ (LLM)   │ │(search)  │
                              └─────────┘ └─────────┘
```

| Service    | Technology         | Purpose                              |
|------------|--------------------|--------------------------------------|
| Frontend   | Next.js 14 + Tailwind | Upload UI, job status, results dashboard |
| Backend    | FastAPI + SQLAlchemy | REST API, file handling, database     |
| Worker     | Celery + Redis     | Async pipeline execution              |
| Database   | PostgreSQL 16      | Job data, features, results           |
| Cache      | Redis 7            | Task queue, result backend            |
| AI Runtime | Ollama             | Local LLM for vision + text analysis  |

## Search Providers

| Provider        | Type    | Status       | Method                     |
|-----------------|---------|--------------|----------------------------|
| IQDB            | Stable  | ✅ Enabled   | HTTP multipart upload      |
| SauceNAO        | Stable  | ✅ Enabled   | HTTP API (optional key)    |
| Wikimedia       | Stable  | ✅ Enabled   | MediaWiki API              |
| Web Search      | Stable  | ✅ Enabled   | DuckDuckGo HTML fallback   |
| Social Media    | Stable  | ✅ Enabled   | DuckDuckGo site: search (FB, IG, X, etc.) |
| Bing Visual     | Stable  | ✅ Enabled   | Playwright browser automation |
| FaceCheck.ID    | Experimental | ✅ Enabled | Face recognition search (social media) |
| TinEye          | Experimental | ✅ Enabled | Playwright browser automation |
| Google Lens     | Experimental | ✅ Enabled | Playwright browser automation |
| Yandex Images   | Experimental | ✅ Enabled | Playwright browser automation |
| FB Direct Lookup| Stable  | ✅ Auto      | Filename pattern → verified URL |

### Facebook/Instagram Image Lookup

TraceLens has multiple strategies for finding images on social media:

1. **FB Direct Lookup** — Detects Facebook filename patterns, constructs photo/profile URLs, fetches OG image, and verifies match via perceptual hash comparison. Produces verified results when possible.
2. **FaceCheck.ID** — Face recognition reverse image search specifically designed for finding people on social media (Facebook, Instagram, LinkedIn, Twitter, TikTok).
3. **Bing Visual Search** — Microsoft has deep integration with Facebook/Instagram content and indexes public posts effectively.
4. **TinEye** — Reverse image search that may find exact matches on social platforms.
5. **Social Media Provider** — Text-based search across Facebook, Instagram, LinkedIn, Twitter, Pinterest, Reddit, TikTok via DuckDuckGo `site:` queries. Uses person-specific AI-generated search terms.
6. **Google Lens** — May find visually similar images that appear on social platforms.

> **Note**: Private Facebook/Instagram posts are not accessible to any reverse image search engine. Results depend on the profile's public visibility.

## Quick Start

### Prerequisites

- Docker and Docker Compose
- ~8GB disk space (for Ollama models)
- GPU recommended (but not required) for Ollama

### 1. Clone and configure

```bash
git clone https://github.com/ricardofplopes/tracelens.git
cd tracelens
cp .env.example .env
```

### 2. Start all services

```bash
docker compose up -d
```

### 3. Pull Ollama models

```bash
# Vision model (required for image analysis)
docker compose exec ollama ollama pull llava

# Text model (required for search term generation and reports)
docker compose exec ollama ollama pull llama3.2
```

### 4. Open the UI

Navigate to [http://localhost:3000](http://localhost:3000)

## Configuration

All configuration is via `.env` file. Key variables:

```env
# Ollama
OLLAMA_HOST=http://ollama:11434
OLLAMA_VISION_MODEL=llava           # or llava:13b, bakllava, etc.
OLLAMA_TEXT_MODEL=llama3.2          # or mistral, phi3, etc.

# Provider toggles
IQDB_ENABLED=true
SAUCENAO_ENABLED=true
WIKIMEDIA_ENABLED=true
WEB_SEARCH_ENABLED=true
GOOGLE_LENS_ENABLED=false           # Experimental
YANDEX_ENABLED=false                # Experimental

# Optional API keys
SAUCENAO_API_KEY=                   # Get from saucenao.com (optional, improves rate limits)
```

## API Endpoints

| Method | Endpoint                  | Description              |
|--------|---------------------------|--------------------------|
| POST   | `/api/jobs`               | Create investigation job |
| GET    | `/api/jobs/{id}`          | Get job details          |
| GET    | `/api/jobs/{id}/results`  | Get search results       |
| GET    | `/api/providers`          | List providers           |
| POST   | `/api/providers/test`     | Test provider health     |
| GET    | `/api/health`             | System health check      |

## Project Structure

```
tracelens/
├── backend/           # FastAPI REST API
│   ├── app/
│   │   ├── api/       # Route handlers
│   │   ├── models/    # SQLAlchemy ORM models
│   │   ├── services/  # Business logic
│   │   └── core/      # Config, database, logging
│   └── tests/         # Pytest tests
├── worker/            # Celery task pipeline
├── providers/         # Search provider adapters
├── frontend/          # Next.js web UI
├── shared/            # Shared schemas
├── docs/              # Documentation
└── docker-compose.yml
```

## Ollama Model Setup

TraceLens uses two types of models:

### Vision Model (default: `llava`)

Used for image analysis, captioning, and entity extraction.

```bash
docker compose exec ollama ollama pull llava
```

Alternative vision models: `llava:13b`, `bakllava`, `llava-llama3`

### Text Model (default: `llama3.2`)

Used for search term generation and report synthesis.

```bash
docker compose exec ollama ollama pull llama3.2
```

Alternative text models: `mistral`, `phi3`, `gemma2`

### Running without GPU

Ollama works on CPU, but analysis will be slower. Remove the GPU reservation from `docker-compose.yml`:

```yaml
# Comment out or remove:
# deploy:
#   resources:
#     reservations:
#       devices:
#         - driver: nvidia
#           count: all
#           capabilities: [gpu]
```

## Provider Limitations

### Stable Providers
- **IQDB**: Best for anime/artwork. Rate limited. May return no results for photos.
- **SauceNAO**: Best with API key (free tier: 6 searches/30s). Covers many databases.
- **Wikimedia**: Text/entity search only — doesn't do visual matching. Best for known subjects.
- **Web Search**: Falls back to DuckDuckGo text search. Depends on OCR and AI-generated terms.

### Experimental Providers
- **Google Lens**: Uses browser automation (Playwright). Google actively blocks automation — may break at any time. Disabled by default.
- **Yandex Images**: Uses browser automation. UI selectors may change. Disabled by default.

> ⚠️ Browser-based providers are fragile by nature. They are provided as best-effort experimental features.

## Legal & Terms Note

⚠️ **Important**: This tool is for legitimate research and investigation purposes only.

- Browser automation providers (Google Lens, Yandex) may violate those services' Terms of Service. They are disabled by default and labeled as experimental.
- Respect rate limits of all search providers.
- This tool does not store or distribute copyrighted content — it only stores search result metadata and thumbnails.
- Users are responsible for ensuring their use complies with applicable laws and service terms.

## MVP Scope

### ✅ What's included
- Working upload → analysis → search → report pipeline
- 4 stable search providers (IQDB, SauceNAO, Wikimedia, Web Search)
- 2 experimental browser providers (Google Lens, Yandex)
- Ollama integration for vision analysis and report synthesis
- Feature extraction (hashes, EXIF, OCR, ORB keypoints)
- Image variant generation for cross-provider matching
- Confidence scoring and duplicate clustering
- Modern dark-mode UI with upload, progress tracking, and results
- Docker Compose one-command startup

### 🔮 Future improvements
- User accounts and investigation history
- S3/MinIO file storage
- Custom provider weights via settings UI
- Drag-and-drop provider priority reordering

### ✅ Recently added
- Real-time job status updates (SSE + polling fallback)
- TinEye reverse image search integration
- Bing Visual Search provider
- Facebook/Instagram image lookup (direct URL + Bing indexing)
- Export reports (PDF, JSON, HTML)
- Result caching across jobs (SHA-256 dedup)
- Scheduled re-checks (hourly Celery Beat scan)
- Batch image processing (multi-file upload)
- Image validation and security (magic bytes, GPS stripping)
- Job deletion with cascade cleanup
- Animated progress stepper with elapsed time

## Development

### Run tests
```bash
cd backend
pip install pytest pytest-asyncio
python -m pytest tests/ -v
```

### Code formatting
```bash
pip install black ruff
black backend/ worker/ providers/ shared/
ruff check backend/ worker/ providers/ shared/
```

## License

MIT
