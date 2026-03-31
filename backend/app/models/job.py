import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    image_source: Mapped[str] = mapped_column(String(20))  # "upload" or "url"
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assets = relationship("Asset", back_populates="job", cascade="all, delete-orphan")
    features = relationship("ExtractedFeature", back_populates="job", cascade="all, delete-orphan")
    provider_runs = relationship("ProviderRun", back_populates="job", cascade="all, delete-orphan")
    candidates = relationship("CandidateResult", back_populates="job", cascade="all, delete-orphan")
    report = relationship("FinalReport", back_populates="job", uselist=False, cascade="all, delete-orphan")
