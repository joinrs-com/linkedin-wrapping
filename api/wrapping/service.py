from sqlmodel import Session, select
from typing import List, Dict

from api.wrapping.models import JobPostings, JobJoobleMapping


def get_available_job_postings(session: Session) -> List[JobPostings]:
    """
    Query job postings available to be published to LinkedIn via wrapping.
    Currently returns all job postings, can be extended with filtering logic.
    """
    statement = select(JobPostings)
    results = session.exec(statement)
    return list(results.all())


def get_jooble_mapping(session: Session) -> Dict[str, str]:
    """Return dict partner_job_id -> jo_ais_id for Jooble apply URL."""
    statement = select(JobJoobleMapping)
    results = session.exec(statement)
    return {row.partner_job_id: row.jo_ais_id for row in results.all()}



