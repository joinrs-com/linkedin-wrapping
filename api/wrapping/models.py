from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

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
    created_at: datetime | None = Field(default=None, sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP"})
    updated_at: datetime | None = Field(
        default=None,
        sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP", "onupdate": datetime.now}
    )

