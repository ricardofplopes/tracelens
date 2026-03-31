from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


class JobCreate(BaseModel):
    source_url: Optional[str] = None


class JobResponse(BaseModel):
    id: uuid.UUID
    status: str
    image_source: str
    source_url: Optional[str] = None
    original_filename: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AssetResponse(BaseModel):
    id: uuid.UUID
    variant: str
    file_path: str
    width: Optional[int] = None
    height: Optional[int] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None

    model_config = {"from_attributes": True}


class FeatureResponse(BaseModel):
    sha256: Optional[str] = None
    phash: Optional[str] = None
    dhash: Optional[str] = None
    ahash: Optional[str] = None
    color_histogram: Optional[dict] = None
    orb_descriptor_count: Optional[int] = None
    dimensions: Optional[str] = None
    mime_type: Optional[str] = None
    exif_data: Optional[dict] = None
    ocr_text: Optional[str] = None

    model_config = {"from_attributes": True}


class CandidateResultResponse(BaseModel):
    id: uuid.UUID
    provider_name: str = ""
    source_url: Optional[str] = None
    page_title: Optional[str] = None
    thumbnail_url: Optional[str] = None
    match_type: str = "similar"
    similarity_score: Optional[float] = None
    confidence: Optional[float] = None
    extracted_text: Optional[str] = None
    metadata: Optional[dict] = Field(None, alias="extra_data")

    model_config = {"from_attributes": True, "populate_by_name": True}


class ProviderRunResponse(BaseModel):
    id: uuid.UUID
    provider_name: str
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    result_count: int = 0

    model_config = {"from_attributes": True}


class ReportResponse(BaseModel):
    summary: Optional[str] = None
    ai_description: Optional[str] = None
    entities: Optional[dict] = None
    search_terms: Optional[dict] = None
    cluster_count: int = 0
    top_matches: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class JobDetailResponse(BaseModel):
    job: JobResponse
    assets: list[AssetResponse] = []
    features: Optional[FeatureResponse] = None
    provider_runs: list[ProviderRunResponse] = []
    report: Optional[ReportResponse] = None


class JobResultsResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    candidates: list[CandidateResultResponse] = []
    report: Optional[ReportResponse] = None
    provider_runs: list[ProviderRunResponse] = []


class ProviderInfo(BaseModel):
    name: str
    enabled: bool
    experimental: bool = False
    description: str = ""


class ProviderTestResult(BaseModel):
    name: str
    healthy: bool
    message: str = ""
    latency_ms: Optional[float] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    database: bool = False
    redis: bool = False
    ollama: bool = False


class ProviderSearchResult(BaseModel):
    """Normalized result from any provider."""
    source_url: str = ""
    page_title: str = ""
    thumbnail_url: str = ""
    match_type: str = "similar"  # exact, similar, text, entity
    similarity_score: float = 0.0
    confidence: float = 0.0
    extracted_text: str = ""
    metadata: dict = Field(default_factory=dict)
