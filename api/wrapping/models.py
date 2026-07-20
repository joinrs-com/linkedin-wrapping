from __future__ import annotations

import os
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Column, Date, Numeric, String, Text
from sqlalchemy.engine.url import make_url
from sqlmodel import SQLModel, Field


def _resolve_schema() -> dict:
    url = os.getenv("DATABASE_URL", "")
    if not url or not str(url).strip():
        return {}
    try:
        if make_url(url).get_backend_name() in ("mysql", "sqlite"):
            return {}
    except Exception:
        pass
    return {"schema": "lw"}


class JobPostings(SQLModel, table=True):
    __tablename__ = "job_postings"
    __table_args__ = _resolve_schema()

    id: Optional[int] = Field(default=None, primary_key=True)
    position: str
    description: str | None = None
    company: str | None = None
    employers_name: str | None = None
    employers_id: int | None = None
    priority: int | None = None
    apply_url: str | None = None
    company_id: str | None = None
    location: str | None = None
    workplace_types: str | None = None
    experience_level: str | None = None
    jobtype: str | None = None
    partner_job_id: str | None = None
    last_build_date: datetime | None = None
    created_at: datetime | None = Field(default=None, sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP"})
    updated_at: datetime | None = Field(
        default=None,
        sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP", "onupdate": datetime.now}
    )


class JobPostingPre(SQLModel, table=True):
    __tablename__ = "job_posting_pre"
    __table_args__ = _resolve_schema()

    id: Optional[int] = Field(default=None, primary_key=True)
    position: str
    job_description: str | None = None
    company: str | None = None
    employers_name: str | None = None
    employers_id: int | None = None
    priority: int | None = None
    apply_url: str | None = None
    company_id: str | None = None
    location: str | None = None
    workplace_types: str | None = None
    experience_level: str | None = None
    jobtype: str | None = None
    partner_job_id: str | None = None
    last_build_date: datetime | None = None
    created_at: datetime | None = Field(default=None, sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP"})
    updated_at: datetime | None = Field(
        default=None,
        sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP", "onupdate": datetime.now}
    )


class JobDescriptionEnriched(SQLModel, table=True):
    """Shared OpenAI-enriched descriptions keyed by production job_id."""

    __tablename__ = "job_description_enriched"
    __table_args__ = _resolve_schema()

    job_id: int = Field(primary_key=True)
    description: str = Field(sa_column=Column("description", Text, nullable=False))
    priority: int | None = None
    has_ita: int | None = None
    employers_id: int | None = None
    enriched_at: datetime


class JobFeedPipelineRun(SQLModel, table=True):
    """One row per run of scripts/run_job_feed_pipeline.py."""

    __tablename__ = "job_feed_pipeline_run"
    __table_args__ = _resolve_schema()

    id: Optional[int] = Field(default=None, primary_key=True)
    started_at: datetime
    finished_at: datetime | None = None
    duration_sec: int | None = None
    status: str
    openai_processed: int = 0
    enriched_deleted: int = 0
    enriched_total: int = 0
    linkedin_active: int = 0
    linkedin_inserted: int = 0
    linkedin_deleted: int = 0
    linkedin_total: int = 0
    jooble_inserted: int = 0
    jooble_deleted: int = 0
    jooble_total: int = 0
    whatjobs_inserted: int = 0
    whatjobs_deleted: int = 0
    whatjobs_total: int = 0
    hirematic_inserted: int = 0
    hirematic_deleted: int = 0
    hirematic_total: int = 0
    error_message: str | None = Field(default=None, sa_column=Column("error_message", Text, nullable=True))


class HirematicJobFeed(SQLModel, table=True):
    """Maps `lw.hirematic_job_feed` (MySQL); column names differ from Appcast XML tags (see wrapping layer)."""

    __tablename__ = "hirematic_job_feed"
    __table_args__ = _resolve_schema()

    id: Optional[int] = Field(default=None, primary_key=True)
    location: Optional[str] = Field(default=None, sa_column=Column("location", Text, nullable=True))
    title: Optional[str] = Field(default=None)
    city: Optional[str] = Field(default=None)
    state: Optional[str] = Field(default=None)
    postal_code: Optional[str] = Field(default=None, sa_column=Column("zip", String(20), nullable=True))
    country: Optional[str] = Field(default=None)
    post_date: Optional[date] = Field(default=None, sa_column=Column("post_date", Date, nullable=True))
    company: Optional[str] = Field(default=None)
    category: Optional[str] = Field(default=None)
    url: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None, sa_column=Column("description", Text, nullable=True))
    cpc: Optional[float] = Field(default=None, sa_column=Column("cpc", Numeric(10, 3), nullable=True))
    priority: Optional[int] = Field(default=None)


class JoobleJobFeed(SQLModel, table=True):
    """Maps `lw.jooble_job_feed`; manual daily refresh for Jooble main feed (non-Italy EU jobs)."""

    __tablename__ = "jooble_job_feed"
    __table_args__ = _resolve_schema()

    id: Optional[int] = Field(default=None, primary_key=True)
    position: str
    employers_name: str | None = None
    employers_id: int | None = None
    priority: int | None = None
    description: str | None = Field(default=None, sa_column=Column("description", Text, nullable=True))
    company: str | None = None
    apply_url: str | None = None
    company_id: str | None = None
    location: str | None = Field(default=None, sa_column=Column("location", Text, nullable=True))
    countries: str | None = Field(default=None, sa_column=Column("countries", Text, nullable=True))
    workplace_types: str | None = None
    experience_level: str | None = None
    jobtype: str | None = None
    partner_job_id: str | None = None
    last_build_date: datetime | None = None


class JoobleAbroadJobFeed(SQLModel, table=True):
    """Maps `lw.jooble_abroad_job_feed`; manual daily refresh for Jooble enterprise abroad feed."""

    __tablename__ = "jooble_abroad_job_feed"
    __table_args__ = _resolve_schema()

    id: Optional[int] = Field(default=None, primary_key=True)
    position: str
    employers_name: str | None = None
    employers_id: int | None = None
    priority: int | None = None
    description: str | None = Field(default=None, sa_column=Column("description", Text, nullable=True))
    company: str | None = None
    apply_url: str | None = None
    company_id: str | None = None
    location: str | None = Field(default=None, sa_column=Column("location", Text, nullable=True))
    countries: str | None = Field(default=None, sa_column=Column("countries", Text, nullable=True))
    workplace_types: str | None = None
    experience_level: str | None = None
    jobtype: str | None = None
    partner_job_id: str | None = None
    last_build_date: datetime | None = None


class WhatjobsJobFeed(SQLModel, table=True):
    """Maps `lw.whatjobs_job_feed`; manual daily refresh for WhatJobs Italy feed."""

    __tablename__ = "whatjobs_job_feed"
    __table_args__ = _resolve_schema()

    id: Optional[int] = Field(default=None, primary_key=True)
    link: str = Field(sa_column=Column("link", Text, nullable=False))
    name: str
    region: str = Field(sa_column=Column("region", Text, nullable=False))
    remote: str | None = None
    salary: str | None = None
    description: str = Field(sa_column=Column("description", Text, nullable=False))
    company: str
    company_logo: str | None = Field(default=None, sa_column=Column("company_logo", Text, nullable=True))
    pubdate: str
    updated: str
    expire: str
    jobtype: str
    employers_id: int | None = None
    priority: int | None = None
    experience_level: str | None = None
