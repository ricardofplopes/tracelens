from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://tracelens:tracelens_secret@localhost:5432/tracelens"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    
    # Ollama
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_VISION_MODEL: str = "llava"
    OLLAMA_TEXT_MODEL: str = "llama3.2"
    
    # Upload
    UPLOAD_DIR: str = "/app/uploads"
    MAX_UPLOAD_SIZE_MB: int = 50
    
    # Providers
    SAUCENAO_API_KEY: Optional[str] = None
    GOOGLE_LENS_ENABLED: bool = False
    YANDEX_ENABLED: bool = False
    IQDB_ENABLED: bool = True
    SAUCENAO_ENABLED: bool = True
    WIKIMEDIA_ENABLED: bool = True
    WEB_SEARCH_ENABLED: bool = True
    
    # Playwright
    PLAYWRIGHT_TIMEOUT: int = 30000

    # Rate limiting
    RATE_LIMIT_UPLOADS: int = 10  # uploads per minute per IP
    RATE_LIMIT_API: int = 60  # API calls per minute per IP

    # Provider priority (higher = shown first, affects score weighting)
    PROVIDER_PRIORITIES: str = "google_lens:10,yandex:9,saucenao:8,iqdb:7,wikimedia:6,web_search:5"

    # Concurrency
    MAX_CONCURRENT_PROVIDERS: int = 4
    
    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
