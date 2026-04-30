import os
import uuid
import asyncio
import json
from datetime import datetime

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
import structlog
import redis as sync_redis

from backend.app.core.config import settings
from backend.app.models.job import Job
from backend.app.models.asset import Asset
from backend.app.models.feature import ExtractedFeature
from backend.app.models.provider_run import ProviderRun
from backend.app.models.candidate import CandidateResult
from backend.app.models.report import FinalReport

logger = structlog.get_logger()

# Sync engine for Celery (Celery doesn't support async natively)
sync_db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2").replace("postgresql+psycopg2", "postgresql")
# Actually use psycopg2 or fallback
sync_db_url = settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2")

try:
    engine = create_engine(sync_db_url)
    SessionLocal = sessionmaker(bind=engine)
except Exception:
    # Fallback for environments without psycopg2
    sync_db_url = settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
    engine = create_engine(sync_db_url)
    SessionLocal = sessionmaker(bind=engine)


def get_session() -> Session:
    return SessionLocal()


def publish_progress(job_id: str, step: str, progress: int, total: int = 10, message: str = ""):
    """Publish progress event to Redis pubsub."""
    try:
        r = sync_redis.from_url(settings.REDIS_URL)
        event = {
            "event": "progress",
            "job_id": job_id,
            "step": step,
            "progress": progress,
            "total": total,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }
        r.publish(f"job:{job_id}:progress", json.dumps(event))
        r.close()
    except Exception:
        pass  # Non-critical, don't break pipeline


def clone_results(session: Session, source_job_id: uuid.UUID, target_job_id: uuid.UUID):
    """Clone search results from a completed job to a new one."""
    # Copy candidates
    source_candidates = session.query(CandidateResult).filter(
        CandidateResult.job_id == source_job_id
    ).all()
    for c in source_candidates:
        new_candidate = CandidateResult(
            job_id=target_job_id,
            provider_run_id=c.provider_run_id,
            source_url=c.source_url,
            page_title=c.page_title,
            thumbnail_url=c.thumbnail_url,
            match_type=c.match_type,
            similarity_score=c.similarity_score,
            confidence=c.confidence,
            extracted_text=c.extracted_text,
            extra_data=c.extra_data,
        )
        session.add(new_candidate)

    # Copy report
    source_report = session.query(FinalReport).filter(
        FinalReport.job_id == source_job_id
    ).first()
    if source_report:
        new_report = FinalReport(
            job_id=target_job_id,
            summary=source_report.summary,
            ai_description=source_report.ai_description,
            entities=source_report.entities,
            search_terms=source_report.search_terms,
            cluster_count=source_report.cluster_count,
            top_matches=source_report.top_matches,
        )
        session.add(new_report)

    session.commit()


def update_job_status(session: Session, job_id: str, status: str, error: str = None):
    job = session.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
    if job:
        job.status = status
        job.updated_at = datetime.utcnow()
        if error:
            job.error_message = error
        session.commit()


@shared_task(name="worker.tasks.run_pipeline", soft_time_limit=1800, time_limit=2100)
def run_pipeline(job_id: str):
    """Main pipeline task - orchestrates the full investigation."""
    logger.info("pipeline_started", job_id=job_id)
    session = get_session()

    try:
        # Step 1: Ingest
        publish_progress(job_id, "ingestion", 1, 10, "Processing image...")
        update_job_status(session, job_id, "ingesting")
        ingest_image(session, job_id)

        # Step 2: Extract features
        publish_progress(job_id, "features", 2, 10, "Extracting features...")
        update_job_status(session, job_id, "extracting")
        extract_features(session, job_id)

        # Cache check: look for existing completed job with same image hash
        feature = session.query(ExtractedFeature).filter(
            ExtractedFeature.job_id == uuid.UUID(job_id)
        ).first()
        if feature and feature.sha256:
            existing = session.query(ExtractedFeature).filter(
                ExtractedFeature.sha256 == feature.sha256,
                ExtractedFeature.job_id != uuid.UUID(job_id),
            ).first()
            if existing:
                existing_job = session.query(Job).filter(
                    Job.id == existing.job_id,
                    Job.status == "complete",
                ).first()
                if existing_job:
                    logger.info("cache_hit", existing_job_id=str(existing_job.id), hash=feature.sha256)
                    clone_results(session, existing_job.id, uuid.UUID(job_id))
                    job = session.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
                    job.status = "complete"
                    job.completed_at = datetime.utcnow()
                    session.commit()
                    try:
                        r = sync_redis.from_url(settings.REDIS_URL)
                        r.publish(f"job:{job_id}:progress", json.dumps({"event": "complete", "job_id": job_id}))
                        r.close()
                    except Exception:
                        pass
                    return {"status": "complete", "cached_from": str(existing_job.id)}

        # Step 3: Ollama analysis
        publish_progress(job_id, "vision", 4, 10, "Running AI analysis...")
        update_job_status(session, job_id, "analyzing")
        analysis = run_ollama_analysis(session, job_id)

        # Step 4: Build search terms
        publish_progress(job_id, "terms", 5, 10, "Generating search terms...")
        update_job_status(session, job_id, "searching")
        search_terms = build_search_terms(session, job_id, analysis)

        # Step 5: Run providers
        publish_progress(job_id, "search", 6, 10, "Searching providers...")
        run_providers(session, job_id, analysis, search_terms)

        # Step 6: Score and rank
        publish_progress(job_id, "scoring", 8, 10, "Scoring results...")
        update_job_status(session, job_id, "scoring")
        score_and_rank(session, job_id)

        # Step 7: Generate report
        publish_progress(job_id, "report", 9, 10, "Generating report...")
        update_job_status(session, job_id, "reporting")
        generate_report(session, job_id, analysis)

        update_job_status(session, job_id, "complete")
        try:
            r = sync_redis.from_url(settings.REDIS_URL)
            r.publish(f"job:{job_id}:progress", json.dumps({"event": "complete", "job_id": job_id}))
            r.close()
        except Exception:
            pass
        logger.info("pipeline_complete", job_id=job_id)

    except (Exception, SoftTimeLimitExceeded) as e:
        error_msg = f"Pipeline timed out after 30 minutes" if isinstance(e, SoftTimeLimitExceeded) else str(e)
        logger.error("pipeline_failed", job_id=job_id, error=error_msg)
        update_job_status(session, job_id, "failed", error=error_msg)
        try:
            r = sync_redis.from_url(settings.REDIS_URL)
            r.publish(f"job:{job_id}:progress", json.dumps({"event": "failed", "job_id": job_id, "error": str(e)}))
            r.close()
        except Exception:
            pass
    finally:
        session.close()


def ingest_image(session: Session, job_id: str):
    """Generate normalized image variants."""
    from backend.app.services.ingestion import generate_variants

    job = session.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
    if not job:
        raise ValueError(f"Job {job_id} not found")

    # Find original asset
    original = session.query(Asset).filter(
        Asset.job_id == uuid.UUID(job_id),
        Asset.variant == "original"
    ).first()

    if not original:
        raise ValueError(f"No original asset for job {job_id}")

    # Skip if variants already exist (idempotent re-run)
    existing_variants = session.query(Asset).filter(
        Asset.job_id == uuid.UUID(job_id),
        Asset.variant != "original"
    ).count()
    if existing_variants > 0:
        logger.info("ingestion_skipped_already_done", job_id=job_id)
        return

    job_dir = os.path.dirname(original.file_path)
    variants = generate_variants(original.file_path, job_dir)

    for variant_name, info in variants.items():
        asset = Asset(
            job_id=uuid.UUID(job_id),
            variant=variant_name,
            file_path=info["file_path"],
            width=info.get("width"),
            height=info.get("height"),
            mime_type=info.get("mime_type"),
            file_size=info.get("file_size"),
        )
        session.add(asset)

    session.commit()
    logger.info("ingestion_complete", job_id=job_id, variant_count=len(variants))


def extract_features(session: Session, job_id: str):
    """Extract all features from the original image."""
    from backend.app.services.feature_extraction import extract_all_features

    original = session.query(Asset).filter(
        Asset.job_id == uuid.UUID(job_id),
        Asset.variant == "original"
    ).first()

    if not original:
        raise ValueError(f"No original asset for job {job_id}")

    features_data = extract_all_features(original.file_path)

    # Upsert: update existing or create new
    existing = session.query(ExtractedFeature).filter(
        ExtractedFeature.job_id == uuid.UUID(job_id)
    ).first()

    if existing:
        for key, value in features_data.items():
            setattr(existing, key, value)
    else:
        feature = ExtractedFeature(
            job_id=uuid.UUID(job_id),
            **features_data,
        )
        session.add(feature)

    session.commit()
    logger.info("feature_extraction_complete", job_id=job_id)


def run_ollama_analysis(session: Session, job_id: str) -> dict:
    """Run Ollama vision analysis on the image."""
    from backend.app.services.ollama_service import OllamaService

    original = session.query(Asset).filter(
        Asset.job_id == uuid.UUID(job_id),
        Asset.variant == "original"
    ).first()

    if not original:
        return {}

    ollama = OllamaService()

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        analysis = loop.run_until_complete(ollama.analyze_image(original.file_path))
        loop.close()
        logger.info("ollama_analysis_complete", job_id=job_id)
        return analysis
    except Exception as e:
        logger.error("ollama_analysis_failed", job_id=job_id, error=str(e))
        return {"error": str(e), "entities": [], "brands": [], "landmarks": []}


def build_search_terms(session: Session, job_id: str, analysis: dict) -> list[str]:
    """Build search terms from analysis + OCR + metadata."""
    from backend.app.services.ollama_service import OllamaService

    feature = session.query(ExtractedFeature).filter(
        ExtractedFeature.job_id == uuid.UUID(job_id)
    ).first()

    ocr_text = feature.ocr_text if feature else None
    exif_data = feature.exif_data if feature else None

    # Check if analysis has real content (not just an error fallback)
    has_analysis = bool(
        analysis.get("raw_description")
        or analysis.get("entities")
        or analysis.get("brands")
        or analysis.get("landmarks")
    )

    # Only call Ollama for search terms if we have meaningful evidence
    if has_analysis or ocr_text:
        ollama = OllamaService()
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            terms = loop.run_until_complete(
                ollama.generate_search_terms(analysis, ocr_text, exif_data)
            )
            loop.close()
            logger.info("search_terms_built", job_id=job_id, terms=terms)
            return terms
        except Exception as e:
            logger.error("search_term_generation_failed", job_id=job_id, error=str(e))

    # Fallback terms from entities, OCR, and EXIF
    fallback = []
    if analysis.get("entities"):
        fallback.extend(analysis["entities"][:2])
    if analysis.get("brands"):
        fallback.extend(analysis["brands"][:2])
    if ocr_text:
        # Use first meaningful words from OCR
        words = ocr_text.strip().split()
        if words:
            fallback.append(" ".join(words[:8]))
    if not fallback:
        fallback.append("image")
    logger.info("search_terms_fallback", job_id=job_id, terms=fallback)
    return fallback


def run_providers(session: Session, job_id: str, analysis: dict, search_terms: list[str]):
    """Run all enabled providers."""
    from providers import get_enabled_providers

    original = session.query(Asset).filter(
        Asset.job_id == uuid.UUID(job_id),
        Asset.variant == "original"
    ).first()

    if not original:
        return

    feature = session.query(ExtractedFeature).filter(
        ExtractedFeature.job_id == uuid.UUID(job_id)
    ).first()

    context = {
        "search_terms": search_terms,
        "entities": analysis.get("entities", []),
        "brands": analysis.get("brands", []),
        "landmarks": analysis.get("landmarks", []),
        "ocr_text": feature.ocr_text if feature else "",
        "saucenao_api_key": settings.SAUCENAO_API_KEY or "",
    }

    enabled = get_enabled_providers(settings)
    logger.info("running_providers", count=len(enabled), names=[p.name for p in enabled])

    async def run_all():
        sem = asyncio.Semaphore(settings.MAX_CONCURRENT_PROVIDERS)

        async def run_one(provider):
            async with sem:
                timeout = 180 if provider.experimental else 120
                try:
                    results = await asyncio.wait_for(
                        provider.safe_search(original.file_path, context),
                        timeout=timeout,
                    )
                    return (provider.name, results, None)
                except asyncio.TimeoutError:
                    logger.error("provider_timeout", provider=provider.name, timeout=timeout)
                    return (provider.name, None, f"Timed out after {timeout}s")
                except Exception as e:
                    logger.error("provider_failed", provider=provider.name, error=str(e))
                    return (provider.name, None, str(e))

        return await asyncio.gather(*[run_one(p) for p in enabled])

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results_list = loop.run_until_complete(run_all())
    finally:
        loop.close()

    # Save all results to DB sequentially (SQLAlchemy sessions are not thread-safe)
    for provider_name, results, error in results_list:
        provider_run = ProviderRun(
            job_id=uuid.UUID(job_id),
            provider_name=provider_name,
            status="running",
            started_at=datetime.utcnow(),
        )
        session.add(provider_run)
        session.flush()

        if error is not None:
            provider_run.status = "failed"
            provider_run.finished_at = datetime.utcnow()
            provider_run.error_message = error
        else:
            provider_run.status = "success"
            provider_run.finished_at = datetime.utcnow()
            provider_run.result_count = len(results)

            for r in results:
                candidate = CandidateResult(
                    job_id=uuid.UUID(job_id),
                    provider_run_id=provider_run.id,
                    source_url=r.source_url,
                    page_title=r.page_title,
                    thumbnail_url=r.thumbnail_url,
                    match_type=r.match_type,
                    similarity_score=r.similarity_score,
                    confidence=r.confidence,
                    extracted_text=r.extracted_text,
                    extra_data=r.metadata,
                )
                session.add(candidate)

        session.commit()


def score_and_rank(session: Session, job_id: str):
    """Score all candidates and update confidence."""
    from backend.app.services.scoring import score_candidate

    feature = session.query(ExtractedFeature).filter(
        ExtractedFeature.job_id == uuid.UUID(job_id)
    ).first()

    features_dict = {}
    if feature:
        features_dict = {
            "sha256": feature.sha256,
            "phash": feature.phash,
            "dhash": feature.dhash,
            "ahash": feature.ahash,
            "ocr_text": feature.ocr_text,
        }

    candidates = session.query(CandidateResult).join(ProviderRun).filter(
        CandidateResult.job_id == uuid.UUID(job_id)
    ).all()

    from backend.app.services.provider_priority import get_provider_priorities, get_confidence_weight
    priorities = get_provider_priorities(settings)

    for candidate in candidates:
        provider_run = session.query(ProviderRun).filter(
            ProviderRun.id == candidate.provider_run_id
        ).first()
        provider_name = provider_run.provider_name if provider_run else "unknown"

        candidate_dict = {
            "source_url": candidate.source_url,
            "page_title": candidate.page_title,
            "similarity_score": candidate.similarity_score or 0,
            "extracted_text": candidate.extracted_text or "",
            "metadata": candidate.extra_data or {},
        }

        confidence = score_candidate(candidate_dict, features_dict, provider_name)
        weight = get_confidence_weight(provider_name, priorities)
        candidate.confidence = min(1.0, (confidence or 0.5) * weight)

    session.commit()
    logger.info("scoring_complete", job_id=job_id, candidate_count=len(candidates))


def generate_report(session: Session, job_id: str, analysis: dict):
    """Generate the final synthesis report."""
    from backend.app.services.ollama_service import OllamaService
    from backend.app.services.scoring import cluster_duplicates

    feature = session.query(ExtractedFeature).filter(
        ExtractedFeature.job_id == uuid.UUID(job_id)
    ).first()

    candidates = session.query(CandidateResult).filter(
        CandidateResult.job_id == uuid.UUID(job_id)
    ).order_by(CandidateResult.confidence.desc()).all()

    features_dict = {}
    if feature:
        features_dict = {
            "sha256": feature.sha256,
            "phash": feature.phash,
            "ocr_text": feature.ocr_text,
            "exif_data": feature.exif_data,
        }

    candidate_dicts = [
        {
            "source_url": c.source_url or "",
            "page_title": c.page_title or "",
            "match_type": c.match_type or "similar",
            "confidence": c.confidence or 0,
            "extracted_text": c.extracted_text or "",
        }
        for c in candidates
    ]

    # Cluster duplicates
    clusters = cluster_duplicates(candidate_dicts)

    # Get top matches (best from each cluster)
    top_matches = []
    for cluster in clusters[:10]:
        best_idx = max(cluster, key=lambda i: candidate_dicts[i].get("confidence", 0))
        top_matches.append(candidate_dicts[best_idx])

    # Generate synthesis via Ollama
    ollama = OllamaService()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        summary = loop.run_until_complete(
            ollama.synthesize_report(analysis, top_matches, features_dict)
        )
        loop.close()
    except Exception as e:
        logger.error("report_synthesis_failed", error=str(e))
        summary = f"Automated synthesis unavailable. Found {len(candidates)} candidates across {len(clusters)} clusters."

    # Build search terms list for storage
    search_terms = analysis.get("entities", []) + analysis.get("brands", []) + analysis.get("landmarks", [])

    report = FinalReport(
        job_id=uuid.UUID(job_id),
        summary=summary,
        ai_description=analysis.get("raw_description", ""),
        entities={"entities": analysis.get("entities", []), "brands": analysis.get("brands", []), "landmarks": analysis.get("landmarks", [])},
        search_terms={"terms": search_terms},
        cluster_count=len(clusters),
        top_matches={"matches": top_matches[:10]},
    )
    session.add(report)
    session.commit()
    logger.info("report_generated", job_id=job_id, clusters=len(clusters))


@shared_task(name="worker.tasks.retry_providers", bind=True, soft_time_limit=1800)
def retry_providers(self, job_id: str, provider_names: list[str] | None = None):
    """Re-run specific providers for an existing job without repeating the full pipeline."""
    logger.info("retry_start", job_id=job_id, providers=provider_names)
    session = get_session()

    try:
        job = session.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
        if not job:
            logger.error("retry_job_not_found", job_id=job_id)
            return

        job.status = "processing"
        job.updated_at = datetime.utcnow()
        session.commit()

        # Get the primary asset path
        original = session.query(Asset).filter(
            Asset.job_id == uuid.UUID(job_id),
            Asset.variant == "original",
        ).first()
        if not original:
            update_job_status(session, job_id, "failed", error="No original asset found")
            return

        # Get features for context
        feature = session.query(ExtractedFeature).filter(
            ExtractedFeature.job_id == uuid.UUID(job_id)
        ).first()

        # Get existing report for search terms and entities
        report = session.query(FinalReport).filter(
            FinalReport.job_id == uuid.UUID(job_id)
        ).first()

        # Reconstruct analysis context from stored data
        search_terms = []
        entities = []
        brands = []
        landmarks = []

        if report:
            if report.search_terms and isinstance(report.search_terms, dict):
                search_terms = report.search_terms.get("terms", [])
            if report.entities and isinstance(report.entities, dict):
                entities = report.entities.get("entities", [])
                brands = report.entities.get("brands", [])
                landmarks = report.entities.get("landmarks", [])

        context = {
            "search_terms": search_terms,
            "entities": entities,
            "brands": brands,
            "landmarks": landmarks,
            "ocr_text": feature.ocr_text if feature else "",
            "saucenao_api_key": settings.SAUCENAO_API_KEY or "",
        }

        # Get enabled providers, filter to requested ones
        from providers import get_enabled_providers
        all_enabled = get_enabled_providers(settings)

        if provider_names:
            providers_to_run = [p for p in all_enabled if p.name in provider_names]
        else:
            # Retry all previously failed providers
            failed_runs = session.query(ProviderRun).filter(
                ProviderRun.job_id == uuid.UUID(job_id),
                ProviderRun.status == "failed",
            ).all()
            failed_names = {r.provider_name for r in failed_runs}
            providers_to_run = [p for p in all_enabled if p.name in failed_names]

        if not providers_to_run:
            update_job_status(session, job_id, "complete")
            logger.info("retry_no_providers", job_id=job_id)
            return

        # Delete old runs and candidates for these providers
        provider_names_to_run = [p.name for p in providers_to_run]
        old_runs = session.query(ProviderRun).filter(
            ProviderRun.job_id == uuid.UUID(job_id),
            ProviderRun.provider_name.in_(provider_names_to_run),
        ).all()
        old_run_ids = [r.id for r in old_runs]

        if old_run_ids:
            session.query(CandidateResult).filter(
                CandidateResult.provider_run_id.in_(old_run_ids),
            ).delete(synchronize_session="fetch")
            session.query(ProviderRun).filter(
                ProviderRun.id.in_(old_run_ids),
            ).delete(synchronize_session="fetch")
        session.commit()

        # Run providers using the same parallel pattern as run_providers()
        async def run_all():
            sem = asyncio.Semaphore(settings.MAX_CONCURRENT_PROVIDERS)

            async def run_one(provider):
                async with sem:
                    timeout = 180 if provider.experimental else 120
                    try:
                        results = await asyncio.wait_for(
                            provider.safe_search(original.file_path, context),
                            timeout=timeout,
                        )
                        return (provider.name, results, None)
                    except asyncio.TimeoutError:
                        return (provider.name, None, f"Timed out after {timeout}s")
                    except Exception as e:
                        return (provider.name, None, str(e))

            return await asyncio.gather(*[run_one(p) for p in providers_to_run])

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results_list = loop.run_until_complete(run_all())
        finally:
            loop.close()

        # Save new results
        for provider_name, results, error in results_list:
            provider_run = ProviderRun(
                job_id=uuid.UUID(job_id),
                provider_name=provider_name,
                status="running",
                started_at=datetime.utcnow(),
            )
            session.add(provider_run)
            session.flush()

            if error is not None:
                provider_run.status = "failed"
                provider_run.finished_at = datetime.utcnow()
                provider_run.error_message = error
            else:
                provider_run.status = "success"
                provider_run.finished_at = datetime.utcnow()
                provider_run.result_count = len(results)

                for r in results:
                    candidate = CandidateResult(
                        job_id=uuid.UUID(job_id),
                        provider_run_id=provider_run.id,
                        source_url=r.source_url,
                        page_title=r.page_title,
                        thumbnail_url=r.thumbnail_url,
                        match_type=r.match_type,
                        similarity_score=r.similarity_score,
                        confidence=r.confidence,
                        extracted_text=r.extracted_text,
                        extra_data=r.metadata,
                    )
                    session.add(candidate)

            session.commit()

        # Re-score all candidates
        score_and_rank(session, job_id)

        update_job_status(session, job_id, "complete")
        logger.info("retry_complete", job_id=job_id)

    except Exception as e:
        logger.error("retry_failed", job_id=job_id, error=str(e))
        session.rollback()
        update_job_status(session, job_id, "failed", error=f"Retry failed: {str(e)}")
    finally:
        session.close()
