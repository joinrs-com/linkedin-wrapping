from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Text
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
    """Hirematic Appcast feed source; DB column `zip` is exposed as `postal_code` (avoids builtin `zip`)."""

    __tablename__ = "hirematic_job_feed"
    __table_args__ = _resolve_schema()

    id: Optional[int] = Field(default=None, primary_key=True)
    location: Optional[str] = Field(default=None)
    title: Optional[str] = Field(default=None)
    city: Optional[str] = Field(default=None)
    state: Optional[str] = Field(default=None)
    postal_code: Optional[str] = Field(default=None, sa_column=Column("zip", String(64), nullable=True))
    country: Optional[str] = Field(default=None)
    job_type: Optional[str] = Field(default=None)
    posted_at: Optional[str] = Field(default=None)
    job_reference: Optional[str] = Field(default=None)
    company: Optional[str] = Field(default=None)
    mobile_friendly_apply: Optional[str] = Field(default=None)
    category: Optional[str] = Field(default=None)
    html_jobs: Optional[str] = Field(default=None)
    url: Optional[str] = Field(default=None)
    body: Optional[str] = Field(default=None, sa_column=Column("body", Text, nullable=True))
    cpc: Optional[str] = Field(default=None)
