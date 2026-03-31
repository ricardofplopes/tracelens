import uuid
import os
import shutil
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import httpx
import structlog

from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.models import Job, Asset, ExtractedFeature, ProviderRun, CandidateResult, FinalReport
from shared.schemas import (
    JobCreate, JobResponse, JobDetailResponse, JobResultsResponse,
    AssetResponse, FeatureResponse, ProviderRunResponse, CandidateResultResponse,
    ReportResponse, ProviderInfo, ProviderTestResult, HealthResponse,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    health = HealthResponse(status="ok")

    # Check database
    try:
        await db.execute(select(Job).limit(1))
        health.database = True
    except Exception:
        health.database = False

    # Check Redis
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL)
        r.ping()
        health.redis = True
    except Exception:
        health.redis = False

    # Check Ollama
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.OLLAMA_HOST}/api/tags")
            health.ollama = resp.status_code == 200
    except Exception:
        health.ollama = False

    return health


@router.post("/jobs", response_model=JobResponse)
async def create_job(
    file: UploadFile | None = File(None),
    source_url: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    if not file and not source_url:
        raise HTTPException(status_code=400, detail="Provide either a file upload or source_url")

    job_id = uuid.uuid4()
    job_dir = os.path.join(settings.UPLOAD_DIR, str(job_id))
    os.makedirs(job_dir, exist_ok=True)

    image_source = "upload" if file else "url"
    original_filename = None
    file_path = None

    if file:
        original_filename = file.filename
        ext = os.path.splitext(file.filename)[1] if file.filename else ".jpg"
        file_path = os.path.join(job_dir, f"original{ext}")
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    elif source_url:
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(source_url)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                ext = ".jpg"
                if "png" in content_type:
                    ext = ".png"
                elif "gif" in content_type:
                    ext = ".gif"
                elif "webp" in content_type:
                    ext = ".webp"
                file_path = os.path.join(job_dir, f"original{ext}")
                with open(file_path, "wb") as f:
                    f.write(resp.content)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to download image: {str(e)}")

    job = Job(
        id=job_id,
        status="pending",
        image_source=image_source,
        source_url=source_url,
        original_filename=original_filename,
    )
    db.add(job)

    if file_path:
        file_size = os.path.getsize(file_path)
        from PIL import Image
        try:
            with Image.open(file_path) as img:
                w, h = img.size
                mime = Image.MIME.get(img.format, "image/jpeg")
        except Exception:
            w, h, mime = None, None, "image/jpeg"

        asset = Asset(
            job_id=job_id,
            variant="original",
            file_path=file_path,
            width=w,
            height=h,
            mime_type=mime,
            file_size=file_size,
        )
        db.add(asset)

    await db.flush()

    # Dispatch celery task
    try:
        from worker.celery_app import celery_app
        celery_app.send_task("worker.tasks.run_pipeline", args=[str(job_id)])
        logger.info("job_dispatched", job_id=str(job_id))
    except Exception as e:
        logger.error("celery_dispatch_failed", error=str(e))
        job.status = "failed"
        job.error_message = f"Failed to dispatch job: {str(e)}"

    await db.commit()
    await db.refresh(job)
    return job


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
async def get_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Job)
        .options(
            selectinload(Job.assets),
            selectinload(Job.features),
            selectinload(Job.provider_runs),
            selectinload(Job.report),
        )
        .where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    features = job.features[0] if job.features else None

    return JobDetailResponse(
        job=JobResponse.model_validate(job),
        assets=[AssetResponse.model_validate(a) for a in job.assets],
        features=FeatureResponse.model_validate(features) if features else None,
        provider_runs=[ProviderRunResponse.model_validate(pr) for pr in job.provider_runs],
        report=ReportResponse.model_validate(job.report) if job.report else None,
    )


@router.get("/jobs/{job_id}/results", response_model=JobResultsResponse)
async def get_job_results(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Job)
        .options(
            selectinload(Job.candidates).selectinload(CandidateResult.provider_run),
            selectinload(Job.provider_runs),
            selectinload(Job.report),
        )
        .where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    candidates = []
    for c in job.candidates:
        cr = CandidateResultResponse.model_validate(c)
        cr.provider_name = c.provider_run.provider_name if c.provider_run else ""
        candidates.append(cr)

    # Sort by confidence descending
    candidates.sort(key=lambda x: x.confidence or 0, reverse=True)

    return JobResultsResponse(
        job_id=job.id,
        status=job.status,
        candidates=candidates,
        report=ReportResponse.model_validate(job.report) if job.report else None,
        provider_runs=[ProviderRunResponse.model_validate(pr) for pr in job.provider_runs],
    )


@router.get("/providers", response_model=list[ProviderInfo])
async def list_providers():
    providers = [
        ProviderInfo(name="iqdb", enabled=settings.IQDB_ENABLED, description="IQDB anime/artwork reverse search"),
        ProviderInfo(name="saucenao", enabled=settings.SAUCENAO_ENABLED, description="SauceNAO reverse image search"),
        ProviderInfo(name="wikimedia", enabled=settings.WIKIMEDIA_ENABLED, description="Wikimedia Commons search"),
        ProviderInfo(name="google_lens", enabled=settings.GOOGLE_LENS_ENABLED, experimental=True, description="[Experimental] Google Lens via browser automation"),
        ProviderInfo(name="yandex", enabled=settings.YANDEX_ENABLED, experimental=True, description="[Experimental] Yandex Images via browser automation"),
        ProviderInfo(name="web_search", enabled=settings.WEB_SEARCH_ENABLED, description="Generic web search using OCR + AI terms"),
    ]
    return providers


@router.post("/providers/test", response_model=list[ProviderTestResult])
async def test_providers():
    from providers import get_all_providers
    results = []
    for provider in get_all_providers(settings):
        try:
            health = await provider.healthcheck()
            results.append(ProviderTestResult(
                name=provider.name,
                healthy=health.get("healthy", False),
                message=health.get("message", ""),
                latency_ms=health.get("latency_ms"),
            ))
        except Exception as e:
            results.append(ProviderTestResult(
                name=provider.name,
                healthy=False,
                message=str(e),
            ))
    return results
