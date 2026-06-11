from __future__ import annotations

import os
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Column, Date, Numeric, String, Text
from sqlalchemy.engine.url import make_url
from sqlmodel import SQLModel, Field


def _resolve_schema() -> dict:
    url = os.getenv("DATABASE_URL", "")
    try:
        if url and make_url(url).get_backend_name() == "mysql":
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
