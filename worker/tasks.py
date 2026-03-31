import os
import uuid
import asyncio
from datetime import datetime

from celery import shared_task
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
import structlog

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


def update_job_status(session: Session, job_id: str, status: str, error: str = None):
    job = session.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
    if job:
        job.status = status
        job.updated_at = datetime.utcnow()
        if error:
            job.error_message = error
        session.commit()


@shared_task(name="worker.tasks.run_pipeline")
def run_pipeline(job_id: str):
    """Main pipeline task - orchestrates the full investigation."""
    logger.info("pipeline_started", job_id=job_id)
    session = get_session()

    try:
        # Step 1: Ingest
        update_job_status(session, job_id, "ingesting")
        ingest_image(session, job_id)

        # Step 2: Extract features
        update_job_status(session, job_id, "extracting")
        extract_features(session, job_id)

        # Step 3: Ollama analysis
        update_job_status(session, job_id, "analyzing")
        analysis = run_ollama_analysis(session, job_id)

        # Step 4: Build search terms
        update_job_status(session, job_id, "searching")
        search_terms = build_search_terms(session, job_id, analysis)

        # Step 5: Run providers
        run_providers(session, job_id, analysis, search_terms)

        # Step 6: Score and rank
        update_job_status(session, job_id, "scoring")
        score_and_rank(session, job_id)

        # Step 7: Generate report
        update_job_status(session, job_id, "reporting")
        generate_report(session, job_id, analysis)

        update_job_status(session, job_id, "complete")
        logger.info("pipeline_complete", job_id=job_id)

    except Exception as e:
        logger.error("pipeline_failed", job_id=job_id, error=str(e))
        update_job_status(session, job_id, "failed", error=str(e))
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
        # Fallback terms from entities
        fallback = []
        if analysis.get("entities"):
            fallback.extend(analysis["entities"][:2])
        if ocr_text:
            fallback.append(ocr_text[:50])
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

    for provider in enabled:
        provider_run = ProviderRun(
            job_id=uuid.UUID(job_id),
            provider_name=provider.name,
            status="running",
            started_at=datetime.utcnow(),
        )
        session.add(provider_run)
        session.flush()

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(
                provider.safe_search(original.file_path, context)
            )
            loop.close()

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

        except Exception as e:
            provider_run.status = "failed"
            provider_run.finished_at = datetime.utcnow()
            provider_run.error_message = str(e)
            logger.error("provider_failed", provider=provider.name, error=str(e))

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
        candidate.confidence = confidence

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
