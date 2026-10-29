from sqlalchemy import asc, desc, or_
from sqlmodel import Session, select
from typing import List

from api.wrapping.models import (
    AdzunaJobFeed,
    FeedXmlArtifact,
    HirematicJobFeed,
    JobPostings,
    JobrapidoJobFeed,
    JoobleAbroadJobFeed,
    JoobleJobFeed,
    WhatjobsJobFeed,
)


def get_available_job_postings(session: Session) -> List[JobPostings]:
    """
    Query job postings (legacy LinkedIn table; no longer exposed via XML).
    Currently returns all job postings, can be extended with filtering logic.
    """
    statement = select(JobPostings)
    results = session.exec(statement)
    return list(results.all())


def get_hirematic_job_feed_rows(session: Session) -> List[HirematicJobFeed]:
    """All rows from hirematic_job_feed for Hirematic Appcast XML export."""
    statement = select(HirematicJobFeed)
    results = session.exec(statement)
    return list(results.all())


def get_jooble_job_feed_rows(
    session: Session,
    *,
    bucket: str | None = None,
    buckets: list[str] | None = None,
) -> List[JoobleJobFeed]:
    """Rows from jooble_job_feed; optional campaign bucket filter.

    Legacy rows with NULL bucket are treated as ``ita_esp`` (pre-migration).
    """
    statement = select(JoobleJobFeed)
    if bucket is not None:
        if bucket == "ita_esp":
            statement = statement.where(
                or_(JoobleJobFeed.bucket == bucket, JoobleJobFeed.bucket.is_(None))
            )
        else:
            statement = statement.where(JoobleJobFeed.bucket == bucket)
    elif buckets:
        if "ita_esp" in buckets:
            statement = statement.where(
                or_(JoobleJobFeed.bucket.in_(buckets), JoobleJobFeed.bucket.is_(None))
            )
        else:
            statement = statement.where(JoobleJobFeed.bucket.in_(buckets))
    statement = statement.order_by(
        asc(JoobleJobFeed.priority),
        desc(JoobleJobFeed.last_build_date),
    )
    results = session.exec(statement)
    return list(results.all())


def get_jooble_abroad_job_feed_rows(session: Session) -> List[JoobleAbroadJobFeed]:
    """Deprecated table; prefer jooble buckets usa|eu3|row. Kept for live fallback."""
    statement = select(JoobleAbroadJobFeed)
    results = session.exec(statement)
    return list(results.all())


def get_whatjobs_job_feed_rows(session: Session) -> List[WhatjobsJobFeed]:
    """All rows from whatjobs_job_feed for WhatJobs XML export."""
    statement = select(WhatjobsJobFeed).order_by(
        asc(WhatjobsJobFeed.priority),
        desc(WhatjobsJobFeed.pubdate),
    )
    results = session.exec(statement)
    return list(results.all())


def get_adzuna_job_feed_rows(
    session: Session,
    *,
    bucket: str | None = None,
) -> List[AdzunaJobFeed]:
    """Rows from adzuna_job_feed; optional campaign bucket filter.

    Legacy rows with NULL bucket are treated as ``ita_esp``.
    """
    statement = select(AdzunaJobFeed)
    if bucket is not None:
        if bucket == "ita_esp":
            statement = statement.where(
                or_(AdzunaJobFeed.bucket == bucket, AdzunaJobFeed.bucket.is_(None))
            )
        else:
            statement = statement.where(AdzunaJobFeed.bucket == bucket)
    statement = statement.order_by(
        asc(AdzunaJobFeed.priority),
        desc(AdzunaJobFeed.posted_date),
    )
    results = session.exec(statement)
    return list(results.all())


def get_jobrapido_job_feed_rows(session: Session) -> List[JobrapidoJobFeed]:
    """All rows from jobrapido_job_feed for Job Rapido XML export."""
    statement = select(JobrapidoJobFeed).order_by(
        asc(JobrapidoJobFeed.priority),
        desc(JobrapidoJobFeed.publishdate),
    )
    results = session.exec(statement)
    return list(results.all())


def get_feed_xml_artifact(session: Session, feed_name: str) -> FeedXmlArtifact | None:
    """Pre-generated gzip XML artifact for a feed, if the pipeline has built one."""
    return session.get(FeedXmlArtifact, feed_name)
