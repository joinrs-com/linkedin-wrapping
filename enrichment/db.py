"""Database engine and session. Keyset pagination only; no OFFSET. Short sessions per batch."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from enrichment.config import config
from enrichment.models import BlueCollarCopy, JobEnrichment

# Lazy engine creation
_engine: Optional[Engine] = None

# Prefer enrichment/.env (no DATABASE_URL) so pipeline never picks up lw from main .env
_ENV_DIR = Path(__file__).resolve().parent
_ENV_PATH = _ENV_DIR / ".env"
_ENV_PATH_FALLBACK = _ENV_DIR.parent / ".env"


def _get_env_path() -> Path:
    """Use enrichment/.env if present, else project root .env."""
    if _ENV_PATH.exists():
        return _ENV_PATH
    return _ENV_PATH_FALLBACK


def _read_env_from_file(var: str) -> str:
    """Read one variable from .env file only. Ignores DATABASE_URL and os.environ."""
    path = _get_env_path()
    if not path.exists():
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == var:
                    return v.strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def _build_enrichment_url() -> str:
    """Build MySQL URL from DB_* in .env file only. Never use DATABASE_URL (used by other scripts)."""
    host = _read_env_from_file("DB_HOST")
    port = _read_env_from_file("DB_PORT") or "3306"
    name = _read_env_from_file("DB_NAME")
    user = _read_env_from_file("DB_USER")
    password = _read_env_from_file("DB_PASSWORD")
    if not all([host, name, user]):
        return ""
    return f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{name}"


def get_engine() -> Engine:
    """Create or return the SQLAlchemy engine. URL from .env DB_* only (ignores DATABASE_URL)."""
    global _engine
    if _engine is None:
        import logging

        from sqlalchemy import create_engine

        url = _build_enrichment_url()
        if not url:
            raise ValueError(
                "Enrichment DB not configured. Copy enrichment/.env.example to enrichment/.env "
                "and set DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD (use enrichment/.env to avoid DATABASE_URL)."
            )
        db_name = url.split("/")[-1].split("?")[0] if "/" in url else ""
        logging.getLogger("enrichment").info(
            "Using database: %s",
            db_name,
            extra={"extra": {"db_name": db_name}},
        )
        _engine = create_engine(
            url,
            pool_recycle=3600,
            pool_pre_ping=True,
            echo=False,
        )
    return _engine


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager for a short-lived session. Use per batch: open, process, commit, close (plan rule 9)."""
    engine = get_engine()
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def fetch_job_batch(
    session: Session,
    *,
    last_id: int = 0,
    batch_size: int,
    mode: str,  # "full" | "incremental" | "only_new"
) -> list[BlueCollarCopy]:
    """
    Fetch a batch of jobs using keyset pagination only (plan rule 6).
    Never runs SELECT * without LIMIT; never uses OFFSET.
    - full: all jobs (id > last_id).
    - incremental: no row yet, or updated_at changed, or needs_repair.
    - only_new: only jobs in blue_collar_copy with no row in job_enrichment (for new manual inserts).
    """
    if mode == "incremental":
        return fetch_job_batch_incremental(session, last_id=last_id, batch_size=batch_size)
    if mode == "only_new":
        return fetch_job_batch_only_new(session, last_id=last_id, batch_size=batch_size)
    return fetch_job_batch_simple(session, last_id=last_id, batch_size=batch_size)


def fetch_job_batch_simple(
    session: Session,
    *,
    last_id: int = 0,
    batch_size: int,
) -> list[BlueCollarCopy]:
    """Full mode: keyset only, no incremental filter. Safer for very large tables."""
    stmt = (
        select(BlueCollarCopy)
        .where(BlueCollarCopy.id > last_id)
        .order_by(BlueCollarCopy.id)
        .limit(batch_size)
    )
    result = session.execute(stmt)
    return list(result.scalars().all())


def _method_empty(column):
    """True when column is NULL or empty/blank (for repair condition)."""
    return or_(
        column.is_(None),
        func.trim(func.coalesce(column, "")) == "",
    )


def fetch_job_batch_incremental(
    session: Session,
    *,
    last_id: int = 0,
    batch_size: int,
) -> list[BlueCollarCopy]:
    """
    Incremental: only jobs that need (re)processing.
    Includes: no row yet, updated_at changed, or at least one of sector/seniority/education_method
    empty (so we can re-run and update in place without deleting).
    """
    needs_repair = or_(
        _method_empty(JobEnrichment.sector_method),
        _method_empty(JobEnrichment.seniority_method),
        _method_empty(JobEnrichment.education_method),
    )
    stmt = (
        select(BlueCollarCopy)
        .select_from(BlueCollarCopy)
        .outerjoin(JobEnrichment, BlueCollarCopy.id == JobEnrichment.job_id)
        .where(BlueCollarCopy.id > last_id)
        .where(
            or_(
                JobEnrichment.job_id.is_(None),
                BlueCollarCopy.updated_at > JobEnrichment.updated_at,
                needs_repair,
            )
        )
        .order_by(BlueCollarCopy.id)
        .limit(batch_size)
    )
    result = session.execute(stmt)
    return list(result.scalars().unique().all())


def fetch_job_batch_only_new(
    session: Session,
    *,
    last_id: int = 0,
    batch_size: int,
) -> list[BlueCollarCopy]:
    """
    Only jobs that exist in blue_collar_copy but have no row in job_enrichment.
    Use after inserting new records manually: processes only the new ones.
    """
    stmt = (
        select(BlueCollarCopy)
        .select_from(BlueCollarCopy)
        .outerjoin(JobEnrichment, BlueCollarCopy.id == JobEnrichment.job_id)
        .where(BlueCollarCopy.id > last_id)
        .where(JobEnrichment.job_id.is_(None))
        .order_by(BlueCollarCopy.id)
        .limit(batch_size)
    )
    result = session.execute(stmt)
    return list(result.scalars().unique().all())
