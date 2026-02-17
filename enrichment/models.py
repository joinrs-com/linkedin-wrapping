"""SQLAlchemy models for enrichment pipeline. blue_collar_copy is read-only; job_enrichment and job_education_types are write targets."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base for enrichment models."""

    type_annotation_map = {dict[str, Any]: JSON}


# ----- Source table (READ ONLY - pipeline never writes here) -----


class BlueCollarCopy(Base):
    """Job ads source table. Immutable: do not update normalized_title, normalized_text, language, collar_type."""

    __tablename__ = "blue_collar_copy"
    __table_args__: Any = ()

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    employment_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    normalized_title: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    normalized_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    collar_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


# ----- Taxonomy tables (read-only, loaded once into cache) -----


class MacroSectorCopy(Base):
    __tablename__ = "macro_sector_copy"
    __table_args__: Any = ()

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class MicroSectorCopy(Base):
    __tablename__ = "micro_sector_copy"
    __table_args__: Any = ()

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    macro_id: Mapped[Optional[int]] = mapped_column("macro_id", Integer, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SeniorityLevel(Base):
    """seniority_levels: id, name, collar_scope, level_rank, created_at, description, normalized_label."""

    __tablename__ = "seniority_levels"
    __table_args__: Any = ()

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    collar_scope: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    level_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    normalized_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class EducationLevel(Base):
    """education_levels: id, name, level_rank, created_at, description, normalized_label."""

    __tablename__ = "education_levels"
    __table_args__: Any = ()

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    level_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    normalized_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class EducationType(Base):
    __tablename__ = "education_types"
    __table_args__: Any = ()

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    normalized_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


# ----- White collar ambiti (macro = group, micro = question) -----


class GptQuestionsGroup(Base):
    """Macro ambito per job white collar (equivalente a macro_sector_copy)."""

    __tablename__ = "gpt_questions_groups"
    __table_args__: Any = ()

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class GptQuestion(Base):
    """Micro ambito per job white collar (equivalente a micro_sector_copy)."""

    __tablename__ = "gpt_questions"
    __table_args__: Any = ()

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gpt_categories_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gpt_questions_groups_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# ----- Output tables (pipeline writes only here) -----


class JobEnrichment(Base):
    """One row per job. All derived data lives here (source table is immutable)."""

    __tablename__ = "job_enrichment"
    __table_args__: Any = ()

    job_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    normalized_title: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    normalized_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detected_language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    processing_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    collar_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    collar_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sector_macro_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sector_micro_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sector_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sector_method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    gpt_group_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gpt_question_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gpt_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gpt_method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    seniority_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    seniority_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    seniority_method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    education_level_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    education_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    education_method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    explanation_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    education_types_rows: Mapped[list[JobEducationType]] = relationship(
        "JobEducationType", back_populates="job_enrichment", cascade="all, delete-orphan"
    )


class JobEducationType(Base):
    """0..N rows per job for education types (patents, certifications, etc.)."""

    __tablename__ = "job_education_types"
    __table_args__: Any = ()

    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("job_enrichment.job_id", ondelete="CASCADE"), primary_key=True)
    education_type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    job_enrichment: Mapped[Optional[JobEnrichment]] = relationship("JobEnrichment", back_populates="education_types_rows")
