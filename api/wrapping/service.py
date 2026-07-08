from sqlalchemy import asc, desc
from sqlmodel import Session, select
from typing import List

from api.wrapping.models import (
    HirematicJobFeed,
    JobPostings,
    JoobleAbroadJobFeed,
    JoobleJobFeed,
    WhatjobsJobFeed,
)


def get_available_job_postings(session: Session) -> List[JobPostings]:
    """
    Query job postings available to be published to LinkedIn via wrapping.
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


def get_jooble_job_feed_rows(session: Session) -> List[JoobleJobFeed]:
    """All rows from jooble_job_feed for Jooble main XML export."""
    statement = select(JoobleJobFeed)
    results = session.exec(statement)
    return list(results.all())


def get_jooble_abroad_job_feed_rows(session: Session) -> List[JoobleAbroadJobFeed]:
    """All rows from jooble_abroad_job_feed for Jooble enterprise abroad XML export."""
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
