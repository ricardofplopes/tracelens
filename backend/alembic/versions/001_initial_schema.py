"""Initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- jobs ---
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("image_source", sa.String(20), nullable=False),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("original_filename", sa.String(500), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])

    # --- assets ---
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("variant", sa.String(50), nullable=False),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("file_size", sa.Integer, nullable=True),
    )
    op.create_index("ix_assets_job_id", "assets", ["job_id"])

    # --- extracted_features ---
    op.create_table(
        "extracted_features",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id"), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("phash", sa.String(64), nullable=True),
        sa.Column("dhash", sa.String(64), nullable=True),
        sa.Column("ahash", sa.String(64), nullable=True),
        sa.Column("color_histogram", sa.JSON, nullable=True),
        sa.Column("orb_descriptor_count", sa.Integer, nullable=True),
        sa.Column("dimensions", sa.String(50), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("exif_data", sa.JSON, nullable=True),
        sa.Column("ocr_text", sa.Text, nullable=True),
    )
    op.create_index("ix_extracted_features_job_id", "extracted_features", ["job_id"])

    # --- provider_runs ---
    op.create_table(
        "provider_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("provider_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("result_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_provider_runs_job_id", "provider_runs", ["job_id"])

    # --- candidate_results ---
    op.create_table(
        "candidate_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("provider_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("provider_runs.id"), nullable=False),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("page_title", sa.Text, nullable=True),
        sa.Column("thumbnail_url", sa.Text, nullable=True),
        sa.Column("match_type", sa.String(50), nullable=False, server_default="similar"),
        sa.Column("similarity_score", sa.Float, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("extracted_text", sa.Text, nullable=True),
        # Python attr is extra_data, DB column is "metadata"
        sa.Column("metadata", sa.JSON, nullable=True),
    )
    op.create_index("ix_candidate_results_job_id", "candidate_results", ["job_id"])
    op.create_index("ix_candidate_results_provider_run_id", "candidate_results", ["provider_run_id"])

    # --- final_reports ---
    op.create_table(
        "final_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id"), nullable=False, unique=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("ai_description", sa.Text, nullable=True),
        sa.Column("entities", sa.JSON, nullable=True),
        sa.Column("search_terms", sa.JSON, nullable=True),
        sa.Column("cluster_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("top_matches", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_final_reports_job_id", "final_reports", ["job_id"])


def downgrade() -> None:
    op.drop_table("final_reports")
    op.drop_table("candidate_results")
    op.drop_table("provider_runs")
    op.drop_table("extracted_features")
    op.drop_table("assets")
    op.drop_table("jobs")
