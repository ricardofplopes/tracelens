import uuid
import os
import json
import shutil
import asyncio
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import httpx
import structlog

from pydantic import BaseModel as PydanticBaseModel

from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.models import Job, Asset, ExtractedFeature, ProviderRun, CandidateResult, FinalReport
from backend.app.services.validation import validate_image, strip_gps_exif, get_mime_from_magic
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
    request: Request,
    file: UploadFile | None = File(None),
    source_url: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    if not file and not source_url:
        raise HTTPException(status_code=400, detail="Provide either a file upload or source_url")

    # Early Content-Length check before buffering
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"Upload exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB} MB")

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

    # Validate the saved image file
    if file_path:
        is_valid, error_msg = validate_image(file_path, max_size_mb=settings.MAX_UPLOAD_SIZE_MB)
        if not is_valid:
            shutil.rmtree(job_dir, ignore_errors=True)
            logger.warning("upload_validation_failed", error=error_msg)
            raise HTTPException(status_code=400, detail=f"Invalid image: {error_msg}")
        strip_gps_exif(file_path)

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
        from celery import Celery
        celery_client = Celery(broker=settings.CELERY_BROKER_URL)
        celery_client.send_task("worker.tasks.run_pipeline", args=[str(job_id)])
        logger.info("job_dispatched", job_id=str(job_id))
    except Exception as e:
        logger.error("celery_dispatch_failed", error=str(e))
        job.status = "failed"
        job.error_message = f"Failed to dispatch job: {str(e)}"

    await db.commit()
    await db.refresh(job)
    return job


@router.get("/jobs")
async def list_jobs(
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
    image_hash: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List all jobs with pagination."""
    query = select(Job).order_by(Job.created_at.desc())
    if status:
        query = query.where(Job.status == status)
    if image_hash:
        query = query.join(ExtractedFeature, ExtractedFeature.job_id == Job.id).where(
            ExtractedFeature.sha256 == image_hash
        )

    # Count total
    from sqlalchemy import func
    count_query = select(func.count()).select_from(Job)
    if status:
        count_query = count_query.where(Job.status == status)
    if image_hash:
        count_query = count_query.join(ExtractedFeature, ExtractedFeature.job_id == Job.id).where(
            ExtractedFeature.sha256 == image_hash
        )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)
    result = await db.execute(query.options(selectinload(Job.assets)))
    jobs = result.scalars().all()

    return {
        "jobs": [
            {
                **JobResponse.model_validate(j).model_dump(),
                "thumbnail": next(
                    (a.file_path.replace("/app/uploads", "/uploads") for a in j.assets if a.variant == "original"),
                    None,
                ),
            }
            for j in jobs
        ],
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
    }


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


@router.get("/jobs/{job_id}/export")
async def export_job(job_id: uuid.UUID, format: str = "json", db: AsyncSession = Depends(get_db)):
    """Export job results as JSON or HTML report."""
    from backend.app.services.export import export_json, export_html_report

    result = await db.execute(
        select(Job)
        .options(
            selectinload(Job.features),
            selectinload(Job.candidates),
            selectinload(Job.report),
        )
        .where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    features = job.features[0] if job.features else None
    candidates = sorted(job.candidates, key=lambda c: c.confidence or 0, reverse=True)

    if format == "json":
        content = export_json(job, features, candidates, job.report)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=tracelens-{job_id}.json"}
        )
    elif format in ("html", "pdf"):
        html = export_html_report(job, features, candidates, job.report)
        return Response(
            content=html,
            media_type="text/html",
            headers={"Content-Disposition": f"attachment; filename=tracelens-{job_id}.html"}
        )
    else:
        raise HTTPException(status_code=400, detail="Format must be 'json' or 'html'")


@router.get("/providers", response_model=list[ProviderInfo])
async def list_providers():
    from backend.app.services.provider_priority import get_provider_priorities

    priorities = get_provider_priorities(settings)
    providers = [
        ProviderInfo(name="iqdb", enabled=settings.IQDB_ENABLED, description="IQDB anime/artwork reverse search", priority=priorities.get("iqdb", 5)),
        ProviderInfo(name="saucenao", enabled=settings.SAUCENAO_ENABLED, description="SauceNAO reverse image search", priority=priorities.get("saucenao", 5)),
        ProviderInfo(name="wikimedia", enabled=settings.WIKIMEDIA_ENABLED, description="Wikimedia Commons search", priority=priorities.get("wikimedia", 5)),
        ProviderInfo(name="google_lens", enabled=settings.GOOGLE_LENS_ENABLED, experimental=True, description="[Experimental] Google Lens via browser automation", priority=priorities.get("google_lens", 5)),
        ProviderInfo(name="bing_visual", enabled=settings.BING_VISUAL_ENABLED, description="Bing Visual Search - strong social media indexing", priority=priorities.get("bing_visual", 5)),
        ProviderInfo(name="yandex", enabled=settings.YANDEX_ENABLED, experimental=True, description="[Experimental] Yandex Images via browser automation", priority=priorities.get("yandex", 5)),
        ProviderInfo(name="web_search", enabled=settings.WEB_SEARCH_ENABLED, description="Generic web search using OCR + AI terms", priority=priorities.get("web_search", 5)),
        ProviderInfo(name="social_media", enabled=settings.SOCIAL_MEDIA_ENABLED, description="Social media search (Facebook, Instagram, LinkedIn, etc.)", priority=priorities.get("social_media", 5)),
        ProviderInfo(name="tineye", enabled=settings.TINEYE_ENABLED, experimental=True, description="[Experimental] TinEye reverse image search via browser", priority=priorities.get("tineye", 5)),
    ]
    # Sort by priority descending
    providers.sort(key=lambda x: x.priority, reverse=True)
    return providers


@router.get("/ollama/models")
async def list_ollama_models():
    """Proxy Ollama's model list."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{settings.OLLAMA_HOST}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = []
            for m in data.get("models", []):
                models.append({
                    "name": m.get("name", ""),
                    "size": m.get("size", 0),
                    "modified_at": m.get("modified_at", ""),
                    "details": m.get("details", {}),
                })
            return {
                "models": models,
                "current_vision_model": settings.OLLAMA_VISION_MODEL,
                "current_text_model": settings.OLLAMA_TEXT_MODEL,
            }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Cannot reach Ollama: {str(e)}")


@router.post("/providers/test", response_model=list[ProviderTestResult])
async def test_providers():
    from providers import get_all_providers
    import time
    results = []
    for provider in get_all_providers(settings):
        try:
            start = time.time()
            health = await provider.healthcheck()
            latency_ms = round((time.time() - start) * 1000)
            results.append(ProviderTestResult(
                name=provider.name,
                healthy=health.get("healthy", False),
                message=health.get("message", ""),
                latency_ms=latency_ms,
            ))
        except Exception as e:
            results.append(ProviderTestResult(
                name=provider.name,
                healthy=False,
                message=str(e),
                latency_ms=None,
            ))
    return results


class RetryRequest(PydanticBaseModel):
    providers: list[str] | None = None  # If None, retry all failed providers


@router.post("/jobs/{job_id}/retry")
async def retry_job_providers(job_id: uuid.UUID, body: RetryRequest, db: AsyncSession = Depends(get_db)):
    """Re-run specific or all failed providers for a job."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in ("complete", "failed"):
        raise HTTPException(status_code=400, detail="Can only retry completed or failed jobs")

    # Update job status
    job.status = "retrying"
    await db.commit()

    # Dispatch retry task
    from celery import Celery
    celery_app = Celery(broker=settings.CELERY_BROKER_URL)
    celery_app.send_task(
        "worker.tasks.retry_providers",
        args=[str(job_id), body.providers],
    )

    return {"status": "retrying", "job_id": str(job_id), "providers": body.providers}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Delete a job and all its related data."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Delete in correct order (respecting foreign keys)
    await db.execute(
        CandidateResult.__table__.delete().where(CandidateResult.job_id == job_id)
    )
    await db.execute(
        FinalReport.__table__.delete().where(FinalReport.job_id == job_id)
    )
    await db.execute(
        ProviderRun.__table__.delete().where(ProviderRun.job_id == job_id)
    )
    await db.execute(
        ExtractedFeature.__table__.delete().where(ExtractedFeature.job_id == job_id)
    )
    await db.execute(
        Asset.__table__.delete().where(Asset.job_id == job_id)
    )
    await db.delete(job)
    await db.commit()

    # Clean up files
    job_dir = os.path.join(settings.UPLOAD_DIR, str(job_id))
    if os.path.exists(job_dir):
        import shutil as sh
        sh.rmtree(job_dir, ignore_errors=True)

    return {"status": "deleted", "job_id": str(job_id)}


@router.get("/system/info")
async def system_info():
    """Get system resource information."""
    upload_dir = settings.UPLOAD_DIR
    try:
        usage = shutil.disk_usage(upload_dir)
        disk_info = {
            "total_gb": round(usage.total / (1024**3), 1),
            "used_gb": round(usage.used / (1024**3), 1),
            "free_gb": round(usage.free / (1024**3), 1),
            "usage_percent": round(usage.used / usage.total * 100, 1),
        }
    except Exception:
        disk_info = None

    upload_count = 0
    upload_size = 0
    if os.path.exists(upload_dir):
        for root, dirs, files in os.walk(upload_dir):
            upload_count += len(files)
            upload_size += sum(os.path.getsize(os.path.join(root, f)) for f in files)

    return {
        "disk": disk_info,
        "uploads": {
            "file_count": upload_count,
            "total_size_mb": round(upload_size / (1024**2), 1),
        },
    }


@router.get("/jobs/{job_id}/stream")
async def stream_job_progress(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Stream job progress via SSE."""
    import redis.asyncio as aioredis

    # Check if job is already in terminal state
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    terminal_status = None
    if job and job.status in ("complete", "failed"):
        terminal_status = job.status

    async def event_generator():
        # Send initial connection event
        yield f"data: {json.dumps({'event': 'connected', 'job_id': str(job_id)})}\n\n"

        # If job is already done, immediately send terminal event
        if terminal_status:
            yield f"data: {json.dumps({'event': terminal_status, 'job_id': str(job_id)})}\n\n"
            return

        r = aioredis.from_url(settings.REDIS_URL)
        pubsub = r.pubsub()
        channel = f"job:{job_id}:progress"
        await pubsub.subscribe(channel)

        try:
            while True:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                    timeout=1800.0,
                )
                if message and message["type"] == "message":
                    yield f"data: {message['data'].decode()}\n\n"
                    data = json.loads(message['data'])
                    if data.get("event") in ("complete", "failed"):
                        break
                else:
                    # Send keepalive
                    yield f": keepalive\n\n"
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'event': 'timeout'})}\n\n"
        finally:
            await pubsub.unsubscribe(channel)
            await r.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
