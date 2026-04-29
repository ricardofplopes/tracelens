# Copilot Instructions for TraceLens

## Architecture

TraceLens is a monorepo with 4 runtime services sharing code via volume mounts:

- **backend/** — FastAPI (async) serving REST API, uses SQLAlchemy with `asyncpg`
- **worker/** — Celery worker running the investigation pipeline synchronously (uses `psycopg2`, not asyncpg)
- **frontend/** — Next.js 14 (App Router, standalone output), proxies `/api/*` and `/uploads/*` to backend via rewrites
- **providers/** — Pluggable reverse-image-search adapters (imported by worker at runtime)
- **shared/** — Pydantic schemas shared between backend, worker, and providers

The backend dispatches jobs to Celery via a standalone `Celery(broker=url).send_task(...)` pattern — it does NOT import the worker module directly. The worker container has its own Dockerfile with Playwright/Chromium.

## Build & Run

```bash
# Start everything (first time pulls images + builds)
docker compose up -d --build

# Rebuild a single service after code changes
docker compose build <service>        # backend | worker | frontend
docker compose up -d --force-recreate <service>
```

## Tests

Tests live in `backend/tests/` and run inside the backend container:

```bash
# Full suite
docker compose exec backend python -m pytest backend/tests/ -q

# Single test file
docker compose exec backend python -m pytest backend/tests/test_scoring.py -q

# Single test
docker compose exec backend python -m pytest backend/tests/test_scoring.py::TestScoring::test_exact_hash_match -q
```

Async tests use `pytest-asyncio` with `asyncio_mode = auto` (configured in `backend/pytest.ini`).

## Key Conventions

### SQLAlchemy `metadata` Workaround
`CandidateResult.extra_data` maps to the DB column named `metadata` via `mapped_column("metadata", JSON)`. SQLAlchemy's `DeclarativeBase` reserves the `metadata` attribute name — always use `extra_data` in Python code.

### Worker Sync/Async Bridge
Celery doesn't support async. The worker calls async provider/Ollama code via `asyncio.new_event_loop()` + `loop.run_until_complete(...)`. The DB URL is rewritten from `postgresql+asyncpg://` to `postgresql+psycopg2://`.

### Provider Interface
All providers extend `providers/base.py::BaseProvider` and implement:
- `async search(image_path, context) -> list[ProviderSearchResult]`
- `async healthcheck() -> dict`
- `def enabled(settings) -> bool`

Provider results are normalized into `ProviderSearchResult` (from `shared/schemas.py`). Providers must fail gracefully — `safe_search()` wraps exceptions.

### Frontend API Access
The frontend uses **relative paths** (empty `API_BASE`). `next.config.js` rewrites `/api/*` → `http://backend:8000/api/*` inside Docker. Never use `NEXT_PUBLIC_*` env vars for API URLs — they're baked at build time.

### Ollama Connectivity
Containers reach the host's Ollama via `host.docker.internal:11434` (configured via `extra_hosts` in docker-compose). Timeouts are set high (600s HTTP, 1800s Celery soft limit) for CPU inference.

### Logging
Use `structlog` throughout Python code. Log with keyword arguments: `logger.info("event_name", key=value)`.

## Port Mapping

| Service    | Container Port | Host Port |
|-----------|---------------|-----------|
| PostgreSQL | 5432          | 5433      |
| Redis      | 6379          | 6380      |
| Backend    | 8000          | 8001      |
| Frontend   | 3000          | 3100      |

## Adding a New Provider

1. Create `providers/<name>.py` extending `BaseProvider`
2. Add `<NAME>_ENABLED: bool` to `backend/app/core/config.py`
3. Import and add to `ALL_PROVIDERS` in `providers/__init__.py`
4. Add the env var to `.env` and `.env.example`
